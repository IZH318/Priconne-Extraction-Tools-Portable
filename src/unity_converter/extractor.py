"""Unity3D 에셋 번들 추출 및 역직렬화 백엔드 모듈.

UnityPy를 활용하여 Unity 에셋 번들(.unity3d) 처리.
번들 내부의 텍스처, 스프라이트, 오디오 클립, 메시, 셰이더, 폰트, 비디오, 스토리 스크립트 등의
바이너리 에셋을 감지하여 규격화된 파일 형식(.png, .wav, .obj, .json 등)으로 변환 및 추출.
프린세스 커넥트 스토리 데이터(TextAsset) 전용 역직렬화 지원.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import IO, Any, ClassVar, Iterator

from src.exceptions import AssetProcessingError
from src.parsers.story_deserializer import StoryDataDeserializer
from src.queue_events import CompletionEvent, LogEvent
from src.utils.filename import WINDOWS_RESERVED_DEVICE_NAMES

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

    DEFAULT_ENABLED: ClassVar[set[str]] = {
        "Texture2D",
        "Sprite",
        "TextAsset",
        "Font",
    }

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
        self._mesh_materials_cache: dict[tuple[str, int], list[Any]] | None = None

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
        """에셋명에서 파일 시스템 금지 문자/제어문자를 제거한 안전한 파일명 생성.

        Windows에서 생성이 불가능하거나 의도하지 않은 대상을 가리킬 수 있는
        예약 디바이스명(CON, NUL, COM1 등)과 후행 점/공백도 함께 정리한다.

        Args:
            name: 원본 원시 에셋 이름.

        Returns:
            Windows 파일 시스템에서 유효한 안전한 파일명 문자열.
        """
        cleaned = re.sub(r'[\\/:*?"<>|]', '_', name)
        cleaned = re.sub(r'[\x00-\x1f]', '', cleaned)
        cleaned = cleaned.rstrip('. ')
        if cleaned.split('.', 1)[0].upper() in WINDOWS_RESERVED_DEVICE_NAMES:
            cleaned = f"_{cleaned}"
        return cleaned or '_'

    def _iter_unique_paths(self, path: str, obj_path_id: int) -> Iterator[str]:
        """파일명 중복 방지용 후보 경로를 순차 생성.

        최초 후보 경로 다음에는 (#PathID) 접미사, 그 이후에는 (n) 번호 인덱스를
        부여한 후보를 계속 산출.

        Args:
            path: 생성 예정 최초 후보 파일 경로.
            obj_path_id: Unity 오브젝트 PathID 정수.

        Yields:
            충돌 시 대체 접미사가 적용된 후보 경로 문자열.
        """
        yield path
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        yield os.path.join(directory, f"{name} (#{obj_path_id}){ext}")
        base_name_for_counting = f"{name} (#{obj_path_id})"
        count = 1
        while True:
            yield os.path.join(directory, f"{base_name_for_counting} ({count}){ext}")
            count += 1

    def _open_unique_path(
        self, path: str, obj_path_id: int, mode: str = "x", **kwargs: Any
    ) -> tuple[IO[Any], str]:
        """대상 경로를 독점 개방('x' 모드)하여 점유한 파일 객체 반환.

        TOCTOU(확인-후-사용) 경쟁 조건 제거를 위해 독점 생성 모드('x'/'xb')로
        open을 수행. 이미 존재하는 경로는 (#PathID)/(n) 접미사를 부여하여
        재시도하므로, 동시 실행 중인 워커 프로세스가 서로 같은 파일을 덮어쓸 수 없음.

        Args:
            path: 생성 예정 최초 후보 파일 경로.
            obj_path_id: Unity 오브젝트 PathID 정수.
            mode: 독점 개방 모드 (예: 'x', 'xb').
            **kwargs: `open` 에 전달할 추가 인자(encoding, newline 등).

        Returns:
            (개방된 파일 객체, 실제 점유된 경로) 튜플.

        Raises:
            FileExistsError: 모든 후보 경로 점유에 실패한 경우.
        """
        for candidate in self._iter_unique_paths(path, obj_path_id):
            try:
                handle = open(candidate, mode, **kwargs)
            except FileExistsError:
                continue
            return handle, candidate
        raise FileExistsError(f"Unable to reserve a unique path for: {path}")

    def _get_unique_path(self, path: str, obj_path_id: int) -> str:
        """동일 경로 파일 충돌 시 (#PathID) 또는 번호 인덱스를 추가한 고유 경로를 예약 후 반환.

        빈 파일을 독점 생성('xb')하여 경로를 미리 선점하므로, 동시 실행 중인
        워커 프로세스가 동일한 파일명을 선택하여 서로 덮어쓰는 것을 방지.
        파일 객체를 자체적으로 위임하는 이미지 라이브러리(Pillow) 등에 사용.

        Args:
            path: 생성 예정 대상 파일 경로.
            obj_path_id: Unity 오브젝트 PathID 정수.

        Returns:
            독점 점유된 고유한 파일 경로.
        """
        handle, reserved = self._open_unique_path(path, obj_path_id, "xb")
        handle.close()
        return reserved

    def _get_export_path(self, obj: Any, extension: str, data: Any = None, sub_folder: str | None = None) -> str:
        """에셋 오브젝트의 내보내기 대상 서브 디렉터리 경로 계산 및 생성.

        고유성(파일명 중복 방지)은 보장하지 않으며, 실제 파일 생성은 각 Writer가
        `_open_unique_path` / `_get_unique_path` 를 통해 독점 점유 수행.

        Args:
            obj: UnityPy ObjectReader 인스턴스.
            extension: 파일 확장자 (점 포함, 예: '.png', '.json').
            data: 사전 파싱된 Unity 오브젝트 데이터.
            sub_folder: 기본값 대체용 출력 서브폴더명.

        Returns:
            중복 방지 접미사가 적용되기 전의 최초 후보 내보내기 파일 경로.
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

        return os.path.join(dest_folder, f"{sanitized_name}{final_ext}")

    def process_all_assets(self) -> int:
        """로드된 Unity 번들 내부의 모든 인식 가능 에셋 일괄 추출 및 저장.

        UnityPy 환경을 로드하고 번들 내 모든 오브젝트를 순회하며 전용 핸들러로 전달.
        추출 완료 후 진행 상황 및 요약 로그 발행.

        Returns:
            성공적으로 추출 및 내보내기 완료된 에셋 수.
        """
        from .asset_reader import open_bundle
        self.env = open_bundle(self.file_path)
        assert self.env is not None
        self._mesh_materials_cache = None
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
            handle, _ = self._open_unique_path(path, obj.path_id, "xb")
            with handle:
                handle.write(raw_data)
            return True
        except (OSError, RuntimeError, ValueError) as e:
            self.log('asset_processing_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': 'raw data', 'error': str(e)})
            return False

    def _export_texture2d(self, obj: Any) -> bool:
        """Texture2D 에셋을 PNG 이미지 파일로 변환 및 저장.

        Args:
            obj: Texture2D를 포함하는 UnityPy ObjectReader.

        Returns:
            이미지 데이터가 존재하여 저장 완료된 경우 True, 아니면 False.
        """
        data = obj.parse_as_object()
        if not data.m_Width:
            return False
        img = data.image
        if not img:
            return False
        path = self._get_export_path(obj, ".png", data=data)
        img.save(self._get_unique_path(path, obj.path_id))
        return True

    def _export_sprite(self, obj: Any) -> bool:
        """Sprite 에셋을 투명도가 포함된 PNG 이미지 파일로 변환 및 저장.

        Args:
            obj: Sprite를 포함하는 UnityPy ObjectReader.

        Returns:
            스프라이트 이미지가 존재하여 저장 완료된 경우 True, 아니면 False.
        """
        data = obj.parse_as_object()
        img = data.image
        if not img:
            return False
        path = self._get_export_path(obj, ".png", data=data)
        img.save(self._get_unique_path(path, obj.path_id))
        return True

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
            handle, _ = self._open_unique_path(path, obj.path_id, "x", encoding="utf-8", errors="replace")
            with handle:
                json.dump(deserialized_data, handle, indent=4, ensure_ascii=False)
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

            handle, _ = self._open_unique_path(path, obj.path_id, "xb")
            with handle:
                handle.write(content)
            return True
        return False

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
                handle, _ = self._open_unique_path(initial_path, obj.path_id, "xb")
                with handle:
                    handle.write(audio_data)
            return True
        return False

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
            handle, _ = self._open_unique_path(path, obj.path_id, "xb")
            with handle:
                handle.write(font_data_bytes)
            return True
        return False

    @staticmethod
    def _mesh_cache_key(reader: Any) -> tuple[str, int]:
        """메시 머티리얼 캐시 키(SerializedFile 이름, PathID) 생성.

        PathID는 SerializedFile 단위로만 고유하므로, 번들에 여러 SerializedFile이
        포함된 경우 파일 이름을 함께 키로 사용해야 서로 다른 파일의 동일 PathID가 충돌하지 않음.

        Args:
            reader: UnityPy 오브젝트 리더(ObjectReader).

        Returns:
            (SerializedFile 이름, PathID) 튜플. 파일 이름을 알 수 없으면 빈 문자열.
        """
        assets_file = getattr(reader, 'assets_file', None)
        file_name = getattr(assets_file, 'name', '')
        path_id: int = reader.path_id
        return (file_name if isinstance(file_name, str) else "", path_id)

    def _mesh_material_map(self) -> dict[tuple[str, int], list[Any]]:
        """환경 내 렌더러를 스캔하여 (SerializedFile 이름, 메시 PathID) → 머티리얼 목록 매핑을 지연 구축.

        Unity 데이터 구조상 메시에서 머티리얼로의 역참조가 없으므로,
        MeshRenderer/SkinnedMeshRenderer를 순회하여 연결 머티리얼을 수집.
        PathID는 SerializedFile 단위로만 고유하므로 번들 내 파일 이름을 키에 함께 사용하며,
        동일한 메시를 참조하는 렌더러가 여러 개면 최초로 스캔된 렌더러의 머티리얼을 채택(first renderer wins).
        번들당 최초 1회만 스캔하고 결과를 캐시.

        Returns:
            (SerializedFile 이름, 메시 PathID)를 키로 하는 머티리얼(또는 None) 목록 매핑 딕셔너리.
        """
        if self._mesh_materials_cache is not None:
            return self._mesh_materials_cache

        mapping: dict[tuple[str, int], list[Any]] = {}
        env = self.env
        get_mesh: Any = None
        if env is not None:
            try:
                from UnityPy.export.MeshRendererExporter import get_mesh as _get_mesh
                get_mesh = _get_mesh
            except ImportError as exc:
                logger.debug("MeshRendererExporter unavailable: %s", exc)

        if get_mesh is not None:
            for renderer_obj in env.objects:
                try:
                    if renderer_obj.type.name not in ("MeshRenderer", "SkinnedMeshRenderer"):
                        continue
                    renderer = renderer_obj.parse_as_object()
                    mesh = get_mesh(renderer)
                    mesh_reader = getattr(mesh, "object_reader", None)
                    if mesh_reader is None:
                        continue
                    materials: list[Any] = []
                    for mat_ptr in (getattr(renderer, "m_Materials", None) or []):
                        try:
                            materials.append(mat_ptr.deref_parse_as_object() if mat_ptr else None)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("Failed to deref material: %s", exc)
                            materials.append(None)
                    # 동일 메시를 참조하는 렌더러가 여러 개면 최초 렌더러의 머티리얼만 유지(first renderer wins).
                    mapping.setdefault(self._mesh_cache_key(mesh_reader), materials)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Failed to resolve mesh material: %s", exc)
                    continue

        self._mesh_materials_cache = mapping
        return mapping

    def _default_mtl_block(self, material_name: str) -> str:
        """머티리얼 해석 실패 시 사용할 기본 MTL 본문 생성.

        Args:
            material_name: `newmtl` 에 기록할 머티리얼 이름.

        Returns:
            최소 속성만 포함한 MTL 본문 문자열.
        """
        return "\n".join([
            f"newmtl {material_name}",
            "Ka 0.2000 0.2000 0.2000",
            "Kd 0.8000 0.8000 0.8000",
            "Ks 0.2000 0.2000 0.2000",
            "Ns 20.0000",
            "Tr 0.0000",
        ])

    def _collect_mesh_materials(self, data: Any) -> tuple[list[str], list[str]]:
        """메시에 연결된 머티리얼 이름 목록 및 MTL 본문 블록을 수집.

        렌더러 스캔으로 머티리얼을 해석할 수 있으면 그 이름과 `export_material` 결과를
        사용하고, 해석이 불가능하면 메시 이름 기반의 기본 머티리얼로 폴백.
        이름은 MTL `newmtl` 과의 링크 유지를 위해 원시 머티리얼 이름(`usemtl` 은 파일명이 아님)을
        그대로 사용하며, 블록을 얻지 못한 인덱스는 기본 블록으로 채워 두 목록의 길이를 동일하게 유지.

        Args:
            data: 파싱된 Unity Mesh 오브젝트.

        Returns:
            (서브메시 순서에 대응하는 머티리얼 이름 목록, MTL 본문 블록 목록) 튜플.
        """
        default_name = self._sanitize_filename(getattr(data, 'm_Name', '') or '') or 'material'

        export_material: Any = None
        try:
            from UnityPy.export.MeshRendererExporter import export_material as _export_material
            export_material = _export_material
        except ImportError as exc:
            logger.debug("export_material unavailable: %s", exc)

        materials: list[Any] | None = None
        reader = getattr(data, 'object_reader', None)
        if reader is not None:
            try:
                materials = self._mesh_material_map().get(self._mesh_cache_key(reader))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Mesh material lookup failed: %s", exc)
                materials = None

        names: list[str] = []
        blocks: list[str] = []
        if materials:
            for index, mat in enumerate(materials):
                if mat is None:
                    mat_name = default_name if index == 0 else f"{default_name}_{index}"
                else:
                    mat_name = getattr(mat, 'm_Name', '') or f"{default_name}_{index}"
                names.append(mat_name)

                block: str | None = None
                if mat is not None and export_material is not None:
                    try:
                        block = export_material(mat)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("export_material failed for %s: %s", mat_name, exc)
                # 블록이 없는 인덱스(미해석 머티리얼/변환 실패)를 기본 블록으로 채워 이름과 1:1 정렬.
                blocks.append(block if block else self._default_mtl_block(mat_name))

        if not names:
            names = [default_name]
        if not blocks:
            blocks = [self._default_mtl_block(default_name)]
        return names, blocks

    def _export_mesh(self, obj: Any) -> bool:
        """3D Mesh 에셋을 Wavefront OBJ 형식(.obj)과 동반 MTL(.mtl)로 변환 및 저장.

        UnityPy `export_mesh_obj` 는 머티리얼 이름을 전달하지 않으면 `mtllib`/`usemtl`
        라인을 생성하지 않으므로, 연결 머티리얼(또는 기본 머티리얼) 이름을 전달하여
        OBJ가 참조할 동반 .mtl 파일을 함께 작성. 에셋명이 .mtl 로 끝나 동반 MTL 경로가
        예약된 OBJ 경로와 동일해지면 OBJ 유실을 막기 위해 MTL 파일명에 _mat 접미사를 부여.

        Args:
            obj: Mesh를 포함하는 UnityPy ObjectReader.

        Returns:
            지오메트리 데이터 추출 성공 시 True, 아니면 False.
        """
        from UnityPy.export.MeshExporter import export_mesh_obj

        data = obj.parse_as_object()
        material_names, mtl_blocks = self._collect_mesh_materials(data)
        exported = export_mesh_obj(data, material_names)
        if not exported:
            return False

        path = self._get_export_path(obj, ".obj", data=data)
        handle, obj_path = self._open_unique_path(path, obj.path_id, "x", encoding="utf-8", newline="")
        mtl_name = os.path.splitext(os.path.basename(obj_path))[0] + ".mtl"
        mtl_path = os.path.join(os.path.dirname(obj_path), mtl_name)
        if os.path.normpath(mtl_path) == os.path.normpath(obj_path):
            # 동일 경로인 경우 MTL 기록이 예약된 OBJ를 잘라내므로 파일명을 분리.
            mtl_name = os.path.splitext(os.path.basename(obj_path))[0] + "_mat.mtl"
            mtl_path = os.path.join(os.path.dirname(obj_path), mtl_name)
        # export_mesh_obj는 mtllib 라인을 원본 메시명으로 출력하므로 실제 예약 파일명으로 정정.
        exported = exported.replace(f"mtllib {getattr(data, 'm_Name', '')}.mtl", f"mtllib {mtl_name}", 1)
        with handle:
            handle.write(exported)

        mtl_written = False
        try:
            with open(mtl_path, "w", encoding="utf-8", newline="") as mtl_handle:
                mtl_handle.write("\n".join(mtl_blocks) + "\n")
            mtl_written = True
        except OSError as exc:
            logger.warning("Failed to write companion .mtl %s: %s", mtl_name, exc)

        if not mtl_written:
            # MTL 기록 실패 시 존재하지 않는 파일을 가리키는 mtllib 참조를 OBJ에서 제거
            try:
                stripped = re.sub(
                    rf"^mtllib\s+{re.escape(mtl_name)}\s*\r?\n?", "", exported, count=1, flags=re.MULTILINE
                )
                with open(obj_path, "w", encoding="utf-8", newline="") as obj_handle:
                    obj_handle.write(stripped)
            except OSError as exc:
                logger.warning("Failed to strip mtllib reference from %s: %s", obj_path, exc)
        return True

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
            handle, _ = self._open_unique_path(path, obj.path_id, "x", encoding="utf-8", newline="")
            with handle:
                handle.write(exported)
            self.log('shader_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

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
        handle, _ = self._open_unique_path(initial_path, obj.path_id, "xb")
        with handle:
            handle.write(export_bytes)
        return True

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
            handle, _ = self._open_unique_path(path, obj.path_id, "xb")
            with handle:
                handle.write(movie_data)
            self.log('movietexture_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

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
            handle, _ = self._open_unique_path(path, obj.path_id, "xb")
            with handle:
                handle.write(video_data)
            return True
        else:
            self.log('videoclip_no_data', 'WARNING', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return False

    def _export_animationclip(self, obj: Any) -> bool:
        """AnimationClip 커브 데이터를 구조화된 JSON으로 변환 및 저장.

        Args:
            obj: AnimationClip을 포함하는 UnityPy ObjectReader.

        Returns:
            JSON 작성 성공 시 True.
        """
        tree = obj.parse_as_dict()
        path = self._get_export_path(obj, ".json")
        handle, _ = self._open_unique_path(path, obj.path_id, "x", encoding="utf-8")
        with handle:
            json.dump(tree, handle, indent=4, ensure_ascii=False,
                      default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

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
        handle, _ = self._open_unique_path(path, obj.path_id, "x", encoding="utf-8", errors="replace")
        with handle:
            json.dump(typetree, handle, indent=4, ensure_ascii=False,
                      default=lambda o: f"<Unserializable: {type(o).__name__}>")
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
    """단일 Unity3D 번들 파일로부터 에셋을 추출하는 워커 엔트리포인트 함수.

    워커 스레드 또는 워커 프로세스에서 실행되도록 설계.
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
    """워커 스레드 내에서 번들 파일 배치 목록을 순차적으로 처리.

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
