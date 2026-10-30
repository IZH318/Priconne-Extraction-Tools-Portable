"""공통 유틸리티 패키지.

보안(Zip-Slip 방지), 파일 시스템 경로 해석, 에러 로그 포맷팅, HTTP 다운로드 완결성 검증,
Tkinter 위젯 생명주기 안전 조작, 마우스 툴팁, 파일 목록 믹스인,
OS 기본 프로그램 연동 및 어바웃 대화상자 모듈 통합 제공.

PEP 562 모듈 레벨 __getattr__ 기반 지연 임포트(Lazy Import)를 적용하여,
`import src.utils`만으로는 하위 모듈이 로드되지 않는다 (tkinter 기반 GUI 모듈 포함).
개별 이름에 최초 접근하는 시점에 해당 모듈만 로드되어 globals()에 캐시된다.
"""
from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "about_dialog",
    "base_path",
    "dialogs",
    "download_file",
    "error_log",
    "file_list_mixin",
    "file_scan",
    "filename",
    "lang_dict",
    "log_history",
    "platform_open",
    "process_check",
    "task_pool",
    "temp_registry",
    "tk_safe",
    "tooltip",
    "zip_safe",
]


def __getattr__(name: str) -> Any:
    """속성 접근 시 __all__ 하위 모듈 반환 (지연 임포트).

    `from src.utils import zip_safe` 또는 `from src.utils import *`처럼 패키지 속성으로
    하위 모듈에 접근할 때 해당 모듈만 importlib로 로드하고 globals()에 저장(캐시)하여,
    이후 동일 이름 접근은 재임포트 없이 모듈 전역 사전 조회로 해석.

    Args:
        name (str): 요청된 하위 모듈 이름 (__all__ 구성원).

    Returns:
        Any: 로드된 하위 모듈 객체 (이후 접근은 캐시된 동일 객체 반환).

    Raises:
        AttributeError: __all__에 정의되지 않은 알 수 없는 속성 이름인 경우.
    """
    if name in __all__:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

