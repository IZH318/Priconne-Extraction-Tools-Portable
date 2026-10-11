from __future__ import annotations
import os
import logging
import threading
import queue
import json
import re
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.languages import STORY_VIEWER_LANGUAGES as LANGUAGES
from src.breadcrumbs import add_breadcrumb
from src.utils.about_dialog import show_about_dialog
from .windows_search import SearchWindow
from .windows_export import ExportWindow
from .logic import StoryDataLoader, StoryFormatter
from . import db_helper
from src.queue_events import ActionEvent
from src.queue_polling import QueuePollingMixin
from .db_manager import StoryDBManager
from .export_handler import StoryExportHandler
from .view import StoryViewerView




def _load_db_config() -> dict[str, dict[str, str]]:
    """db_config.json에서 서버별 DB 테이블/컬럼 매핑 정보를 로드합니다.

    계층형 구조(common, servers, tables)를 기존 호환 딕셔너리로 자동 정규화합니다.

    Returns:
        dict: 서버 키('JP', 'KR') 및 'Common'을 키로 갖는 정규화된 DB 정보 딕셔너리.
    """
    config_path = os.path.join(os.path.dirname(__file__), 'db_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning("Failed to load db_config.json: %s. Using empty fallback.", e)
        return {}

    # 신규 계층 구조(common, servers, tables)인 경우 정규화
    if "servers" in raw_cfg and "tables" in raw_cfg:
        common = raw_cfg.get("common", raw_cfg.get("Common", {}))
        tables = raw_cfg.get("tables", {})
        
        flat_tables = {}
        if "event_story" in tables:
            ev = tables["event_story"]
            flat_tables["event_list_table"] = ev.get("list_table", "")
            flat_tables["event_name_col_list"] = ev.get("name_col", "")
            flat_tables["event_details_table"] = ev.get("details_table", "")
            flat_tables["event_info_col_details"] = ev.get("info_col", "")
            flat_tables["event_id_col_details"] = ev.get("id_col", "")
        if "birthday" in tables:
            bd = tables["birthday"]
            flat_tables["birthday_table"] = bd.get("table", "")
            flat_tables["birthday_name_col"] = bd.get("name_col", "")
            flat_tables["birthday_adv_id_col"] = bd.get("id_col", "")
        if "quest" in tables:
            q = tables["quest"]
            flat_tables["quest_table"] = q.get("table", "")
            flat_tables["quest_name_col"] = q.get("name_col", "")
            flat_tables["quest_wavestart_col"] = q.get("wavestart_col", "")
            flat_tables["quest_waveend_col"] = q.get("waveend_col", "")
        merged = {"Common": common}
        for s_key, s_info in raw_cfg["servers"].items():
            s_dict = dict(s_info)
            s_dict.update(flat_tables)
            s_baseline_dbs = s_info.get("baseline_dbs", {})
            for key, entry in tables.items():
                if key in ("event_story", "birthday", "quest"):
                    continue
                if isinstance(entry, dict) and "table" in entry:
                    req_base = entry.get("baseline")
                    if req_base and req_base not in s_baseline_dbs:
                        s_dict[f"{key}_table"] = ""
                        s_dict[f"{key}_id_col"] = ""
                        s_dict[f"{key}_title_col"] = ""
                        s_dict[f"{key}_sub_title_col"] = ""
                        s_dict[f"{key}_baseline"] = ""
                    else:
                        s_dict[f"{key}_table"] = entry["table"]
                        s_dict[f"{key}_id_col"] = entry.get("id_col", "story_id")
                        s_dict[f"{key}_title_col"] = entry.get("title_col", "title")
                        s_dict[f"{key}_sub_title_col"] = entry.get("sub_title_col", "sub_title")
                        s_dict[f"{key}_baseline"] = entry.get("baseline", "default")
            merged[s_key] = s_dict
        return merged

    return raw_cfg

class StoryViewerController(QueuePollingMixin):
    def __init__(self, app_wrapper: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
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
        self.raw_file_titles = {}
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
        self.server_var = tk.StringVar(value='JP')
        
        self.db_analyzed = False
        self.empty_title_files = set()

        # 서버별 DB 테이블/컬럼 해시 매핑 정보. (외부 db_config.json에서 로드)
        self.server_db_info = _load_db_config()

        self.view = StoryViewerView(app_wrapper, self)

        self._db_manager = StoryDBManager(
            master=self.master,
            server_db_info=self.server_db_info,
            get_lang_dict=self.get_lang_dict,
            task_queue=self.task_queue,
            view=self.view,
            get_all_files=lambda: self.all_files,
        )
        self._export_handler = StoryExportHandler(
            get_lang_dict=self.get_lang_dict,
            task_queue=self.task_queue,
            master=self.master,
            view_mode_var=self.view_mode_var,
            get_current_filenames=lambda: self.current_filenames_in_list,
            get_loaded_filenames=lambda: self.loaded_filenames,
            get_all_files=lambda: self.all_files,
            get_search_data=lambda: self.search_data,
            get_server_db_info=lambda: self.server_db_info,
            get_db_manager=lambda: self._db_manager,
            view=self.view,
        )
        
        self.lang_var.trace_add('write', self._on_language_change)

        self._init_queue_polling(self.view)
        self.view.update_ui_text()
        self.view.update_status_bar('status_bar_initial')

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트를 처리하고 UI 텍스트 및 뷰 모드를 업데이트합니다.

        Args:
            *args: 가변 인자 리스트.
        """
        try:
            self.view.update_ui_text()
            self.on_display_mode_change(force_update=True)
            self.on_view_mode_change(force_update=True)
        except tk.TclError:
            pass

    def start_db_analysis(self) -> None:
        """사용자가 DB 분석 시작 버튼을 눌렀을 때 호출되어 DB 체크 및 UI 활성화를 수행합니다."""
        self.view.btn_db_analyze.config(state=tk.DISABLED)
        self.view.update_status_bar('db_checking_msg')
        
        def _on_ready():
            self.task_queue.put(ActionEvent(action=self._on_db_analyzed))
            
        self._db_manager.check_and_cache_db_status(on_ready=_on_ready)

    def _on_db_analyzed(self) -> None:
        """DB 분석이 완료된 후 관련 UI 요소들을 활성화합니다."""
        self.db_analyzed = True
        self.view.btn_db_analyze.config(state=tk.NORMAL)
        # DB 분석 후 요소 활성화
        self.view.display_mode_combo.config(state="readonly")
        self.view.search_button.config(state=tk.NORMAL if self.all_files else tk.DISABLED)
        self.view.btn_export.config(state=tk.NORMAL if self.all_files else tk.DISABLED)
        for child in self.view.server_frame.winfo_children():
            child.config(state=tk.NORMAL)
            
        # 기존에 로드된 파일들이 있다면 현재 서버 기준으로 DB 타이틀 조회
        if self.all_files:
            self.on_server_change()
        
        self.view.update_status_bar('status_bar_initial')

    def on_server_change(self) -> None:
        """게임 서버 라디오 버튼 변경 시 호출되어 DB에서 타이틀을 조회하여 갱신합니다."""
        if not self.db_analyzed or not self.all_files:
            return
            
        server = self.server_var.get()
        db_info = self.server_db_info.get(server, {})
        
        # 1. adv_id 목록 수집
        filename_to_adv_id = {}
        for filename in self.all_files:
            match = re.match(r'^storydata_(\d+)\.json$', filename)
            if match:
                filename_to_adv_id[filename] = match.group(1)
        
        # 2. 일괄 조회 (우선순위: story_detail -> dear_story_detail -> tower_story_detail -> birthday -> quest)
        fetched_titles = {}
        if filename_to_adv_id:
            adv_ids = list(filename_to_adv_id.values())
            if 'story_detail_table' in db_info:
                fetched_titles.update(db_helper.fetch_story_detail_titles_batch(db_info, adv_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'dear_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_dear_story_detail_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'tower_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_tower_story_detail_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'alchemy_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_alchemy_story_detail_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'birthday_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_birthday_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'quest_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_quest_titles_batch(db_info, remaining_ids))
            
        # 3. 타이틀 갱신: DB 결과 우선, 미존재 시 JSON 원본 타이틀(또는 파일명) 유지
        for filename in self.all_files:
            adv_id = filename_to_adv_id.get(filename)
            title = fetched_titles.get(adv_id) if adv_id else None
            
            if title:
                self.file_titles[filename] = title
            else:
                self.file_titles[filename] = self.raw_file_titles.get(filename, filename)
                
        target_files = self.current_filenames_in_list or list(self.all_files.keys())
        self.update_file_list(target_files)

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = self.get_lang_dict()
        show_about_dialog(lang_dict, self.about_info, self.master)

    def _on_poll_cycle(self) -> None:
        """태스크 큐에 쌓인 액션 이벤트들을 메인 스레드에서 처리합니다."""
        for event in self._drain_queue(self.task_queue):
            if isinstance(event, ActionEvent):
                event.action()

    def _clear_workspace(self) -> None:
        """작업 공간을 초기화하여 모든 로드된 데이터와 UI 상태를 초기 상태로 되돌립니다."""
        self.view.update_story_text([])
        self.all_files.clear()
        self.search_data.clear()
        self.view.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.raw_file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.view.btn_db_analyze.config(state=tk.DISABLED)
        self.view.search_button.config(state=tk.DISABLED)
        self.view.btn_export.config(state=tk.DISABLED)
        self.view.display_mode_combo.config(state=tk.DISABLED)
        self.view.jp_radio.config(state=tk.DISABLED)
        self.view.kr_radio.config(state=tk.DISABLED)
        
        self.db_analyzed = False
        
        self._db_manager.db_status.clear()
        self._db_manager.db_check_done = False
        self._db_manager.db_warning_shown = False

    def _start_loading_task(self, paths: tuple[str, ...] | list[str] | None = None, folder_path: str | None = None) -> None:
        """스토리 데이터 파일 로딩 작업을 백그라운드 스레드로 시작합니다."""
        lang_dict = self.get_lang_dict()
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return

        self._clear_workspace()
        self.is_loading = True
        self.view.update_status_bar('status_bar_loading_start')
        self.view.btn_open_file.config(state=tk.DISABLED)
        self.view.btn_open_folder.config(state=tk.DISABLED)
        
        lang_dict = self.get_lang_dict()
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path, lang_dict))
        thread.daemon = True
        thread.start()

    def open_files(self) -> None:
        """파일 선택 대화상자를 열고 스토리 데이터 파일을 로드합니다."""
        lang_dict = self.get_lang_dict()
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[(lang_dict.get('filetype_json', "JSON Files"), "*.json"), (lang_dict.get('filetype_all', "All Files"), "*.*")]
        )
        if file_paths:
            add_breadcrumb("io", "Opened story files", {"count": len(file_paths)})
            self._start_loading_task(paths=file_paths)

    def open_folder(self) -> None:
        """폴더 선택 대화상자를 열고 내부 스토리 데이터 파일을 로드합니다."""
        lang_dict = self.get_lang_dict()
        folder_path = filedialog.askdirectory(title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files"))
        if folder_path:
            add_breadcrumb("io", "Opened story folder", {"path": folder_path})
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths: tuple[str, ...] | list[str] | None, folder_path: str | None, lang_dict: dict) -> None:
        """선택된 파일/폴더 내의 스토리 데이터를 백그라운드에서 로드하고 분석합니다.

        Args:
            paths: 로드할 파일 경로들의 튜플 또는 리스트.
            folder_path: 로드할 폴더 경로.
            lang_dict: 오류 메시지 다국어 처리 딕셔너리.
        """
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
        unique_char_names, unique_bgms, unique_bgs = set(), set(), set()
        temp_file_titles, temp_raw_titles = {}, {}
        temp_empty_titles = set()

        for i, path in enumerate(file_list_to_process):
            def _update_status(idx=i, total=total_files):
                self.view.update_status_bar('status_bar_analyzing', i=idx+1, t=total)
            self.task_queue.put(ActionEvent(action=_update_status))
            is_valid, data, error_reason = StoryDataLoader.is_valid_storydata(path, lang_dict)
            
            if is_valid:
                filename = os.path.basename(path)
                temp_all_files[filename] = path
                json_title = str(data.get('0', {}).get('title', '') or '').strip()
                base_title = json_title if json_title else filename
                temp_raw_titles[filename] = base_title
                temp_file_titles[filename] = base_title
                if not json_title:
                    temp_empty_titles.add(filename)
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
        results = {
            "all_files": temp_all_files,
            "titles": temp_file_titles,
            "raw_titles": temp_raw_titles,
            "empty_titles": temp_empty_titles,
            "search_data": temp_search_data
        }
        self.task_queue.put(ActionEvent(action=lambda: self._finish_loading(results, invalid_files)))

    def _finish_loading(self, results: dict[str, Any] | None, invalid_files: list[tuple[str, str]]) -> None:
        """파일 로딩 작업을 완료하고 UI를 갱신합니다.

        Args:
            results: 파싱된 데이터 딕셔너리 (all_files, titles, search_data) 또는 실패 시 None.
            invalid_files: 로드에 실패한 (파일경로, 에러사유) 튜플 리스트.
        """
        lang_dict = self.get_lang_dict()
            
        self.is_loading = False
        self.view.btn_open_file.config(state=tk.NORMAL)
        self.view.btn_open_folder.config(state=tk.NORMAL)
        if not results:
            self.view.update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'], parent=self.view)
        else:
            self.all_files = results['all_files']
            self.file_titles = results['titles']
            self.raw_file_titles = results.get('raw_titles', {})
            self.empty_title_files = results['empty_titles']
            self.search_data = results['search_data']
            self.loaded_filenames = sorted(list(self.all_files.keys()))
            self.view.update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))
            
            # DB 분석 시작 버튼 활성화
            self.view.btn_db_analyze.config(state=tk.NORMAL)
            
            if self.db_analyzed:
                self.view.search_button.config(state=tk.NORMAL)
                self.view.btn_export.config(state=tk.NORMAL)
                self.view.display_mode_combo.config(state="readonly")
                self.view.jp_radio.config(state=tk.NORMAL)
                self.view.kr_radio.config(state=tk.NORMAL)
                self.on_server_change()
            else:
                self.update_file_list(list(self.all_files.keys()))
        
        if invalid_files:
            msg = lang_dict['msgbox_load_fail_msg'].format(count=len(invalid_files))
            if messagebox.askyesno(lang_dict['msgbox_load_fail_title'], msg, parent=self.view):
                try:
                    import platform
                    import multiprocessing
                    import sys
                    from pathlib import Path
                    from src.constants import SEPARATOR_LONG, APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER
                    
                    python_ver = platform.python_version()
                    os_ver = platform.platform()
                    cpu_cores = multiprocessing.cpu_count()
                    
                    if sys.argv and sys.argv[0]:
                        exec_path = os.path.dirname(os.path.abspath(sys.argv[0]))
                    else:
                        exec_path = os.path.abspath(os.getcwd())
                        
                    now = datetime.now()
                    
                    log_dir = Path(exec_path) / "logs"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_filename = log_dir / f"StoryViewerLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"

                    with open(log_filename, 'w', encoding='utf-8') as f:
                        f.write(f"{SEPARATOR_LONG}\n")
                        f.write(f"[SESSION] Invalid Storydata Load Log Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                        f.write(f"{SEPARATOR_LONG}\n")
                        f.write(f"[TOOL]    App Version:     {APP_VERSION} ({APP_LAST_UPDATE})\n")
                        f.write(f"[TOOL]    Developer:       {APP_DEVELOPER}\n")
                        f.write(f"[ENGINE]  Python Version:  {python_ver}\n")
                        f.write(f"[SYSTEM]  OS Version:      {os_ver}\n")
                        f.write(f"[SYSTEM]  Processor Count: {cpu_cores} Cores\n")
                        f.write(f"[PATH]    Exec Path:       {exec_path}\n")
                        f.write(f"[REPORT]  Total Failed:    {len(invalid_files)}\n")
                        f.write(f"{SEPARATOR_LONG}\n\n")

                        for idx, (path, reason) in enumerate(invalid_files, 1):
                            f.write(f"[ERROR ITEM #{idx}]\n")
                            f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                            f.write(f"Context   : Storydata Validation\n")
                            f.write(f"File      : {path}\n")
                            f.write(f"Reason    : {reason}\n")
                            f.write(f"{SEPARATOR_LONG}\n\n")
                    messagebox.showinfo(lang_dict['msgbox_log_saved_title'], lang_dict['msgbox_log_saved_msg'].format(filename=log_filename), parent=self.view)
                except OSError as e:
                    messagebox.showerror(lang_dict['msgbox_log_save_error_title'], lang_dict['msgbox_log_save_error_msg'].format(e=e), parent=self.view)



    def open_search_window(self) -> None:
        """검색 창을 엽니다. DB 상태를 사전 확인하고 누락 시 다운로드를 안내합니다."""
        lang_dict = self.get_lang_dict()
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_search_before_load_title'], lang_dict['msgbox_search_before_load_msg'], parent=self.view)
            return
        SearchWindow(
            master=self.master,
            get_lang_dict=self.get_lang_dict,
            get_lang_code=lambda: self.lang_var.get(),
            search_callback=self.update_file_list,
            task_queue=self.task_queue,
            update_status_bar=self.view.update_status_bar,
            all_files_dict=self.all_files,
            search_data=self.search_data,
            db_status=self._db_manager.db_status,
            server_db_info=self.server_db_info,
            db_manager=self._db_manager,
            selected_server=self.server_var.get(),
        )

    def open_export_window(self) -> None:
        """내보내기 창을 엽니다. DB 상태를 사전 확인하고 누락 시 다운로드를 안내합니다."""
        lang_dict = self.get_lang_dict()
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_no_export_files_title'], lang_dict['msgbox_no_export_files_msg'], parent=self.view)
            return
        ExportWindow(
            master=self.master,
            get_lang_dict=self.get_lang_dict,
            export_func=self.export_master_thread,
            update_status_bar=self.view.update_status_bar,
            all_files_dict=self.all_files,
            search_data=self.search_data,
            db_status=self._db_manager.db_status,
            server_db_info=self.server_db_info,
        )

    def update_file_list(self, filenames: list[str]) -> None:
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

    def on_file_select(self, event: Any = None) -> None:
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
                    self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get()))
                    self.view.update_status_bar('status_bar_displaying', filename=filename)
                else:
                    self.view.update_status_bar('status_bar_cache_error', filename=filename)

    def on_display_mode_change(self, event: Any = None, force_update: bool = False) -> None:
        """리스트박스의 파일명 표시 모드(원본 이름/스토리 제목)를 변경합니다.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
            force_update: 로딩 중에도 강제로 업데이트할지 여부.
        """
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

    def on_view_mode_change(self, force_update: bool = False) -> None:
        """스토리 내용 표시 모드(심플/상세)를 변경합니다.

        Args:
            force_update: 로딩 중에도 강제로 업데이트할지 여부.
        """
        if not force_update and self.is_loading:
            return
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            is_valid, data, _ = StoryDataLoader.is_valid_storydata(self.current_file_path)
            if is_valid:
                self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get()))

    # Export functionality helper methods
    def export_master_thread(self, selected_options: dict[str, Any], output_folder: str) -> None:
        """선택된 여러 유형의 데이터들을 백그라운드 스레드에서 파일로 내보냅니다.

        Args:
            selected_options: 사용자가 선택한 내보내기 옵션 딕셔너리.
            output_folder: 내보낼 대상 폴더 경로.
        """
        self._export_handler.export_master_thread(selected_options, output_folder)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다."""
        self._stop_polling()
