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
from .windows_export import ExportWindow, SingleExportWindow
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
            flat_tables["event_group_id_col_list"] = ev.get("group_id_col_list", "story_group_id")
            flat_tables["event_details_table"] = ev.get("details_table", "")
            flat_tables["event_group_id_col_details"] = ev.get("group_id_col_details", "story_group_id")
            flat_tables["event_info_col_details"] = ev.get("info_col", "")
            flat_tables["event_title_col_details"] = ev.get("title_col", "title")
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
        if "sekai_top_data" in tables:
            sk = tables["sekai_top_data"]
            flat_tables["sekai_top_data_table"] = sk.get("table", "")
            flat_tables["sekai_top_data_id_col"] = sk.get("id_col", "story_id")
            flat_tables["sekai_top_data_name_col"] = sk.get("name_col", "name")
            flat_tables["sekai_top_data_boss_mode_col"] = sk.get("boss_mode_col", "boss_mode")
            flat_tables["sekai_top_data_boss_time_from_col"] = sk.get("boss_time_from_col", "boss_time_from")
            flat_tables["sekai_top_data_boss_hp_from_col"] = sk.get("boss_hp_from_col", "boss_hp_from")
        if "sekai_top_story_data" in tables:
            sks = tables["sekai_top_story_data"]
            flat_tables["sekai_top_story_data_table"] = sks.get("table", "")
            flat_tables["sekai_top_story_data_id_col"] = sks.get("id_col", "story_id")
            flat_tables["sekai_top_story_data_boss_time_from_col"] = sks.get("boss_time_from_col", "boss_time_from")
            flat_tables["sekai_top_story_data_boss_time_to_col"] = sks.get("boss_time_to_col", "boss_time_to")
        if "event_top_adv" in tables:
            eta = tables["event_top_adv"]
            flat_tables["event_top_adv_table"] = eta.get("table", "")
            flat_tables["event_top_adv_id_col"] = eta.get("id_col", "story_id")
            flat_tables["event_top_adv_character_id_col"] = eta.get("character_id_col", "character_id")
            flat_tables["event_top_adv_event_id_col"] = eta.get("event_id_col", "event_id")
        if "unit" in tables:
            u = tables["unit"]
            flat_tables["unit_table"] = u.get("table", "")
            flat_tables["unit_id_col"] = u.get("id_col", "unit_id")
            flat_tables["unit_name_col"] = u.get("name_col", "unit_name")
        if "hatsune_boss" in tables:
            hb = tables["hatsune_boss"]
            flat_tables["hatsune_boss_table"] = hb.get("table", "")
            flat_tables["hatsune_boss_event_id_col"] = hb.get("event_id_col", "event_id")
            flat_tables["hatsune_boss_quest_name_col"] = hb.get("quest_name_col", "quest_name")
            flat_tables["hatsune_boss_wavestart_col"] = hb.get("wavestart_col", "story_id_wavestart_1")
            flat_tables["hatsune_boss_waveend_col"] = hb.get("waveend_col", "story_id_waveend_1")
        if "hatsune_special_battle" in tables:
            hsb = tables["hatsune_special_battle"]
            flat_tables["hatsune_special_battle_table"] = hsb.get("table", "")
            flat_tables["hatsune_special_battle_event_id_col"] = hsb.get("event_id_col", "event_id")
            flat_tables["hatsune_special_battle_mode_col"] = hsb.get("mode_col", "mode")
            flat_tables["hatsune_special_battle_mode_start_col"] = hsb.get("mode_start_col", "story_id_mode_start")
            flat_tables["hatsune_special_battle_mode_end_col"] = hsb.get("mode_end_col", "story_id_mode_end")
        merged = {"Common": common}
        for s_key, s_info in raw_cfg["servers"].items():
            s_dict = dict(s_info)
            s_dict.update(flat_tables)
            s_baseline_dbs = s_info.get("baseline_dbs", {})
            for key, entry in tables.items():
                if key in ("event_story", "birthday", "quest", "sekai_top_data", "sekai_top_story_data", "event_top_adv", "unit", "hatsune_boss", "hatsune_special_battle"):
                    continue
                if isinstance(entry, dict) and "table" in entry:
                    req_base = entry.get("baseline")
                    if req_base and req_base not in s_baseline_dbs:
                        for col_k in entry:
                            if col_k == "table":
                                s_dict[f"{key}_table"] = ""
                            elif col_k == "baseline":
                                s_dict[f"{key}_baseline"] = ""
                            else:
                                s_dict[f"{key}_{col_k}"] = ""
                    else:
                        for col_k, col_v in entry.items():
                            if col_k == "table":
                                s_dict[f"{key}_table"] = col_v
                            elif col_k == "baseline":
                                s_dict[f"{key}_baseline"] = col_v
                            else:
                                s_dict[f"{key}_{col_k}"] = col_v
                        s_dict.setdefault(f"{key}_id_col", "story_id")
                        s_dict.setdefault(f"{key}_title_col", "title")
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
        self.file_situations = {}
        self.file_voice_adv_ids = {}
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
        self.view_mode_var = tk.StringVar(value="script")
        self.server_var = tk.StringVar(value='JP')
        
        self.filter_var = tk.StringVar(value="")
        self.filter_timer: str | None = None
        self.base_search_files: list[str] = []
        self._populate_generation: int = 0
        
        self.db_analyzed = False
        self.empty_title_files = set()
        self._server_titles_cache: dict[str, dict[str, str]] = {'JP': {}, 'KR': {}}
        self._pending_json_results: dict[str, Any] | None = None
        self._pending_invalid_files: list[tuple[str, str]] = []
        self._db_ready: bool = False

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
            get_file_titles=lambda: self.file_titles,
        )
        
        self.lang_var.trace_add('write', self._on_language_change)
        self.filter_var.trace_add('write', self._on_filter_changed)

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
            self.on_view_mode_change(force_update=True)
        except tk.TclError:
            pass

    def start_db_analysis(self) -> None:
        """DB 체크 및 스키마 분석을 수행하고 UI를 활성화합니다."""
        self.view.update_status_bar('db_checking_msg')
        
        def _on_ready():
            self.task_queue.put(ActionEvent(action=self._on_db_analyzed))
            
        self._db_manager.check_and_cache_db_status(on_ready=_on_ready)

    def _on_db_analyzed(self) -> None:
        """DB 분석이 완료된 후 관련 UI 요소들을 활성화하고 로딩 완료를 시도합니다."""
        self.db_analyzed = True
        self._db_ready = True

        # DB 분석 후 요소 활성화
        has_files = bool(self.all_files or (self._pending_json_results and self._pending_json_results.get('all_files')))
        self.view.display_mode_combo.config(state="readonly" if has_files else tk.DISABLED)
        self.view.search_button.config(state=tk.NORMAL if has_files else tk.DISABLED)
        self.view.btn_export.config(state=tk.NORMAL if has_files else tk.DISABLED)
        for child in self.view.server_frame.winfo_children():
            child.config(state=tk.NORMAL if has_files else tk.DISABLED)
            
        if self._pending_json_results is not None:
            self._try_finalize_loading()
        elif self.all_files:
            self.on_server_change()
            self.view.update_status_bar('status_bar_initial')
        else:
            self.view.update_status_bar('status_bar_initial')

    def on_server_change(self, force_fetch: bool = False, skip_filter: bool = False) -> None:
        """게임 서버 라디오 버튼 변경 시 호출되어 DB에서 타이틀을 조회하여 갱신합니다.
        
        Args:
            force_fetch: 캐시를 무시하고 DB에서 강제로 새로 조회할지 여부.
            skip_filter: 필터링 및 리스트 갱신 호출을 생략할지 여부.
        """
        if not self.db_analyzed or not self.all_files:
            return
            
        server = self.server_var.get()

        # 1. 캐시 확인: force_fetch가 False이고 캐시에 저장된 타이틀이 있다면 0ms 즉시 복원
        if not force_fetch and server in self._server_titles_cache and self._server_titles_cache[server]:
            self.file_titles = dict(self._server_titles_cache[server])
            if not skip_filter:
                self._apply_filter()
            return

        db_info = self.server_db_info.get(server, {})
        
        # 2. adv_id 목록 수집
        filename_to_adv_id = {}
        for filename in self.all_files:
            match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
            if match:
                filename_to_adv_id[filename] = match.group(1)
        
        # 3. 일괄 조회 (우선순위: story_detail -> dear_story_detail -> tower_story_detail -> alchemy -> sekai -> birthday -> quest -> event_top_adv)
        fetched_titles = {}
        if filename_to_adv_id:
            adv_ids = list(filename_to_adv_id.values())
            if 'story_detail_table' in db_info:
                fetched_titles.update(db_helper.fetch_story_detail_titles_batch(db_info, adv_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'dear_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_dear_story_detail_titles_batch(db_info, remaining_ids))
                remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
                dear_fallback_ids = [aid for aid in remaining_ids if aid.startswith('6')]
                if dear_fallback_ids:
                    meta_dict = {
                        aid: (self.file_voice_adv_ids.get(fn), self.file_situations.get(fn))
                        for fn, aid in filename_to_adv_id.items() if aid in dear_fallback_ids
                    }
                    fetched_titles.update(db_helper.fetch_dear_story_detail_fallback_titles_batch(db_info, meta_dict))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'tower_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_tower_story_detail_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'alchemy_story_detail_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_alchemy_story_detail_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'sekai_top_data_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_sekai_story_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'birthday_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_birthday_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'quest_table' in db_info and remaining_ids:
                fetched_titles.update(db_helper.fetch_quest_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if 'event_top_adv_table' in db_info and remaining_ids:
                eta_meta = {
                    aid: (self.file_voice_adv_ids.get(fn), self.file_situations.get(fn))
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                fetched_titles.update(db_helper.fetch_event_top_adv_titles_batch(db_info, remaining_ids, eta_meta))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if ('hatsune_boss_table' in db_info or 'hatsune_special_battle_table' in db_info or 'event_list_table' in db_info) and remaining_ids:
                fetched_titles.update(db_helper.fetch_event_boss_battle_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            sub_5_ids = [aid for aid in remaining_ids if aid.startswith('5')]
            if sub_5_ids:
                fetched_titles.update(db_helper.fetch_event_minigame_and_sub_scenes_batch(db_info, sub_5_ids))
            
        # 4. 타이틀 갱신: DB 결과 우선, 미존재 시 JSON 원본 타이틀(또는 파일명) 유지
        for filename in self.all_files:
            adv_id = filename_to_adv_id.get(filename)
            title = fetched_titles.get(adv_id) if adv_id else None
            
            if title:
                self.file_titles[filename] = title
            else:
                self.file_titles[filename] = self.raw_file_titles.get(filename, filename)
                
        # 5. 캐시에 보관
        self._server_titles_cache[server] = dict(self.file_titles)

        if not skip_filter:
            self._apply_filter()

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
        self._populate_generation += 1
        self.view.update_story_text([])
        self.all_files.clear()
        self.search_data.clear()
        self.view.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.raw_file_titles.clear()
        self.file_situations.clear()
        self.file_voice_adv_ids.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.base_search_files.clear()
        self.filter_var.set("")
        self.current_file_path = None
        self.view.search_button.config(state=tk.DISABLED)
        self.view.btn_export.config(state=tk.DISABLED)
        self.view.btn_copy.config(state=tk.DISABLED)
        self.view.display_mode_combo.config(state=tk.DISABLED)
        self.view.jp_radio.config(state=tk.DISABLED)
        self.view.kr_radio.config(state=tk.DISABLED)
        
        self._server_titles_cache = {'JP': {}, 'KR': {}}
        self._pending_json_results = None
        self._pending_invalid_files = []

        if not self.db_analyzed:
            self._db_manager.db_status.clear()
            self._db_manager.db_check_done = False
            self._db_manager.db_warning_shown = False
            self._db_ready = False
        else:
            self._db_ready = True

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
        
        # 병렬 동기화 상태 초기화
        self._pending_json_results = None
        self._pending_invalid_files = []
        self._db_ready = bool(self.db_analyzed)

        # 1. JSON 파일 파싱 스레드 시작
        lang_dict = self.get_lang_dict()
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path, lang_dict))
        thread.daemon = True
        thread.start()

        # 2. DB 분석이 아직 안 된 경우, 백그라운드에서 동시에 DB 분석 시작 (방안 A: 병렬 실행)
        if not self.db_analyzed:
            self.start_db_analysis()

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
        unique_char_names, unique_bgms, unique_bgs, unique_voices = set(), set(), set(), set()
        temp_file_titles, temp_raw_titles = {}, {}
        temp_file_situations, temp_file_voice_adv_ids = {}, {}
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
                situation = str(data.get('0', {}).get('situation', '') or '').strip()
                if situation:
                    temp_file_situations[filename] = situation
                base_title = json_title if json_title else (situation if situation else filename)
                temp_raw_titles[filename] = base_title
                temp_file_titles[filename] = base_title
                if not json_title:
                    temp_empty_titles.add(filename)
                for scene in data.values():
                    if isinstance(scene, dict):
                        if 'print' in scene and 'name' in scene['print'] and (name := str(scene['print']['name']).strip()): unique_char_names.add(name)
                        if 'bgm' in scene and (bgm_name := StoryDataLoader.extract_asset_name(scene['bgm'])): unique_bgms.add(bgm_name)
                        if 'background' in scene and (bg_name := StoryDataLoader.extract_asset_name(scene['background'])): unique_bgs.add(bg_name)
                        if 'vo' in scene and (vo_name := StoryDataLoader.extract_asset_name(scene['vo'])):
                            unique_voices.add(vo_name)
                            if filename not in temp_file_voice_adv_ids:
                                m = re.search(r'vo_adv_(\d+)_', vo_name)
                                if m:
                                    temp_file_voice_adv_ids[filename] = m.group(1)
            else:
                invalid_files.append((path, error_reason))
        
        if not temp_all_files:
            self.task_queue.put(ActionEvent(action=lambda: self._finish_loading(None, invalid_files)))
            return

        temp_search_data = {
            'filenames': sorted(list(temp_all_files.keys())), 
            'character_names': sorted(list(unique_char_names)), 
            'bgms': sorted(list(unique_bgms)), 
            'backgrounds': sorted(list(unique_bgs)),
            'voices': sorted(list(unique_voices))
        }
        results = {
            "all_files": temp_all_files,
            "titles": temp_file_titles,
            "raw_titles": temp_raw_titles,
            "file_situations": temp_file_situations,
            "file_voice_adv_ids": temp_file_voice_adv_ids,
            "empty_titles": temp_empty_titles,
            "search_data": temp_search_data
        }
        self.task_queue.put(ActionEvent(action=lambda: self._finish_loading(results, invalid_files)))

    def _finish_loading(self, results: dict[str, Any] | None, invalid_files: list[tuple[str, str]]) -> None:
        """파일 로딩 작업을 완료하고 결과를 임시 보관한 뒤 최종 확정을 시도합니다.

        Args:
            results: 파싱된 데이터 딕셔너리 (all_files, titles, search_data) 또는 실패 시 None.
            invalid_files: 로드에 실패한 (파일경로, 에러사유) 튜플 리스트.
        """
        lang_dict = self.get_lang_dict()
        if not results:
            self.is_loading = False
            self.view.btn_open_file.config(state=tk.NORMAL)
            self.view.btn_open_folder.config(state=tk.NORMAL)
            self.view.update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'], parent=self.view)
            if invalid_files:
                self._handle_invalid_files_log(invalid_files)
            self._pending_json_results = None
            self._pending_invalid_files = []
            return

        self._pending_json_results = results
        self._pending_invalid_files = invalid_files
        self._try_finalize_loading()

    def _try_finalize_loading(self) -> None:
        """JSON 파싱과 DB 분석이 모두 완료되었을 때 최종 DB 타이틀로 단 1회 렌더링을 수행합니다."""
        if self._pending_json_results is None or not self._db_ready:
            return

        results = self._pending_json_results
        invalid_files = self._pending_invalid_files
        self._pending_json_results = None
        self._pending_invalid_files = []

        self.is_loading = False
        self.view.btn_open_file.config(state=tk.NORMAL)
        self.view.btn_open_folder.config(state=tk.NORMAL)

        self.all_files = results['all_files']
        self.file_titles = results['titles']
        self.raw_file_titles = results.get('raw_titles', {})
        self.file_situations = results.get('file_situations', {})
        self.file_voice_adv_ids = results.get('file_voice_adv_ids', {})
        self.empty_title_files = results['empty_titles']
        self.search_data = results['search_data']
        self.loaded_filenames = sorted(list(self.all_files.keys()))
        self.base_search_files = list(self.loaded_filenames)

        # UI 요소 활성화
        self.view.display_mode_combo.config(state="readonly")
        self.view.search_button.config(state=tk.NORMAL if self.all_files else tk.DISABLED)
        self.view.btn_export.config(state=tk.NORMAL if self.all_files else tk.DISABLED)
        self.view.jp_radio.config(state=tk.NORMAL)
        self.view.kr_radio.config(state=tk.NORMAL)

        # DB 분석 완료 상태이므로 DB에서 타이틀 일괄 조회 및 캐싱 (skip_filter=True로 필터 중복 호출 방지)
        self.on_server_change(force_fetch=True, skip_filter=True)

        # 완성된 공식 DB 타이틀로 단 1회 렌더링
        self._apply_filter()

        self.view.update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))

        if invalid_files:
            self._handle_invalid_files_log(invalid_files)

    def _handle_invalid_files_log(self, invalid_files: list[tuple[str, str]]) -> None:
        """손상되거나 유효하지 않은 파일들에 대한 오류 로그 저장을 묻고 처리합니다."""
        lang_dict = self.get_lang_dict()
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
            search_callback=self.set_search_results,
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

    def open_single_export_window(self) -> None:
        """선택한 단일 스토리 파일의 전용 내보내기 창을 엽니다."""
        lang_dict = self.get_lang_dict()
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self.view)
            return
        if not self.view.file_listbox.curselection():
            return

        try:
            display_name = self.view.file_listbox.get(self.view.file_listbox.curselection()[0])
        except tk.TclError:
            return

        filename = self.display_name_to_filename.get(display_name)
        if not filename or filename not in self.all_files:
            return

        # 타이틀 및 ID 추출
        match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
        adv_id = match.group(1) if match else ""
        raw_title = self.file_titles.get(filename, "")

        if adv_id and raw_title:
            item_display_title = f"[{adv_id}] {raw_title}"
        elif raw_title:
            item_display_title = raw_title
        elif adv_id:
            item_display_title = f"storydata_{adv_id}"
        else:
            item_display_title = filename

        SingleExportWindow(
            master=self.master,
            target_filename=filename,
            item_display_title=item_display_title,
            get_lang_dict=self.get_lang_dict,
            export_func=self.export_master_thread,
            update_status_bar=self.view.update_status_bar,
            default_view_mode=self.view_mode_var.get(),
            default_naming_rule='original',
        )

    def remove_selected_files(self, event: Any = None) -> None:
        """선택된 파일(들)을 파일 목록에서 제거합니다."""
        if self.is_loading:
            return
        selected_indices = self.view.file_listbox.curselection()
        if not selected_indices:
            return

        to_remove = set()
        for idx in selected_indices:
            try:
                display_name = self.view.file_listbox.get(idx)
                if fn := self.display_name_to_filename.get(display_name):
                    to_remove.add(fn)
            except tk.TclError:
                continue

        if not to_remove:
            return

        self.current_filenames_in_list = [f for f in self.current_filenames_in_list if f not in to_remove]
        self.loaded_filenames = [f for f in self.loaded_filenames if f not in to_remove]
        for fn in to_remove:
            self.all_files.pop(fn, None)

        if self.current_filenames_in_list:
            self.update_file_list(self.current_filenames_in_list)
        else:
            self._populate_generation += 1
            self.display_name_to_filename.clear()
            self.current_file_path = None
            self.view.file_listbox.delete(0, tk.END)
            self.view.update_story_text([])
            self.view.btn_export.config(state=tk.DISABLED)
            self.view.btn_copy.config(state=tk.DISABLED)
            self.view.update_status_bar('status_bar_ready')

    def remove_all_files(self, event: Any = None) -> None:
        """모든 파일을 파일 목록에서 제거합니다."""
        if self.is_loading:
            return
        if not self.current_filenames_in_list and not self.all_files:
            return

        self._populate_generation += 1
        self.all_files.clear()
        self.loaded_filenames.clear()
        self.current_filenames_in_list.clear()
        self.display_name_to_filename.clear()
        self.current_file_path = None

        self.view.file_listbox.delete(0, tk.END)
        self.view.update_story_text([])
        self.view.btn_export.config(state=tk.DISABLED)
        self.view.btn_copy.config(state=tk.DISABLED)
        self.view.update_status_bar('status_bar_ready')

    def update_file_list(self, filenames: list[str]) -> None:
        """파일 목록 뷰를 업데이트합니다."""
        self._populate_generation += 1
        current_gen = self._populate_generation
        self.view.update_story_text([])
        self.current_file_path = None
        self.current_filenames_in_list = sorted(filenames)
        target_files = list(self.current_filenames_in_list)
        self.display_name_to_filename.clear()
        self.view.file_listbox.delete(0, tk.END)
        total, chunk_size = len(target_files), 200
        
        def _populate_list(index=0):
            if current_gen != self._populate_generation:
                return
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
                filename = target_files[i]
                display_name = filename
                if display_mode == 'title':
                    if title := self.file_titles.get(filename, filename):
                        display_name = f"{title}"
                elif display_mode == 'id_title':
                    match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
                    adv_id = match.group(1) if match else filename
                    title = self.file_titles.get(filename, filename)
                    display_name = f"[{adv_id}] {title}"
                display_chunk.append(display_name)
                self.display_name_to_filename[display_name] = filename
            self.view.file_listbox.insert(tk.END, *display_chunk)
            self.view.after(1, lambda: _populate_list(end_index))
        _populate_list()

    def set_search_results(self, filenames: list[str]) -> None:
        """고급 검색 결과로 기본 파일 목록을 설정하고 현재 필터를 적용합니다."""
        self.base_search_files = list(filenames)
        self._apply_filter()

    def _on_filter_changed(self, *args: Any) -> None:
        """빠른 필터 입력값 변경 시 150ms 디바운스로 필터링을 실행합니다."""
        if self.filter_timer:
            try:
                self.view.after_cancel(self.filter_timer)
            except tk.TclError:
                pass
        try:
            self.filter_timer = self.view.after(150, self._apply_filter)
        except tk.TclError:
            self._apply_filter()

    def _apply_filter(self) -> None:
        """현재 filter_var 값에 따라 base_search_files를 필터링하여 목록을 업데이트합니다."""
        query = self.filter_var.get().strip().lower()
        source_files = self.base_search_files if self.base_search_files else list(self.loaded_filenames)
        
        if not query:
            self.update_file_list(source_files)
            return
        
        matched = []
        for fname in source_files:
            if query in fname.lower():
                matched.append(fname)
                continue
            match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', fname)
            if match and query in match.group(1):
                matched.append(fname)
                continue
            title = self.file_titles.get(fname, "")
            if query in title.lower():
                matched.append(fname)
                continue
        
        self.update_file_list(matched)

    def clear_filter(self) -> None:
        """빠른 필터 입력값을 초기화합니다."""
        self.filter_var.set("")

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
                    self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get(), self.get_lang_dict()))
                    self.view.update_status_bar('status_bar_displaying', filename=filename)
                else:
                    self.view.update_status_bar('status_bar_cache_error', filename=filename)

    def on_display_mode_change(self, event: Any = None, force_update: bool = False) -> None:
        """리스트박스의 파일명 표시 모드(원본 이름/스토리 제목/[ID] + 제목)를 변경합니다.

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
            elif idx == 2:
                self.display_mode_var.set("id_title")
        except tk.TclError:
            pass
        self.update_file_list(self.current_filenames_in_list)

    def on_view_mode_change(self, event: Any = None, force_update: bool = False) -> None:
        """스토리 내용 표시 모드(대본/심플/상세)를 변경합니다.

        Args:
            event: 이벤트 객체 (ComboboxSelected 등).
            force_update: 로딩 중에도 강제로 업데이트할지 여부.
        """
        if not force_update and self.is_loading:
            return
        try:
            idx = self.view.view_mode_combo.current()
            if idx == 0:
                self.view_mode_var.set("script")
            elif idx == 1:
                self.view_mode_var.set("simple")
            elif idx == 2:
                self.view_mode_var.set("detailed")
        except (tk.TclError, AttributeError):
            pass
        if self.current_file_path:
            is_valid, data, _ = StoryDataLoader.is_valid_storydata(self.current_file_path)
            if is_valid:
                self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get(), self.get_lang_dict()))

    # Export functionality helper methods
    def export_master_thread(
        self,
        selected_options: dict[str, Any],
        output_folder: str,
        progress_callback: Any = None,
        check_cancelled: Any = None,
        on_finish: Any = None,
    ) -> None:
        """선택된 여러 유형의 데이터들을 백그라운드 스레드에서 파일로 내보냅니다.

        Args:
            selected_options: 사용자가 선택한 내보내기 옵션 딕셔너리.
            output_folder: 내보낼 대상 폴더 경로.
            progress_callback: 진행률 업데이트 콜백.
            check_cancelled: 취소 상태 확인 콜백.
            on_finish: 완료 후 정리 콜백.
        """
        self._export_handler.export_master_thread(
            selected_options,
            output_folder,
            progress_callback=progress_callback,
            check_cancelled=check_cancelled,
            on_finish=on_finish,
        )

    def copy_script_to_clipboard(self) -> None:
        """현재 화면에 표시된 대본 텍스트를 클립보드에 복사합니다."""
        text = self.view.story_text.get("1.0", tk.END).strip()
        if not text:
            return
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            lang_dict = self.get_lang_dict()
            messagebox.showinfo(
                lang_dict.get('btn_copy_script', '대본 복사'),
                lang_dict.get('msgbox_copy_complete', '대본이 클립보드에 복사되었습니다.'),
                parent=self.view
            )
        except tk.TclError:
            pass

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다."""
        self._stop_polling()
