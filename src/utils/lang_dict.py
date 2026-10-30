"""다국어 사전 조회 콜백 안전 호출 공용 헬퍼 모듈.

각 서비스가 개별적으로 재구현하던 "getter 호출 → 예외 시 빈 딕셔너리 반환" 패턴을
단일 함수로 통합한다.
"""
from __future__ import annotations

from collections.abc import Callable


def safe_lang_dict(getter: Callable[[], dict[str, str] | None] | None) -> dict[str, str]:
    """다국어 사전 조회 콜백을 안전하게 호출.

    Args:
        getter: 현재 언어의 키-문자열 매핑을 반환하는 콜백. None/비호출 가능 시 빈 사전.

    Returns:
        dict[str, str]: 조회 결과. 콜백이 없거나, None/예외를 반환하면 빈 딕셔너리.
    """
    if not callable(getter):
        return {}
    try:
        return getter() or {}
    except (TypeError, ValueError, AttributeError, RuntimeError):
        return {}
