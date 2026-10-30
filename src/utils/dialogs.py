"""Tkinter 창/대화상자 배치 공통 유틸리티 모듈.

여러 모듈에 중복 구현돼 있던 '화면 중앙 배치' 계산을 단일 헬퍼로 제공한다.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Any

logger = logging.getLogger(__name__)


def center_window(window: Any, width: int, height: int) -> None:
    """창을 현재 화면 중앙에 배치한다(지오메트리 설정 포함).

    Args:
        window (Any): Tk/Toplevel 위젯 인스턴스.
        width (int): 창 너비(픽셀).
        height (int): 창 높이(픽셀).
    """
    try:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
    except (tk.TclError, AttributeError) as exc:
        logger.debug("center_window failed to read screen size: %s", exc)
        return
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    try:
        window.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError as exc:
        logger.debug("center_window failed to set geometry: %s", exc)
