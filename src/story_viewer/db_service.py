"""Story Viewer 데이터베이스 질의 및 메타데이터 캐싱 서비스 모듈.

선택된 서버(JP, KR, EN, TW, CN 등)의 master.db로부터 스토리 제목, 상황(Situation),
줄거리(Outline), 음성 ADV ID, 화자 정보 등을 쿼리하여 메모리에 캐싱하고,
서버 전환 시 메타데이터 재바인딩 처리.
"""

from __future__ import annotations

import os
import re
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox
from typing import Any

from src.queue_events import ActionEvent
from src.story_viewer import db_helper
from src.story_viewer.logic import StoryDataLoader


class StoryDBService:
    """스토리 메타데이터 DB 조회 및 다국어 타이틀 캐싱 서비스.

    서버별 SQLite master.db 연결을 관리하고, 스토리 파일(JSON)의 ID 패턴(예: 100101,
    200101, 500101 등)을 식별하여 캐릭터/메인/이벤트 스토리 메타데이터 매핑.
    """


    def __init__(
        self,
        view: Any,
        master: Any,
        base_path: Path,
        server_db_info: dict,
        server_var: Any,
        task_queue: Any,
        db_manager: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        # 가변 상태 접근자(Mutable state accessors)
        get_all_files: Callable[[], dict[str, str]],
        set_all_files: Callable[[dict[str, str]], None],
        get_file_titles: Callable[[], dict[str, str]],
        set_file_titles: Callable[[dict[str, str]], None],
        get_is_loading: Callable[[], bool],
        set_is_loading: Callable[[bool], None],
        get_pending_json: Callable[[], dict[str, Any] | None],
        set_pending_json: Callable[[dict[str, Any] | None], None],
        get_pending_invalid: Callable[[], list],
        set_pending_invalid: Callable[[list], None],
        get_db_analyzed: Callable[[], bool],
        set_db_analyzed: Callable[[bool], None],
        get_db_ready: Callable[[], bool],
        set_db_ready: Callable[[bool], None],
        get_kr_notice_shown: Callable[[], bool],
        set_kr_notice_shown: Callable[[bool], None],
        get_raw_file_titles: Callable[[], dict[str, str]],
        set_raw_file_titles: Callable[[dict[str, str]], None],
        get_file_situations: Callable[[], dict[str, str]],
        set_file_situations: Callable[[dict[str, str]], None],
        get_file_outlines: Callable[[], dict[str, str]],
        set_file_outlines: Callable[[dict[str, str]], None],
        get_file_voice_adv_ids: Callable[[], dict[str, str]],
        set_file_voice_adv_ids: Callable[[dict[str, str]], None],
        get_file_speakers: Callable[[], dict[str, str]],
        set_file_speakers: Callable[[dict[str, str]], None],
        get_server_titles_cache: Callable[[], dict],
        set_server_titles_cache: Callable[[dict], None],
        get_loaded_filenames: Callable[[], list[str]],
        set_loaded_filenames: Callable[[list[str]], None],
        get_base_search_files: Callable[[], list[str]],
        set_base_search_files: Callable[[list[str]], None],
        get_search_data: Callable[[], dict[str, Any]],
        set_search_data: Callable[[dict[str, Any]], None],
        # 콜백(Callbacks)
        apply_filter: Callable[[], None],
        clear_workspace: Callable[[], None],
        shared_state: Any = None,
    ) -> None:
        self._view = view
        self._master = master
        self._base_path = base_path
        self._server_db_info = server_db_info
        self._server_var = server_var
        self._task_queue = task_queue
        self._db_manager = db_manager
        self._get_lang_dict = get_lang_dict
        self._get_all_files = get_all_files
        self._set_all_files = set_all_files
        self._get_file_titles = get_file_titles
        self._set_file_titles = set_file_titles
        self._get_is_loading = get_is_loading
        self._set_is_loading = set_is_loading
        self._get_pending_json = get_pending_json
        self._set_pending_json = set_pending_json
        self._get_pending_invalid = get_pending_invalid
        self._set_pending_invalid = set_pending_invalid
        self._get_db_analyzed = get_db_analyzed
        self._set_db_analyzed = set_db_analyzed
        self._get_db_ready = get_db_ready
        self._set_db_ready = set_db_ready
        self._get_kr_notice_shown = get_kr_notice_shown
        self._set_kr_notice_shown = set_kr_notice_shown
        self._get_raw_file_titles = get_raw_file_titles
        self._set_raw_file_titles = set_raw_file_titles
        self._get_file_situations = get_file_situations
        self._set_file_situations = set_file_situations
        self._get_file_outlines = get_file_outlines
        self._set_file_outlines = set_file_outlines
        self._get_file_voice_adv_ids = get_file_voice_adv_ids
        self._set_file_voice_adv_ids = set_file_voice_adv_ids
        self._get_file_speakers = get_file_speakers
        self._set_file_speakers = set_file_speakers
        self._get_server_titles_cache = get_server_titles_cache
        self._set_server_titles_cache = set_server_titles_cache
        self._get_loaded_filenames = get_loaded_filenames
        self._set_loaded_filenames = set_loaded_filenames
        self._get_base_search_files = get_base_search_files
        self._set_base_search_files = set_base_search_files
        self._get_search_data = get_search_data
        self._set_search_data = set_search_data
        self._apply_filter = apply_filter
        self._clear_workspace = clear_workspace

    def _lang_dict(self) -> dict[str, str]:
        return self._get_lang_dict()

    def _server(self) -> str:
        return self._server_var.get()  # type: ignore[no-any-return]

    def start_db_analysis(self) -> None:
        self._view.update_status_bar('db_checking_msg')

        def _on_ready() -> None:
            self._task_queue.put(ActionEvent(action=self.on_db_analyzed))

        self._db_manager.check_and_cache_db_status(on_ready=_on_ready)

    def on_db_analyzed(self) -> None:
        self._set_db_analyzed(True)
        self._set_db_ready(True)

        pending = self._get_pending_json()
        has_files = bool(self._get_all_files() or (pending and pending.get('all_files')))
        self._view.display_mode_combo.config(state="readonly" if has_files else tk.DISABLED)
        self._view.search_button.config(state=tk.NORMAL if has_files else tk.DISABLED)
        self._view.btn_export.config(state=tk.NORMAL if has_files else tk.DISABLED)
        for child in self._view.server_frame.winfo_children():
            child.config(state=tk.NORMAL if has_files else tk.DISABLED)

        if self._get_pending_json() is not None:
            self.try_finalize_loading()
        elif self._get_all_files():
            self.on_server_change()
            self._view.update_status_bar('status_bar_initial')
        else:
            self._view.update_status_bar('status_bar_initial')

    def on_server_change(self, force_fetch: bool = False, skip_filter: bool = False) -> None:
        if not self._get_db_analyzed() or not self._get_all_files():
            return

        server = self._server()

        if server == 'KR' and not self._get_kr_notice_shown():
            self._set_kr_notice_shown(True)
            lang_dict = self._lang_dict()
            title = lang_dict.get('msgbox_kr_server_notice_title', 'Korean Server Data Notice')
            msg = lang_dict.get(
                'msgbox_kr_server_notice_msg',
                'Data for the Korean server (KR) is only processed up to July 25, 2024.\n\n'
                'Stories added after this date may not display official titles or metadata.',
            )
            messagebox.showinfo(title, msg, parent=self._view)

        cache = self._get_server_titles_cache()
        if not force_fetch and server in cache and cache[server]:
            self._set_file_titles(dict(cache[server]))
            if not skip_filter:
                self._apply_filter()
            return

        db_info = self._server_db_info.get(server, {})

        filename_to_adv_id = {}
        for filename in self._get_all_files():
            match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
            if match:
                filename_to_adv_id[filename] = match.group(1)

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
                        aid: (self._get_file_voice_adv_ids().get(fn), self._get_file_situations().get(fn))
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
                    aid: (self._get_file_voice_adv_ids().get(fn), self._get_file_situations().get(fn))
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                fetched_titles.update(db_helper.fetch_event_top_adv_titles_batch(db_info, remaining_ids, eta_meta))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if ('hatsune_boss_table' in db_info or 'hatsune_special_battle_table' in db_info or 'event_list_table' in db_info) and remaining_ids:
                fetched_titles.update(db_helper.fetch_event_boss_battle_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if ('legion_special_battle_table' in db_info or 'byway_battle_quest_data_table' in db_info or 'baseline_dbs' in db_info or 'baseline_db_path' in db_info) and remaining_ids:
                fetched_titles.update(db_helper.fetch_legion_and_byway_battle_titles_batch(db_info, remaining_ids))
            remaining_ids = [aid for aid in adv_ids if aid not in fetched_titles]
            if remaining_ids:
                speaker_meta = {
                    aid: self._get_file_speakers().get(fn)
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                raw_titles_meta = {
                    aid: self._get_raw_file_titles().get(fn, "")
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                situation_meta = {
                    aid: self._get_file_situations().get(fn)
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                fetched_titles.update(db_helper.fetch_event_minigame_and_sub_scenes_batch(
                    db_info, remaining_ids, speaker_meta, raw_titles_meta, situation_meta
                ))

        for filename in self._get_all_files():
            adv_id = filename_to_adv_id.get(filename)
            title = fetched_titles.get(adv_id) if adv_id is not None else None  # type: ignore[assignment]
            if title is not None:
                self._get_file_titles()[filename] = title
            else:
                self._get_file_titles()[filename] = self._get_raw_file_titles().get(filename, filename)

        cache = self._get_server_titles_cache()
        cache[server] = dict(self._get_file_titles())
        self._set_server_titles_cache(cache)

        if not skip_filter:
            self._apply_filter()

    def load_and_analyze_thread(self, paths: Any, folder_path: Any, lang_dict: dict[str, str]) -> None:
        import re as _re
        temp_all_files, invalid_files = {}, []
        file_candidates: dict[str, Any] = {}
        pattern = _re.compile(r'^storydata_\d+\.json$')

        if paths:
            for path in paths:
                filename = os.path.basename(path)
                if pattern.match(filename):
                    if filename not in file_candidates:
                        file_candidates[filename] = []
                    file_candidates[filename].append(path)

        if folder_path:
            _MAX_WALK_FILES = 100000
            _MAX_WALK_DEPTH = 20
            _collected = 0
            for dirpath, dirnames, filenames in os.walk(folder_path):
                try:
                    rel = os.path.relpath(dirpath, folder_path)
                    depth = 0 if rel == '.' else rel.count(os.sep) + 1
                except ValueError:
                    depth = 0
                if depth > _MAX_WALK_DEPTH:
                    dirnames[:] = []
                    continue
                for filename in filenames:
                    if _collected >= _MAX_WALK_FILES:
                        break
                    if pattern.match(filename):
                        full_path = os.path.join(dirpath, filename)
                        if filename not in file_candidates:
                            file_candidates[filename] = []
                        file_candidates[filename].append(full_path)
                        _collected += 1
                if _collected >= _MAX_WALK_FILES:
                    break

        file_list_to_process = []
        for path_list in file_candidates.values():
            if len(path_list) > 1:
                try:
                    winner_path = max(path_list, key=os.path.getsize)
                    file_list_to_process.append(winner_path)
                except OSError:
                    pass
            elif path_list:
                file_list_to_process.append(path_list[0])

        file_list_to_process.sort()
        total_files = len(file_list_to_process)
        unique_char_names, unique_bgms, unique_bgs, unique_voices = set(), set(), set(), set()
        temp_file_titles, temp_raw_titles = {}, {}
        temp_file_situations, temp_file_outlines = {}, {}
        temp_file_voice_adv_ids = {}
        temp_file_speakers = {}

        for i, path in enumerate(file_list_to_process):
            def _update_status(idx: int = i, total: int = total_files) -> None:
                self._view.update_status_bar('status_bar_analyzing', i=idx+1, t=total)
            self._task_queue.put(ActionEvent(action=_update_status))
            is_valid, data, error_reason = StoryDataLoader.is_valid_storydata(path, lang_dict)

            if is_valid:
                filename = os.path.basename(path)
                temp_all_files[filename] = path

                frame0 = data.get('0', {}) if isinstance(data, dict) else {}
                json_title = str(frame0.get('title', '') or '').strip()
                situation = str(frame0.get('situation', '') or '').strip()
                outline = str(frame0.get('outline', '') or '').strip()

                for scene in (data.values() if isinstance(data, dict) else []):
                    if isinstance(scene, dict):
                        if not situation and (s := str(scene.get('situation', '') or '').strip()) and s != 'null':
                            situation = s
                        if not outline and (o := str(scene.get('outline', '') or '').strip()) and o != 'null':
                            outline = o
                        if not json_title and (t := str(scene.get('title', '') or '').strip()) and not t.isdigit() and not t.startswith('storydata_'):
                            json_title = t

                        if 'print' in scene and 'name' in scene['print'] and (name := str(scene['print']['name']).strip()):
                            unique_char_names.add(name)
                            if filename not in temp_file_speakers and name not in ['主人公', '{player_name}', '{0}', '???', '？？？', 'ナレーション', ''] and not (name.startswith('{') and name.endswith('}')):
                                temp_file_speakers[filename] = name
                        if 'bgm' in scene and (bgm_name := StoryDataLoader.extract_asset_name(scene['bgm'])):
                            unique_bgms.add(bgm_name)
                        if 'background' in scene and (bg_name := StoryDataLoader.extract_asset_name(scene['background'])):
                            unique_bgs.add(bg_name)
                        if 'vo' in scene and (vo_name := StoryDataLoader.extract_asset_name(scene['vo'])):
                            unique_voices.add(vo_name)
                            if filename not in temp_file_voice_adv_ids:
                                m = _re.search(r'vo_adv_(\d+)_', vo_name)
                                if m:
                                    temp_file_voice_adv_ids[filename] = m.group(1)

                if situation:
                    temp_file_situations[filename] = situation
                if outline:
                    temp_file_outlines[filename] = outline
                base_title = json_title if json_title else (situation if situation else filename)
                temp_raw_titles[filename] = base_title
                temp_file_titles[filename] = base_title
            else:
                invalid_files.append((path, error_reason))

        if not temp_all_files:
            self._task_queue.put(ActionEvent(action=lambda: self.finish_loading(None, invalid_files)))
            return

        temp_search_data = {
            'filenames': sorted(temp_all_files.keys()),
            'character_names': sorted(unique_char_names),
            'bgms': sorted(unique_bgms),
            'backgrounds': sorted(unique_bgs),
            'voices': sorted(unique_voices)
        }
        results = {
            "all_files": temp_all_files,
            "titles": temp_file_titles,
            "raw_titles": temp_raw_titles,
            "file_situations": temp_file_situations,
            "file_outlines": temp_file_outlines,
            "file_voice_adv_ids": temp_file_voice_adv_ids,
            "file_speakers": temp_file_speakers,
            "search_data": temp_search_data
        }
        self._task_queue.put(ActionEvent(action=lambda: self.finish_loading(results, invalid_files)))

    def finish_loading(self, results: Any, invalid_files: Any) -> None:
        lang_dict = self._lang_dict()
        if not results:
            self._set_is_loading(False)
            self._view.btn_open_file.config(state=tk.NORMAL)
            self._view.btn_open_folder.config(state=tk.NORMAL)
            self._view.update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(
                lang_dict.get('msgbox_no_valid_files_title', 'Notice'),
                lang_dict.get('msgbox_no_valid_files_msg', 'No valid storydata files found.'),
                parent=self._view,
            )
            if invalid_files:
                self.handle_invalid_files_log(invalid_files)
            self._set_pending_json(None)
            self._set_pending_invalid([])
            return

        self._set_pending_json(results)
        self._set_pending_invalid(invalid_files)
        self.try_finalize_loading()

    def try_finalize_loading(self) -> None:
        if self._get_pending_json() is None or not self._get_db_ready():
            return

        results = self._get_pending_json()
        invalid_files = self._get_pending_invalid()
        self._set_pending_json(None)
        self._set_pending_invalid([])

        self._set_is_loading(False)
        self._view.btn_open_file.config(state=tk.NORMAL)
        self._view.btn_open_folder.config(state=tk.NORMAL)

        if results is None:
            return
        self._set_all_files(results['all_files'])
        self._set_file_titles(results['titles'])
        self._set_raw_file_titles(results.get('raw_titles', {}))
        self._set_file_situations(results.get('file_situations', {}))
        self._set_file_outlines(results.get('file_outlines', {}))
        self._set_file_voice_adv_ids(results.get('file_voice_adv_ids', {}))
        self._set_file_speakers(results.get('file_speakers', {}))
        self._set_search_data(results['search_data'])
        self._set_loaded_filenames(sorted(self._get_all_files().keys()))
        self._set_base_search_files(list(self._get_loaded_filenames()))

        self._view.display_mode_combo.config(state="readonly")
        self._view.search_button.config(state=tk.NORMAL if self._get_all_files() else tk.DISABLED)
        self._view.btn_export.config(state=tk.NORMAL if self._get_all_files() else tk.DISABLED)
        self._view.jp_radio.config(state=tk.NORMAL)
        self._view.kr_radio.config(state=tk.NORMAL)

        self.on_server_change(force_fetch=True, skip_filter=True)

        self._apply_filter()

        self._view.update_status_bar('status_bar_loading_done', loaded=len(self._get_all_files()), failed=len(invalid_files))

        if invalid_files:
            self.handle_invalid_files_log(invalid_files)

    def handle_invalid_files_log(self, invalid_files: Any) -> None:
        lang_dict = self._lang_dict()
        try:
            from src.constants import APP_DEVELOPER, APP_LAST_UPDATE, APP_VERSION
            from src.utils.error_log import write_log_header

            app_base = self._base_path
            log_dir = Path(app_base) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime as _dt
            now = _dt.now()
            log_filename = log_dir / f"StoryViewerLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"

            app_info = {'APP_VERSION': APP_VERSION, 'APP_LAST_UPDATE': APP_LAST_UPDATE, 'APP_DEVELOPER': APP_DEVELOPER}
            extra_report = [f"[REPORT]  Total Failed:    {len(invalid_files)}"]

            with open(log_filename, 'w', encoding='utf-8') as f:
                now = write_log_header(f, "Invalid Storydata Load Log", app_base, app_info, extra_report)
                from src.utils.error_log import write_log_items
                write_log_items(f, invalid_files, item_label="File", item_header="[ERROR ITEM #{idx}]", timestamp=now, context="Storydata Validation", reason_fn=lambda item: item[1] if isinstance(item, (tuple, list)) else "Unknown")

            msg_fmt = lang_dict.get(
                'msgbox_load_fail_msg',
                "{count} file(s) were invalid and failed to load.\n\nThe detailed failure log has been automatically saved to:\n'{filename}'",
            )
            msg = msg_fmt.format(count=len(invalid_files), filename=str(log_filename))
            messagebox.showwarning(lang_dict.get('msgbox_load_fail_title', 'Load Failed'), msg, parent=self._view)
        except OSError as e:
            err_fmt = lang_dict.get('msgbox_log_save_error_msg', 'An error occurred while saving the log file:\n{e}')
            messagebox.showerror(lang_dict.get('msgbox_log_save_error_title', 'Log Save Error'), err_fmt.format(e=e), parent=self._view)
