"""Story Viewer 데이터베이스 질의 및 메타데이터 캐싱 서비스 모듈.

선택된 서버(JP, KR)의 master.db로부터 스토리 제목, 상황(Situation),
줄거리(Outline), 음성 ADV ID, 화자 정보 등을 쿼리하여 메모리에 캐싱하고,
서버 전환 시 메타데이터 재바인딩 처리.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox
from typing import Any

from src.utils.file_scan import iter_files
from src.utils.tk_safe import post_to_ui, post_to_ui_deferred
from src.story_viewer import db_helper
from src.story_viewer.logic import StoryDataLoader
from src.story_viewer.workspace_state import StoryWorkspaceState

logger = logging.getLogger(__name__)


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
        db_manager: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        workspace: StoryWorkspaceState,
        apply_filter: Callable[[], None],
        clear_workspace: Callable[[], None],
        get_loading_cancel_requested: Callable[[], bool] | None = None,
        shared_state: Any = None,
    ) -> None:
        self._view = view
        self._master = master
        self._base_path = base_path
        self._server_db_info = server_db_info
        self._server_var = server_var
        self._db_manager = db_manager
        self._get_lang_dict = get_lang_dict
        self._workspace = workspace
        self._apply_filter = apply_filter
        self._clear_workspace = clear_workspace
        self._get_loading_cancel_requested: Callable[[], bool] = get_loading_cancel_requested or (lambda: False)
        self._server_resolve_seq: int = 0
        # 진행 중인 서버 제목 해석: (서버, 요청 시점 파일 키 스냅샷) -> [순번, 필터 생략 여부].
        # 동일 요청이 이미 진행 중이면 중복 스레드 생성 대신 최신 순번/플래그로 갱신하여
        # 급격한 서버 전환 시 결과가 폐기되는 중복 질의를 방지.
        self._inflight_resolve: dict[tuple[str, frozenset[str]], list[Any]] = {}

    def _lang_dict(self) -> dict[str, str]:
        return self._get_lang_dict()

    def _server(self) -> str:
        return self._server_var.get()  # type: ignore[no-any-return]

    def _is_loading_cancelled(self) -> bool:
        """로딩 취소 요청 여부 반환 (백그라운드 워커 스레드 안전 조회)."""
        return bool(self._get_loading_cancel_requested())

    def start_db_analysis(self) -> None:
        self._view.update_status_bar('db_checking_msg')

        def _on_ready() -> None:
            # 메인 스레드에서 호출될 수 있으므로 다음 드레인 주기로 분리 실행
            post_to_ui_deferred(self.on_db_analyzed)

        self._db_manager.check_and_cache_db_status(on_ready=_on_ready)

    def on_db_analyzed(self) -> None:
        self._workspace.db_analyzed = True
        self._workspace.db_ready = True

        force_fetch = False
        if self._db_manager.has_updated_servers():
            updated = self._db_manager.consume_updated_servers()
            for s in updated:
                self._workspace.server_titles_cache.pop(s, None)
            self._workspace.file_titles.clear()
            force_fetch = True

        pending = self._workspace.pending_json_results
        has_files = bool(self._workspace.all_files or (pending and pending.get('all_files')))
        self._view.display_mode_combo.config(state="readonly" if has_files else tk.DISABLED)
        self._view.search_button.config(state=tk.NORMAL if has_files else tk.DISABLED)
        self._view.btn_export.config(state=tk.NORMAL if has_files else tk.DISABLED)
        for child in self._view.server_frame.winfo_children():
            child.config(state=tk.NORMAL if has_files else tk.DISABLED)

        if self._workspace.pending_json_results is not None:
            self.try_finalize_loading()
        elif self._workspace.all_files:
            self.on_server_change(force_fetch=force_fetch)
            self._view.update_status_bar('status_bar_initial')
        else:
            self._view.update_status_bar('status_bar_initial')

    def on_server_change(self, force_fetch: bool = False, skip_filter: bool = False) -> None:
        # 순번을 최상단에서 증가: 조기 반환(캐시 히트 등) 경로에서도 진행 중인
        # 이전 요청의 해석 결과가 새로 설정된 제목을 덮어쓰지 않도록 무효화.
        self._server_resolve_seq += 1

        if not self._workspace.db_analyzed or not self._workspace.all_files:
            return

        server = self._server()

        if server == 'KR' and not self._workspace.kr_notice_shown:
            self._workspace.kr_notice_shown = True
            lang_dict = self._lang_dict()
            title = lang_dict.get('msgbox_kr_server_notice_title', 'Korean Server Data Notice')
            msg = lang_dict.get(
                'msgbox_kr_server_notice_msg',
                'Data for the Korean server (KR) is only processed up to July 25, 2024.\n\n'
                'Stories added after this date may not display official titles or metadata.',
            )
            messagebox.showinfo(title, msg, parent=self._view)

        cache = self._workspace.server_titles_cache
        if not force_fetch and server in cache and cache[server]:
            self._workspace.file_titles = dict(cache[server])
            if not skip_filter:
                self._apply_filter()
            return

        self._start_server_title_resolution(server, self._workspace.all_files, skip_filter)

    def _start_server_title_resolution(self, server: str, all_files: dict[str, str], skip_filter: bool) -> None:
        """서버 전환 제목 해석(무거운 DB 조회)을 백그라운드 스레드에서 시작.

        메인 Tk 스레드 프리징 방지를 위해 DB 질의는 워커 스레드에서 수행하고,
        결과 반영(UI 갱신)만 태스크 큐를 통해 메인 스레드로 전달.
        순번(_server_resolve_seq)은 호출자(on_server_change)에서 이미 증가시킨 값을
        스냅샷하여 스테일 결과 판정 기준으로 사용.
        동일한 (서버, 파일 키 스냅샷) 해석이 이미 진행 중이면 스레드를 추가 생성하지 않고
        진행 중인 요청의 순번만 최신 값으로 갱신(결과 미폐기) 처리.

        Args:
            server: 대상 서버 키('JP', 'KR' 등).
            all_files: 파일명 -> 파일 경로 스냅샷 딕셔너리.
            skip_filter: 완료 후 필터/목록 갱신 생략 여부.
        """
        # 요청 시점 파일 키 스냅샷: 중복 요청 식별 및 반영 시점 워크스페이스 검증 기준.
        snapshot = frozenset(all_files.keys())
        key = (server, snapshot)

        # 진행 중 동일 요청 존재 시: 중복 스레드 생략, 최신 순번/플래그만 갱신.
        request = self._inflight_resolve.get(key)
        if request is not None:
            request[0] = self._server_resolve_seq
            request[1] = skip_filter
            return
        request = [self._server_resolve_seq, skip_filter]
        self._inflight_resolve[key] = request

        def _worker() -> None:
            try:
                titles = self._resolve_server_titles(server, all_files)
            except Exception:
                logger.exception("Server title resolution failed for %s", server)
                self._inflight_resolve.pop(key, None)
                if not skip_filter:
                    # 해석 실패 시에도 목록이 비어 보이지 않도록 기존 제목 기준 필터 갱신 예약.
                    post_to_ui(self._apply_filter)
                return

            def _apply() -> None:
                self._inflight_resolve.pop(key, None)
                latest_seq, latest_skip_filter = request[0], request[1]
                self._apply_resolved_titles(server, snapshot, titles, latest_skip_filter, latest_seq)

            post_to_ui(_apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _resolve_server_titles(self, server: str, all_files: dict[str, str]) -> dict[str, str]:
        """서버별 스토리 제목 해석 (무거운 DB 조회 전용, 워커 스레드 실행).

        Args:
            server: 대상 서버 키('JP', 'KR' 등).
            all_files: 파일명 -> 파일 경로 스냅샷 딕셔너리.

        Returns:
            dict[str, str]: 파일명 -> 해석된 표시 제목 매핑.
        """
        db_info = self._server_db_info.get(server, {})

        filename_to_adv_id = {}
        for filename in all_files:
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
                        aid: (self._workspace.file_voice_adv_ids.get(fn), self._workspace.file_situations.get(fn))
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
                    aid: (self._workspace.file_voice_adv_ids.get(fn), self._workspace.file_situations.get(fn))
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
                    aid: self._workspace.file_speakers.get(fn)
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                raw_titles_meta = {
                    aid: self._workspace.raw_file_titles.get(fn, "")
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                situation_meta = {
                    aid: self._workspace.file_situations.get(fn)
                    for fn, aid in filename_to_adv_id.items() if aid in remaining_ids
                }
                fetched_titles.update(db_helper.fetch_event_minigame_and_sub_scenes_batch(
                    db_info, remaining_ids, speaker_meta, raw_titles_meta, situation_meta
                ))

        raw_titles = self._workspace.raw_file_titles
        titles: dict[str, str] = {}
        for filename in all_files:
            adv_id = filename_to_adv_id.get(filename)
            title = fetched_titles.get(adv_id) if adv_id is not None else None
            if title is not None:
                titles[filename] = title
            else:
                titles[filename] = raw_titles.get(filename, filename)
        return titles

    def _apply_resolved_titles(self, server: str, snapshot: frozenset[str], titles: dict[str, str], skip_filter: bool, seq: int) -> None:
        """워커 스레드에서 해석된 제목을 메인 스레드에서 반영 (최신 요청만 적용).

        Args:
            server: 대상 서버 키('JP', 'KR' 등).
            snapshot: 요청 시점의 파일명 키 스냅샷 (워크스페이스 변경 판정용).
            titles: 해석된 파일명 -> 표시 제목 매핑.
            skip_filter: 필터/목록 갱신 생략 여부.
            seq: 서버 전환 요청 순번 (스테일 결과 무시용).
        """
        if seq != self._server_resolve_seq:
            return
        # all_files.clear() 같은 in-place 초기화(동일 객체 유지)도 감지하도록 키 스냅샷 비교.
        if frozenset(self._workspace.all_files.keys()) != snapshot:
            return
        self._workspace.file_titles.update(titles)
        cache = self._workspace.server_titles_cache
        cache[server] = dict(self._workspace.file_titles)
        self._workspace.server_titles_cache = cache
        if not skip_filter:
            self._apply_filter()

    def load_and_analyze_thread(self, paths: Any, folder_path: Any, lang_dict: dict[str, str]) -> None:
        """선택된 파일/폴더의 스토리 데이터를 백그라운드에서 로드/분석한다.

        워커 본체에서 예외가 발생하더라도 반드시 메인 스레드에 실패 통지를 예약하여
        UI 잠금(is_loading)이 영구적으로 남지 않도록 보장한다.

        Args:
            paths: 로드 대상 파일 경로 시퀀스 (없으면 None).
            folder_path: 재귀 탐색할 폴더 경로 (없으면 None).
            lang_dict: 현재 언어 번역 사전.
        """
        try:
            self._load_and_analyze_worker(paths, folder_path, lang_dict)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Story load worker aborted: %s", exc)
            error = exc
            try:
                post_to_ui(lambda: self.fail_loading(error))
            except (OSError, EOFError, RuntimeError, ValueError) as queue_exc:
                logger.debug("Failed to enqueue load failure handler: %s", queue_exc)

    def _load_and_analyze_worker(self, paths: Any, folder_path: Any, lang_dict: dict[str, str]) -> None:
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
            for full_path in iter_files(
                folder_path,
                predicate=lambda name: bool(pattern.match(name)),
                max_files=100000,
                cancel=self._is_loading_cancelled,
            ):
                filename = os.path.basename(full_path)
                if filename not in file_candidates:
                    file_candidates[filename] = []
                file_candidates[filename].append(full_path)
            if self._is_loading_cancelled():
                return

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
            if self._is_loading_cancelled():
                return
            try:
                def _update_status(idx: int = i, total: int = total_files) -> None:
                    self._view.update_status_bar('status_bar_analyzing', i=idx+1, t=total)
                post_to_ui(_update_status)
                is_valid, data, error_reason = StoryDataLoader.is_valid_storydata(path, lang_dict)

                if is_valid:
                    filename = os.path.basename(path)
                    temp_all_files[filename] = path

                    frame0 = data.get('0', {}) if isinstance(data, dict) else {}
                    json_title = str(frame0.get('title', '') or '').strip()
                    situation = str(frame0.get('situation', '') or '').strip()
                    outline = str(frame0.get('outline', '') or '').strip()

                    for scene in (data.values() if isinstance(data, dict) else []):
                        if self._is_loading_cancelled():
                            return
                        if isinstance(scene, dict):
                            if not situation and (s := str(scene.get('situation', '') or '').strip()) and s != 'null':
                                situation = s
                            if not outline and (o := str(scene.get('outline', '') or '').strip()) and o != 'null':
                                outline = o
                            if not json_title and (t := str(scene.get('title', '') or '').strip()) and not t.isdigit() and not t.startswith('storydata_'):
                                json_title = t

                            print_data = scene.get('print')
                            if isinstance(print_data, dict) and (name := str(print_data.get('name', '')).strip()):
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
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to analyze storydata file %s: %s", path, exc)
                temp_all_files.pop(os.path.basename(path), None)
                invalid_files.append((path, str(exc)))

        if not temp_all_files:
            post_to_ui(lambda: self.finish_loading(None, invalid_files))
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
        post_to_ui(lambda: self.finish_loading(results, invalid_files))

    def fail_loading(self, error: BaseException) -> None:
        """로더 치명 오류 시 UI 잠금 해제 및 사용자 통지 (메인 스레드에서 실행).

        Args:
            error: 로더 워커에서 발생한 예외.
        """
        lang_dict = self._lang_dict()
        self._workspace.is_loading = False
        self._workspace.pending_json_results = None
        self._workspace.pending_invalid_files = []
        self._view.btn_open_file.config(state=tk.NORMAL)
        self._view.btn_open_folder.config(state=tk.NORMAL)
        self._view.update_status_bar('status_bar_loading_done', loaded=0, failed=0)
        messagebox.showerror(
            lang_dict.get('msgbox_load_error_title', 'Load Error'),
            lang_dict.get('msgbox_load_error_msg', 'An error occurred while loading story data.\n\n{error}').format(error=error),
            parent=self._view,
        )

    def finish_loading(self, results: Any, invalid_files: Any) -> None:
        lang_dict = self._lang_dict()
        if not results:
            self._workspace.is_loading = False
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
            self._workspace.pending_json_results = None
            self._workspace.pending_invalid_files = []
            return

        self._workspace.pending_json_results = results
        self._workspace.pending_invalid_files = invalid_files
        self.try_finalize_loading()

    def try_finalize_loading(self) -> None:
        if self._workspace.pending_json_results is None or not self._workspace.db_ready:
            return

        results = self._workspace.pending_json_results
        invalid_files = self._workspace.pending_invalid_files
        self._workspace.pending_json_results = None
        self._workspace.pending_invalid_files = []

        self._workspace.is_loading = False
        self._view.btn_open_file.config(state=tk.NORMAL)
        self._view.btn_open_folder.config(state=tk.NORMAL)

        if results is None:
            return
        self._workspace.all_files = results['all_files']
        self._workspace.file_titles = results['titles']
        self._workspace.raw_file_titles = results.get('raw_titles', {})
        self._workspace.file_situations = results.get('file_situations', {})
        self._workspace.file_outlines = results.get('file_outlines', {})
        self._workspace.file_voice_adv_ids = results.get('file_voice_adv_ids', {})
        self._workspace.file_speakers = results.get('file_speakers', {})
        self._workspace.search_data = results['search_data']
        self._workspace.loaded_filenames = sorted(self._workspace.all_files.keys())
        self._workspace.base_search_files = list(self._workspace.loaded_filenames)

        self._view.display_mode_combo.config(state="readonly")
        self._view.search_button.config(state=tk.NORMAL if self._workspace.all_files else tk.DISABLED)
        self._view.btn_export.config(state=tk.NORMAL if self._workspace.all_files else tk.DISABLED)
        self._view.jp_radio.config(state=tk.NORMAL)
        self._view.kr_radio.config(state=tk.NORMAL)

        # 제목 해석은 워커 스레드에서 수행되며 완료 시 _apply_resolved_titles가 필터를 갱신.
        self.on_server_change(force_fetch=True, skip_filter=False)

        self._view.update_status_bar('status_bar_loading_done', loaded=len(self._workspace.all_files), failed=len(invalid_files))

        if invalid_files:
            self.handle_invalid_files_log(invalid_files)

    def handle_invalid_files_log(self, invalid_files: Any) -> None:
        lang_dict = self._lang_dict()
        try:
            from src.utils.error_log import open_task_log, write_log_items

            app_base = self._base_path
            extra_report = [f"[REPORT]  Total Failed:    {len(invalid_files)}"]
            opened = open_task_log("StoryViewerLog", "Invalid Storydata Load Log", app_base, extra_report)
            if opened is None:
                return
            log_filename, f, now_ts = opened
            try:
                write_log_items(
                    f,
                    invalid_files,
                    item_header="[ERROR ITEM #{idx}]",
                    timestamp=now_ts,
                    context="Storydata Validation",
                    message_fn=lambda item: item[1] if isinstance(item, (tuple, list)) else "Unknown",
                )
            finally:
                f.close()

            msg_fmt = lang_dict.get(
                'msgbox_load_fail_msg',
                "{count} file(s) were invalid and failed to load.\n\nThe detailed failure log has been automatically saved to:\n'{filename}'",
            )
            msg = msg_fmt.format(count=len(invalid_files), filename=str(log_filename))
            messagebox.showwarning(lang_dict.get('msgbox_load_fail_title', 'Load Failed'), msg, parent=self._view)
        except OSError as e:
            err_fmt = lang_dict.get('msgbox_log_save_error_msg', 'An error occurred while saving the log file:\n{e}')
            messagebox.showerror(lang_dict.get('msgbox_log_save_error_title', 'Log Save Error'), err_fmt.format(e=e), parent=self._view)
