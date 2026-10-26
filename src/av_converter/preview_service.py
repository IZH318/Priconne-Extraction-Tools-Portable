"""AV Converter 미디어 파일 미리보기 준비 서비스 모듈.

비디오(.usm) 및 오디오(.awb, .acb, .hca) 파일의 단일 항목 재생 미리보기를 위해
필요한 외부 툴(UsmToolkit, vgmstream, FFmpeg)의 다운로드 및 준비 여부를 점검하고,
완료 시 미리보기 콜백 호출.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox
from typing import Any, cast

logger = logging.getLogger(__name__)


class AVPreviewService:
    """미디어 파일 미리보기 툴체인 점검 및 준비 서비스.

    중복 실행 방지 플래그(_preview_busy)를 통해 다중 클릭 레이스 컨디션을 차단하며,
    .NET 런타임 검사 및 다운로드 Future 완료를 폴링하여 성공 시 on_success 콜백 호출.

    Attributes:
        _shared_state (Any): 상위 공유 애플리케이션 상태 컨테이너.
        _view (Any): 알림 대화상자 표시 및 after 타이머 호출을 위한 View.
        _polling_interval_ms (int): 비동기 툴 준비 완료 여부 폴링 주기(ms).
        _preview_busy (bool): 현재 미리보기 준비 작업 진행 중 플래그.
    """

    def __init__(
        self,
        shared_state: Any = None,
        polling_interval_ms: int = 100,
    ) -> None:
        """AVPreviewService 초기화.

        Args:
            shared_state (Any): 상태 컨테이너 객체.
            polling_interval_ms (int): 폴링 간격(밀리초).
        """
        ss = shared_state
        self._shared_state = ss
        _v = (ss.get_view() if ss is not None and callable(getattr(ss, "get_view", None)) else None)
        self._view: Any = cast(Any, _v if _v is not None else {})
        gld = getattr(ss, "get_lang_dict", None) if ss is not None else None
        self._get_lang_dict: Callable[[], dict[str, str]] = gld if callable(gld) else (dict)
        ald = getattr(ss, "add_log_entry", None) if ss is not None else None
        self._add_log_entry = ald if callable(ald) else (lambda *a, **k: None)
        idra = getattr(ss, "is_dotnet_runtime_available", None) if ss is not None else None
        self._is_dotnet_runtime_available = idra if callable(idra) else (lambda: False)
        ft = getattr(ss, "find_tools", None) if ss is not None else None
        self._find_tools = ft if callable(ft) else (lambda: None)
        self._tool_pipeline: Any = cast(Any, getattr(ss, "tool_pipeline", None) if ss is not None else None)
        psf = getattr(ss, "preview_selected_fn", None) if ss is not None else None
        self._preview_selected_fn = psf if callable(psf) else (lambda *a, **k: None)
        self._polling_interval_ms = polling_interval_ms
        self._preview_busy: bool = False

    def preview_selected(self, listbox: Any, tab_type: Any) -> None:
        """리스트박스에서 현재 선택된 파일 항목의 미리보기 처리 위임 실행.

        Args:
            listbox (Any): 파일 목록을 표시하는 Listbox 위젯.
            tab_type (Any): 대상 탭 ('video' 또는 'audio').
        """
        self._preview_selected_fn(listbox, tab_type)

    def prepare_tools_for_preview(self, tab_type: Any, on_success: Callable[[], None]) -> None:
        """미리보기에 필요한 툴체인을 비동기로 다운로드/준비하고 완료 시 콜백 실행.

        동시 중복 호출 시 무시되며, 비디오 탭의 경우 .NET 런타임 설치 여부 확인.

        Args:
            tab_type (Any): 검사할 탭 식별자 ('video' 또는 'audio').
            on_success (Callable[[], None]): 도구 준비가 성공적으로 끝났을 때 호출될 콜백 함수.
        """
        if self._preview_busy:
            return
        self._preview_busy = True
        view = self._view
        lang_dict = self._get_lang_dict()
        if tab_type == "video" and not self._is_dotnet_runtime_available():
            messagebox.showwarning(
                lang_dict.get("dotnet_runtime_missing_title", ".NET Runtime Required"),
                lang_dict.get(
                    "dotnet_runtime_missing_msg",
                    "A 'Microsoft .NET Runtime' is required to convert video (.usm) files.\n\n"
                    "Please install .NET Core 3.1 or higher, or .NET 8.0 or higher, and try again.\n"
                    "(※ Note: This is different from .NET Framework)",
                ),
                parent=view,
            )
            self._preview_busy = False
            return
        self._add_log_entry(tab_type, "tools_preparing")
        download_future = self._tool_pipeline.ensure_tools_ready(tab_type)

        def check_status() -> None:
            """Future 완료 여부를 폴링하고 결과에 따라 성공 콜백 또는 경고창 표시."""
            if download_future.done():
                try:
                    if download_future.result():
                        self._find_tools()
                        on_success()
                    else:
                        fail_msg = lang_dict.get(
                            "usmtoolkit_prepare_fail" if tab_type == "video" else "vgmstream_prepare_fail",
                            "Tool preparation failed.",
                        )
                        messagebox.showwarning(lang_dict.get("preview_menu", "Preview"), fail_msg, parent=view)
                except (OSError, RuntimeError, ValueError) as e:
                    self._add_log_entry(tab_type, "conv_log_error_exception", error=str(e))
                finally:
                    self._preview_busy = False
            else:
                try:
                    view.after(self._polling_interval_ms, check_status)
                except (tk.TclError, RuntimeError):
                    self._preview_busy = False
                    logger.debug("view.after failed in prepare_tools_for_preview", exc_info=True)

        try:
            view.after(self._polling_interval_ms, check_status)
        except (tk.TclError, RuntimeError):
            self._preview_busy = False
            logger.debug("view.after failed in prepare_tools_for_preview", exc_info=True)

