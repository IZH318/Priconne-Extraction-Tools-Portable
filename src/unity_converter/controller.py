from __future__ import annotations
import atexit
import logging
import os
import threading
from src.cancellation_token import CancellationToken
import concurrent.futures
from multiprocessing import Manager, cpu_count
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from src.languages import UNITY_CONVERTER_LANGUAGES as LANGUAGES
from src.breadcrumbs import add_breadcrumb
from src.queue_events import LogEvent, CompletionEvent
from .extractor import process_single_file, AssetProcessor
from .asset_browser import AssetBrowserWindow
from src.constants import UNITY_SUPPORTED_EXTENSIONS as SUPPORTED_EXTENSIONS
from src.constants import DEFAULT_UNITY_VERSION, UNITY_VERSION_PRESETS
from src.queue_polling import QueuePollingMixin
from src.log_history import LogHistoryMixin
from src.utils.file_list_mixin import FileListMixin
from .view import AssetExtractorView

class AssetExtractorController(QueuePollingMixin, LogHistoryMixin, FileListMixin):
    # --- Lifecycle & Initialization ---
    def __init__(self, frame: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None, app_temp_dir: str | None = None) -> None:
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
        from src.utils.base_path import get_application_base_path
        self.base_path = get_application_base_path()
        self.file_paths = []
        self.output_path = ""
        self.is_running = False
        self.processed_files_count = 0
        self.base_input_path = None
        self.log_events = []
        self.unity_version_var = tk.StringVar(value=DEFAULT_UNITY_VERSION)
        self.version_combo_var = tk.StringVar(value=DEFAULT_UNITY_VERSION)
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
        self.UNITY_VERSION_PRESETS = list(UNITY_VERSION_PRESETS)

        self.view = AssetExtractorView(frame, self)
        
        self.lang_var.trace_add('write', self._on_language_change)
        
        self.view.update_ui_text()
        self._log('program_started')
        self._init_queue_polling(self.frame)

    @property
    def manager(self) -> Any:
        """멀티프로세싱 Manager 객체를 반환하거나 필요시 초기화합니다."""
        if self._manager is None:
            self._manager = Manager()
            atexit.register(self.cleanup)
        return self._manager

    @property
    def log_queue(self) -> Any:
        """백그라운드 워커에서 로그를 전달받을 큐를 반환합니다."""
        if self._log_queue is None:
            self._log_queue = self.manager.Queue()
        return self._log_queue

    @property
    def completion_queue(self) -> Any:
        """파일 처리 완료 이벤트를 전달받을 큐를 반환합니다."""
        if self._completion_queue is None:
            self._completion_queue = self.manager.Queue()
        return self._completion_queue

    def cleanup(self) -> None:
        """폴링을 중지하고 멀티프로세싱 Manager 리소스를 정리합니다."""
        self._stop_polling()
        if self._manager is not None:
            try:
                self._manager.shutdown()
            except (OSError, EOFError):
                pass
            self._manager = None
            self._log_queue = None
            self._completion_queue = None
            try:
                atexit.unregister(self.cleanup)
            except Exception:
                pass

    def _get_enabled_types(self) -> set[str]:
        """체크박스에서 활성화된 에셋 타입 목록을 반환합니다.

        Returns:
            활성화된 에셋 타입들의 집합(set).
        """
        return {name for name, var in self.asset_type_vars.items() if var.get()}

    @property
    def asset_skip_types(self) -> set[str]:
        """추출에서 건너뛸 에셋 타입 목록을 반환합니다."""
        return AssetProcessor.SKIP_TYPES

    @property
    def asset_default_enabled(self) -> set[str]:
        """기본으로 활성화할 에셋 타입 목록을 반환합니다."""
        return AssetProcessor.DEFAULT_ENABLED

    def select_all_types(self) -> None:
        """모든 에셋 타입 체크박스를 선택 상태로 변경합니다."""
        for var in self.asset_type_vars.values():
            var.set(True)

    def deselect_all_types(self) -> None:
        """모든 에셋 타입 체크박스를 선택 해제 상태로 변경합니다."""
        for var in self.asset_type_vars.values():
            var.set(False)

    def on_version_selection_change(self, event: Any = None) -> None:
        """Unity 버전 콤보박스 선택이 변경되었을 때의 이벤트를 처리합니다.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
        """
        selected = self.version_combo_var.get()
        if selected in self.UNITY_VERSION_PRESETS:
            self.unity_version_var.set(selected)
            self.view.set_version_entry_state('disabled')
        else:
            self.view.set_version_entry_state('normal')
            if self.unity_version_var.get() in self.UNITY_VERSION_PRESETS:
                self.unity_version_var.set("")
            self.view.set_version_entry_state('normal', focus=True)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))

    def _on_language_change(self, *args: str) -> None:
        """언어 변경 이벤트를 처리하고 UI 텍스트 및 로그를 업데이트합니다.

        Args:
            *args: 가변 인자 리스트.
        """
        try:
            self.view.update_ui_text()
            self.redraw_all_logs()
        except tk.TclError:
            pass

    def _get_log_configs(self) -> list[tuple[list, tk.Text]]:
        """재렌더링 대상 (히스토리 리스트, Text 위젯) 쌍의 리스트를 반환합니다."""
        return [(self.log_events, self.view.log_text)]

    def _render_single_entry(self, entry: Any, index: int, history: list, widget: tk.Text) -> None:
        """단일 로그 이벤트를 Text 위젯에 포매팅하여 출력합니다."""
        self._render_log_event(entry, widget)

    def _add_log_event(self, message_key: str, level: str = 'INFO', format_args: dict[str, Any] | None = None, prefix: str | None = None) -> LogEvent:
        """로그 이벤트를 생성하여 반환합니다.

        Args:
            message_key: 다국어 딕셔너리의 로그 메시지 키.
            level: 로그 레벨 ('INFO', 'WARNING', 'ERROR', 'SUCCESS').
            format_args: 메시지 포매팅에 사용할 인자 딕셔너리.
            prefix: 로그 라인 앞에 붙일 접두사.

        Returns:
            생성된 LogEvent 객체.
        """
        return LogEvent(
            target=prefix or "",
            key=message_key,
            level=level,
            kwargs=format_args or {},
            un_timestamped=False,
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3]
        )

    def _render_log_event(self, event: LogEvent, widget=None) -> None:
        """단일 로그 이벤트를 UI Text 위젯에 포매팅하여 출력합니다.

        Args:
            event: 출력할 LogEvent 객체.
            widget: 로그를 출력할 Text 위젯 (기본값: self.view.log_text).
        """
        target_widget = widget or self.view.log_text
        timestamp = event.timestamp or datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = event.target
        message_key = event.key
        level = event.level
        format_args = event.kwargs
        
        lang = self.lang_var.get()
        message_template = LANGUAGES.get(lang, LANGUAGES.get('ko', {})).get(message_key, message_key)
        
        if message_key == 'raw_text':
            message = format_args.get('text', '') if format_args else ''
        else:
            message = message_template.format(**format_args) if format_args else message_template
        
        log_prefix = f"[{prefix}] " if prefix else ""
        full_message = f"[{timestamp}] {log_prefix}{message}\n"
        
        logging.info("[Unity Converter] %s%s", log_prefix, message)
        
        target_widget.config(state=tk.NORMAL)
        target_widget.insert(tk.END, full_message, level)
        target_widget.config(state=tk.DISABLED)

    def _log(self, message_key: str, level: str = 'INFO', format_args: dict[str, Any] | None = None, prefix: str | None = None) -> None:
        """로그 이벤트를 생성하고 히스토리에 추가한 뒤 UI에 출력합니다.

        Args:
            message_key: 다국어 딕셔너리의 로그 메시지 키.
            level: 로그 레벨 ('INFO', 'WARNING', 'ERROR', 'SUCCESS').
            format_args: 메시지 포매팅에 사용할 인자 딕셔너리.
            prefix: 로그 라인 앞에 붙일 접두사.
        """
        event = self._add_log_event(message_key, level, format_args, prefix)
        self.log_events.append(event)
        self._render_log_event(event)
        self.view.log_text.see(tk.END)

    def _on_poll_cycle(self) -> None:
        """멀티프로세싱 큐에서 로그 및 진행 상황 이벤트를 가져와 UI를 업데이트합니다."""
        log_batch = self._drain_queue(self.log_queue)

        completion_batch_size = 0
        is_extraction_done = False
        for event in self._drain_queue(self.completion_queue):
            if getattr(event, 'target', '') == '__EXTRACTION_DONE__':
                is_extraction_done = True
                continue
            completion_batch_size += 1
            if hasattr(event, 'result') and isinstance(event.result, int):
                self.total_extracted_assets += event.result

        if log_batch:
            self.view.log_text.config(state=tk.NORMAL)
            for log_item in log_batch:
                if isinstance(log_item, LogEvent):
                    if log_item.key == 'raw_text':
                        event = self._add_log_event('raw_text', log_item.level, {'text': log_item.kwargs.get('text', '')})
                    else:
                        if log_item.key == 'worker_process_error':
                            error_msg = str(log_item.kwargs.get('error', 'Unknown Error'))
                            if hasattr(self, 'failed_files'):
                                self.failed_files.append((log_item.target, error_msg))
                        event = self._add_log_event(log_item.key, log_item.level, log_item.kwargs, log_item.target)
                    self.log_events.append(event)
                    self._render_log_event(event)
            self.view.log_text.config(state=tk.DISABLED)
            self.view.log_text.see(tk.END)

        if completion_batch_size > 0:
            self.processed_files_count += completion_batch_size
            self.view.update_progress_bar()

        if is_extraction_done:
            self._on_extraction_complete()

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
        """드래그 앤 드롭으로 파일을 추가합니다.

        Args:
            event: Tkinter 드래그 앤 드롭 이벤트 객체.
        """
        if self.is_running:
            return
        paths = self._parse_dnd_paths(self.view.winfo_toplevel(), event.data)
            
        found_paths = self._collect_files_from_paths(paths, SUPPORTED_EXTENSIONS)
        # 폴더가 포함된 경우 base_input_path 설정
        for path in paths:
            if os.path.isdir(path):
                self.base_input_path = path if not self.base_input_path else self.base_input_path
                break
                
        if found_paths:
            self._add_files_to_list(found_paths)
        else:
            self._log('no_files_to_process', "WARNING")

    def _add_files_to_list(self, new_paths) -> None:
        """주어진 파일 경로들을 내부 리스트와 UI 리스트박스에 추가합니다.

        Args:
            new_paths: 추가할 파일 경로 리스트.
        """
        added = self._add_paths_to_file_list(new_paths, self.file_paths)
        added_count = len(added)
        
        if added_count > 0:
            self.file_paths.sort()
            self.view.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.view.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('added_files', format_args={'count': added_count, 'total': len(self.file_paths)})
            
    def remove_selected_files(self, event=None) -> None:
        """선택된 파일을 목록에서 제거합니다.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
        """
        if self.is_running:
            return
        selected_indices = self.view.file_listbox.curselection()
        count = self._remove_selected_from_file_list(self.file_paths, selected_indices)
        if count > 0:
            self.view.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.view.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('removed_selected_files', format_args={'count': count, 'total': len(self.file_paths)})
        
    def remove_all_files(self) -> None:
        """모든 파일을 목록에서 제거합니다."""
        if self.is_running:
            return
        if not self.file_paths:
            return
        count = self._clear_file_list(self.file_paths)
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
        unity_version = self.unity_version_var.get().strip() or DEFAULT_UNITY_VERSION
        AssetBrowserWindow(
            self.view.winfo_toplevel(),
            file_path,
            d,
            unity_version,
            self.app_temp_dir,
            generate_error_log=self._generate_error_log,
        )

    def select_output_dir(self) -> None:
        """출력 폴더 선택 대화상자를 엽니다."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        path = filedialog.askdirectory(title=d['output_folder'])
        if path:
            self.output_path = path
            self.view.output_entry.config(state=tk.NORMAL)
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
        add_breadcrumb("conv", "Started asset extraction", {"files": len(self.file_paths), "output": self.output_path})
        self.view.toggle_controls(False)
        self.processed_files_count = 0
        self.total_extracted_assets = 0
        self.failed_files: list[tuple[str, str]] = []
        self.view.progress_bar.config(maximum=len(self.file_paths))
        self.view.update_progress_bar()
        self._current_enabled_types = self._get_enabled_types()
        unity_version = self.unity_version_var.get().strip()
        if not unity_version: unity_version = DEFAULT_UNITY_VERSION
        self._current_unity_version = unity_version
        threading.Thread(target=self._run_process_pool, daemon=True).start()

    def _run_process_pool(self) -> None:
        """프로세스 풀을 사용하여 파일을 병렬 처리합니다."""
        num_workers = min(cpu_count(), len(self.file_paths))
        self.log_queue.put(LogEvent(target="", key='processing_started', level='INFO', kwargs={'num_workers': num_workers}))
        
        unity_version = self._current_unity_version
        enabled_types = self._current_enabled_types
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                future_to_path = {
                    executor.submit(process_single_file, file_path, self.output_path, self.base_input_path, self.log_queue, self.completion_queue, unity_version, enabled_types): file_path 
                    for file_path in self.file_paths
                }
                for future in concurrent.futures.as_completed(future_to_path):
                    if self.cancel_token.is_cancelled:
                        self.log_queue.put(LogEvent(target="", key='extraction_cancelled', level='ERROR'))
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
        except Exception as e:
            logging.error("ProcessPoolExecutor encountered an unexpected failure: %s", e)
        finally:
            self.completion_queue.put(CompletionEvent(target='__EXTRACTION_DONE__'))

    def _on_extraction_complete(self) -> None:
        """추출 작업이 모두 완료되었을 때 호출되는 콜백입니다."""
        self.frame.after(200, self._finalize_completion)

    def _finalize_completion(self) -> None:
        """완료 상태를 정리하고 UI 컨트롤을 다시 활성화합니다."""
        if hasattr(self, 'failed_files') and len(self.failed_files) > 0:
            self._generate_error_log(self.failed_files)
            from tkinter import messagebox
            d = self.get_lang_dict()
            title = d.get('msgbox_error_log_saved_title', 'Error Log Created / 오류 로그 생성 안내')
            text = d.get('msgbox_error_log_saved_msg', 'An error log has been created in the logs folder. / 작업 중 오류가 발생하여 logs 폴더에 오류 로그가 생성되었습니다.')
            messagebox.showwarning(title, text, parent=self.view)

        self._log("raw_text", format_args={'text': "========================================"})
        if hasattr(self, 'total_extracted_assets') and self.total_extracted_assets > 0:
            self._log("total_extracted_assets", format_args={'count': self.total_extracted_assets})
        if not self.cancel_token.is_cancelled:
            self._log('all_tasks_completed', "SUCCESS")
        self.is_running = False
        self.frame.after(0, lambda: self.view.toggle_controls(True))

    def _generate_error_log(self, failed_files: list[tuple[str, str]], context: str = "Asset Extraction") -> None:
        import platform, multiprocessing, sys, os
        from datetime import datetime
        from pathlib import Path
        from src.constants import SEPARATOR_LONG, APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER
        from src.utils.base_path import get_application_base_path
        
        try:
            if hasattr(self, 'base_path') and self.base_path:
                exec_path = str(self.base_path)
            else:
                exec_path = str(get_application_base_path())
            log_dir = Path(exec_path) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
            now = datetime.now()
            log_filename = log_dir / f"UnityConverterLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"
            
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(f"{SEPARATOR_LONG}\n")
                f.write(f"[SESSION] Unity Converter Task Log Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                f.write(f"{SEPARATOR_LONG}\n")
                f.write(f"[TOOL]    App Version:     {APP_VERSION} ({APP_LAST_UPDATE})\n")
                f.write(f"[TOOL]    Developer:       {APP_DEVELOPER}\n")
                f.write(f"[ENGINE]  Python Version:  {platform.python_version()}\n")
                f.write(f"[SYSTEM]  OS Version:      {platform.platform()}\n")
                f.write(f"[SYSTEM]  Processor Count: {multiprocessing.cpu_count()} Cores\n")
                f.write(f"[PATH]    Exec Path:       {exec_path}\n")
                f.write(f"[REPORT]  Context:         {context}\n")
                f.write(f"[REPORT]  Base Input:      {self.base_input_path if self.base_input_path else 'Files'}\n")
                f.write(f"[REPORT]  Output Path:     {self.output_path if self.output_path else 'Temp/Preview'}\n")
                f.write(f"[REPORT]  Total Failed:    {len(failed_files)}\n")
                f.write(f"{SEPARATOR_LONG}\n\n")

                for idx, (path, reason) in enumerate(failed_files, 1):
                    f.write(f"[ERROR ITEM #{idx}]\n")
                    f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                    f.write(f"Context   : {context}\n")
                    f.write(f"File      : {path}\n")
                    clean_reason = (reason or "").strip()
                    if "\n" in clean_reason:
                        f.write(f"Reason    :\n{clean_reason}\n")
                    else:
                        f.write(f"Reason    : {clean_reason}\n")
                    f.write(f"{SEPARATOR_LONG}\n\n")
        except Exception as e:
            import logging
            logging.error(f"Failed to write UnityConverterLog: {e}")
