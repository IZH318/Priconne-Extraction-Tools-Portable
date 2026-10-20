from __future__ import annotations
import os
import re
import json
from typing import Any

from src.queue_events import LogEvent, CompletionEvent
from src.parsers.story_deserializer import StoryDataDeserializer
from src.exceptions import AssetProcessingError


class AssetProcessor:
    # 에셋 타입별 기본 출력 폴더명 매핑
    SPECIAL_TYPES = {
        "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
        "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
        "VideoClip": "Videos", "MovieTexture": "Videos", "Material": "Materials",
        "MonoBehaviour": "MonoBehaviours", "Texture2DArray": "Textures",
        "AnimationClip": "Animations",
    }

    # 추출이 불필요한 내부 엔진/메타데이터 타입 목록
    # (이 타입들은 직접적인 에셋 데이터가 아니라 Unity 내부 구조체입니다.)
    SKIP_TYPES = {
        "GameObject", "Transform", "RectTransform", "AssetBundle", "PreloadData",
        "MeshRenderer", "SkinnedMeshRenderer", "MeshFilter", "Canvas", "CanvasRenderer",
        "MonoScript", "BuildSettings", "Animator", "SpriteAtlas",
    }

    # 전용 핸들러가 있는 에셋 타입 목록 (체크박스 UI용)
    HANDLER_TYPES = [
        "Texture2D", "Sprite", "TextAsset", "AudioClip", "Mesh",
        "Font", "Shader", "MonoBehaviour", "Texture2DArray",
        "MovieTexture", "VideoClip", "AnimationClip",
    ]

    # 기본적으로 추출이 활성화되는 타입 (HANDLER_TYPES 전체)
    DEFAULT_ENABLED = set(HANDLER_TYPES)

    def __init__(self, file_path: str, output_path: str, base_input_path: str | None, log_queue: Any, enabled_types: set[str] | None = None) -> None:
        """
        AssetProcessor 인스턴스 초기화.

        Args:
            file_path (str): 처리할 .unity3d 파일의 전체 경로.
            output_path (str): 결과물이 저장될 최상위 출력 폴더 경로.
            base_input_path (str | None): 폴더 단위로 열었을 경우의 기본 입력 폴더 경로.
            log_queue (Queue): GUI와 통신하기 위한 멀티프로세싱 큐.
            enabled_types (set | None): 추출할 에셋 타입 이름 집합. None이면 기본값 사용.
        """
        self.file_path = file_path
        self.output_path = output_path
        self.log_queue = log_queue
        self.base_name = os.path.basename(file_path) # 현재 처리 중인 파일 이름
        self.enabled_types = enabled_types if enabled_types is not None else self.DEFAULT_ENABLED
        
        # 입력 경로 구조를 보존하는 출력 폴더 경로 생성
        if base_input_path:
            relative_path = os.path.relpath(file_path, base_input_path)
            folder_path_without_ext, _ = os.path.splitext(relative_path)
            self.output_dir = os.path.join(self.output_path, folder_path_without_ext)
        else:
            folder_name_without_ext, _ = os.path.splitext(self.base_name)
            self.output_dir = os.path.join(self.output_path, folder_name_without_ext)

        self.env = None # UnityPy 환경 객체
        self.fallback_count = 0 # 오류로 인해 원본(.bin)으로 저장된 에셋 수

    def log(self, message_key: str, level: str = 'INFO', format_args: dict[str, Any] | None = None) -> None:
        """로그 메시지를 통신 큐에 추가합니다."""
        safe_args = None
        if format_args is not None:
            safe_args = {k: str(v) if isinstance(v, Exception) else v for k, v in format_args.items()}
        self.log_queue.put(LogEvent(target=self.base_name, key=message_key, level=level, kwargs=safe_args))

    def _sanitize_filename(self, name: str) -> str:
        """파일 시스템에서 사용할 수 없는 문자를 '_'로 치환합니다."""
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def _get_unique_path(self, path: str, obj_path_id: int) -> str:
        """파일명 충돌 시 `(#PathID)` 또는 `(count)` 접미사를 붙여 고유한 경로를 생성합니다."""
        if not os.path.exists(path):
            return path
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        new_path = os.path.join(directory, f"{name} (#{obj_path_id}){ext}")
        if not os.path.exists(new_path):
            return new_path
        count = 1
        base_name_for_counting = f"{name} (#{obj_path_id})"
        while True:
            final_path = os.path.join(directory, f"{base_name_for_counting} ({count}){ext}")
            if not os.path.exists(final_path):
                return final_path
            count += 1

    def _get_export_path(self, obj: Any, extension: str, data: Any = None, sub_folder: str | None = None) -> str:
        """
        에셋을 저장할 최종 경로를 결정하고 생성합니다.
        
        Args:
            obj: UnityPy ObjectReader.
            extension (str): 파일 확장자 (예: ".png").
            data: 이미 파싱된 데이터 객체 (None이면 내부에서 파싱).
            sub_folder (str | None): 특수 하위 폴더 이름.
        """
        if data is None:
            data = obj.parse_as_object()
        base_name_asset = getattr(data, 'm_Name', '') or obj.type.name
        folder_name = sub_folder or self.SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(self.output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True) # 폴더 자동 생성
        sanitized_name = self._sanitize_filename(base_name_asset)
        
        # 이미 원본 이름에 확장자가 포함되어 있다면 추가 확장자 부착을 생략 (유저 요청)
        _, existing_ext = os.path.splitext(sanitized_name)
        final_ext = "" if existing_ext else extension
        
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{final_ext}")
        return self._get_unique_path(initial_path, obj.path_id)

    def process_all_assets(self) -> int:
        """파일 내의 모든 에셋을 순회하며 처리를 시작하는 메인 함수입니다."""
        import UnityPy
        from UnityPy import config
        from src.constants import DEFAULT_UNITY_VERSION
        if not getattr(config, 'FALLBACK_UNITY_VERSION', None):
            config.FALLBACK_UNITY_VERSION = DEFAULT_UNITY_VERSION
        self.env = UnityPy.load(self.file_path) # 파일 로드
        num_assets = len(self.env.objects)
        if num_assets == 0:
            self.log("no_assets_to_process", "WARNING")
            return 0
        
        self.log('processing_started_assets', format_args={'count': num_assets})
        
        extracted_count = 0
        for obj in self.env.objects:
            if self._dispatch_asset(obj): # 각 에셋 처리
                extracted_count += 1
        
        # 최종 결과 로그
        if self.fallback_count > 0:
            self.log('extraction_complete_with_fallback', 'SUCCESS', {'total': num_assets, 'success': extracted_count, 'fallback_count': self.fallback_count})
        else:
            self.log('extraction_complete', 'SUCCESS', {'total': num_assets, 'success': extracted_count})

        return extracted_count

    # 에셋 타입별 핸들러 디스패치 테이블 (if-elif 체인 대신 O(1) 조회)
    _DISPATCH_TABLE: dict[str, str] = {
        "Texture2D": "_export_texture2d",
        "Sprite": "_export_sprite",
        "TextAsset": "_export_textasset_dispatch",
        "AudioClip": "_export_audioclip",
        "Mesh": "_export_mesh",
        "Font": "_export_font",
        "Shader": "_export_shader",
        "MonoBehaviour": "_export_monobehaviour",
        "Texture2DArray": "_export_texture2darray",
        "MovieTexture": "_export_movietexture",
        "VideoClip": "_export_videoclip",
        "AnimationClip": "_export_animationclip",
    }

    def _dispatch_asset(self, obj: Any) -> bool:
        """에셋의 타입에 따라 적절한 처리 함수를 호출하는 라우터 역할을 합니다."""
        obj_type = obj.type.name

        # 사용자가 선택하지 않은 타입은 스킵
        if obj_type not in self.enabled_types:
            # 전용 핸들러가 없는 기타 타입인 경우 "_OTHER_" 체크
            if obj_type not in self._DISPATCH_TABLE and obj_type != "Material" and "_OTHER_" in self.enabled_types:
                pass  # 아래 제네릭 처리로 계속 진행
            else:
                return False

        try:
            # 디스패치 테이블에서 핸들러 조회
            handler_name = self._DISPATCH_TABLE.get(obj_type)
            if handler_name:
                return getattr(self, handler_name)(obj)

            # Material: 사용자가 명시적으로 활성화한 경우에만 제네릭 JSON으로 추출
            if obj_type == "Material":
                if "Material" in self.enabled_types:
                    return self._export_generic_json(obj)
                return False

            # 전용 핸들러가 없는 기타 타입: 제네릭 JSON으로 추출
            return self._export_generic_json(obj)
        except Exception as e:
            # 처리 실패 시 예외 로깅 및 대체 저장 시도 (대체 저장을 시도하므로 우선 WARNING 처리)
            self.log('asset_processing_error', 'WARNING', {'path_id': obj.path_id, 'obj_type': obj_type, 'error': str(e)})
            if obj_type == "Mesh":
                self.log('mesh_fallback_info', "WARNING")
                if self._export_raw_data(obj):
                    self.fallback_count += 1
                    return True
                return False
            else:
                try:
                    return self._export_generic_json(obj, error_info=str(e))
                except Exception as e2:
                    self.log('json_fallback_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': obj.type.name, 'error': str(e2)})
        return False

    def _export_raw_data(self, obj: Any) -> bool:
        """에셋을 처리할 수 없을 때 원본 바이너리 데이터(.bin)로 저장합니다."""
        try:
            path = self._get_export_path(obj, ".bin")
            raw_data = obj.get_raw_data()
            with open(path, "wb") as f:
                f.write(raw_data)
            return True
        except Exception as e:
            self.log('asset_processing_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': 'raw data', 'error': str(e)})
            return False

    # =====================================================================
    # Texture2D 추출
    # UnityPy의 .image 속성이 PIL.Image로 변환해줌.
    # m_Width 체크로 빈 텍스처 크래시 방지.
    # =====================================================================
    def _export_texture2d(self, obj: Any) -> bool:
        """Texture2D 에셋을 .png 파일로 저장합니다."""
        data = obj.parse_as_object()
        if data.m_Width and data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # Sprite 추출
    # Sprite는 텍스처의 일부분이며, 별도의 알파 이미지를 가질 수 있음.
    # UnityPy가 자동으로 알파 이미지를 합성하여 .image로 반환함.
    # =====================================================================
    def _export_sprite(self, obj: Any) -> bool:
        """Sprite 에셋을 .png 파일로 저장합니다 (알파 합성 포함)."""
        data = obj.parse_as_object()
        if data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # TextAsset 추출
    # 'storydata_' 접두사를 가진 에셋은 커스텀 바이너리 역직렬화를 시도.
    # m_Script는 UnityPy에서 str로 반환됨.
    # =====================================================================
    def _export_textasset_dispatch(self, obj: Any) -> bool:
        """TextAsset의 이름에 따라 일반 바이너리 또는 StoryData JSON으로 분기합니다."""
        data = obj.parse_as_object()
        asset_name = data.m_Name or ''
        if asset_name.startswith('storydata_'):
            return self._export_storydata_as_json(obj, data)
        else:
            return self._export_textasset(obj, data)

    def _export_storydata_as_json(self, obj: Any, data: Any) -> bool:
        """'storydata_'로 시작하는 TextAsset을 JSON으로 역직렬화하여 저장합니다."""
        asset_name = data.m_Name or ''
        
        # 원본 .bin 파일은 항상 저장
        bin_saved = self._export_textasset(obj, data)

        try:
            # m_Script에서 바이너리 데이터 추출
            # UnityPy에서 m_Script는 str로 반환되므로 surrogateescape로 바이트 복원
            script_bytes = data.m_Script.encode('utf-8', 'surrogateescape')

            if not script_bytes:
                raise AssetProcessingError(obj.name, "Story_data is empty or cannot be converted to bytes")

            # 역직렬화 및 JSON 저장
            deserialized_data = StoryDataDeserializer.deserialize(script_bytes)
            
            path = self._get_export_path(obj, ".json", data=data)
            with open(path, "w", encoding="utf-8", errors="replace") as f:
                json.dump(deserialized_data, f, indent=4, ensure_ascii=False)
            self.log('storydata_deserialization_success', 'SUCCESS', {'asset_name': asset_name})
        
        except Exception as e:
            # 실패 시 로그 기록 (대체 저장되므로 에러가 아닌 경고로 처리)
            self.log('storydata_deserialization_fail', 'WARNING', {'asset_name': asset_name, 'error': str(e)})
        
        return bin_saved

    def _export_textasset(self, obj: Any, data: Any = None) -> bool:
        """TextAsset을 원본 바이너리(.bin) 파일로 저장합니다."""
        if data is None:
            data = obj.parse_as_object()
        content = data.m_Script
        if content is not None:
            path = self._get_export_path(obj, ".bin", data=data)
            # UnityPy에서 m_Script는 str로 반환됨 → bytes로 변환
            if isinstance(content, str):
                content = content.encode('utf-8', 'surrogateescape')
            elif not isinstance(content, (bytes, bytearray)):
                content = str(content).encode('utf-8', 'surrogateescape')

            with open(path, "wb") as f:
                f.write(content)
            return True
        return False

    # =====================================================================
    # AudioClip 추출
    # UnityPy의 .samples 속성이 딕셔너리를 반환 → {파일명: 바이너리 데이터}
    # 파일명에 올바른 확장자(.wav, .ogg, .m4a)가 포함되어 있음.
    # =====================================================================
    def _export_audioclip(self, obj: Any) -> bool:
        """AudioClip 에셋을 올바른 형식(.wav/.ogg/.m4a)으로 저장합니다."""
        data = obj.parse_as_object()
        if data.samples:
            for sample_name, audio_data in data.samples.items():
                # samples dict의 키에서 실제 확장자 추출
                _, ext = os.path.splitext(sample_name)
                if not ext:
                    ext = ".wav" # 폴백
                
                # 에셋 이름으로 저장 (확장자는 samples dict에서 가져옴)
                dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["AudioClip"])
                os.makedirs(dest_folder, exist_ok=True)
                sanitized_name = self._sanitize_filename(sample_name)
                # sample_name에 이미 확장자가 포함되어 있으므로 그대로 사용
                initial_path = os.path.join(dest_folder, sanitized_name)
                path = self._get_unique_path(initial_path, obj.path_id)
                
                with open(path, "wb") as f:
                    f.write(audio_data)
            return True
        return False

    # =====================================================================
    # Font 추출
    # m_FontData 바이트 배열에서 TTF/OTF를 판별하여 저장.
    # =====================================================================
    def _export_font(self, obj: Any) -> bool:
        """Font 에셋을 .ttf 또는 .otf 파일로 저장합니다."""
        data = obj.parse_as_object()
        if data.m_FontData:
            font_data_bytes = bytes(data.m_FontData)
            extension = ".otf" if font_data_bytes[:4] == b"OTTO" else ".ttf"
            path = self._get_export_path(obj, extension, data=data)
            with open(path, "wb") as f:
                f.write(font_data_bytes)
            return True
        return False

    # =====================================================================
    # Mesh 추출
    # UnityPy의 내장 Mesh.export()가 압축/비압축 메시 모두 처리함.
    # MeshHelper.MeshHandler가 내부적으로 CompressedMesh 언패킹도 수행.
    # =====================================================================
    def _export_mesh(self, obj: Any) -> bool:
        """Mesh 에셋을 .obj 파일로 저장합니다 (UnityPy 내장 export 사용)."""
        data = obj.parse_as_object()
        exported = data.export()
        if exported:
            path = self._get_export_path(obj, ".obj", data=data)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(exported)
            return True
        return False

    # =====================================================================
    # Shader 추출
    # UnityPy의 내장 Shader.export()가 셰이더 소스 코드를 텍스트로 변환.
    # =====================================================================
    def _export_shader(self, obj: Any) -> bool:
        """Shader 에셋을 .shader 텍스트 파일로 저장합니다."""
        data = obj.parse_as_object()
        exported = data.export()
        if exported:
            path = self._get_export_path(obj, ".shader", data=data)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(exported)
            self.log('shader_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

    # =====================================================================
    # MonoBehaviour 추출
    # TypeTree를 사용하여 JSON으로 추출 시도.
    # TypeTree가 없으면 바이너리(.bin)로 폴백.
    # =====================================================================
    def _export_monobehaviour(self, obj: Any) -> bool:
        """MonoBehaviour 에셋을 JSON 또는 바이너리로 저장합니다."""
        try:
            # TypeTree 기반 JSON 추출 시도
            tree = obj.parse_as_dict()
            export_data = json.dumps(tree, indent=4, ensure_ascii=False, 
                                     default=lambda o: f"<Unserializable: {type(o).__name__}>")
            export_bytes = export_data.encode("utf-8", errors="surrogateescape")
            extension = ".json"
        except (ValueError, KeyError, AttributeError):
            # TypeTree가 없는 경우 바이너리로 폴백
            export_bytes = obj.get_raw_data()
            extension = ".bin"
            self.fallback_count += 1
        
        # 이름 추출 (파싱하지 않고 peek_name 사용하여 성능 향상)
        try:
            asset_name = obj.peek_name() or obj.type.name
        except AttributeError:
            asset_name = obj.type.name
        
        dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["MonoBehaviour"])
        os.makedirs(dest_folder, exist_ok=True)
        sanitized_name = self._sanitize_filename(asset_name)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        path = self._get_unique_path(initial_path, obj.path_id)
        
        with open(path, "wb") as f:
            f.write(export_bytes)
        return True

    # =====================================================================
    # Texture2DArray 추출
    # UnityPy의 .images 속성이 PIL.Image 리스트를 반환.
    # 각 이미지를 인덱스를 붙여 개별 .png로 저장.
    # =====================================================================
    def _export_texture2darray(self, obj: Any) -> bool:
        """Texture2DArray 에셋의 각 레이어를 개별 .png 파일로 저장합니다."""
        data = obj.parse_as_object()
        try:
            images = data.images  # property로 접근
        except AttributeError:
            return False
        
        if not images:
            return False
        
        dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["Texture2DArray"])
        os.makedirs(dest_folder, exist_ok=True)
        asset_name = self._sanitize_filename(data.m_Name or "Texture2DArray")
        
        for i, image in enumerate(images):
            image_path = os.path.join(dest_folder, f"{asset_name}_{i}.png")
            image_path = self._get_unique_path(image_path, obj.path_id)
            image.save(image_path)
        
        self.log('texture2darray_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})', 'count': len(images)})
        return True

    # =====================================================================
    # MovieTexture 추출 (레거시, Unity 5 이전)
    # m_MovieData 바이트 배열에 Ogg Theora 비디오 데이터가 저장됨.
    # =====================================================================
    def _export_movietexture(self, obj: Any) -> bool:
        """MovieTexture 에셋의 비디오 데이터를 .ogv 파일로 저장합니다."""
        data = obj.parse_as_object()
        if hasattr(data, 'm_MovieData') and data.m_MovieData:
            movie_data = bytes(data.m_MovieData)
            path = self._get_export_path(obj, ".ogv", data=data)
            with open(path, "wb") as f:
                f.write(movie_data)
            self.log('movietexture_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

    # =====================================================================
    # VideoClip 추출 (Unity 5.6+)
    # 비디오 데이터는 m_ExternalResources에 StreamedResource로 참조됨.
    # 또는 에셋 내부에 직접 포함될 수 있음.
    # =====================================================================
    def _export_videoclip(self, obj: Any) -> bool:
        """VideoClip 에셋의 비디오 데이터를 추출합니다."""
        data = obj.parse_as_object()
        
        video_data = None
        
        # 외부 리소스에서 데이터 로드 시도
        if hasattr(data, 'm_ExternalResources') and data.m_ExternalResources:
            resource = data.m_ExternalResources
            source = getattr(resource, 'm_Source', '') or getattr(resource, 'path', '')
            if source:
                try:
                    from UnityPy.helpers.ResourceReader import get_resource_data
                    video_data = get_resource_data(
                        source,
                        obj.assets_file,
                        resource.m_Offset if hasattr(resource, 'm_Offset') else getattr(resource, 'offset', 0),
                        resource.m_Size if hasattr(resource, 'm_Size') else getattr(resource, 'size', 0),
                    )
                except AttributeError:
                    pass
        
        if video_data:
            # OriginalPath에서 확장자 추출 시도
            ext = ".mp4"
            if hasattr(data, 'm_OriginalPath') and data.m_OriginalPath:
                _, original_ext = os.path.splitext(data.m_OriginalPath)
                if original_ext:
                    ext = original_ext
            
            path = self._get_export_path(obj, ext, data=data)
            with open(path, "wb") as f:
                f.write(video_data)
            return True
        else:
            self.log('videoclip_no_data', 'WARNING', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return False

    # =====================================================================
    # AnimationClip 추출
    # TypeTree를 사용하여 JSON으로 추출.
    # =====================================================================
    def _export_animationclip(self, obj: Any) -> bool:
        """AnimationClip 에셋을 JSON 파일로 저장합니다."""
        tree = obj.parse_as_dict()
        path = self._get_export_path(obj, ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False,
                      default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

    # =====================================================================
    # 제네릭 JSON 추출 (기타 모든 타입)
    # TypeTree를 사용하여 오브젝트 데이터를 JSON으로 저장.
    # =====================================================================
    def _export_generic_json(self, obj: Any, error_info: str | None = None) -> bool:
        """처리 규칙이 없는 모든 에셋 타입을 TypeTree 기반의 .json 파일로 저장합니다."""
        path = self._get_export_path(obj, ".json")
        typetree = obj.parse_as_dict()
        if error_info:
            typetree["EXPORT_ERROR"] = error_info
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True


def process_single_file(file_path: str, output_path: str, base_input_path: str | None, log_queue: Any, completion_queue: Any, unity_version: str | None = None, enabled_types: set[str] | None = None) -> None:
    """
    단일 파일을 처리하는 독립적인 워커(worker) 함수. (멀티프로세싱용)
    
    Args:
        file_path (str): 처리할 파일 경로.
        output_path (str): 최상위 출력 폴더 경로.
        base_input_path (str | None): 입력 기준 폴더 경로.
        log_queue (Queue): GUI에 로그를 전달하기 위한 큐.
        completion_queue (Queue): GUI에 작업 완료 신호를 전달하기 위한 큐.
        unity_version (str): 유니티 파싱을 위한 백업/강제 버전 지정.
        enabled_types (set | None): 추출할 에셋 타입 집합. None이면 기본값.
    """
    extracted_count = None
    try:
        from UnityPy import config
        from src.constants import DEFAULT_UNITY_VERSION
        if unity_version is None:
            unity_version = DEFAULT_UNITY_VERSION
        config.FALLBACK_UNITY_VERSION = unity_version
        
        processor = AssetProcessor(file_path, output_path, base_input_path, log_queue, enabled_types)
        extracted_count = processor.process_all_assets()
    except Exception as e:
        # 심각한 오류 발생 시 로그 전송
        base_name = os.path.basename(file_path)
        log_queue.put(LogEvent(target=base_name, key='worker_process_error', level='ERROR', kwargs={'error': str(e)}))
    finally:
        # 작업 완료 신호 전송
        completion_queue.put(CompletionEvent(success=(extracted_count is not None), result=extracted_count))
