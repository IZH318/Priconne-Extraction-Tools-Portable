"""Story Viewer 컨트롤러 모듈.

추출 스토리 JSON 스크립트 로딩, 파싱, 다국어 master.db 메타데이터 조회,
실시간 빠른 검색 필터, 다중 조건 검색 창 연동, 텍스트/마크다운 내보내기 및
QueuePollingMixin 기반 백그라운드 태스크 통신 관리.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.breadcrumbs import add_breadcrumb
from src.cancellation_token import CancellationToken
from src.constants import STORY_CLEANUP_JOIN_TIMEOUT
from src.languages import STORY_VIEWER_LANGUAGES as LANGUAGES
from src.languages import pick_language
from src.queue_polling import QueuePollingMixin
from src.shared_state import SharedState
from src.utils.base_path import get_application_base_path

from .db_manager import StoryDBManager
from .db_service import StoryDBService
from .export_handler import StoryExportHandler
from .file_list_service import StoryFileListService
from .filter_service import StoryFilterService
from .logic import StoryDataLoader, StoryFormatter
from .view import StoryViewerView
from .windows_export import ExportWindow, SingleExportWindow
from .windows_search import SearchWindow
from .workspace_state import StoryWorkspaceState

logger = logging.getLogger(__name__)


def _load_db_config() -> dict[str, dict[str, str]]:
    """db_config.json 기반 서버별 DB 테이블/컬럼 매핑 정보 로드.

    계층형 구조(common, servers, tables)를 기존 호환 딕셔너리로 자동 정규화.

    Returns:
        dict[str, dict[str, str]]: 서버 키('JP', 'KR') 및 'Common'을 키로 갖는 정규화된 DB 정보 딕셔너리 반환.
    """
    config_path = os.path.join(os.path.dirname(__file__), 'db_config.json')
    try:
        with open(config_path, encoding='utf-8') as f:

            raw_cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load db_config.json: %s. Using empty fallback.", e)
        return {}

    if "servers" in raw_cfg and "tables" in raw_cfg:
        common = raw_cfg.get("common", raw_cfg.get("Common", {}))
        raw_tables = raw_cfg.get("tables", {})

        tables = {}
        for k, v in raw_tables.items():
            if isinstance(v, dict) and "table" not in v and not any(k2.endswith(("_col", "_table")) for k2 in v):
                for sub_k, sub_v in v.items():
                    if isinstance(sub_v, dict):
                        tables[sub_k] = sub_v
            else:
                tables[k] = v

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
                            if col_k.startswith("_"):
                                continue
                            if col_k == "table":
                                s_dict[f"{key}_table"] = ""
                            elif col_k == "baseline":
                                s_dict[f"{key}_baseline"] = ""
                            else:
                                s_dict[f"{key}_{col_k}"] = ""
                    else:
                        for col_k, col_v in entry.items():
                            if col_k.startswith("_"):
                                continue
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

    return raw_cfg  # type: ignore[no-any-return]

class StoryViewerController(QueuePollingMixin):
    """Story Viewer 비즈니스 로직 및 서브 서비스 제어 컨트롤러."""

    def __init__(self, app_wrapper: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str | int] | None = None) -> None:
        """StoryViewerController 인스턴스 초기화.

        Args:
            app_wrapper: gui.py의 ttk.Frame 래퍼 (View의 부모 위젯).
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            app_lang_var: 앱 전역 언어 StringVar.
            about_info: About 대화상자에 표시될 정보 딕셔너리.

        Note:
            다른 Controller(Renamer, AV, ResourceRemover)는 master 하나만 받지만,
            StoryViewer와 UnityConverter는 대화상자 위치 지정을 위해
            별도 master(최상위 윈도우) 필요에 따른 2개 위젯 인자 수신.
        """
        self.master: tk.Tk | tk.Toplevel = master
        self.about_info: dict[str, str | int] = about_info or {}
        self.base_path: Path = get_application_base_path()

        self._workspace: StoryWorkspaceState = StoryWorkspaceState()
        self._loading_thread: threading.Thread | None = None
        self._loading_cancel_token: CancellationToken = CancellationToken()

        if app_lang_var:
            self.lang_var: tk.StringVar = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.display_mode_var: tk.StringVar = tk.StringVar(value="original")
        self.view_mode_var: tk.StringVar = tk.StringVar(value="script")
        self.server_var: tk.StringVar = tk.StringVar(value='JP')

        self.filter_var: tk.StringVar = tk.StringVar(value="")
        self.filter_timer: str | None = None


        self.server_db_info: dict[str, Any] = _load_db_config()

        self.view: StoryViewerView = StoryViewerView(app_wrapper, self)

        self._db_manager: StoryDBManager = StoryDBManager(
            master=self.master,
            server_db_info=self.server_db_info,
            get_lang_dict=self.get_lang_dict,
            view=self.view,
            get_all_files=lambda: self._workspace.all_files,
        )
        self.shared_state: SharedState = SharedState()
        self.shared_state.get_lang_dict = self.get_lang_dict
        self.shared_state.get_view = lambda: self.view
        self.shared_state.get_base_path = lambda: self.base_path
        self._db_service: StoryDBService = StoryDBService(
            shared_state=self.shared_state,
            view=self.view,
            master=self.master,
            base_path=self.base_path,
            server_db_info=self.server_db_info,
            server_var=self.server_var,
            db_manager=self._db_manager,
            get_lang_dict=self.get_lang_dict,
            workspace=self._workspace,
            apply_filter=self._apply_filter,
            clear_workspace=self._clear_workspace,
            get_loading_cancel_requested=lambda: self._loading_cancel_token.is_cancelled,
        )
        self._export_handler: StoryExportHandler = StoryExportHandler(
            shared_state=self.shared_state,
            get_lang_dict=self.get_lang_dict,
            master=self.master,
            view_mode_var=self.view_mode_var,
            get_current_filenames=lambda: self._workspace.current_filenames_in_list,
            get_loaded_filenames=lambda: self._workspace.loaded_filenames,
            get_all_files=lambda: self._workspace.all_files,
            get_search_data=lambda: self._workspace.search_data,
            get_server_db_info=lambda: self.server_db_info,
            get_db_manager=lambda: self._db_manager,
            view=self.view,
            get_file_titles=lambda: self._workspace.file_titles,
        )
        self._file_list_service: StoryFileListService = StoryFileListService(
            shared_state=self.shared_state,
            view=self.view,
            display_mode_var=self.display_mode_var,
            workspace=self._workspace,
        )
        self._filter_service: StoryFilterService = StoryFilterService(
            view=self.view,
            get_lang_dict=self.get_lang_dict,
            workspace=self._workspace,
            update_file_list=self._file_list_service.update_file_list,
            filter_var=self.filter_var,
        )

        self.lang_var.trace_add('write', self._on_language_change)
        self.filter_var.trace_add('write', self._on_filter_changed)

        self._init_queue_polling(self.view)
        self.view.update_ui_text()
        self.view.update_status_bar('status_bar_initial')
        self.view.show_filter_placeholder()

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리 반환."""
        return pick_language(self.lang_var.get(), LANGUAGES)

    @property
    def is_loading(self) -> bool:
        """파일 로딩 진행 여부(작업 공간 상태 위임)."""
        return self._workspace.is_loading

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트 처리 및 UI 텍스트/뷰 모드 갱신.

        Args:
            *args: 가변 인자 리스트.
        """
        try:
            self.view.update_ui_text()
            self.on_view_mode_change(force_update=True)
            self.view.update_status_bar('status_bar_initial')
        except tk.TclError:
            pass

    def start_db_analysis(self) -> None:
        """DB 검사 및 스키마 분석 후 UI 활성화."""
        self._db_service.start_db_analysis()

    def _on_db_analyzed(self) -> None:
        """DB 분석 완료 후 관련 UI 요소 활성화 및 로딩 완료 시도."""
        self._db_service.on_db_analyzed()

    def on_server_change(self, force_fetch: bool = False, skip_filter: bool = False) -> None:
        """게임 서버 라디오 버튼 변경 이벤트 처리 (DB 타이틀 조회 및 갱신).

        Args:
            force_fetch: 캐시를 무시하고 DB에서 강제로 새로 조회할지 여부.
            skip_filter: 필터링 및 리스트 갱신 호출을 생략할지 여부.
        """
        self._db_service.on_server_change(force_fetch=force_fetch, skip_filter=skip_filter)

    def _on_poll_cycle(self) -> None:
        """폴링 훅: 스토리 뷰어는 전역 UI 콜백 큐(post_to_ui)로 갱신하므로 추가 작업 없음."""

    def _clear_workspace(self) -> None:
        """작업 공간 초기화 (모든 로드 데이터 및 UI 상태 초기화)."""
        self._workspace.populate_generation += 1
        self.view.update_story_text([])
        self._workspace.all_files.clear()
        self._workspace.search_data.clear()
        self.view.file_listbox.delete(0, tk.END)
        self._workspace.file_titles.clear()
        self._workspace.raw_file_titles.clear()
        self._workspace.file_situations.clear()
        self._workspace.file_outlines.clear()
        self._workspace.file_voice_adv_ids.clear()
        self._workspace.file_speakers.clear()
        self._workspace.display_name_to_filename.clear()
        self._workspace.current_filenames_in_list = []
        self._workspace.loaded_filenames = []
        self._workspace.base_search_files.clear()
        self.filter_var.set("")
        self.view.show_filter_placeholder()
        self._workspace.current_file_path = None
        self._workspace.story_data_cache.clear()
        self.view.search_button.config(state=tk.DISABLED)
        self.view.btn_export.config(state=tk.DISABLED)
        self.view.btn_copy.config(state=tk.DISABLED)
        self.view.display_mode_combo.config(state=tk.DISABLED)
        self.view.jp_radio.config(state=tk.DISABLED)
        self.view.kr_radio.config(state=tk.DISABLED)

        self._workspace.server_titles_cache = {'JP': {}, 'KR': {}}
        self._workspace.pending_json_results = None
        self._workspace.pending_invalid_files = []

        if not self._workspace.db_analyzed:
            self._db_manager.db_status.clear()
            self._db_manager.db_check_done = False
            self._db_manager.db_warning_shown = False
            self._workspace.db_ready = False
        else:
            self._workspace.db_ready = True

    def _start_loading_task(self, paths: tuple[str, ...] | list[str] | None = None, folder_path: str | None = None) -> None:
        """스토리 데이터 파일 로딩 작업 백그라운드 스레드 시작."""
        lang_dict = self.get_lang_dict()
        if self._workspace.is_loading:
            messagebox.showwarning(
                lang_dict.get('msgbox_loading_title', 'In Progress'),
                lang_dict.get('msgbox_loading_msg', 'Currently loading other files.'),
                parent=self.view,
            )
            return

        self._clear_workspace()
        self._workspace.is_loading = True
        self._resume_polling()
        self.view.update_status_bar('status_bar_loading_start')
        self.view.btn_open_file.config(state=tk.DISABLED)
        self.view.btn_open_folder.config(state=tk.DISABLED)

        self._workspace.pending_json_results = None
        self._workspace.pending_invalid_files = []
        self._workspace.db_ready = bool(self._workspace.db_analyzed)

        lang_dict = self.get_lang_dict()
        self._loading_cancel_token.finish()
        self._loading_cancel_token.reset()
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path, lang_dict))
        thread.daemon = True
        self._loading_thread = thread
        thread.start()

        if not self._workspace.db_analyzed:
            self.start_db_analysis()

    def open_files(self) -> None:
        """파일 선택 대화상자 오픈 및 스토리 데이터 파일 로드."""
        lang_dict = self.get_lang_dict()
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[(lang_dict.get('filetype_json', "JSON Files"), "*.json"), (lang_dict.get('filetype_all', "All Files"), "*.*")]
        )
        if file_paths:
            add_breadcrumb("io", "Opened story files", {"count": len(file_paths)})
            self._start_loading_task(paths=file_paths)

    def open_folder(self) -> None:
        """폴더 선택 대화상자 오픈 및 내부 스토리 데이터 파일 로드."""
        lang_dict = self.get_lang_dict()
        folder_path = filedialog.askdirectory(title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files"))
        if folder_path:
            add_breadcrumb("io", "Opened story folder", {"path": folder_path})
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths: tuple[str, ...] | list[str] | None, folder_path: str | None, lang_dict: dict) -> None:
        """선택된 파일/폴더의 스토리 데이터 백그라운드 로드 및 분석.

        Args:
            paths: 로드할 파일 경로들의 튜플 또는 리스트.
            folder_path: 로드할 폴더 경로.
            lang_dict: 오류 메시지 다국어 처리 딕셔너리.
        """
        self._db_service.load_and_analyze_thread(paths, folder_path, lang_dict)

    def _finish_loading(self, results: dict[str, Any] | None, invalid_files: list[tuple[str, str]]) -> None:
        """파일 로딩 작업 완료 처리 (결과 임시 보관 및 최종 확정 시도).

        Args:
            results: 파싱된 데이터 딕셔너리 (all_files, titles, search_data) 또는 실패 시 None.
            invalid_files: 로드에 실패한 (파일경로, 에러사유) 튜플 리스트.
        """
        self._db_service.finish_loading(results, invalid_files)

    def _try_finalize_loading(self) -> None:
        """JSON 파싱 및 DB 분석 완료 시 DB 타이틀 기반 렌더링."""
        self._db_service.try_finalize_loading()

    def _handle_invalid_files_log(self, invalid_files: list[tuple[str, str]]) -> None:
        """손상/비정상 파일 대상 오류 로그 자동 저장 및 알림."""
        self._db_service.handle_invalid_files_log(invalid_files)



    def open_search_window(self) -> None:
        """검색 창 오픈 (DB 상태 사전 확인 및 누락 시 다운로드 안내)."""
        lang_dict = self.get_lang_dict()
        if self._workspace.is_loading:
            messagebox.showwarning(
                lang_dict.get('msgbox_loading_title', 'In Progress'),
                lang_dict.get('msgbox_loading_msg', 'Currently loading other files.'),
                parent=self.view,
            )
            return
        if not self._workspace.all_files:
            messagebox.showinfo(
                lang_dict.get('msgbox_search_before_load_title', 'Notice'),
                lang_dict.get('msgbox_search_before_load_msg', 'Please open a storydata file or folder first.'),
                parent=self.view,
            )
            return
        SearchWindow(
            master=self.master,
            get_lang_dict=self.get_lang_dict,
            get_lang_code=lambda: self.lang_var.get(),
            search_callback=self.set_search_results,
            update_status_bar=self.view.update_status_bar,
            all_files_dict=self._workspace.all_files,
            search_data=self._workspace.search_data,
            db_status=self._db_manager.db_status,
            server_db_info=self.server_db_info,
            db_manager=self._db_manager,
            selected_server=self.server_var.get(),
        )

    def open_export_window(self) -> None:
        """내보내기 창 오픈 (DB 상태 사전 확인 및 누락 시 다운로드 안내)."""
        lang_dict = self.get_lang_dict()
        if self._workspace.is_loading:
            messagebox.showwarning(
                lang_dict.get('msgbox_loading_title', 'In Progress'),
                lang_dict.get('msgbox_loading_msg', 'Currently loading other files.'),
                parent=self.view,
            )
            return
        if not self._workspace.all_files:
            messagebox.showinfo(
                lang_dict.get('msgbox_no_export_files_title', 'Notice'),
                lang_dict.get('msgbox_no_export_files_msg', 'There are no files to export.'),
                parent=self.view,
            )
            return
        ExportWindow(
            master=self.master,
            get_lang_dict=self.get_lang_dict,
            export_func=self.export_master_thread,
            update_status_bar=self.view.update_status_bar,
            all_files_dict=self._workspace.all_files,
            search_data=self._workspace.search_data,
            db_status=self._db_manager.db_status,
            server_db_info=self.server_db_info,
        )

    def open_single_export_window(self) -> None:
        """선택한 단일 스토리 파일의 전용 내보내기 창 열기."""
        lang_dict = self.get_lang_dict()
        if self._workspace.is_loading:
            messagebox.showwarning(
                lang_dict.get('msgbox_loading_title', 'In Progress'),
                lang_dict.get('msgbox_loading_msg', 'Currently loading other files.'),
                parent=self.view,
            )
            return
        sel = self.view.file_listbox.curselection()
        if not sel:
            return
        sel_idx = sel[0]
        filename = None
        if 0 <= sel_idx < len(self._workspace.current_filenames_in_list):
            filename = self._workspace.current_filenames_in_list[sel_idx]
        else:
            try:
                display_name = self.view.file_listbox.get(sel_idx)
                filename = self._workspace.display_name_to_filename.get(display_name)
            except tk.TclError:
                return

        if not filename or filename not in self._workspace.all_files:
            return

        match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
        adv_id = match.group(1) if match else ""
        raw_title = self._workspace.file_titles.get(filename, "")

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
        """선택된 파일 목록에서 제거."""
        self._file_list_service.remove_selected_files(event)

    def remove_all_files(self, event: Any = None) -> None:
        """전체 파일 목록 비우기."""
        self._file_list_service.remove_all_files(event)

    def update_file_list(self, filenames: list[str], status_key: str | None = None, **status_kwargs: Any) -> None:
        """파일 목록 갱신."""
        self._file_list_service.update_file_list(filenames, status_key=status_key, **status_kwargs)

    def set_search_results(self, filenames: list[str]) -> None:
        """고급 검색 결과 기반 기본 파일 목록 설정 및 현재 필터 적용."""
        self._filter_service.set_search_results(filenames)

    def _on_filter_changed(self, *args: Any) -> None:
        """빠른 필터 입력값 변경 처리 (150ms 디바운스 필터링 실행)."""
        if getattr(self.view, "_placeholder_active", False):
            return
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
        """현재 filter_var 값 기준 base_search_files 필터링 및 목록 갱신."""
        self._filter_service.apply_filter()

    def clear_filter(self) -> None:
        """빠른 필터 입력값 초기화."""
        self._filter_service.clear_filter()

    def _cache_story_data(self, path: Path | str, value: Any) -> Any:
        """스토리 데이터 캐시에 값을 저장.

        Args:
            path: 캐시 키로 사용할 스토리 파일 경로.
            value: 저장할 스토리 데이터((is_valid, data) 튜플 등) 값.

        Returns:
            저장된 value.
        """
        self._workspace.story_data_cache[path] = value
        return value

    def on_file_select(self, event: Any = None) -> None:
        """파일 목록 항목 선택 이벤트 처리 (스토리 내용 표시)."""
        sel = self.view.file_listbox.curselection()
        if not sel:
            return
        sel_idx = sel[0]
        filename = None
        if 0 <= sel_idx < len(self._workspace.current_filenames_in_list):
            filename = self._workspace.current_filenames_in_list[sel_idx]
        else:
            try:
                display_name = self.view.file_listbox.get(sel_idx)
                filename = self._workspace.display_name_to_filename.get(display_name)
            except tk.TclError:
                return

        if filename:
            self._workspace.current_file_path = self._workspace.all_files.get(filename)
            if self._workspace.current_file_path:
                cached = self._workspace.story_data_cache.get(self._workspace.current_file_path)
                if cached is None:
                    is_valid, data, _ = StoryDataLoader.is_valid_storydata(str(self._workspace.current_file_path))
                    cached = (is_valid, data)
                is_valid, data = self._cache_story_data(self._workspace.current_file_path, cached)
                if is_valid and data is not None:
                    self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get(), self.get_lang_dict()))
                    self.view.update_status_bar('status_bar_displaying', filename=filename)
                else:
                    self.view.update_status_bar('status_bar_cache_error', filename=filename)

    def on_display_mode_change(self, event: Any = None, force_update: bool = False) -> None:
        """리스트박스 파일명 표시 모드(원본 이름/스토리 제목/[ID] + 제목) 변경 처리.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
            force_update: 로딩 중에도 강제로 업데이트할지 여부.
        """
        if not force_update and self._workspace.is_loading:
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
        self.update_file_list(self._workspace.current_filenames_in_list)

    def on_view_mode_change(self, event: Any = None, force_update: bool = False) -> None:
        """스토리 내용 표시 모드(대본/심플/상세) 변경 처리.

        Args:
            event: 이벤트 객체 (ComboboxSelected 등).
            force_update: 로딩 중에도 강제로 업데이트할지 여부.
        """
        if not force_update and self._workspace.is_loading:
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
        if self._workspace.current_file_path:
            cached = self._workspace.story_data_cache.get(self._workspace.current_file_path)
            if cached is None:
                is_valid, data, _ = StoryDataLoader.is_valid_storydata(str(self._workspace.current_file_path))
                cached = (is_valid, data)
            is_valid, data = self._cache_story_data(self._workspace.current_file_path, cached)
            if is_valid and data is not None:
                self.view.update_story_text(StoryFormatter.format_story_data(data, self.view_mode_var.get(), self.get_lang_dict()))

    # 내보내기 헬퍼 메서드 (Export functionality helper methods)
    def export_master_thread(
        self,
        selected_options: dict[str, Any],
        output_folder: str,
        progress_callback: Any = None,
        check_cancelled: Any = None,
        on_finish: Any = None,
    ) -> None:
        """선택된 데이터를 백그라운드 스레드에서 파일로 내보내기.

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
        """현재 대본을 클립보드에 복사."""
        text = self.view.story_text.get("1.0", tk.END).strip()
        if not text:
            return
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            lang_dict = self.get_lang_dict()
            messagebox.showinfo(
                lang_dict.get('btn_copy_script', 'Copy Script'),
                lang_dict.get('msgbox_copy_complete', 'Script copied to clipboard.'),
                parent=self.view
            )
        except tk.TclError:
            pass

    def cleanup(self) -> None:
        """앱 종료 시 리소스 정리 및 폴링 중지.

        로딩 취소 플래그를 세워 진행 중인 로딩 워커가 파일/씬 경계에서 조기 종료하도록 한 뒤,
        유한 타임아웃으로 조인하여 워커 종료를 대기.
        """
        self._loading_cancel_token.cancel()
        t = self._loading_thread
        if t is not None and t.is_alive():
            t.join(timeout=STORY_CLEANUP_JOIN_TIMEOUT)
        self._loading_thread = None
        self._stop_polling()
