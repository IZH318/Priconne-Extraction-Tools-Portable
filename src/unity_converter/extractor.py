"""Unity3D 에셋 번들 추출 및 역직렬화 백엔드 모듈.

UnityPy를 활용하여 Unity 에셋 번들(.unity3d, .bundle) 처리.
번들 내부의 텍스처, 스프라이트, 오디오 클립, 메시, 셰이더, 폰트, 비디오, 스토리 스크립트 등의
바이너리 에셋을 감지하여 규격화된 파일 형식(.png, .wav, .obj, .json 등)으로 변환 및 추출.
프린세스 커넥트 스토리 데이터(TextAsset) 전용 역직렬화 지원.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, ClassVar

from src.exceptions import AssetProcessingError
from src.parsers.story_deserializer import StoryDataDeserializer
from src.queue_events import CompletionEvent, LogEvent

logger = logging.getLogger(__name__)


class AssetProcessor:
    """단일 Unity3D 에셋 번들 파일에 대한 핵심 추출 엔진 클래스.

    UnityPy 환경을 로드하고 오브젝트 테이블을 순회하며 인식된 에셋을 전용 내보내기 루틴으로 라우팅.
    에러 발생 시 폴백 메커니즘(바이너리 원본 덤프 또는 TypeTree JSON) 지원.

    Attributes:
        file_path: 원본 .unity3d 번들의 절대 또는 정규화 경로.
        output_path: 추출된 에셋이 저장될 루트 대상 디렉터리.
        log_queue: UI로 LogEvent 객체를 전송하는 이벤트 큐.
        base_name: 처리 중인 파일의 기본 파일명.
        enabled_types: 추출 활성화된 에셋 타입 문자열 세트.
        output_dir: 상대 디렉터리 구조를 보존하여 결정된 출력 서브폴더 경로.
        env: 처리 중 활성화된 UnityPy.Environment 인스턴스.
        fallback_count: 폴백 메커니즘을 통해 추출된 에셋 수.
    """

    SPECIAL_TYPES: ClassVar[dict[str, str]] = {
        "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
        "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
        "VideoClip": "Videos", "MovieTexture": "Videos", "Material": "Materials",
        "MonoBehaviour": "MonoBehaviours", "Texture2DArray": "Textures",
        "AnimationClip": "Animations",
    }

    SKIP_TYPES: ClassVar[set[str]] = {
        "GameObject", "Transform", "RectTransform", "AssetBundle", "PreloadData",
        "MeshRenderer", "SkinnedMeshRenderer", "MeshFilter", "Canvas", "CanvasRenderer",
        "MonoScript", "BuildSettings", "Animator", "SpriteAtlas",
    }

    HANDLER_TYPES: ClassVar[list[str]] = [
        "Texture2D", "Sprite", "TextAsset", "AudioClip", "Mesh",
        "Font", "Shader", "MonoBehaviour", "Texture2DArray",
        "MovieTexture", "VideoClip", "AnimationClip",
    ]

    DEFAULT_ENABLED: ClassVar[set[str]] = set(HANDLER_TYPES)

    def __init__(
        self,
        file_path: str,
        output_path: str,
        base_input_path: str | None,
        log_queue: Any,
        enabled_types: set[str] | None = None,
    ) -> None:
        """AssetProcessor 인스턴스 초기화.

        Args:
            file_path: 대상 .unity3d 번들의 파일 시스템 전체 경로.
            output_path: 추출 파일이 저장될 루트 디렉터리 경로.
            base_input_path: 폴더 단위 처리 시 상대 경로 구조 보존을 위한 공통 입력 루트 디렉터리.
            log_queue: LogEvent 항목을 수신하는 큐.
            enabled_types: 추출할 에셋 타입 이름 세트 (None인 경우 지원되는 모든 타입 활성화).

        Raises:
            AssetProcessingError: 입력 기준 경로 또는 출력 루트를 벗어나는 경로 순회 감지 시 발생.
        """
        self.file_path = file_path
        self.output_path = output_path
        self.log_queue = log_queue
        self.base_name = os.path.basename(file_path)
        self.enabled_types = enabled_types if enabled_types is not None else self.DEFAULT_ENABLED

        _norm_output = os.path.normpath(output_path)
        if base_input_path:
            relative_path = os.path.relpath(file_path, base_input_path)
            if relative_path.startswith('..') or '..' in relative_path.split(os.sep):
                raise AssetProcessingError(self.base_name, "path traversal detected in relative path")
            folder_path_without_ext, _ = os.path.splitext(relative_path)
            self.output_dir = os.path.join(_norm_output, folder_path_without_ext)
        else:
            folder_name_without_ext, _ = os.path.splitext(self.base_name)
            self.output_dir = os.path.join(_norm_output, folder_name_without_ext)

        try:
            if os.path.commonpath([os.path.normpath(self.output_dir), _norm_output]) != _norm_output:
                raise AssetProcessingError(self.base_name, "output path escapes output root")
        except ValueError:
            raise AssetProcessingError(self.base_name, "invalid output path") from None

        self.env: Any = None
        self.fallback_count = 0

    def log(self, message_key: str, level: str = 'INFO', format_args: dict[str, Any] | None = None) -> None:
        """구조화된 로그 이벤트를 로그 큐에 발행.

        Args:
            message_key: 다국어 사전 키.
            level: 로그 중요도 레벨 ('INFO', 'WARNING', 'ERROR', 'SUCCESS').
            format_args: 로그 메시지 포맷팅 딕셔너리.
        """
        safe_args = None
        if format_args is not None:
            safe_args = {k: str(v) if isinstance(v, Exception) else v for k, v in format_args.items()}
        self.log_queue.put(LogEvent(target=self.base_name, key=message_key, level=level, kwargs=safe_args if safe_args is not None else {}))

    def _sanitize_filename(self, name: str) -> str:
        """에셋명에서 파일 시스템 금지 문자를 밑줄(_)로 대체하여 안전한 파일명 생성.

        Args:
            name: 원본 원시 에셋 이름.

        Returns:
            Windows 파일 시스템에서 유효한 안전한 파일명 문자열.
        """
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def _get_unique_path(self, path: str, obj_path_id: int) -> str:
        """동일 경로 파일 충돌 시 (#PathID) 또는 번호 인덱스를 추가하여 고유 경로 생성.

        Args:
            path: 생성 예정 대상 파일 경로.
            obj_path_id: Unity 오브젝트 PathID 정수.

        Returns:
            기존 파일과 충돌하지 않는 고유한 파일 경로.
        """
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
        """에셋 오브젝트의 내보내기 대상 서브 디렉터리 경로 계산 및 생성.

        Args:
            obj: UnityPy ObjectReader 인스턴스.
            extension: 파일 확장자 (점 포함, 예: '.png', '.json').
            data: 사전 파싱된 Unity 오브젝트 데이터.
            sub_folder: 기본값 대체용 출력 서브폴더명.

        Returns:
            고유성이 보장된 최종 내보내기 파일 경로.
        """
        if data is None:
            data = obj.parse_as_object()
        base_name_asset = getattr(data, 'm_Name', '') or obj.type.name
        folder_name = sub_folder or self.SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(self.output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True)
        sanitized_name = self._sanitize_filename(base_name_asset)

        _, existing_ext = os.path.splitext(sanitized_name)
        final_ext = "" if existing_ext else extension

        initial_path = os.path.join(dest_folder, f"{sanitized_name}{final_ext}")
        return self._get_unique_path(initial_path, obj.path_id)

    def process_all_assets(self) -> int:
        """로드된 Unity 번들 내부의 모든 인식 가능 에셋 일괄 추출 및 저장.

        UnityPy 환경을 로드하고 번들 내 모든 오브젝트를 순회하며 전용 핸들러로 전달.
        추출 완료 후 진행 상황 및 요약 로그 발행.

        Returns:
            성공적으로 추출 및 내보내기 완료된 에셋 수.
        """
        import UnityPy
        from UnityPy import config

        from src.constants import DEFAULT_UNITY_VERSION
        if not getattr(config, 'FALLBACK_UNITY_VERSION', None):
            config.FALLBACK_UNITY_VERSION = DEFAULT_UNITY_VERSION  # type: ignore[assignment]
        self.env = UnityPy.load(self.file_path)
        assert self.env is not None
        num_assets = len(self.env.objects)
        if num_assets == 0:
            self.log("no_assets_to_process", "WARNING")
            self.env = None
            return 0

        self.log('processing_started_assets', format_args={'count': num_assets})

        extracted_count = 0
        try:
            for obj in self.env.objects:
                if self._dispatch_asset(obj):
                    extracted_count += 1
        finally:
            self.env = None

        if self.fallback_count > 0:
            self.log('extraction_complete_with_fallback', 'SUCCESS', {'total': num_assets, 'success': extracted_count, 'fallback_count': self.fallback_count})
        else:
            self.log('extraction_complete', 'SUCCESS', {'total': num_assets, 'success': extracted_count})

        return extracted_count

    _DISPATCH_TABLE: ClassVar[dict[str, str]] = {
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
        """개별 UnityPy 오브젝트를 적절한 전용 내보내기 메서드로 분기 호출.

        enabled_types 필터링 검사, 전용 추출 메서드 호출 및 에러 시 폴백(바이너리 덤프/TypeTree JSON) 처리.

        Args:
            obj: UnityPy ObjectReader 인스턴스.

        Returns:
            에셋 추출 성공 시 True, 건너뛰거나 실패 시 False.
        """
        obj_type = obj.type.name

        if obj_type not in self.enabled_types:
            if obj_type not in self._DISPATCH_TABLE and obj_type != "Material" and "_OTHER_" in self.enabled_types:
                pass
            else:
                return False

        try:
            handler_name = self._DISPATCH_TABLE.get(obj_type)
            if handler_name:
                return getattr(self, handler_name)(obj)  # type: ignore[no-any-return]

            if obj_type == "Material":
                if "Material" in self.enabled_types:
                    return self._export_generic_json(obj)
                return False

            return self._export_generic_json(obj)
        except Exception as e:  # noqa: BLE001
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
                except Exception as e2:  # noqa: BLE001
                    self.log('json_fallback_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': obj.type.name, 'error': str(e2)})
        return False

    def _export_raw_data(self, obj: Any) -> bool:
        """미지원 또는 에러 발생 에셋을 원시 바이너리 데이터(.bin)로 폴백 저장.

        Args:
            obj: UnityPy ObjectReader 인스턴스.

        Returns:
            파일 작성 성공 시 True, 실패 시 False.
        """
        try:
            path = self._get_export_path(obj, ".bin")
            raw_data = obj.get_raw_data()
            with open(path, "wb") as f:
                f.write(raw_data)
            return True
        except (OSError, RuntimeError, ValueError) as e:
            self.log('asset_processing_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': 'raw data', 'error': str(e)})
            return False

    # =====================================================================
    # 텍스처(Texture2D) 에셋 내보내기
    # =====================================================================
    def _export_texture2d(self, obj: Any) -> bool:
        """Texture2D 에셋을 PNG 이미지 파일로 변환 및 저장.

        Args:
            obj: Texture2D를 포함하는 UnityPy ObjectReader.

        Returns:
            이미지 데이터가 존재하여 저장 완료된 경우 True, 아니면 False.
        """
        data = obj.parse_as_object()
        if data.m_Width and data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # 스프라이트(Sprite) 에셋 내보내기
    # =====================================================================
    def _export_sprite(self, obj: Any) -> bool:
        """Sprite 에셋을 투명도가 포함된 PNG 이미지 파일로 변환 및 저장.

        Args:
            obj: Sprite를 포함하는 UnityPy ObjectReader.

        Returns:
            스프라이트 이미지가 존재하여 저장 완료된 경우 True, 아니면 False.
        """
        data = obj.parse_as_object()
        if data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # 텍스트(TextAsset) 에셋 분기 내보내기
    # =====================================================================
    def _export_textasset_dispatch(self, obj: Any) -> bool:
        """TextAsset 오브젝트를 스토리 데이터 파서 또는 바이너리 내보내기로 분기 처리.

        Args:
            obj: TextAsset을 포함하는 UnityPy ObjectReader.

        Returns:
            텍스트 또는 스토리 데이터 추출 성공 시 True.
        """
        data = obj.parse_as_object()
        asset_name = data.m_Name or ''
        if asset_name.startswith('storydata_'):
            return self._export_storydata_as_json(obj, data)
        else:
            return self._export_textasset(obj, data)

    def _export_storydata_as_json(self, obj: Any, data: Any) -> bool:
        """프린세스 커넥트 스토리 스크립트 TextAsset을 구조화된 JSON 및 바이너리로 역직렬화 저장.

        surrogateescape 인코딩을 통해 원시 바이트를 추출하고,
        StoryDataDeserializer를 호출하여
        원시 .bin 파일과 역직렬화된 .json 파일 동시 생성.

        Args:
            obj: UnityPy ObjectReader.
            data: m_Script를 포함하는 파싱된 TextAsset 오브젝트.

        Returns:
            바이너리 또는 JSON 데이터가 성공적으로 저장되었으면 True.
        """
        asset_name = data.m_Name or ''

        bin_saved = self._export_textasset(obj, data)

        try:
            script_bytes = data.m_Script.encode('utf-8', 'surrogateescape')

            if not script_bytes:
                raise AssetProcessingError(obj.name, "Story_data is empty or cannot be converted to bytes")

            deserialized_data = StoryDataDeserializer.deserialize(script_bytes)

            path = self._get_export_path(obj, ".json", data=data)
            with open(path, "w", encoding="utf-8", errors="replace") as f:
                json.dump(deserialized_data, f, indent=4, ensure_ascii=False)
            self.log('storydata_deserialization_success', 'SUCCESS', {'asset_name': asset_name})

        except (ValueError, TypeError, KeyError, AttributeError, OSError) as e:
            self.log('storydata_deserialization_fail', 'WARNING', {'asset_name': asset_name, 'error': str(e)})

        return bin_saved

    def _export_textasset(self, obj: Any, data: Any = None) -> bool:
        """일반 TextAsset을 원시 바이너리 데이터(.bin) 파일로 저장.

        Args:
            obj: UnityPy ObjectReader.
            data: 사전 파싱된 TextAsset 오브젝트.

        Returns:
            파일 작성 성공 시 True, 스크립트 내용이 None이면 False.
        """
        if data is None:
            data = obj.parse_as_object()
        content = data.m_Script
        if content is not None:
            path = self._get_export_path(obj, ".bin", data=data)
            if isinstance(content, str):
                content = content.encode('utf-8', 'surrogateescape')
            elif not isinstance(content, (bytes, bytearray)):
                content = str(content).encode('utf-8', 'surrogateescape')

            with open(path, "wb") as f:
                f.write(content)
            return True
        return False

    # =====================================================================
    # 오디오 클립(AudioClip) 에셋 내보내기
    # =====================================================================
    def _export_audioclip(self, obj: Any) -> bool:
        """AudioClip 오디오 샘플을 규격 형식(.wav, .ogg, .m4a)으로 변환 및 저장.

        Args:
            obj: AudioClip을 포함하는 UnityPy ObjectReader.

        Returns:
            하나 이상의 오디오 샘플이 추출되었으면 True, 아니면 False.
        """
        data = obj.parse_as_object()
        if data.samples:
            for sample_name, audio_data in data.samples.items():
                _, ext = os.path.splitext(sample_name)
                if not ext:
                    ext = ".wav"

                dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["AudioClip"])
                os.makedirs(dest_folder, exist_ok=True)
                sanitized_name = self._sanitize_filename(sample_name)
                initial_path = os.path.join(dest_folder, sanitized_name)
                path = self._get_unique_path(initial_path, obj.path_id)

                with open(path, "wb") as f:
                    f.write(audio_data)
            return True
        return False

    # =====================================================================
    # 폰트(Font) 에셋 내보내기
    # =====================================================================
    def _export_font(self, obj: Any) -> bool:
        """매직 바이트를 판별하여 Font 에셋을 .otf 또는 .ttf 형식으로 저장.

        Args:
            obj: Font를 포함하는 UnityPy ObjectReader.

        Returns:
            폰트 데이터가 존재하여 파일 작성 성공 시 True, 아니면 False.
        """
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
    # 메시(Mesh) 에셋 내보내기
    # =====================================================================
    def _export_mesh(self, obj: Any) -> bool:
        """3D Mesh 에셋을 Wavefront OBJ 형식(.obj)으로 변환 및 저장.

        Args:
            obj: Mesh를 포함하는 UnityPy ObjectReader.

        Returns:
            지오메트리 데이터 추출 성공 시 True, 아니면 False.
        """
        data = obj.parse_as_object()
        exported = data.export()
        if exported:
            path = self._get_export_path(obj, ".obj", data=data)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(exported)
            return True
        return False

    # =====================================================================
    # 셰이더(Shader) 에셋 내보내기
    # =====================================================================
    def _export_shader(self, obj: Any) -> bool:
        """Shader 에셋을 텍스트 파일(.shader)로 변환 및 저장.

        Args:
            obj: Shader를 포함하는 UnityPy ObjectReader.

        Returns:
            셰이더 텍스트 추출 성공 시 True, 아니면 False.
        """
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
    # 모노비헤이비어(MonoBehaviour) 에셋 내보내기
    # =====================================================================
    def _export_monobehaviour(self, obj: Any) -> bool:
        """MonoBehaviour 에셋을 JSON으로 변환하거나 파싱 실패 시 바이너리(.bin)로 저장.

        Args:
            obj: MonoBehaviour를 포함하는 UnityPy ObjectReader.

        Returns:
            데이터 저장 성공 시 True.
        """
        try:
            tree = obj.parse_as_dict()
            export_data = json.dumps(tree, indent=4, ensure_ascii=False,
                                     default=lambda o: f"<Unserializable: {type(o).__name__}>")
            export_bytes = export_data.encode("utf-8", errors="surrogateescape")
            extension = ".json"
        except (ValueError, KeyError, AttributeError):
            export_bytes = obj.get_raw_data()
            extension = ".bin"
            self.fallback_count += 1

        try:
            asset_name = obj.peek_name() or obj.type.name
        except AttributeError as exc:
            logger.debug("peek_name failed for %s: %s", getattr(obj, 'type', None), exc)
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
    # 텍스처2D 배열(Texture2DArray) 에셋 내보내기
    # =====================================================================
    def _export_texture2darray(self, obj: Any) -> bool:
        """Texture2DArray의 각 슬라이스/레이어를 개별 PNG 이미지 파일로 분할 저장.

        Args:
            obj: Texture2DArray를 포함하는 UnityPy ObjectReader.

        Returns:
            레이어 이미지가 존재하여 내보내기 성공 시 True, 아니면 False.
        """
        data = obj.parse_as_object()
        try:
            images = data.images
        except AttributeError as exc:
            logger.debug("No images property: %s", exc)
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
    # 무비 텍스처(MovieTexture) 에셋 내보내기
    # =====================================================================
    def _export_movietexture(self, obj: Any) -> bool:
        """MovieTexture Ogg Theora 비디오 스트림을 .ogv 형식으로 저장.

        Args:
            obj: MovieTexture를 포함하는 UnityPy ObjectReader.

        Returns:
            동영상 데이터가 존재하여 파일 작성 성공 시 True, 아니면 False.
        """
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
    # 비디오 클립(VideoClip, Unity 5.6+) 에셋 내보내기
    # =====================================================================
    def _export_videoclip(self, obj: Any) -> bool:
        """UnityPy ResourceReader를 통해 VideoClip 미디어 스트림을 추출 및 저장.

        Args:
            obj: VideoClip을 포함하는 UnityPy ObjectReader.

        Returns:
            외부 비디오 스트림을 읽어 파일 작성 성공 시 True, 아니면 False.
        """
        data = obj.parse_as_object()

        video_data = None

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
                except AttributeError as exc:
                    logger.debug("Resource attribute missing: %s", exc)

        if video_data:
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
    # 애니메이션 클립(AnimationClip) 에셋 내보내기
    # =====================================================================
    def _export_animationclip(self, obj: Any) -> bool:
        """AnimationClip 커브 데이터를 구조화된 JSON으로 변환 및 저장.

        Args:
            obj: AnimationClip을 포함하는 UnityPy ObjectReader.

        Returns:
            JSON 작성 성공 시 True.
        """
        tree = obj.parse_as_dict()
        path = self._get_export_path(obj, ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False,
                      default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

    # =====================================================================
    # 일반 TypeTree JSON 내보내기
    # =====================================================================
    def _export_generic_json(self, obj: Any, error_info: str | None = None) -> bool:
        """임의의 Unity 에셋 타입을 TypeTree 기반 JSON으로 변환 및 저장.

        Args:
            obj: UnityPy ObjectReader.
            error_info: JSON에 기록할 선택적 에러 설명 문자열.

        Returns:
            JSON 작성 성공 시 True.
        """
        path = self._get_export_path(obj, ".json")
        typetree = obj.parse_as_dict()
        if error_info:
            typetree["EXPORT_ERROR"] = error_info
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True


def process_single_file(
    file_path: str,
    output_path: str,
    base_input_path: str | None,
    log_queue: Any,
    completion_queue: Any,
    unity_version: str | None = None,
    enabled_types: set[str] | None = None,
) -> None:
    """단일 Unity3D 번들 파일로부터 에셋을 추출하는 작업자 엔트리포인트 함수.

    동시성 스레드 또는 작업자 프로세스에서 실행되도록 설계.
    로그 이벤트 및 최종 완료 상태를 스레드 안전 큐로 전송.

    Args:
        file_path: 대상 .unity3d 번들 경로.
        output_path: 추출 루트 디렉터리 경로.
        base_input_path: 폴더 계층 보존용 입력 기준 디렉터리 경로.
        log_queue: LogEvent 업데이트를 수신하는 큐.
        completion_queue: 작업 완료 시 CompletionEvent를 수신하는 큐.
        unity_version: 폴백 적용용 Unity 엔진 버전 문자열.
        enabled_types: 추출 활성화된 에셋 타입 세트.
    """
    try:
        from UnityPy import config

        from src.constants import DEFAULT_UNITY_VERSION
        if unity_version is None:
            resolved_version = DEFAULT_UNITY_VERSION
        else:
            resolved_version = unity_version
        config.FALLBACK_UNITY_VERSION = resolved_version  # type: ignore[assignment]

        processor = AssetProcessor(file_path, output_path, base_input_path, log_queue, enabled_types)
        extracted_count = processor.process_all_assets()
        completion_queue.put(CompletionEvent(success=True, result=extracted_count))
    except Exception as e:  # noqa: BLE001
        base_name = os.path.basename(file_path)
        log_queue.put(LogEvent(target=base_name, key='worker_process_error', level='ERROR', kwargs={'error': str(e)}))
        completion_queue.put(CompletionEvent(success=False, result=0))


def process_file_batch(
    file_paths: list[str],
    output_path: str,
    base_input_path: str | None,
    log_queue: Any,
    completion_queue: Any,
    unity_version: str | None = None,
    enabled_types: set[str] | None = None,
) -> int:
    """작업자 스레드 내에서 번들 파일 배치 목록을 순차적으로 처리.

    Args:
        file_paths: 입력 번들 파일 경로 문자열 리스트.
        output_path: 대상 루트 디렉터리 경로.
        base_input_path: 공통 입력 루트 디렉터리 경로.
        log_queue: LogEvent 업데이트를 수신하는 큐.
        completion_queue: CompletionEvent 인스턴스를 수신하는 큐.
        unity_version: 폴백 적용용 Unity 엔진 버전 문자열.
        enabled_types: 추출 활성화된 에셋 타입 세트.

    Returns:
        처리 완료된 번들 파일 수.
    """
    count = 0
    for fp in file_paths:
        process_single_file(fp, output_path, base_input_path, log_queue, completion_queue, unity_version, enabled_types)
        count += 1
    return count
