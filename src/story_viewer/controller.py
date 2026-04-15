from __future__ import annotations
import os
import logging
import shutil
import threading
import queue
import json
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.languages import STORY_VIEWER_LANGUAGES as LANGUAGES
from .windows_search import SearchWindow
from .windows_export import ExportWindow
from .logic import StoryDataLoader, StoryFormatter
from . import db_helper
from src.constants import DB_DOWNLOAD_BASE_URL
from src.queue_events import ActionEvent
from .view import StoryViewerView

# SQLite 파일 식별을 위한 매직 바이트 (16바이트 헤더)
_SQLITE_MAGIC = b'SQLite format 3\x00'


def _load_db_config() -> dict[str, dict[str, str]]:
    """db_config.json에서 서버별 DB 테이블/컬럼 매핑 정보를 로드합니다.

    외부 JSON 설정 파일로 분리하여 DB 스키마 변경 시
    코드 수정 없이 설정 파일만 업데이트하면 됩니다.

    Returns:
        dict: 서버 키('JP', 'KR')별 DB 정보 딕셔너리.
    """
    config_path = os.path.join(os.path.dirname(__file__), 'db_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning("Failed to load db_config.json: %s. Using empty fallback.", e)
        return {}

class StoryViewerController:
    def __init__(self, app_wrapper: ttk.Frame, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        """StoryViewerController를 초기화합니다.

        Args:
            app_wrapper: gui.py의 ttk.Frame 래퍼 (View의 부모 위젯).
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            app_lang_var: 앱 전역 언어 StringVar.
            about_info: About 대화상자에 표시될 정보 딕셔너리.

        Note:
            다른 Controller(Renamer, AV, ResourceRemover)는 master 하나만 받지만,
            StoryViewer와 UnityConverter는 대화상자 위치 지정을 위해
            별도의 master(최상위 윈도우)가 필요하여 2개의 위젯 인자를 받습니다.
        """
        self.master = master
        self.app_wrapper = app_wrapper
        self.about_info = about_info or {}
        
        self.all_files = {}
        self.search_data = {}
        self.file_titles = {}
        self.display_name_to_filename = {}
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.is_loading = False
        self.task_queue = queue.Queue()

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.display_mode_var = tk.StringVar(value="original")
        self.view_mode_var = tk.StringVar(value="simple")

        self.db_status = {}
        self.db_check_done = False
        self.db_warning_shown = False

        # 서버별 DB 테이블/컬럼 해시 매핑 정보. (외부 db_config.json에서 로드)
        self.server_db_info = _load_db_config()

        self.view = StoryViewerView(app_wrapper, self)
        
        self.lang_var.trace_add('write', self._on_language_change_event)

        self.view.after(100, self._process_queue)
        self.view.update_ui_text()
        self.view.update_status_bar('status_bar_initial')

    def get_lang_dict(self) -> dict:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

    def _on_language_change_event(self, *args) -> None:
        try:
            self.view.update_ui_text()
            self.on_display_mode_change(force_update=True)
            self.on_view_mode_change(force_update=True)
        except tk.TclError:
            pass

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        title = lang_dict['about_header']
        info_lines = []
        for key, value in self.about_info.items():
            label_key = f'about_label_{key}'
            label_text = lang_dict.get(label_key, key.capitalize())
            info_lines.append(f"{label_text}: {value}")
        messagebox.showinfo(title, "\n".join(info_lines), parent=self.master)

    def _process_queue(self) -> None:
        try:
            while not self.task_queue.empty():
                task_event = self.task_queue.get_nowait()
                if isinstance(task_event, ActionEvent):
                    task_event.action()
        except queue.Empty:
            pass
        finally:
            self.view.after(100, self._process_queue)

    def _clear_workspace(self) -> None:
        """작업 공간을 초기화하여 모든 로드된 데이터와 UI 상태를 초기 상태로 되돌립니다."""
        self.view.update_story_text([])
        self.all_files.clear()
        self.search_data.clear()
        self.view.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.view.search_button.config(state="disabled")
        self.view.btn_export.config(state="disabled")
        self.db_status.clear()
        self.db_check_done = False
        self.db_warning_shown = False

    def _start_loading_task(self, paths=None, folder_path=None) -> None:
        """스토리 데이터 파일 로딩 작업을 백그라운드 스레드로 시작합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return

        self._clear_workspace()
        self.is_loading = True
        self.view.update_status_bar('status_bar_loading_start')
        self.view.btn_open_file.config(state="disabled")
        self.view.btn_open_folder.config(state="disabled")
        
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path))
        thread.daemon = True
        thread.start()

    def open_files(self) -> None:
        """파일 선택 대화상자를 열고 스토리 데이터 파일을 로드합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[(lang_dict.get('filetype_json', "JSON Files"), "*.json"), (lang_dict.get('filetype_all', "All Files"), "*.*")]
        )
        if file_paths:
            self._start_loading_task(paths=file_paths)

    def open_folder(self) -> None:
        """폴더 선택 대화상자를 열고 내부 스토리 데이터 파일을 로드합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        folder_path = filedialog.askdirectory(title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files"))
        if folder_path:
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths, folder_path) -> None:
        import re
        temp_all_files, invalid_files = {}, []
        file_candidates = {}
        pattern = re.compile(r'^storydata_\d{7}\.json$')

        if paths:
            for path in paths:
                filename = os.path.basename(path)
                if pattern.match(filename):
                    if filename not in file_candidates:
                        file_candidates[filename] = []
                    file_candidates[filename].append(path)

        if folder_path:
            for dirpath, _, filenames in os.walk(folder_path):
                for filename in filenames:
                    if pattern.match(filename):
                        full_path = os.path.join(dirpath, filename)
                        if filename not in file_candidates:
                            file_candidates[filename] = []
                        file_candidates[filename].append(full_path)
        
        file_list_to_process = []
        for filename, path_list in file_candidates.items():
            if len(path_list) > 1:
                try:
                    winner_path = max(path_list, key=os.path.getsize)
                    file_list_to_process.append(winner_path)
                except FileNotFoundError:
                    pass 
            elif path_list:
                file_list_to_process.append(path_list[0])
        
        file_list_to_process.sort()
        total_files = len(file_list_to_process)
        unique_char_names, unique_bgms, unique_bgs, temp_file_titles = set(), set(), set(), {}

        for i, path in enumerate(file_list_to_process):
            def _update_status(idx=i, total=total_files):
                self.view.update_status_bar('status_bar_analyzing', i=idx+1, t=total)
            self.task_queue.put(ActionEvent(action=_update_status))
            is_valid, data, error_reason = StoryDataLoader.is_valid_storydata(path)
            
            if is_valid:
                filename = os.path.basename(path)
                temp_all_files[filename] = path
                title = data.get('0', {}).get('title', '').strip()
                temp_file_titles[filename] = title if title else filename
                for scene in data.values():
                    if 'print' in scene and 'name' in scene['print'] and (name := str(scene['print']['name']).strip()): unique_char_names.add(name)
                    if 'bgm' in scene and (bgm_name := StoryDataLoader.extract_asset_name(scene['bgm'])): unique_bgms.add(bgm_name)
                    if 'background' in scene and (bg_name := StoryDataLoader.extract_asset_name(scene['background'])): unique_bgs.add(bg_name)
            else:
                invalid_files.append((path, error_reason))
        
        if not temp_all_files:
            self.task_queue.put(ActionEvent(action=lambda: self._finish_loading(None, invalid_files)))
            return

        temp_search_data = {
            'filenames': sorted(list(temp_all_files.keys())), 
            'character_names': sorted(list(unique_char_names)), 
            'bgms': sorted(list(unique_bgms)), 
            'backgrounds': sorted(list(unique_bgs))
        }
        results = {"all_files": temp_all_files, "titles": temp_file_titles, "search_data": temp_search_data}
        self.task_queue.put(ActionEvent(action=lambda: self._finish_loading(results, invalid_files)))

    def _finish_loading(self, results, invalid_files) -> None:
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
            
        self.is_loading = False
        self.view.btn_open_file.config(state="normal")
        self.view.btn_open_folder.config(state="normal")
        if not results:
            self.view.update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'], parent=self.view)
        else:
            self.all_files, self.file_titles, self.search_data = results['all_files'], results['titles'], results['search_data']
            self.loaded_filenames = sorted(list(self.all_files.keys()))
            self.view.update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))
            self.view.search_button.config(state="normal")
            self.view.btn_export.config(state="normal")
            self.update_file_list(list(self.all_files.keys()))
        
        if invalid_files:
            msg = lang_dict['msgbox_load_fail_msg'].format(count=len(invalid_files))
            if messagebox.askyesno(lang_dict['msgbox_load_fail_title'], msg, parent=self.view):
                # 첫 번째 로드된 파일의 디렉터리에 로그 파일 생성 (CWD 의존 방지)
                first_file_dir = os.path.dirname(invalid_files[0][0]) if invalid_files else os.getcwd()
                log_filename = os.path.join(first_file_dir, "invalid_storydata_log.txt")
                try:
                    with open(log_filename, 'w', encoding='utf-8') as f:
                        f.write(lang_dict['log_header'].format(timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                        f.write(lang_dict['log_total_failed'].format(count=len(invalid_files)))
                        f.write("-" * 50 + "\n\n")
                        for path, reason in invalid_files:
                            f.write(f"{lang_dict['log_file_label']}: {path}\n")
                            f.write(f"{lang_dict['log_reason_label']}: {reason}\n")
                            f.write("-" * 30 + "\n")
                    messagebox.showinfo(lang_dict['msgbox_log_saved_title'], lang_dict['msgbox_log_saved_msg'].format(filename=log_filename), parent=self.view)
                except OSError as e:
                    messagebox.showerror(lang_dict['msgbox_log_save_error_title'], lang_dict['msgbox_log_save_error_msg'].format(e=e), parent=self.view)

    def _check_and_cache_db_status(self) -> bool:
        if self.db_check_done:
            return False
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
            
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        missing_db_files = []
        
        for server, info in self.server_db_info.items():
            db_path = os.path.join(script_dir, info['db_path'])
            exists = os.path.exists(db_path)
            self.db_status[server] = exists
            if not exists:
                missing_db_files.append(info['db_path'])

        if missing_db_files and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_files)
            is_online = False
            try:
                import urllib.request
                urllib.request.urlopen("https://github.com", timeout=2)
                is_online = True
            except OSError:
                pass
                
            if is_online:
                if messagebox.askyesno(
                    lang_dict.get('db_download_prompt_title', 'Download DB'), 
                    lang_dict.get('db_download_prompt_msg', 'Missing:\n{paths}').format(paths=paths_str), 
                    parent=self.master
                ):
                    self._start_db_download(missing_db_files, script_dir)
                    return True
                else:
                    self._show_offline_warning(paths_str, lang_dict, reason='cancel')
            else:
                self._show_offline_warning(paths_str, lang_dict, reason='offline')

        self.db_check_done = True
        return False
        
    def _show_offline_warning(self, paths_str, lang_dict, reason='offline') -> None:
        if reason == 'cancel':
            extra_msg = lang_dict.get('db_download_cancel_msg', '')
        else:
            extra_msg = lang_dict.get('db_download_offline_msg', '')
            
        messagebox.showwarning(
            lang_dict.get('db_not_found_title', 'DB Not Found'), 
            lang_dict.get('db_not_found_msg', '{paths}').format(paths=paths_str) + "\n\n" + extra_msg,
            parent=self.master
        )
        self.db_warning_shown = True

    def _start_db_download(self, files_to_download, dest_dir) -> None:
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        self.view.search_button.config(state="disabled")
        self.view.btn_export.config(state="disabled")
        
        from tkinter import ttk
        top = tk.Toplevel(self.master)
        top.title(lang_dict.get('db_download_prompt_title', 'Downloading DB...'))
        top.geometry("300x100")
        top.transient(self.master)
        top.grab_set()
        lbl = ttk.Label(top, text="Downloading...")
        lbl.pack(pady=10)
        pb = ttk.Progressbar(top, mode='indeterminate')
        pb.pack(fill=tk.X, padx=20)
        pb.start(10)
        
        def _download_thread():
            import urllib.request
            base_url = DB_DOWNLOAD_BASE_URL
            try:
                for f in files_to_download:
                    url = base_url + f
                    dest_path = os.path.join(dest_dir, f)
                    with urllib.request.urlopen(url) as response:
                        with open(dest_path, 'wb') as out_file:
                            shutil.copyfileobj(response, out_file)
                    # 다운로드된 파일이 유효한 SQLite DB인지 무결성 검증
                    with open(dest_path, 'rb') as db_file:
                        header = db_file.read(16)
                    if header != _SQLITE_MAGIC:
                        os.remove(dest_path)
                        raise RuntimeError(f"Downloaded file '{f}' is not a valid SQLite database (header mismatch).")
                self.task_queue.put(ActionEvent(action=lambda: self._on_download_success(top)))
            except (OSError, RuntimeError) as e:
                self.task_queue.put(ActionEvent(action=lambda err=e: self._on_download_error(top, err)))
                
        t = threading.Thread(target=_download_thread, daemon=True)
        t.start()
        
    def _on_download_success(self, top) -> None:
        top.destroy()
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        messagebox.showinfo(lang_dict.get('db_download_prompt_title', 'Complete'), lang_dict.get('db_download_success_msg', 'Success'), parent=self.master)
        self.db_warning_shown = False
        self.db_check_done = False
        self._check_and_cache_db_status()
        self.view.search_button.config(state="normal" if self.all_files else "disabled")
        self.view.btn_export.config(state="normal" if self.all_files else "disabled")
        
    def _on_download_error(self, top, err) -> None:
        top.destroy()
        messagebox.showerror(LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko']).get('db_download_error_title', 'Download Error'), str(err), parent=self.master)
        self.db_check_done = True
        self.view.search_button.config(state="normal" if self.all_files else "disabled")
        self.view.btn_export.config(state="normal" if self.all_files else "disabled")

    def open_search_window(self) -> None:
        """DB 검색 창을 엽니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_search_before_load_title'], lang_dict['msgbox_search_before_load_msg'], parent=self.view)
            return
        is_downloading = self._check_and_cache_db_status()
        if is_downloading:
            return
        
        # pass self (Controller) instead of App ttk.Frame
        SearchWindow(app=self, all_files_dict=self.all_files, search_callback=self.update_file_list, search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)

    def open_export_window(self) -> None:
        """DB 내보내기 창을 엽니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_no_export_files_title'], lang_dict['msgbox_no_export_files_msg'], parent=self.view)
            return
        is_downloading = self._check_and_cache_db_status()
        if is_downloading:
            return
        ExportWindow(app=self, all_files_dict=self.all_files, search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)

    def update_file_list(self, filenames) -> None:
        """파일 목록 뷰를 업데이트합니다."""
        self.view.update_story_text([])
        self.current_file_path = None
        self.current_filenames_in_list = sorted(filenames)
        self.display_name_to_filename.clear()
        self.view.file_listbox.delete(0, tk.END)
        total, chunk_size = len(self.current_filenames_in_list), 200
        
        def _populate_list(index=0):
            if index >= total:
                self.view.update_status_bar('status_bar_list_updated', count=total)
                if total > 0:
                    self.view.file_listbox.selection_set(0)
                    self.view.file_listbox.event_generate("<<ListboxSelect>>")
                else:
                    self.view.update_status_bar('status_bar_ready')
                return
            self.view.update_status_bar('status_bar_list_updating', i=index + 1, t=total)
            end_index = min(index + chunk_size, total)
            display_mode = self.display_mode_var.get()
            display_chunk = []
            for i in range(index, end_index):
                filename = self.current_filenames_in_list[i]
                display_name = filename
                if display_mode == 'title':
                    if title := self.file_titles.get(filename, filename):
                        display_name = f"{title}"
                display_chunk.append(display_name)
                self.display_name_to_filename[display_name] = filename
            self.view.file_listbox.insert(tk.END, *display_chunk)
            self.view.after(1, lambda: _populate_list(end_index))
        _populate_list()

    def on_file_select(self, event=None) -> None:
        """파일 목록에서 항목을 선택했을 때 스토리 내용을 표시합니다."""
        if not self.view.file_listbox.curselection():
            return
        try:
            display_name = self.view.file_listbox.get(self.view.file_listbox.curselection()[0])
        except tk.TclError:
            return
        
        if filename := self.display_name_to_filename.get(display_name):
            self.current_file_path = self.all_files.get(filename)
            if self.current_file_path:
                is_valid, data, _ = StoryDataLoader.is_valid_storydata(self.current_file_path)
                if is_valid:
                    formatter = StoryFormatter()
                    self.view.update_story_text(formatter.format_story_data(data, self.view_mode_var.get()))
                    self.view.update_status_bar('status_bar_displaying', filename=filename)
                else:
                    self.view.update_status_bar('status_bar_cache_error', filename=filename)

    def on_display_mode_change(self, event=None, force_update=False) -> None:
        if not force_update and self.is_loading:
            return
        try:
            idx = self.view.display_mode_combo.current()
            if idx == 0:
                self.display_mode_var.set("original")
            elif idx == 1:
                self.display_mode_var.set("title")
        except tk.TclError:
            pass
        self.update_file_list(self.current_filenames_in_list)

    def on_view_mode_change(self, force_update=False) -> None:
        if not force_update and self.is_loading:
            return
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            is_valid, data, _ = StoryDataLoader.is_valid_storydata(self.current_file_path)
            if is_valid:
                formatter = StoryFormatter()
                self.view.update_story_text(formatter.format_story_data(data, self.view_mode_var.get()))

    # Export functionality helper methods
    def _save_list_to_file(self, data_list, filename_suffix, output_folder, header_text) -> tuple[bool, Exception | None]:
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    for item in data_list:
                        f.write(f"{item}\n")
                else:
                    f.write(f"(No data found for {filename_suffix})\n")
            return True, None
        except OSError as e:
            return False, e

    def _export_master_thread(self, selected_options, output_folder) -> None:
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []

        if selected_options['story_data']:
            story_data_scope = selected_options['story_data_scope']
            filenames_to_export = []
            if story_data_scope == 'current_list':
                filenames_to_export = self.current_filenames_in_list
            elif story_data_scope == 'all_loaded':
                filenames_to_export = self.loaded_filenames
            
            if not filenames_to_export:
                export_results['story_data'] = {'success': 0, 'failed': 0, 'details': ["No story data files selected for export."]}
            else:
                type_name = lang_dict.get('export_type_story_data', 'Story Data')
                success_count = 0
                fail_count = 0
                current_failed_details = []

                for i, filename in enumerate(filenames_to_export):
                    current_success = success_count
                    current_fail = fail_count
                    def _update_export_status(tn=type_name, s=current_success, f=current_fail, idx=i, tf=len(filenames_to_export)):
                        self.view.update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=idx+1, t=tf)
                    self.task_queue.put(ActionEvent(action=_update_export_status))
                    filepath = self.all_files.get(filename)
                    if not filepath:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (File Not Found)")
                        continue
                    
                    is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
                    if not is_valid:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Parse Error)")
                        continue
                        
                    output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".txt")
                    try:
                        formatter = StoryFormatter()
                        text_to_write = "".join([text for text, _ in formatter.format_story_data(data, self.view_mode_var.get())])
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(text_to_write)
                        success_count += 1
                    except (OSError, json.JSONDecodeError) as e:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Error: {e})")
                
                export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        other_export_types = [
            {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': lambda: sorted(list(self.loaded_filenames)), 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
            {'type': 'character_names', 'name_key': 'export_type_character_names', 'data_func': lambda: sorted(self.search_data.get('character_names', [])), 'file_suffix': 'character_names', 'header_key': 'export_type_character_names'},
            {'type': 'bgm_names', 'name_key': 'export_type_bgm_names', 'data_func': lambda: sorted(self.search_data.get('bgms', [])), 'file_suffix': 'bgm_names', 'header_key': 'export_type_bgm_names'},
            {'type': 'background_names', 'name_key': 'export_type_background_names', 'data_func': lambda: sorted(self.search_data.get('backgrounds', [])), 'file_suffix': 'background_names', 'header_key': 'export_type_background_names'},
        ]
        
        for task in other_export_types:
            task_type = task['type']
            if not selected_options[task_type]:
                continue

            type_name = lang_dict.get(task['name_key'], task_type)
            success_count = 0
            fail_count = 0
            current_failed_details = []

            self.task_queue.put(ActionEvent(action=lambda tn=type_name: self.view.update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0)))
            try:
                data_list = task['data_func']()
                if not data_list:
                    export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                    continue

                success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                if success:
                    success_count = 1
                else:
                    fail_count = 1
                    current_failed_details.append(f"{type_name} (Error: {error})")
            except (sqlite3.Error, OSError) as e:
                fail_count += 1
                current_failed_details.append(f"{type_name} (Unexpected Error: {e})")

            export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
            total_exported_count += success_count
            total_failed_count += fail_count
            all_failed_details.extend(current_failed_details)

        if selected_options['event_list_master']:
            def get_event_list(server_key):
                db_info = self.server_db_info.get(server_key)
                if not db_info or not self.db_status.get(server_key):
                    return []
                try:
                    return sorted(db_helper.fetch_event_names(db_info))
                except sqlite3.Error as e:
                    return []

            event_list_tasks = [
                {'type': 'event_list_jp', 'name_key': 'export_type_event_list_jp', 'data_func': lambda: get_event_list('JP'), 'file_suffix': 'event_list_jp', 'header_key': 'export_type_event_list_jp'},
                {'type': 'event_list_kr', 'name_key': 'export_type_event_list_kr', 'data_func': lambda: get_event_list('KR'), 'file_suffix': 'event_list_kr', 'header_key': 'export_type_event_list_kr'}
            ]
            for task in event_list_tasks:
                task_type = task['type']
                if not selected_options[task_type]:
                    continue
                type_name = lang_dict.get(task['name_key'], task_type)
                success_count = 0
                fail_count = 0
                current_failed_details = []

                self.task_queue.put(ActionEvent(action=lambda tn=type_name: self.view.update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0)))
                try:
                    data_list = task['data_func']()
                    if not data_list:
                        export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                        continue

                    success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                    if success:
                        success_count = 1
                    else:
                        fail_count = 1
                        current_failed_details.append(f"{type_name} (Error: {error})")
                except (sqlite3.Error, OSError) as e:
                    fail_count += 1
                    current_failed_details.append(f"{type_name} (Unexpected Error: {e})")
                
                export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        self.task_queue.put(ActionEvent(action=lambda: self._finish_export(total_exported_count, total_failed_count, all_failed_details)))

    def _finish_export(self, exported_count, failed_count, failed_list) -> None:
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

        if exported_count > 0:
            messagebox.showinfo(lang_dict['msgbox_export_complete_title'], lang_dict['msgbox_export_complete_msg'].format(exported_count=exported_count), parent=self.master)
            self.view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        else:
            messagebox.showwarning(lang_dict['msgbox_export_failed_title'], lang_dict['msgbox_export_failed_msg'].format(failed_count=failed_count), parent=self.master)
            self.view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        
        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(lang_dict['msgbox_export_error_details_title'], lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg), parent=self.master)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다."""
        pass
