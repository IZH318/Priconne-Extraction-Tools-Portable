from __future__ import annotations
import logging
import tkinter as tk
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from src.languages import RENAMER_LANGUAGES as LANGUAGES
from .logic import RenameHashedFile
from .view import RenamerView
from src.constants import APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, APP_WEBSITE, GUI_UPDATE_INTERVAL_MS

class RenamerController:
    """
    MVC 아키텍처 중 Controller(상태 및 뷰모델 관리)를 전담하는 클래스입니다.
    View로부터 이벤트를 전달받아 Background Worker(RenamerLogic)를 제어하고, View에 렌더링을 명령합니다.
    """
    _DEFAULT_ABOUT_INFO: dict[str, str] = {
        'program': "Manifest File Renamer",
        'version': APP_VERSION,
        'updated': APP_LAST_UPDATE,
        'license': "GNU General Public License v3.0",
        'developer': APP_DEVELOPER,
        'website': APP_WEBSITE,
    }

    def __init__(self, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        self.view = RenamerView(master, self)
        self.about_info = about_info or self._DEFAULT_ABOUT_INFO
        
        self.current_lang = 'ko'
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value=self.current_lang)
        self.lang_var.trace_add("write", self.on_language_change)
        
        self.log_data = []  # tuple[timestamp, key, kwargs]
        self.last_progress_info = {'current': 0, 'total': 0}
        self.is_processing = False
        self.total_files_count = 0

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        
        self._base_path = None
        
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue, self.get_string, base_path=self._base_path)

        
        self.update_ui_language(is_initial_setup=True)
        self.view.set_base_path_text("")

    def get_string(self, key: str, **kwargs: Any) -> str:
        return LANGUAGES[self.current_lang].get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    def set_language(self, lang_code: str) -> None:
        if self.current_lang != lang_code:
            self.current_lang = lang_code
            self.file_processor.set_get_string_func(self.get_string)
            self.update_ui_language()

    def on_language_change(self, *args: Any) -> None:
        new_lang = self.lang_var.get()
        self.set_language(new_lang)

    def update_ui_language(self, is_initial_setup: bool = False) -> None:
        self.view.set_texts(
            self.get_string('start_button'),
            self.get_string('game_client_folder'),
            self.get_string('folder_open')
        )
        
        if not self.is_processing:
            if self.total_files_count > 0 and self.view.get_progress_value() >= 100:
                self.view.set_progress_text(self.get_string('status_complete_count', count=self.total_files_count))
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
        
        self.re_render_logs()

    def show_about_info(self) -> None:
        """
        Main.py에서 상단 About 메뉴 클릭 시 호출될 수 있도록 유지명세화
        """
        self._add_raw_text("")
        self._add_log_event('SHOW_ABOUT_INFO')
        self._add_raw_text("")
        self.re_render_logs()

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

    def re_render_logs(self) -> None:
        output_buffer = []

        for i, (timestamp, key, kwargs) in enumerate(self.log_data):
            if timestamp is None:
                output_buffer.append(key + "\n")
                continue

            if key == 'initial_info_db' and kwargs is not None:
                folder_lines = []
                folders = self.file_processor.target_folders
                for idx, folder in enumerate(folders):
                    prefix_key = 'folder_item_last' if idx == len(folders) - 1 else 'folder_item_branch'
                    folder_lines.append(self.get_string(prefix_key, folder_name=folder))
                kwargs['folder_structure'] = "\n".join(folder_lines)

            message = self.get_string(key, **kwargs) if kwargs is not None else self.get_string(key)
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
            self.re_render_logs()

    def start_processing_thread(self) -> None:
        from tkinter import messagebox
        if self._base_path is None:
            messagebox.showerror(self.get_string('error_title'), self.get_string('dialog_select_folder'))
            return
            
        if not (self._base_path / "manifest.db").exists():
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        self.log_data.clear()
        self.show_initial_message()
        self.re_render_logs()
        
        self.is_processing = True
        self.view.set_start_button_state(tk.DISABLED)
        self.view.set_progress_value(0)
        self.last_progress_info = {'current': 0, 'total': 0}
        self.view.set_progress_text(self.get_string('status_searching'))
        
        self.file_processor.set_get_string_func(self.get_string)
        
        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()
        
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread) -> None:
        log_items_batch = []
        progress_updates = []
        
        try:
            while not self.log_queue.empty():
                log_items_batch.append(self.log_queue.get_nowait())
            while not self.progress_queue.empty():
                progress_updates.append(self.progress_queue.get_nowait())
        except queue.Empty:
            pass

        if log_items_batch:
            # 첫 실행이 아닌 경우, 처리 로그 앞에 빈 줄 추가
            last_key = self.log_data[-1][1] if self.log_data else None
            if last_key is not None and last_key.strip() != "":
                if log_items_batch[0][0] == 'raw' and log_items_batch[0][1].get('text') == "":
                    pass
                else:
                    self._add_raw_text("")

            for key, kwargs in log_items_batch:
                self._add_log_event(key, kwargs)
            self.re_render_logs()

        if progress_updates:
            for progress_val, current, total in progress_updates:
                self.view.set_progress_value(progress_val)
                self.last_progress_info = {'current': current, 'total': total}
                self.view.set_progress_text(self.get_string('status_processing', current=current, total=total))
                self.total_files_count = total

        if thread.is_alive():
            self.view.after(GUI_UPDATE_INTERVAL_MS, lambda: self.monitor_queue(thread))
        else:
            final_log_items = []
            try:
                while True: 
                    final_log_items.append(self.log_queue.get_nowait())
            except queue.Empty: pass
            
            if final_log_items:
                for key, kwargs in final_log_items:
                    self._add_log_event(key, kwargs)
            
            self.re_render_logs()

            self.is_processing = False
            self.view.set_progress_value(100)
            if self.total_files_count > 0:
                self.view.set_progress_text(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                self.view.set_progress_text(self.get_string('status_complete'))
            self.view.set_start_button_state(tk.NORMAL)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다. (현재 리소스 없음)"""
        pass
