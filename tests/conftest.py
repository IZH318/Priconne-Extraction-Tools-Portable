from __future__ import annotations
import os
import sys
import pytest
from pathlib import Path
from queue import Queue
from typing import Callable

# 프로젝트 루트를 sys.path에 추가 (pytest 실행 시 import 해결용)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.fixture
def base_test_dir(tmp_path) -> Path:
    """테스트에서 사용할 임시 기준 폴더를 제공합니다."""
    return tmp_path

@pytest.fixture
def mock_log_queue() -> Queue:
    """통신 테스트용 Mock Log Queue"""
    return Queue()

@pytest.fixture
def mock_progress_queue() -> Queue:
    """통신 테스트용 Mock Progress Queue"""
    return Queue()

@pytest.fixture
def mock_get_string() -> Callable[[str], str]:
    """다국어 문자열 반환을 가정한 Mock Dummy Function.
    kwargs가 전달될 경우 반환 문자열에 포함하여 포맷 인자 관련 버그를 감지합니다.
    """
    def _mock_get_string(key: str, **kwargs: object) -> str:
        if kwargs:
            kv_pairs = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"Trans_{key}({kv_pairs})"
        return f"Trans_{key}"
    return _mock_get_string
