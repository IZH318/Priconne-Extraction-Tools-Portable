"""
Unity Extractor Unit Tests
StoryDataDeserializer의 커맨드 역직렬화 및 텍스트 정리 기능,
그리고 AssetProcessor의 초기화, 경로 생성, 라우팅 기능을 검증합니다.
"""
from __future__ import annotations
import os
import pytest
import base64
from unittest.mock import MagicMock, patch
from queue import Queue
from src.unity_converter.extractor import StoryDataDeserializer, AssetProcessor


class TestStoryDataDeserializer:
    """StoryDataDeserializer의 역직렬화 기능을 검증합니다."""

    def test_clean_text(self) -> None:
        """줄바꿈, 변수 치환, 따옴표 이스케이프 제거가 올바르게 동작하는지 확인합니다."""
        # 각 변환을 개별 검증
        assert StoryDataDeserializer._clean_text("Hello\\nWorld") == "Hello\nWorld"
        assert StoryDataDeserializer._clean_text("{0}") == "{player_name}"
        assert StoryDataDeserializer._clean_text('\\"Hi\\"') == '"Hi"'

    def test_deserialize_command_success(self) -> None:
        """일반 base64 인코딩된 PRINT 명령이 올바르게 역직렬화되는지 확인합니다."""
        b64_encoded = base64.b64encode("hello".encode('utf-8'))
        data_mock = [6, b64_encoded]
        
        cmd_id, args = StoryDataDeserializer._deserialize_command(data_mock)
        
        assert cmd_id == StoryDataDeserializer.CommandId.PRINT
        assert args == ["hello"]

    def test_deserialize_command_obscured(self) -> None:
        """255-byte 역산 로직이 적용된 난독화 인자가 올바르게 복호화되는지 확인합니다."""
        b64_original = base64.b64encode("secret".encode('utf-8'))
        
        obscured_arg = bytearray()
        for b in b64_original:
            obscured_arg.append(255 - b)
            
        data_mock = [1, obscured_arg]  # CommandId.OUTLINE == 1
        
        cmd_id, args = StoryDataDeserializer._deserialize_command(data_mock)
        
        assert cmd_id == StoryDataDeserializer.CommandId.OUTLINE
        assert args == ["secret"]

    def test_deserialize_command_unknown_id(self) -> None:
        """CommandId enum에 없는 값이 UNKNOWN으로 처리되는지 확인합니다."""
        data_mock = [9999]
        cmd_id, args = StoryDataDeserializer._deserialize_command(data_mock)
        
        assert cmd_id == StoryDataDeserializer.CommandId.UNKNOWN
        assert args == []


# =====================================================================
# AssetProcessor Tests
# =====================================================================

class TestAssetProcessorInit:
    """AssetProcessor 초기화 및 설정 로직을 검증합니다."""

    @pytest.fixture
    def log_queue(self) -> Queue:
        return Queue()

    def test_init_without_base_input_path(self, base_test_dir, log_queue) -> None:
        """base_input_path 없이 초기화 시 단일 파일 기반 출력 경로가 생성되는지 확인합니다."""
        file_path = str(base_test_dir / "test_asset.unity3d")
        output_path = str(base_test_dir / "output")

        processor = AssetProcessor(file_path, output_path, None, log_queue)

        assert processor.base_name == "test_asset.unity3d"
        assert processor.output_dir == os.path.join(output_path, "test_asset")
        assert processor.env is None
        assert processor.fallback_count == 0

    def test_init_with_base_input_path(self, base_test_dir, log_queue) -> None:
        """base_input_path가 있을 때 상대 경로 구조가 보존되는지 확인합니다."""
        base_input = str(base_test_dir / "input")
        file_path = str(base_test_dir / "input" / "sub" / "data.unity3d")
        output_path = str(base_test_dir / "output")

        processor = AssetProcessor(file_path, output_path, base_input, log_queue)

        expected_output = os.path.join(output_path, "sub", "data")
        assert processor.output_dir == expected_output

    def test_default_enabled_types(self, base_test_dir, log_queue) -> None:
        """enabled_types 미지정 시 DEFAULT_ENABLED가 사용되는지 확인합니다."""
        processor = AssetProcessor(str(base_test_dir / "f.unity3d"), str(base_test_dir), None, log_queue)
        assert processor.enabled_types == AssetProcessor.DEFAULT_ENABLED

    def test_custom_enabled_types(self, base_test_dir, log_queue) -> None:
        """커스텀 enabled_types가 올바르게 적용되는지 확인합니다."""
        custom = {"Texture2D", "AudioClip"}
        processor = AssetProcessor(str(base_test_dir / "f.unity3d"), str(base_test_dir), None, log_queue, enabled_types=custom)
        assert processor.enabled_types == custom


class TestAssetProcessorHelpers:
    """AssetProcessor의 내부 헬퍼 메서드들을 검증합니다."""

    @pytest.fixture
    def processor(self, base_test_dir) -> AssetProcessor:
        return AssetProcessor(
            str(base_test_dir / "test.unity3d"),
            str(base_test_dir / "output"),
            None,
            Queue()
        )

    def test_sanitize_filename_special_chars(self, processor) -> None:
        """파일명에서 금지 문자가 '_'로 치환되는지 확인합니다."""
        assert processor._sanitize_filename('test:file<name>.png') == 'test_file_name_.png'
        assert processor._sanitize_filename('normal_name') == 'normal_name'

    def test_sanitize_filename_preserves_valid(self, processor) -> None:
        """유효한 문자(한글, 영문, 숫자, '-', '_')는 보존되는지 확인합니다."""
        assert processor._sanitize_filename('한글_test-123') == '한글_test-123'

    def test_get_unique_path_no_conflict(self, processor, base_test_dir) -> None:
        """충돌 없는 경로는 원본 그대로 반환되는지 확인합니다."""
        path = str(base_test_dir / "unique_file.png")
        assert processor._get_unique_path(path, 12345) == path

    def test_get_unique_path_with_conflict(self, processor, base_test_dir) -> None:
        """기존 파일이 있을 때 PathID 접미사가 붙는지 확인합니다."""
        existing = base_test_dir / "conflict.png"
        existing.write_text("existing")

        result = processor._get_unique_path(str(existing), 99)
        assert "(#99)" in result
        assert result.endswith(".png")

    def test_log_sends_to_queue(self, processor) -> None:
        """log() 호출이 큐에 올바른 형식의 메시지를 전송하는지 확인합니다."""
        processor.log("test_key", "INFO", {"detail": "value"})
        msg = processor.log_queue.get_nowait()
        assert msg == ('log', 'test.unity3d', 'test_key', 'INFO', {"detail": "value"})


class TestAssetProcessorClassConstants:
    """AssetProcessor의 클래스 레벨 상수 무결성을 검증합니다."""

    def test_handler_types_are_list(self) -> None:
        """HANDLER_TYPES가 리스트 타입인지 확인합니다."""
        assert isinstance(AssetProcessor.HANDLER_TYPES, list)

    def test_skip_types_are_set(self) -> None:
        """SKIP_TYPES가 집합 타입인지 확인합니다."""
        assert isinstance(AssetProcessor.SKIP_TYPES, set)

    def test_default_enabled_matches_handler_types(self) -> None:
        """DEFAULT_ENABLED가 HANDLER_TYPES의 set 변환과 일치하는지 확인합니다."""
        assert AssetProcessor.DEFAULT_ENABLED == set(AssetProcessor.HANDLER_TYPES)

    def test_no_overlap_between_handler_and_skip(self) -> None:
        """HANDLER_TYPES와 SKIP_TYPES 간 중복이 없는지 확인합니다."""
        overlap = set(AssetProcessor.HANDLER_TYPES) & AssetProcessor.SKIP_TYPES
        assert len(overlap) == 0, f"HANDLER_TYPES and SKIP_TYPES overlap: {overlap}"

    def test_special_types_keys_are_strings(self) -> None:
        """SPECIAL_TYPES의 키/값이 모두 문자열인지 확인합니다."""
        for k, v in AssetProcessor.SPECIAL_TYPES.items():
            assert isinstance(k, str), f"Key {k} is not str"
            assert isinstance(v, str), f"Value {v} for key {k} is not str"


class TestAssetProcessorDispatch:
    """AssetProcessor._dispatch_asset()의 라우팅 로직을 검증합니다."""

    @pytest.fixture
    def processor(self, base_test_dir) -> AssetProcessor:
        return AssetProcessor(
            str(base_test_dir / "test.unity3d"),
            str(base_test_dir / "output"),
            None,
            Queue()
        )

    def test_dispatch_skips_disabled_type(self, processor) -> None:
        """enabled_types에 없는 타입은 스킵(False)되는지 확인합니다."""
        processor.enabled_types = {"Texture2D"}
        mock_obj = MagicMock()
        mock_obj.type.name = "AudioClip"
        assert processor._dispatch_asset(mock_obj) is False

    def test_dispatch_routes_enabled_type(self, processor) -> None:
        """enabled_types에 있는 타입이 올바른 핸들러로 라우팅되는지 확인합니다."""
        processor.enabled_types = {"Texture2D"}
        mock_obj = MagicMock()
        mock_obj.type.name = "Texture2D"

        with patch.object(processor, '_export_texture2d', return_value=True) as mock_handler:
            result = processor._dispatch_asset(mock_obj)
            assert result is True
            mock_handler.assert_called_once_with(mock_obj)

    def test_dispatch_other_type_when_enabled(self, processor) -> None:
        """'_OTHER_'가 enabled 시 알 수 없는 타입이 제네릭 핸들러로 처리되는지 확인합니다."""
        processor.enabled_types = {"_OTHER_"}
        mock_obj = MagicMock()
        mock_obj.type.name = "UnknownCustomType"

        with patch.object(processor, '_export_generic_json', return_value=True) as mock_handler:
            result = processor._dispatch_asset(mock_obj)
            assert result is True
