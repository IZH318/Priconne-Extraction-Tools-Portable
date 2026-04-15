"""
Priconne Extraction Tools — Core Module Unit Tests
LRUCache, SubprocessRunner, StoryDataLoader 등 핵심 로직의 단위 테스트
"""
from __future__ import annotations
import sys
import os

from src.subprocess_runner import SubprocessRunner

# =====================================================================


# SubprocessRunner Tests
# =====================================================================

class TestSubprocessRunner:
    """외부 프로세스 실행기의 기본 동작을 검증합니다."""

    def test_run_simple_command(self) -> None:
        """python --version 실행이 성공하는지 확인합니다."""
        result = SubprocessRunner.run([sys.executable, "--version"])
        assert result.returncode == 0
        assert "Python" in result.stdout

    def test_run_captures_stdout(self) -> None:
        """stdout 출력이 올바르게 캡처되는지 확인합니다."""
        result = SubprocessRunner.run([
            sys.executable, "-c", "print('hello_test_output')"
        ])
        assert result.returncode == 0
        assert "hello_test_output" in result.stdout

    def test_run_nonexistent_command_raises(self) -> None:
        """존재하지 않는 명령을 실행하면 FileNotFoundError가 발생하는지 확인합니다."""
        import pytest
        with pytest.raises(FileNotFoundError):
            SubprocessRunner.run(["this_command_does_not_exist_12345"])
