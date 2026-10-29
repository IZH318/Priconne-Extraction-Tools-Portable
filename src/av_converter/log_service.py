"""AV Converter 실시간 큐 이벤트 및 UI 로그 상태 관리 서비스 모듈.

비디오/오디오 변환 백그라운드 스레드에서 발생하는 ProgressEvent, LogEvent,
LogBlockEvent, CompletionEvent를 논블로킹으로 수신하여 Tkinter 위젯(ScrolledText,
ProgressBar, StatusLabel)에 렌더링하고, 언어 전환 시 재렌더링 캐시 관리.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from collections.abc import Callable
from typing import Any

from src.constants import SENTINEL_VIDEO_DONE
from src.queue_events import (
    CompletionEvent,
    LogBlockEvent,
    LogEvent,
    ProgressEvent,
    QueueEvent,
)
from src.utils.log_history import new_log_timestamp

logger = logging.getLogger(__name__)


class AVLogService:
    """AV Converter 탭의 로그 렌더링 및 큐 이벤트 처리 서비스 클래스.

    SharedState 또는 주입받은 큐로부터 실시간 변환 진행 상황을 디스패치하며,
    동적 다국어 언어 변경 시 기존 로그 히스토리를 대상 언어로 일괄 재렌더링.

    Attributes:
        _view (Any): 상위 Tkinter 뷰 객체.
        _log_queue (Any): 스레드 간 이벤트 전달용 Queue.
        _get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _video_log_history (list): 비디오 탭 로그 히스토리 버퍼.
        _audio_log_history (list): 오디오 탭 로그 히스토리 버퍼.
        _last_log_timestamp (dict): 탭별 최근 로그 타임스탬프 캐시.
    """

    def __init__(
        self,
        view: Any,
        log_queue: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        video_log_history: list,
        audio_log_history: list,
        last_log_timestamp: dict,
        redraw_logs_fn: Callable[[list, dict], None],
        render_log_entry_fn: Callable[[str | None, str, Any, str | None], str],
        get_video_total_files: Callable[[], int],
        set_video_total_files: Callable[[int], None],
        get_audio_total_files: Callable[[], int],
        set_audio_total_files: Callable[[int], None],
        get_video_cancel_token: Callable[[], Any],
        get_audio_cancel_token: Callable[[], Any],
        reset_ui_state: Callable[..., None],
        get_video_widgets: Callable[[], dict],
        get_audio_widgets: Callable[[], dict],
        get_base_path: Callable[[], Any] | None = None,
    ) -> None:
        """AVLogService 인스턴스 초기화.

        Args:
            view (Any): UI 컨트롤러 뷰 인스턴스.
            log_queue (Any): 이벤트 통신용 큐.
            get_lang_dict (Callable[[], dict[str, str]]): 다국어 맵 반환 함수.
            video_log_history (list): 비디오 로그 버퍼 리스트.
            audio_log_history (list): 오디오 로그 버퍼 리스트.
            last_log_timestamp (dict): 탭별 타임스탬프 딕셔너리.
            redraw_logs_fn (Callable[[list, dict], None]): 전체 로그 재렌더링 함수.
            render_log_entry_fn (Callable[[str | None, str, Any, str | None], str]): 개별 로그 텍스트 포맷터.
            get_video_total_files (Callable[[], int]): 비디오 파일 총 개수 조회 함수.
            set_video_total_files (Callable[[int], None]): 비디오 파일 총 개수 저장 함수.
            get_audio_total_files (Callable[[], int]): 오디오 파일 총 개수 조회 함수.
            set_audio_total_files (Callable[[int], None]): 오디오 파일 총 개수 저장 함수.
            get_video_cancel_token (Callable[[], Any]): 비디오 취소 토큰 반환 함수.
            get_audio_cancel_token (Callable[[], Any]): 오디오 취소 토큰 반환 함수.
            reset_ui_state (Callable[..., None]): UI 복구 함수.
            get_video_widgets (Callable[[], dict]): 비디오 위젯 사전 조회 함수.
            get_audio_widgets (Callable[[], dict]): 오디오 위젯 사전 조회 함수.
            get_base_path (Callable[[], Any] | None): 실행 루트 경로 반환 함수.
        """
        self._view = view
        self._log_queue = log_queue
        self._get_lang_dict = get_lang_dict
        self._video_log_history = video_log_history
        self._audio_log_history = audio_log_history
        self._last_log_timestamp = last_log_timestamp
        self._redraw_logs_fn = redraw_logs_fn
        self._render_log_entry_fn = render_log_entry_fn
        self._get_base_path = get_base_path or (lambda: None)
        self._get_video_total_files = get_video_total_files
        self._set_video_total_files = set_video_total_files
        self._get_audio_total_files = get_audio_total_files
        self._set_audio_total_files = set_audio_total_files
        self._get_video_cancel_token = get_video_cancel_token
        self._get_audio_cancel_token = get_audio_cancel_token
        self._reset_ui_state = reset_ui_state
        self._get_video_widgets = get_video_widgets
        self._get_audio_widgets = get_audio_widgets


    def _history(self, tab_type: str) -> list:
        return self._video_log_history if tab_type == 'video' else self._audio_log_history

    def _log_widget(self, tab_type: str) -> Any:
        return self._view.video_log_text if tab_type == 'video' else self._view.audio_log_text

    def add_log_entry(self, target_tab: str, log_key: str, **kwargs: Any) -> None:
        self._log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def log_system_message(self, target_tab: str, message: str) -> None:
        self._log_queue.put(LogEvent(target=target_tab, key='raw', kwargs={'text': message}))

    def add_spacing(self, target_tab: str) -> None:
        history = self._history(target_tab)
        if history and history[-1][1] == 'spacing':
            return
        self._log_queue.put(LogEvent(target=target_tab, is_spacing=True))

    def redraw_all_logs(self) -> None:
        configs_with_tabs = [
            ('video', self._video_log_history, self._view.video_log_text),
            ('audio', self._audio_log_history, self._view.audio_log_text),
        ]
        self._redraw_logs_fn(configs_with_tabs, self._last_log_timestamp)

    def on_poll_cycle(self) -> None:
        for msg in self._drain_queue():
            if not isinstance(msg, QueueEvent):
                continue

            if isinstance(msg, (ProgressEvent, CompletionEvent)):
                if isinstance(msg, ProgressEvent):
                    self.handle_progress_update(msg)
                else:
                    self.handle_completion_signal(msg)
                continue

            target_tab = getattr(msg, 'target', None) or 'video'
            if target_tab == 'video':
                log_widget = self._view.video_log_text
                history = self._video_log_history
            else:
                log_widget = self._view.audio_log_text
                history = self._audio_log_history

            log_widget.config(state=tk.NORMAL)

            if isinstance(msg, LogEvent):
                if msg.is_spacing:
                    history.append((None, 'spacing', {}))
                    log_widget.insert(tk.END, '\n')
                else:
                    timestamp = None if msg.un_timestamped else new_log_timestamp()
                    log_key = msg.key
                    kwargs = msg.kwargs
                    last_ts = self._last_log_timestamp[target_tab]
                    history.append((timestamp, log_key, kwargs))
                    log_widget.insert(tk.END, self._render_log_entry_fn(timestamp, log_key, kwargs, last_ts))

                    logger.info("[AV_%s] %s %s", target_tab.upper(), log_key, kwargs)

                    if timestamp:
                        self._last_log_timestamp[target_tab] = timestamp

            elif isinstance(msg, LogBlockEvent):
                log_entries = msg.entries
                block_timestamp = new_log_timestamp()
                last_ts_before_block = self._last_log_timestamp[target_tab]

                for i, (l_key, l_kwargs) in enumerate(log_entries):
                    last_ts_for_render = last_ts_before_block if i == 0 else block_timestamp
                    history.append((block_timestamp, l_key, l_kwargs))
                    log_widget.insert(tk.END, self._render_log_entry_fn(block_timestamp, l_key, l_kwargs, last_ts_for_render))
                    logger.info("[AV_%s] %s %s", target_tab.upper(), l_key, l_kwargs)

                if log_entries:
                    self._last_log_timestamp[target_tab] = block_timestamp

            log_widget.see(tk.END)
            log_widget.config(state=tk.DISABLED)

    def _drain_queue(self) -> list:
        from src.queue_polling import QueuePollingMixin
        return QueuePollingMixin._drain_queue(self._log_queue)

    def handle_progress_update(self, msg: ProgressEvent) -> None:
        d = self._get_lang_dict()
        target_tab = getattr(msg, 'target', None) or 'video'
        widgets = self._get_video_widgets() if target_tab == 'video' else self._get_audio_widgets()
        if not isinstance(widgets, dict):
            return

        if msg.is_start:
            total = msg.total
            if target_tab == 'video':
                self._set_video_total_files(total)
            else:
                self._set_audio_total_files(total)
            progress = widgets.get('progress')
            status_label = widgets.get('status_label')
            if progress is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    progress.config(maximum=total, value=0)
            if status_label is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    status_label.config(text=d.get('status_starting', 'Starting... (Total {total})').format(total=total))
        else:
            value = msg.current
            total = self._get_video_total_files() if target_tab == 'video' else self._get_audio_total_files()
            progress = widgets.get('progress')
            status_label = widgets.get('status_label')
            if progress is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    progress['value'] = value
            if status_label is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    status_label.config(text=d.get('status_processing', 'Processing: {current} / {total}').format(current=value, total=total))

    def handle_completion_signal(self, msg: CompletionEvent) -> None:
        from tkinter import messagebox
        d = self._get_lang_dict()
        tab_type = 'video' if msg.target == SENTINEL_VIDEO_DONE else 'audio'
        widgets = self._get_video_widgets() if tab_type == 'video' else self._get_audio_widgets()
        if not isinstance(widgets, dict):
            widgets = {}
        cancel_token = self._get_video_cancel_token() if tab_type == 'video' else self._get_audio_cancel_token()
        total = self._get_video_total_files() if tab_type == 'video' else self._get_audio_total_files()
        progress = widgets.get('progress') if isinstance(widgets, dict) else None
        current = 0
        if progress is not None:
            with contextlib.suppress(tk.TclError, RuntimeError, AttributeError, KeyError):
                current = progress['value']

        failed_files = msg.result if msg.result is not None else []
        if len(failed_files) > 0:
            self.generate_error_log(tab_type, failed_files)
            title = d.get('msgbox_error_log_saved_title', 'Error Log Created')
            text = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
            messagebox.showwarning(title, text, parent=self._view)

        self._reset_ui_state(tab_type, False)
        status_label = widgets.get('status_label') if isinstance(widgets, dict) else None
        if cancel_token and cancel_token.is_cancelled:
            if status_label is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    status_label.config(text=d.get('status_cancelled', 'Operation cancelled'))
        else:
            if status_label is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    status_label.config(text=d.get('status_complete', 'Completed: {current} / {total}').format(current=current, total=total))
            if progress is not None:
                with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
                    progress['value'] = total

    def generate_error_log(self, tab_type: str, failed_files: list) -> None:
        import os
        import sys

        from src.utils.error_log import open_task_log, write_log_items
        try:
            base_path = self._get_base_path()
            if base_path:
                exec_path = str(base_path)
            elif hasattr(self, 'base_path') and self.base_path:
                exec_path = str(self.base_path)
            elif sys.argv and sys.argv[0]:
                exec_path = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                exec_path = os.path.abspath(os.getcwd())

            extra_report = [
                f"[REPORT]  Target Type:     {tab_type.upper()}",
                f"[REPORT]  Total Failed:    {len(failed_files)}",
            ]

            opened = open_task_log("AVConverterLog", "AV Converter Task Log", exec_path, extra_report)
            if opened is None:
                return
            _log_path, f, now_ts = opened
            try:
                write_log_items(
                    f,
                    failed_files,
                    item_header="[ERROR ITEM #{idx}]",
                    timestamp=now_ts,
                    context=f"{tab_type.capitalize()} Conversion",
                    message_fn=lambda item: (item[1] or "").strip() or "Unknown",
                )
            finally:
                f.close()
        except (OSError, ValueError, TypeError) as e:
            logger.exception("Failed to write AVConverterLog: %s", e)
