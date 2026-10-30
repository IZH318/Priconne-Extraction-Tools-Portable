"""Renamer 큐 폴링 및 이벤트 처리기 모듈.

파일 이름 복원 작업 중 백그라운드 스레드와 UI 간의 브리지 이벤트를 처리하며,
Tkinter 폴링 주기마다 로그 및 진행률 이벤트 큐를 드레인하고 작업 스레드 종료 시 UI 상태 마무리.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any

from src.queue_events import LogEvent
from src.utils.log_history import new_log_timestamp

logger = logging.getLogger(__name__)


class RenamerQueueHandler:
    """Renamer의 논블로킹 큐 이벤트 수신(Drain) 및 완료 상태 조정을 담당하는 이벤트 핸들러 클래스.

    QueuePollingMixin 타이머 틱에 의해 주기적으로 실행.
    스레드 안전 큐에서 이벤트를 꺼내 UI 로그 텍스트를 추가하고 프로그레스 위젯을 갱신하며,
    워커 스레드 종료 시 완료 후처리 담당.

    Attributes:
        controller: 애플리케이션 상태를 관리하는 상위 MVC 컨트롤러.
        log_manager: 로그 메시지 포맷팅 및 캐싱을 담당하는 렌더러.
        rename_service: 스레드 실행 및 에러 리포트 생성을 관리하는 서비스.
        view: Tkinter 위젯을 호스팅하는 프레젠테이션 뷰.
    """

    def __init__(self, controller: Any, log_manager: Any, rename_service: Any, view: Any) -> None:
        """RenamerQueueHandler 초기화.

        Args:
            controller: 상위 RenamerController.
            log_manager: 연동 RenamerLogRenderer.
            rename_service: 연동 RenameService.
            view: 연동 RenamerView.
        """
        self.controller = controller
        self.log_manager = log_manager
        self.rename_service = rename_service
        self.view = view

    def on_poll_cycle(self) -> None:
        """단일 폴링 주기 스텝 실행, 큐 비우기 및 스레드 상태 확인."""
        c = self.controller
        if not c.is_processing:
            return

        log_items_batch = c._drain_queue(c.log_queue)
        progress_updates = c._drain_queue(c.progress_queue)

        # 1. 배치 로그 이벤트 처리
        if log_items_batch:
            incremental_buffer = []
            last_key = c.log_data[-1][1] if c.log_data else None
            if last_key is not None and last_key.strip() != "":
                first = log_items_batch[0]
                if isinstance(first, LogEvent) and first.key == 'raw' and (first.kwargs or {}).get('text') == "":
                    pass
                else:
                    c._add_raw_text("")
                    incremental_buffer.append("\n")

            for event in log_items_batch:
                timestamp = new_log_timestamp()
                kwargs = event.kwargs if event.kwargs else None
                is_same_group = len(c.log_data) > 0 and c.log_data[-1][0] == timestamp
                c.log_data.append((timestamp, event.key, kwargs))
                display_text, raw_msg = c._format_log_entry(timestamp, event.key, kwargs, is_same_group)
                if raw_msg:
                    logger.info("[Renamer] %s", raw_msg)
                if display_text:
                    incremental_buffer.append(display_text)

            if incremental_buffer:
                c.view.append_log("".join(incremental_buffer))

        # 2. 진행률 퍼센트 및 상태 이벤트 처리
        if progress_updates:
            for event in progress_updates:
                c.view.set_progress_value(event.value)
                c.last_progress_info = {'current': event.current, 'total': event.total}
                c.view.set_progress_text(c.get_string('status_processing', current=event.current, total=event.total))
                c.total_files_count = event.total

        # 3. 작업 스레드 종료 감지 및 워크플로 마무리
        if getattr(c, "_active_thread", None) is not None and not c._active_thread.is_alive():
            final_log_items = c._drain_queue(c.log_queue)
            if final_log_items:
                final_buffer = []
                for event in final_log_items:
                    timestamp = new_log_timestamp()
                    kwargs = event.kwargs if event.kwargs else None
                    is_same_group = len(c.log_data) > 0 and c.log_data[-1][0] == timestamp
                    c.log_data.append((timestamp, event.key, kwargs))
                    display_text, raw_msg = c._format_log_entry(timestamp, event.key, kwargs, is_same_group)
                    if raw_msg:
                        logger.info("[Renamer] %s", raw_msg)
                    if display_text:
                        final_buffer.append(display_text)
                if final_buffer:
                    c.view.append_log("".join(final_buffer))

            c.is_processing = False
            c._active_thread = None
            c.view.set_start_button_state(tk.NORMAL)
            c.view.set_folder_button_state(tk.NORMAL)

            processor = getattr(c, "_processing_processor", None) or c.file_processor
            result = c._rename_service.classify_result(processor)
            total_processed = result["total_processed"]
            has_error = result["has_error"]
            unprocessed_files = result["unprocessed"]
            total_files_count = result["total_files"]
            if total_files_count:
                c.total_files_count = total_files_count

            # 오류 발생 시 에러 로그 생성 및 알림 대화상자 노출
            if has_error or len(unprocessed_files) > 0:
                c._rename_service.generate_error_log(unprocessed_files, getattr(processor, 'error_message', None))

                from tkinter import messagebox
                d = c.get_lang_dict()
                title = d.get('msgbox_error_log_saved_title', 'Error Log Created')
                text = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
                messagebox.showwarning(title, text, parent=c.view)

            c._processing_processor = None

            # 최종 진행률 및 완료 상태 표시 갱신
            if has_error:
                if c.total_files_count > 0 and total_processed > 0:
                    pct = int((total_processed / c.total_files_count) * 100)
                    c.view.set_progress_value(pct)
                    c.view.set_progress_text(f"{c.get_string('error_title')}: {total_processed} / {c.total_files_count}")
                else:
                    c.view.set_progress_value(0)
                    c.view.set_progress_text(c.get_string('error_title'))
            elif c.total_files_count > 0:
                if total_processed >= c.total_files_count:
                    c.view.set_progress_value(100)
                    c.view.set_progress_text(c.get_string('status_complete_count', count=c.total_files_count))
                elif total_processed > 0:
                    pct = int((total_processed / c.total_files_count) * 100)
                    c.view.set_progress_value(pct)
                    c.view.set_progress_text(f"{c.get_string('status_complete')} ({total_processed} / {c.total_files_count})")
                else:
                    c.view.set_progress_value(0)
                    c.view.set_progress_text(f"{c.get_string('error_title')} (0 / {c.total_files_count})")
            else:
                c.view.set_progress_value(0)
                c.view.set_progress_text(c.get_string('status_waiting'))
