from __future__ import annotations
import logging
import tkinter as tk
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from tkinter import ttk
from src.languages import RENAMER_LANGUAGES as LANGUAGES
from src.breadcrumbs import add_breadcrumb
from .logic import RenameHashedFile
from .view import RenamerView
from src.constants import APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, APP_WEBSITE, GUI_UPDATE_INTERVAL_MS
from src.queue_events import LogEvent, ProgressEvent
from src.queue_polling import QueuePollingMixin
from src.log_history import LogHistoryMixin

class RenamerController(QueuePollingMixin, LogHistoryMixin):
    """
    MVC 아키텍처 중 Controller(상태 및 뷰모델 관리)를 전담하는 클래스입니다.
    View로부터 이벤트를 전달받아 Background Worker(RenamerLogic)를 제어하고, View에 렌더링을 명령합니다.

    QueuePollingMixin을 상속하여 다른 모듈(AV Converter, Unity Converter, Resource Remover 등)과
    동일한 큐 폴링 인프라를 사용합니다.
    """
    _DEFAULT_ABOUT_INFO: dict[str, str] = {
        'program': "Manifest File Renamer",
        'version': APP_VERSION,
        'updated': APP_LAST_UPDATE,
        'license': "GNU General Public License v3.0",
        'developer': APP_DEVELOPER,
        'website': APP_WEBSITE,
    }

    def __init__(self, frame: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        self.master = master
        self.view = RenamerView(frame, self)
        self.about_info = about_info or self._DEFAULT_ABOUT_INFO
        
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
        self.lang_var.trace_add("write", self._on_language_change)
        
        self.log_data = []  # tuple[timestamp, key, kwargs]
        self.last_progress_info = {'current': 0, 'total': 0}
        self.is_processing = False
        self.total_files_count = 0
        self._active_thread: threading.Thread | None = None

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        
        self._base_path = None
        
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue, self.get_string, base_path=self._base_path)

        
        self.update_ui_language(is_initial_setup=True)
        self.view.set_base_path_text("")

        # QueuePollingMixin 초기화 — 기존 10ms 폴링 주기를 유지
        self._init_queue_polling(self.view, interval_ms=GUI_UPDATE_INTERVAL_MS)

    def get_string(self, key: str, **kwargs: Any) -> str:
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))
        return lang_dict.get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트를 처리하고 UI 텍스트를 업데이트합니다.

        Args:
            *args: 가변 인자 리스트.
        """
        self.file_processor.set_get_string_func(self.get_string)
        self.update_ui_language()

    def update_ui_language(self, is_initial_setup: bool = False) -> None:
        self.view.update_ui_text()
        
        if not self.is_processing:
            total_processed = getattr(self.file_processor, 'processed_count_rename', 0) + getattr(self.file_processor, 'processed_count_check', 0)
            has_error = getattr(self.file_processor, 'has_error', False)
            if has_error:
                if self.total_files_count > 0 and total_processed > 0:
                    self.view.set_progress_text(f"{self.get_string('error_title')}: {total_processed} / {self.total_files_count}")
                else:
                    self.view.set_progress_text(self.get_string('error_title'))
            elif self.total_files_count > 0:
                if total_processed >= self.total_files_count:
                    self.view.set_progress_text(self.get_string('status_complete_count', count=self.total_files_count))
                elif total_processed > 0:
                    self.view.set_progress_text(f"{self.get_string('status_complete')} ({total_processed} / {self.total_files_count})")
                else:
                    self.view.set_progress_text(f"{self.get_string('error_title')} (0 / {self.total_files_count})")
            else:
                self.view.set_progress_text(self.get_string('status_waiting'))
        else:
            if self.last_progress_info['total'] == 0:
                self.view.set_progress_text(self.get_string('status_searching'))
            else:
                self.view.set_progress_text(self.get_string('status_processing', **self.last_progress_info))
        
        if is_initial_setup:
            self.log_data.clear()
            self.show_initial_message()
        
        self.redraw_all_logs()

    def show_about_info(self) -> None:
        """
        Main.py에서 상단 About 메뉴 클릭 시 호출될 수 있도록 유지명세화
        """
        self._add_raw_text("")
        self._add_log_event('SHOW_ABOUT_INFO')
        self._add_raw_text("")
        self.redraw_all_logs()

    def show_initial_message(self) -> None:
        self._add_log_event('program_started')
        self._add_raw_text("")
        
        folder_lines = []
        folders = self.file_processor.target_folders
        for i, folder in enumerate(folders):
            prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
            folder_lines.append(self.get_string(prefix_key, folder_name=folder))
        
        self._add_log_event('initial_info_db', {'folder_structure': "\n".join(folder_lines)})
        self._add_log_event('initial_info_start')
        self._add_raw_text("")

    def redraw_all_logs(self) -> None:
        output_buffer = []

        for i, (timestamp, key, kwargs) in enumerate(self.log_data):
            if timestamp is None:
                output_buffer.append(key + "\n")
                continue

            render_kwargs = dict(kwargs) if kwargs is not None else None
            if key == 'initial_info_db' and render_kwargs is not None:
                folder_lines = []
                folders = self.file_processor.target_folders
                for idx, folder in enumerate(folders):
                    prefix_key = 'folder_item_last' if idx == len(folders) - 1 else 'folder_item_branch'
                    folder_lines.append(self.get_string(prefix_key, folder_name=folder))
                render_kwargs['folder_structure'] = "\n".join(folder_lines)

            message = self.get_string(key, **render_kwargs) if render_kwargs is not None else self.get_string(key)
            if not message:
                continue

            is_same_group = i > 0 and self.log_data[i-1][0] == timestamp
            line_prefix = f"[{timestamp}] " if not is_same_group else ' ' * 13

            if key == 'SHOW_ABOUT_INFO':
                about_lines = [self.get_string('about_header')]
                for info_key, value in self.about_info.items():
                    label_key = f'about_label_{info_key}'
                    label_text = self.get_string(label_key)
                    about_lines.append(f"  - {label_text}\t: {value}")
                output_buffer.append("\n".join(about_lines) + "\n")
                continue
                
            if key == 'backend_job_summary':
                logging.info("[Renamer] %s", message)
                output_buffer.append(f"\n[{timestamp}] {message}")
            else:
                logging.info("[Renamer] %s", message)
                output_buffer.append(f"{line_prefix}{message}")

        final_text = "".join(output_buffer)
        self.view.write_log(final_text)

    def _add_raw_text(self, text: str) -> None:
        self.log_data.append((None, text, None))

    def _add_log_event(self, key: str, kwargs: dict[str, Any] | None = None) -> None:
        if kwargs is None:
            kwargs = {}
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_data.append((timestamp, key, kwargs))

    def select_folder(self) -> None:
        from tkinter import filedialog
        initial_dir = str(self._base_path) if self._base_path else "/"
        folder_selected = filedialog.askdirectory(title=self.get_string('dialog_select_folder'), initialdir=initial_dir)
        if folder_selected:
            self._base_path = Path(folder_selected)
            self.file_processor.set_base_path(self._base_path)
            self.view.set_base_path_text(str(self._base_path))
            
            # 로그를 초기화하고 새 경로로 초기 메시지 재표시
            self.log_data.clear()
            self.show_initial_message()
            self.redraw_all_logs()

    def start_processing_thread(self) -> None:
        from tkinter import messagebox
        if self._base_path is None:
            messagebox.showerror(self.get_string('error_title'), self.get_string('dialog_select_folder'))
            return
            
        manifest_db_path = self._base_path / "manifest.db"
        manifest_dir = self._base_path / "manifest"
        if not manifest_db_path.exists() and not manifest_dir.is_dir():
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        self.log_data.clear()
        self.show_initial_message()
        self.redraw_all_logs()
        add_breadcrumb("conv", "Started renamer task", {"path": str(self._base_path)})
        
        self.is_processing = True
        self.view.set_start_button_state(tk.DISABLED)
        self.view.set_progress_value(0)
        self.last_progress_info = {'current': 0, 'total': 0}
        self.view.set_progress_text(self.get_string('status_searching'))
        
        self.file_processor.set_get_string_func(self.get_string)
        
        self._active_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        self._active_thread.start()

    def _on_poll_cycle(self) -> None:
        """QueuePollingMixin 훅: 매 폴링 사이클마다 로그/진행률 큐를 처리합니다."""
        # 처리 중이 아니면 큐 확인 불필요
        if not self.is_processing:
            return

        log_items_batch = self._drain_queue(self.log_queue)
        progress_updates = self._drain_queue(self.progress_queue)

        if log_items_batch:
            # 첫 실행이 아닌 경우, 처리 로그 앞에 빈 줄 추가
            last_key = self.log_data[-1][1] if self.log_data else None
            if last_key is not None and last_key.strip() != "":
                first = log_items_batch[0]
                if isinstance(first, LogEvent) and first.key == 'raw' and first.kwargs.get('text') == "":
                    pass
                else:
                    self._add_raw_text("")

            for event in log_items_batch:
                self._add_log_event(event.key, event.kwargs if event.kwargs else None)
            self.redraw_all_logs()

        if progress_updates:
            for event in progress_updates:
                self.view.set_progress_value(event.value)
                self.last_progress_info = {'current': event.current, 'total': event.total}
                self.view.set_progress_text(self.get_string('status_processing', current=event.current, total=event.total))
                self.total_files_count = event.total

        # 스레드 종료 감지 — 잔여 이벤트 드레인 후 완료 처리
        if self._active_thread is not None and not self._active_thread.is_alive():
            final_log_items = self._drain_queue(self.log_queue)
            if final_log_items:
                for event in final_log_items:
                    self._add_log_event(event.key, event.kwargs if event.kwargs else None)
            
            self.redraw_all_logs()

            self.is_processing = False
            self._active_thread = None
            self.view.set_start_button_state(tk.NORMAL)

            # 처리 결과에 따른 정확한 상태 표시 (오류 및 미완료 거짓 반환 방지)
            total_processed = getattr(self.file_processor, 'processed_count_rename', 0) + getattr(self.file_processor, 'processed_count_check', 0)
            has_error = getattr(self.file_processor, 'has_error', False)

            if has_error:
                # 오류 발생 시: 100% 완료로 표시하지 않고 오류 상태 표시
                if self.total_files_count > 0 and total_processed > 0:
                    pct = int((total_processed / self.total_files_count) * 100)
                    self.view.set_progress_value(pct)
                    self.view.set_progress_text(f"{self.get_string('error_title')}: {total_processed} / {self.total_files_count}")
                else:
                    self.view.set_progress_value(0)
                    self.view.set_progress_text(self.get_string('error_title'))
            elif self.total_files_count > 0:
                if total_processed >= self.total_files_count:
                    # 모든 파일 정상 처리 완료
                    self.view.set_progress_value(100)
                    self.view.set_progress_text(self.get_string('status_complete_count', count=self.total_files_count))
                elif total_processed > 0:
                    # 일부 파일만 처리되고 일부는 미처리/실패
                    pct = int((total_processed / self.total_files_count) * 100)
                    self.view.set_progress_value(pct)
                    self.view.set_progress_text(f"{self.get_string('status_complete')} ({total_processed} / {self.total_files_count})")
                else:
                    # 처리된 파일이 0개인 경우 (전체 실패)
                    self.view.set_progress_value(0)
                    self.view.set_progress_text(f"{self.get_string('error_title')} (0 / {self.total_files_count})")
            else:
                self.view.set_progress_value(0)
                self.view.set_progress_text(self.get_string('status_waiting'))

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다."""
        self._stop_polling()
