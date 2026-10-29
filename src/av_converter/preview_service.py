"""AV Converter 미디어 파일 미리보기 준비 서비스 모듈.

비디오(.usm) 및 오디오(.awb) 파일의 단일 항목 재생 미리보기를 위해
필요한 외부 툴(UsmToolkit, vgmstream, FFmpeg, .NET Runtime)의 다운로드 및 준비 여부를 점검하고,
완료 시 미리보기 콜백 호출.
"""

from __future__ import annotations

import logging
import subprocess
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox
from typing import Any

from src.constants import GUI_POLLING_INTERVAL_MS

logger = logging.getLogger(__name__)


class AVPreviewService:
    """미디어 파일 미리보기 툴체인 점검 및 준비 서비스.

    탭별 중복 실행 방지 플래그(_preview_busy_tabs)를 통해 다중 클릭으로 인한 경쟁 상태(Race Condition)를 방지하며,
    툴체인 준비 Future 완료를 폴링하여 성공 시 on_success 콜백 호출.

    Attributes:
        _view (Any): 알림 대화상자 표시 및 after 타이머 호출을 위한 View.
        _get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _add_log_entry (Callable[..., None]): 로그 이벤트 발행 콜백.
        _find_tools (Callable[[], None]): 도구 경로 재탐색 콜백.
        _tool_pipeline (Any): 도구 준비 파이프라인(Future 반환).
        _preview_selected_fn (Callable[[Any, Any], None]): 선택 항목 미리보기 위임 콜백.
        _polling_interval_ms (int): 비동기 툴 준비 완료 여부 폴링 주기(ms).
        _preview_busy_tabs (set[str]): 툴 준비 작업이 진행 중인 탭 키 집합 (탭별 독립).
    """

    def __init__(
        self,
        view: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        add_log_entry: Callable[..., None],
        find_tools: Callable[[], None],
        tool_pipeline: Any,
        preview_selected_fn: Callable[[Any, Any], None],
        polling_interval_ms: int = GUI_POLLING_INTERVAL_MS,
    ) -> None:
        """AVPreviewService 초기화.

        Args:
            view (Any): 알림 대화상자/after 타이머용 View.
            get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
            add_log_entry (Callable[..., None]): 로그 이벤트 발행 콜백.
            find_tools (Callable[[], None]): 도구 경로 재탐색 콜백.
            tool_pipeline (Any): 도구 준비 파이프라인.
            preview_selected_fn (Callable[[Any, Any], None]): 선택 항목 미리보기 위임 콜백.
            polling_interval_ms (int): 폴링 간격(밀리초).
        """
        self._view: Any = view if view is not None else {}
        self._get_lang_dict: Callable[[], dict[str, str]] = get_lang_dict if callable(get_lang_dict) else dict
        self._add_log_entry = add_log_entry if callable(add_log_entry) else (lambda *a, **k: None)
        self._find_tools = find_tools if callable(find_tools) else (lambda: None)
        self._tool_pipeline = tool_pipeline
        self._preview_selected_fn = (
            preview_selected_fn if callable(preview_selected_fn) else (lambda *a, **k: None)
        )
        self._polling_interval_ms = polling_interval_ms
        self._preview_busy_tabs: set[str] = set()

    def preview_selected(self, listbox: Any, tab_type: Any) -> None:
        """리스트박스에서 현재 선택된 파일 항목의 미리보기 처리 위임 실행.

        Args:
            listbox (Any): 파일 목록을 표시하는 Listbox 위젯.
            tab_type (Any): 대상 탭 ('video' 또는 'audio').
        """
        self._preview_selected_fn(listbox, tab_type)

    def prepare_tools_for_preview(self, tab_type: Any, on_success: Callable[[], None]) -> None:
        """미리보기에 필요한 툴체인을 비동기로 다운로드/준비하고 완료 시 콜백 실행.

        탭별로 동시 중복 호출 시 무시되며(진행 중 플래그), 준비 작업은 백그라운드 파이프라인에 위임된다.

        Args:
            tab_type (Any): 검사할 탭 식별자 ('video' 또는 'audio').
            on_success (Callable[[], None]): 도구 준비가 성공적으로 끝났을 때 호출될 콜백 함수.
        """
        busy_key = str(tab_type)
        if busy_key in self._preview_busy_tabs:
            # 이미 준비 중인 동일 탭 요청은 중복 다운로드 방지를 위해 무시 (탭 간 간섭 없음).
            logger.debug("Preview tool preparation is already in progress for '%s'; request ignored.", busy_key)
            return
        self._preview_busy_tabs.add(busy_key)
        # 비동기 폴링(check_status)에 위임되기 전까지는 동기 구간이므로,
        # 예외/조기 반환을 포함한 모든 종료 경로에서 플래그를 해제해야 한다.
        handed_off = False

        def release_busy() -> None:
            """해당 탭의 진행 중 플래그 해제 (중복 해제 무해)."""
            self._preview_busy_tabs.discard(busy_key)

        try:
            view = self._view
            lang_dict = self._get_lang_dict()
            if self._tool_pipeline is None:
                logger.warning("Tool pipeline is unavailable; skipping preview tool preparation for %s.", tab_type)
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
                    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
                        self._add_log_entry(tab_type, "conv_log_error_exception", error=str(e))
                    finally:
                        release_busy()
                else:
                    try:
                        view.after(self._polling_interval_ms, check_status)
                    except (tk.TclError, RuntimeError, AttributeError):
                        release_busy()
                        logger.debug("view.after failed in prepare_tools_for_preview", exc_info=True)

            try:
                view.after(self._polling_interval_ms, check_status)
                handed_off = True
            except (tk.TclError, RuntimeError, AttributeError):
                logger.debug("view.after failed in prepare_tools_for_preview", exc_info=True)
        finally:
            # 폴링에 성공적으로 위임한 경우가 아니면 항상 진행 중 플래그를 해제한다.
            if not handed_off:
                release_busy()
