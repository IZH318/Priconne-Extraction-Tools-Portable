"""
AV Converter Logic Unit Tests
ConversionLogic의 스트림 분석 및 변환 로직을 검증합니다.
"""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from queue import Queue

from src.av_converter.logic import ConversionLogic


@pytest.fixture
def mock_conversion_logic(base_test_dir, mock_log_queue) -> ConversionLogic:
    """테스트용 ConversionLogic 인스턴스를 생성합니다."""
    return ConversionLogic(
        log_queue=mock_log_queue,
        base_path=base_test_dir
    )


class TestConversionLogicStream:
    """ConversionLogic의 스트림 파싱 기능을 검증합니다."""

    def test_get_stream_count_success(self, mock_conversion_logic) -> None:
        """정상적인 stdout 출력에서 스트림 개수를 올바르게 파싱하는지 확인합니다."""
        fake_stdout = "sample output\nstream count: 3\nanother line\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_stdout
        
        with patch.object(mock_conversion_logic, '_run_subprocess', return_value=mock_result) as mock_run:
            count = mock_conversion_logic.get_stream_count(Path("dummy.awb"), Path("vgmstream.exe"))
            
            assert count == 3
            mock_run.assert_called_once_with(["vgmstream.exe", "-m", "dummy.awb"])

    def test_get_stream_count_fail_fallback(self, mock_conversion_logic) -> None:
        """stream count 라인이 없는 경우 기본값 1을 반환하는지 확인합니다."""
        fake_stdout = "sample output without stream count line\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_stdout
        
        with patch.object(mock_conversion_logic, '_run_subprocess', return_value=mock_result):
            count = mock_conversion_logic.get_stream_count(Path("dummy.awb"), Path("vgmstream.exe"))
            assert count == 1

    def test_get_stream_name_success(self, mock_conversion_logic) -> None:
        """정상적인 stdout 출력에서 스트림 이름을 올바르게 파싱하는지 확인합니다."""
        fake_stdout = "some setup\nstream name: BGM_01; additional info\ninfo\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_stdout
        
        with patch.object(mock_conversion_logic, '_run_subprocess', return_value=mock_result):
            name = mock_conversion_logic.get_stream_name(Path("dummy_audio.awb"), 1, Path("vgmstream.exe"))
            assert name == "BGM_01"

    def test_get_stream_name_fallback(self, mock_conversion_logic) -> None:
        """이름 라인이 없을 시 파일명_스트림번호 형식으로 반환하는지 확인합니다."""
        fake_stdout = "no name info here\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_stdout
        
        with patch.object(mock_conversion_logic, '_run_subprocess', return_value=mock_result):
            name = mock_conversion_logic.get_stream_name(Path("dummy_audio.awb"), 2, Path("vgmstream.exe"))
            assert name == "dummy_audio_0002"

    def test_get_stream_count_nonzero_returncode(self, mock_conversion_logic) -> None:
        """프로세스 실패(returncode != 0)시 0을 반환하는지 확인합니다."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        
        with patch.object(mock_conversion_logic, '_run_subprocess', return_value=mock_result):
            count = mock_conversion_logic.get_stream_count(Path("bad.awb"), Path("vgmstream.exe"))
            assert count == 0


class TestFFmpegDownloader:
    """FFmpegDownloader의 초기화 및 경로 설정 기능을 검증합니다."""

    @pytest.fixture
    def mock_lang_func(self):
        """다국어 데이터 반환 mock 함수."""
        return lambda: {'ffmpeg_not_found': 'not found', 'ffmpeg_already_exists': 'exists'}

    def test_initialization(self, base_test_dir, mock_log_queue, mock_lang_func) -> None:
        """FFmpegDownloader가 올바르게 초기화되는지 확인합니다."""
        from src.av_converter.logic import FFmpegDownloader
        
        ffmpeg_dir = base_test_dir / "ffmpeg_init_test"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        downloader = FFmpegDownloader(
            log_queue=mock_log_queue,
            usmtoolkit_path_parent_dir=ffmpeg_dir,
            get_lang_data_func=mock_lang_func
        )
        assert downloader.download_dir == ffmpeg_dir

    def test_ffmpeg_path_not_found_initially(self, base_test_dir, mock_log_queue, mock_lang_func) -> None:
        """FFmpeg이 없는 디렉터리에서 경로가 존재하지 않는 파일을 가리키는지 확인합니다."""
        from src.av_converter.logic import FFmpegDownloader

        ffmpeg_dir = base_test_dir / "ffmpeg_empty_test"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        downloader = FFmpegDownloader(
            log_queue=mock_log_queue,
            usmtoolkit_path_parent_dir=ffmpeg_dir,
            get_lang_data_func=mock_lang_func
        )
        # FFmpeg이 설치되지 않은 빈 디렉터리에서는 경로가 존재하지 않아야 함
        assert not downloader.ffmpeg_path.exists()

    def test_ffmpeg_found_when_exists(self, base_test_dir, mock_log_queue, mock_lang_func) -> None:
        """FFmpeg 바이너리가 존재할 때 경로가 올바르게 설정되는지 확인합니다."""
        from src.av_converter.logic import FFmpegDownloader

        ffmpeg_dir = base_test_dir / "ffmpeg_exists_test"
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        
        # 테스트 대상 상수에 의존하지 않고 리터럴 사용하여 회귀 방지
        expected_exe_name = "ffmpeg.exe"
        (ffmpeg_dir / expected_exe_name).write_text("fake_binary", encoding='utf-8')

        downloader = FFmpegDownloader(
            log_queue=mock_log_queue,
            usmtoolkit_path_parent_dir=ffmpeg_dir,
            get_lang_data_func=mock_lang_func
        )
        # 경로가 올바르게 설정되었는지 확인
        assert downloader.ffmpeg_path.exists()
        assert expected_exe_name in str(downloader.ffmpeg_path)

