from __future__ import annotations
import logging
import os
import threading
from src.cancellation_token import CancellationToken
import queue
import concurrent.futures
from multiprocessing import Manager, cpu_count
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.languages import UNITY_CONVERTER_LANGUAGES as LANGUAGES
from src.queue_events import LogEvent, CompletionEvent
from .extractor import process_single_file, AssetProcessor
from .asset_browser import AssetBrowserWindow
from src.constants import UNITY_SUPPORTED_EXTENSIONS as SUPPORTED_EXTENSIONS
from .view import AssetExtractorView

class AssetExtractorController:
    # --- Lifecycle & Initialization ---
    def __init__(self, frame: ttk.Frame, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None, app_temp_dir: str | None = None) -> None:
        """AssetExtractorController를 초기화합니다.

        Args:
            frame: gui.py의 ttk.Frame 래퍼 (View의 부모 위젯).
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            app_lang_var: 앱 전역 언어 StringVar.
            about_info: About 대화상자에 표시될 정보 딕셔너리.
            app_temp_dir: 앱 전역 임시 디렉터리 경로.

        Note:
            다른 Controller(Renamer, AV, ResourceRemover)는 master 하나만 받지만,
            UnityConverter와 StoryViewer는 대화상자 위치 지정을 위해
            별도의 master(최상위 윈도우)가 필요하여 2개의 위젯 인자를 받습니다.
        """
        self.frame = frame
        self.master = master
        self.app_temp_dir = app_temp_dir
        self.file_paths = []
        self.output_path = ""
        self.is_running = False
        self.processed_files_count = 0
        self.base_input_path = None
        self.log_events = []
        self.unity_version_var = tk.StringVar(value="2021.3.20f1")
        self.version_combo_var = tk.StringVar(value="2021.3.20f1")
        self.cancel_token = CancellationToken()
        self.about_info = about_info or {}
        self.asset_type_vars = {}

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self._manager = None
        self._log_queue = None
        self._completion_queue = None
        
        # UI_PRESETS
        self.UNITY_VERSION_PRESETS = ["2021.3.20f1", "6000.0.58.57061"]

        self.view = AssetExtractorView(frame, self)
        
        self.lang_var.trace_add('write', self._on_language_change)
        
        self.view.update_ui_text()
        self._log('program_started')
        self.frame.after(100, self._process_queues)

    @property
    def manager(self):
        if self._manager is None:
            self._manager = Manager()
        return self._manager

    @property
    def log_queue(self):
        if self._log_queue is None:
            self._log_queue = self.manager.Queue()
        return self._log_queue

    @property
    def completion_queue(self):
        if self._completion_queue is None:
            self._completion_queue = self.manager.Queue()
        return self._completion_queue

    def cleanup(self) -> None:
        """멀티프로세싱 Manager 리소스를 정리합니다."""
        if self._manager is not None:
            try:
                self._manager.shutdown()
            except OSError:
                pass
            self._manager = None
            self._log_queue = None
            self._completion_queue = None

    def _get_enabled_types(self) -> set[str]:
        return {name for name, var in self.asset_type_vars.items() if var.get()}

    def select_all_types(self) -> None:
        for var in self.asset_type_vars.values():
            var.set(True)

    def deselect_all_types(self) -> None:
        for var in self.asset_type_vars.values():
            var.set(False)

    def on_version_selection_change(self, event=None) -> None:
        selected = self.version_combo_var.get()
        if selected in self.UNITY_VERSION_PRESETS:
            self.unity_version_var.set(selected)
            self.view.version_entry.config(state='disabled')
        else:
            self.view.version_entry.config(state='normal')
            if self.unity_version_var.get() in self.UNITY_VERSION_PRESETS:
                self.unity_version_var.set("")
            self.view.version_entry.focus_set()

    def get_lang_dict(self) -> dict:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

    def _on_language_change(self, *args) -> None:
        try:
            self.view.update_ui_text()
            self._redisplay_logs()
        except tk.TclError:
            pass

    def _redisplay_logs(self) -> None:
        self.view.log_text.config(state='normal')
        self.view.log_text.delete('1.0', tk.END)
        for event in self.log_events:
            self._render_log_event(event)
        self.view.log_text.config(state='disabled')
        self.view.log_text.see(tk.END)

    def _add_log_event(self, message_key, level='INFO', format_args=None, prefix=None) -> LogEvent:
        return LogEvent(
            target=prefix or "",
            key=message_key,
            level=level,
            kwargs=format_args or {},
            un_timestamped=False
        )

    def _render_log_event(self, event: LogEvent, widget=None) -> None:
        target_widget = widget or self.view.log_text
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = event.target
        message_key = event.key
        level = event.level
        format_args = event.kwargs
        
        lang = self.lang_var.get()
        message_template = LANGUAGES.get(lang, LANGUAGES['ko']).get(message_key, message_key)
        
        if message_key == 'raw_text':
            message = format_args.get('text', '') if format_args else ''
        else:
            message = message_template.format(**format_args) if format_args else message_template
        
        log_prefix = f"[{prefix}] " if prefix else ""
        full_message = f"[{timestamp}] {log_prefix}{message}\n"
        
        logging.info("[Unity Converter] %s%s", log_prefix, message)
        
        target_widget.config(state='normal')
        target_widget.insert(tk.END, full_message, level)
        target_widget.config(state='disabled')

    def _log(self, message_key, level='INFO', format_args=None, prefix=None) -> None:
        event = self._add_log_event(message_key, level, format_args, prefix)
        self.log_events.append(event)
        self._render_log_event(event)
        self.view.log_text.see(tk.END)

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        title = lang_dict.get('about_header', '프로그램 정보 (Unity Converter)')
        
        info_lines = []
        for key, value in self.about_info.items():
            label_key = f'about_label_{key}'
            label_text = lang_dict.get(label_key, key.capitalize())
            info_lines.append(f"{label_text}: {value}")
            
        messagebox.showinfo(title, "\n".join(info_lines), parent=self.view)

    def _process_queues(self) -> None:
        log_batch = []
        completion_batch_size = 0
        try:
            while not self.log_queue.empty():
                log_batch.append(self.log_queue.get_nowait())
            while not self.completion_queue.empty():
                self.completion_queue.get_nowait()
                completion_batch_size += 1
        except queue.Empty:
            pass

        if log_batch:
            self.view.log_text.config(state='normal')
            for log_item in log_batch:
                if isinstance(log_item, LogEvent):
                    if log_item.key == 'raw_text':
                        event = self._add_log_event('raw_text', log_item.level, {'text': log_item.kwargs.get('text', '')})
                    else:
                        event = self._add_log_event(log_item.key, log_item.level, log_item.kwargs, log_item.target)
                    self.log_events.append(event)
                    self._render_log_event(event)
            self.view.log_text.config(state='disabled')
            self.view.log_text.see(tk.END)

        if completion_batch_size > 0:
            self.processed_files_count += completion_batch_size
            self.view.update_progress_bar()

        self.frame.after(100, self._process_queues)

    def select_files(self) -> None:
        """파일 선택 대화상자를 열고 .unity3d 파일을 추가합니다."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        paths = filedialog.askopenfilenames(
            title=d['file_dialog_title'],
            filetypes=((d['file_dialog_type'], "*.unity3d"),)
        )
        if paths:
            self.base_input_path = None
            self._add_files_to_list(paths)
        
    def select_folder(self) -> None:
        """폴더 선택 대화상자를 열고 내부 .unity3d 파일을 추가합니다."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        folder_path = filedialog.askdirectory(title=d['folder_dialog_title'])
        if folder_path:
            self.base_input_path = folder_path
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log('no_files_to_process', "WARNING")
            
    def on_dnd_drop(self, event) -> None:
        """드래그 앤 드롭으로 파일을 추가합니다."""
        if self.is_running:
            return
        try:
            paths = self.view.winfo_toplevel().tk.splitlist(event.data)
        except (AttributeError, tk.TclError):
            import re
            paths = [p.strip() for p in re.findall(r'\\{[^{}]*\\}|[^ ]+', event.data) if p.strip()]
            
        found_paths = []
        for path in paths:
            if os.path.isfile(path) and path.lower().endswith(SUPPORTED_EXTENSIONS):
                found_paths.append(path)
            elif os.path.isdir(path):
                self.base_input_path = path if not self.base_input_path else self.base_input_path
                found_paths.extend([os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)])
                
        if found_paths:
            self._add_files_to_list(found_paths)
        else:
            self._log('no_files_to_process', "WARNING")

    def _add_files_to_list(self, new_paths) -> None:
        current_paths_set = set(self.file_paths)
        added_count = 0
        for path in new_paths:
            if path not in current_paths_set:
                self.file_paths.append(path)
                current_paths_set.add(path)
                added_count += 1
        
        if added_count > 0:
            self.file_paths.sort()
            self.view.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.view.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('added_files', format_args={'count': added_count, 'total': len(self.file_paths)})
            
    def remove_selected_files(self, event=None) -> None:
        """선택된 파일을 목록에서 제거합니다."""
        if self.is_running:
            return
        selected_indices = self.view.file_listbox.curselection()
        if not selected_indices:
            return
        count = len(selected_indices)
        for index in sorted(selected_indices, reverse=True):
            del self.file_paths[index]
            self.view.file_listbox.delete(index)
        self._log('removed_selected_files', format_args={'count': count, 'total': len(self.file_paths)})
        
    def remove_all_files(self) -> None:
        """모든 파일을 목록에서 제거합니다."""
        if self.is_running:
            return
        if not self.file_paths:
            return
        count = len(self.file_paths)
        self.file_paths.clear()
        self.view.file_listbox.delete(0, tk.END)
        self.base_input_path = None
        self._log('removed_all_files', format_args={'count': count})

    def open_asset_browser(self) -> None:
        """선택된 파일의 에셋 브라우저를 엽니다."""
        selection = self.view.file_listbox.curselection()
        if not selection or selection[0] >= len(self.file_paths):
            return
        file_path = str(self.file_paths[selection[0]])
        d = self.get_lang_dict()
        unity_version = self.unity_version_var.get().strip() or "2021.3.20f1"
        AssetBrowserWindow(self.view.winfo_toplevel(), file_path, d, unity_version, self.app_temp_dir)

    def select_output_dir(self) -> None:
        """출력 폴더 선택 대화상자를 엽니다."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        path = filedialog.askdirectory(title=d['output_folder'])
        if path:
            self.output_path = path
            self.view.output_entry.config(state='normal')
            self.view.output_entry.delete(0, tk.END)
            self.view.output_entry.insert(0, path)
            self.view.output_entry.config(state='readonly')
            self._log('output_dir_set', format_args={'path': path})

    def start_extraction(self) -> None:
        """에셋 추출 작업을 시작합니다."""
        d = self.get_lang_dict()
        if not self.file_paths:
            messagebox.showwarning(d['warn_no_files_title'], d['warn_no_files_msg'], parent=self.view)
            return
        if not self.output_path:
            messagebox.showwarning(d['warn_no_output_title'], d['warn_no_output_msg'], parent=self.view)
            return
            
        self.is_running = True
        self.cancel_token.reset()
        self.view.toggle_controls(False)
        self.processed_files_count = 0
        self.view.progress_bar.config(maximum=len(self.file_paths))
        self.view.update_progress_bar()
        self._current_enabled_types = self._get_enabled_types()
        unity_version = self.unity_version_var.get().strip()
        if not unity_version: unity_version = "2021.3.20f1"
        self._current_unity_version = unity_version
        threading.Thread(target=self._run_process_pool, daemon=True).start()

    def _run_process_pool(self) -> None:
        """프로세스 풀을 사용하여 파일을 병렬 처리합니다."""
        num_workers = min(cpu_count(), len(self.file_paths))
        self._log('processing_started', format_args={'num_workers': num_workers})
        
        unity_version = self._current_unity_version
        enabled_types = self._current_enabled_types
        cancelled = False

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_path = {
                executor.submit(process_single_file, file_path, self.output_path, self.base_input_path, self.log_queue, self.completion_queue, unity_version, enabled_types): file_path 
                for file_path in self.file_paths
            }
            for future in concurrent.futures.as_completed(future_to_path):
                if self.cancel_token.is_cancelled:
                    cancelled = True
                    self._log('extraction_cancelled', "ERROR")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
        
        self.frame.after(0, self._on_extraction_complete)

    def _on_extraction_complete(self) -> None:
        self.frame.after(200, self._finalize_completion)

    def _finalize_completion(self) -> None:
        self._log("raw_text", format_args={'text': "========================================"})
        self._log('all_tasks_completed', "SUCCESS")
        self.is_running = False
        self.frame.after(0, lambda: self.view.toggle_controls(True))

