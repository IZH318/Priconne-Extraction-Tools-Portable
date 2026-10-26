"""Tkinter 위젯 생명주기 안전 조작(Defensive Tk Operation) 유틸리티 모듈.

Tkinter 애플리케이션에서 창이 닫히거나 위젯이 파괴(destroy)된 이후
지연 타이머(after), 설정 변경(config), 취소(after_cancel)가 호출될 때 발생하는
TclError: bad window path name 및 RuntimeError 안전 방어.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def safe_after(widget: Any, ms: int, callback: Callable[[], None]) -> str | None:
    """위젯이 유효할 때만 after() 타이머 콜백 안전 등록.

    winfo_exists() 검사 선행 및 Tcl 인터프리터 예외 발생 시 크래시 방어 (None 반환).

    Args:
        widget (Any): 타이머를 등록할 Tkinter 위젯 인스턴스.
        ms (int): 실행 지연 시간 (밀리초).
        callback (Callable[[], None]): 지연 후 호출될 콜백 함수.

    Returns:
        str | None: 등록 성공 시 Tkinter 타이머 식별자(ID 문자열), 실패 시 None.
    """
    try:
        if widget is None or not getattr(widget, "winfo_exists", lambda: True)():
            return None
        return widget.after(ms, callback)  # type: ignore[no-any-return]
    except (tk.TclError, RuntimeError, AttributeError) as exc:
        logger.debug("safe_after failed: %s", exc)
        return None


def safe_after_cancel(widget: Any, after_id: Any) -> None:
    """등록된 after 지연 작업 안전 취소.

    Args:
        widget (Any): 타이머가 등록되었던 Tkinter 위젯 인스턴스.
        after_id (Any): 취소할 타이머 ID 문자열. None인 경우 무시 처리.
    """
    if after_id is None or widget is None:
        return
    try:
        widget.after_cancel(after_id)
    except (tk.TclError, ValueError, AttributeError) as exc:
        logger.debug("safe_after_cancel failed: %s", exc)


def safe_destroy(widget: Any) -> None:
    """위젯 안전 파기.

    Args:
        widget (Any): 파기 대상 Tkinter 위젯 인스턴스.
    """
    if widget is None:
        return
    try:
        widget.destroy()
    except (tk.TclError, RuntimeError, AttributeError) as exc:
        logger.debug("safe_destroy failed: %s", exc)


def safe_config(widget: Any, **kwargs: Any) -> bool:
    """위젯 대상 설정(config/configure) 옵션 안전 적용.

    Args:
        widget (Any): 설정을 변경할 Tkinter 위젯 인스턴스.
        **kwargs (Any): 위젯 옵션 키워드 인자 (예: text="...", state="disabled").

    Returns:
        bool: 설정 적용 성공 시 True, 위젯 소멸 또는 예외 발생 시 False.
    """
    if widget is None:
        return False
    try:
        widget.config(**kwargs)
        return True
    except (tk.TclError, RuntimeError, AttributeError) as exc:
        logger.debug("safe_config failed: %s", exc)
        return False

