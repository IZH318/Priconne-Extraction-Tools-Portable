"""Story Viewer의 SQLite 데이터베이스 다운로드 및 무결성 관리자 모듈.

서버별(JP, KR, EN/GL, TW, CN 등) master.db의 로컬 존재 여부 및 PRAGMA integrity_check,
원격 GitHub API를 통한 최신 DB 버전 점검, 백그라운드 다운로드 진행 대화상자(Toplevel)
제공 및 SQLite 헤더 검증.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from src.exceptions import DatabaseIntegrityError
from src.queue_events import ActionEvent

if TYPE_CHECKING:
    from .view import StoryViewerView

logger = logging.getLogger(__name__)

# 데이터베이스(SQLite) 파일 식별 매직 바이트 (16바이트 헤더)
_SQLITE_MAGIC = b'SQLite format 3\x00'


class StoryDBManager:
    """Story Viewer DB 다운로드, 무결성 검사 및 업데이트 관리자.

    서버별 SQLite DB 파일의 로컬 유효성을 검증하고,
    필요 시 모달 창을 띄워 비동기 다운로드 진행.

    Attributes:
        _master (tk.Tk | tk.Toplevel): 최상위 Tkinter 윈도우.
        _server_db_info (dict[str, Any]): 서버별 DB 파일 경로 및 원격 URL 정보 딕셔너리.
        _get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _task_queue (queue.Queue[ActionEvent]): 메인 스레드 액션 전달 큐.
        _view (StoryViewerView): 스토리 뷰어 GUI 인스턴스.
        _get_all_files (Callable[[], dict[str, str]]): 메모리에 로드된 전체 파일 맵 조회 콜백.
        db_status (dict[str, bool]): 서버별 DB 준비 완료 여부 플래그 맵.
        db_check_done (bool): 전체 DB 점검 완료 여부.
        db_warning_shown (bool): DB 누락 경고 대화상자 기표시 여부.
    """

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        server_db_info: dict[str, Any],
        get_lang_dict: Callable[[], dict[str, str]],
        task_queue: queue.Queue[ActionEvent],
        view: StoryViewerView,
        get_all_files: Callable[[], dict[str, str]],
    ) -> None:
        """StoryDBManager 인스턴스 초기화.

        Args:
            master (tk.Tk | tk.Toplevel): 최상위 Tk 윈도우 (다이얼로그 위치 기준).
            server_db_info (dict[str, Any]): 서버별 DB 테이블/컬럼 매핑 정보.
            get_lang_dict (Callable[[], dict[str, str]]): 현재 언어 딕셔너리를 반환하는 콜백.
            task_queue (queue.Queue[ActionEvent]): 메인 스레드로 액션을 전달할 큐.
            view (StoryViewerView): StoryViewerView 인스턴스 (UI 조작용).
            get_all_files (Callable[[], dict[str, str]]): 로드된 파일 딕셔너리를 반환하는 콜백.
        """
        self._master = master
        self._server_db_info = server_db_info
        self._get_lang_dict = get_lang_dict
        self._task_queue = task_queue
        self._view = view
        self._get_all_files = get_all_files
        self.db_status: dict[str, bool] = {}
        self.db_check_done: bool = False
        self.db_warning_shown: bool = False


    def check_and_cache_db_status(self, on_ready: Callable[..., Any] | None = None) -> None:
        """서버별 SQLite DB 파일 존재 여부 및 업데이트 확인/캐싱.

        Args:
            on_ready: 검사 및 다운로드 완료 후 실행할 콜백 함수.
        """
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root_dir = os.path.dirname(src_dir)

        if self.db_check_done:
            missing = False
            stale = False
            for server, info in self._server_db_info.items():
                if isinstance(info, dict) and 'db_path' in info and self.db_status.get(server, False):
                    db_path = os.path.join(root_dir, info['db_path'])
                    if not os.path.exists(db_path):
                        missing = True
                        break
                    # 캐시/만료 항목 대상 무결성 재검사 (Recheck integrity)
                    try:
                        import sqlite3
                        with contextlib.closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as _conn:
                            _res = _conn.execute("PRAGMA integrity_check").fetchone()
                            if not _res or _res[0] != "ok":
                                stale = True
                                break
                    except (sqlite3.Error, OSError):
                        stale = True
                        break
            if not missing and not stale:
                if on_ready is not None:
                    on_ready()
                return
            else:
                self.db_check_done = False
                self.db_warning_shown = False

        lang_dict = self._get_lang_dict()

        self._view.set_action_buttons_state("disabled")

        top = tk.Toplevel(self._master)
        top.withdraw()
        top.title(lang_dict.get('db_checking_title', 'DB Analysis'))

        top.update_idletasks()
        w, h = 360, 105
        x = (top.winfo_screenwidth() // 2) - (w // 2)
        y = (top.winfo_screenheight() // 2) - (h // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.resizable(False, False)

        top.transient(self._master)
        top.grab_set()

        def _on_check_window_close() -> None:
            try:
                if top.winfo_exists():
                    top.grab_release()
                    top.destroy()
            except tk.TclError:
                pass
        top.protocol("WM_DELETE_WINDOW", _on_check_window_close)

        main_frame = ttk.Frame(top, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        lbl = ttk.Label(main_frame, text=lang_dict.get('db_checking_msg', "Checking for updates and parsing schemas..."), anchor="center", justify="center")
        lbl.pack(fill=tk.X, pady=(10, 12))
        pb = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        pb.pack(fill=tk.X, padx=15, pady=(0, 10))
        pb['value'] = 0
        top.deiconify()

        def _safe_update_ui(val: float | None = None, text: str | None = None) -> None:
            def _task() -> None:
                try:
                    if top.winfo_exists():
                        if val is not None and pb.winfo_exists():
                            pb.configure(value=val)
                        if text is not None and lbl.winfo_exists():
                            lbl.configure(text=text)
                except tk.TclError:
                    pass
            try:
                if top.winfo_exists():
                    top.after(0, _task)
            except tk.TclError:
                pass

        def _check_thread() -> None:
            import json
            try:
                local_version_path = os.path.join(root_dir, "version.json")
                local_version_data = {}
                if os.path.exists(local_version_path):
                    try:
                        with open(local_version_path, encoding="utf-8") as f:
                            local_version_data = json.load(f)
                    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                        logger.debug("Failed to read local version.json: %s", exc)

                common_config = self._server_db_info.get("Common", {})
                api_url = common_config.get("version_api_url", "https://api.github.com/repos/Expugn/priconne-database/contents/version.json")
                raw_url = common_config.get("version_raw_url", "https://raw.githubusercontent.com/Expugn/priconne-database/master/version.json")

                remote_version_data = {}
                try:
                    # 1순위: GitHub API (캐시 무시, 항상 최신 버전 보장)
                    api_req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(api_req, timeout=5) as response:
                        import base64
                        data = json.loads(response.read().decode('utf-8'))
                        content = data.get('content') if isinstance(data, dict) else None
                        if not content:
                            raise ValueError("Missing content in GitHub API response")
                        remote_version_data = json.loads(base64.b64decode(content).decode('utf-8'))
                except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError, OSError):
                    try:
                        # 2순위: Raw URL (API 제한 시 fallback, 5분 캐시 있음)
                        req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=5) as response:
                            remote_version_data = json.loads(response.read().decode('utf-8'))
                    except (urllib.error.URLError, json.JSONDecodeError, ValueError, OSError) as e:
                        log_msg = lang_dict.get('log_remote_version_fail', 'Failed to check remote version.json: {e}').format(e=e)
                        logger.warning("%s", log_msg)

                _safe_update_ui(val=10)

                missing_db_files = [] # 누락 메시지용 문자열 리스트
                downloads_list = []   # (url, dest_path, dest_filename) 튜플 리스트

                from .schema_resolver import COLUMN_MAPPINGS

                tag_missing = lang_dict.get('tag_missing', '[Missing] ')
                tag_update = lang_dict.get('tag_update', '[Update] ')
                is_feature_completely_unavailable = False

                # 서버 간 전체 테이블 수 동적 계산 (Calculate total tables)
                total_steps = 0
                for i in self._server_db_info.values():
                    if isinstance(i, dict) and 'db_path' in i:
                        total_steps += sum(1 for t in COLUMN_MAPPINGS if i.get(t))
                total_steps = max(1, total_steps)
                step_size = 90 / total_steps
                current_progress: float = 10

                def on_table_progress(server_key: str, table_key: str) -> None:
                    nonlocal current_progress
                    current_progress += step_size
                    fmt_str = lang_dict.get('db_parsing_table', '{server} schema resolved: {table}')
                    msg = fmt_str.format(server=server_key, table=table_key)
                    _safe_update_ui(val=current_progress, text=msg)

                for server, info in self._server_db_info.items():
                    if not isinstance(info, dict) or 'db_path' not in info:
                        continue

                    db_path = os.path.join(root_dir, info['db_path'])
                    b_default_fname = (
                        info.get('baseline_dbs', {}).get('default', {}).get('db_path', '')
                        if isinstance(info.get('baseline_dbs'), dict)
                        else ''
                    )
                    _baseline_fname = b_default_fname or info.get('baseline_db_path', '')
                    baseline_path = os.path.join(src_dir, _baseline_fname) if _baseline_fname else None

                    # 기준점(Baseline) 확인 (파일 존재 여부 및 유효성 검사)
                    baseline_dbs = info.get('baseline_dbs')
                    if isinstance(baseline_dbs, dict) and baseline_dbs:
                        for b_item in baseline_dbs.values():
                            b_fname = b_item.get('db_path', '')
                            b_url = b_item.get('db_url', '')
                            b_full_path = os.path.join(src_dir, b_fname)
                            if b_fname and not os.path.exists(b_full_path):
                                missing_db_files.append(f"{tag_missing}src/{b_fname}")
                                if b_url:
                                    downloads_list.append((b_url, b_full_path, b_fname))
                    else:
                        if not baseline_path or not os.path.exists(baseline_path):
                            missing_db_files.append(f"{tag_missing}src/{info.get('baseline_db_path', '')}")
                            if info.get('baseline_db_url'):
                                downloads_list.append((info.get('baseline_db_url', ''), baseline_path or '', info.get('baseline_db_path', '')))

                    # 선택된 버전 DB 확인 및 다운로드 목록 구성
                    needs_latest = False
                    if not os.path.exists(db_path):
                        needs_latest = True
                        missing_db_files.append(f"{tag_missing}{info['db_path']}")
                    else:
                        v_key = info.get('version_key', '')
                        if v_key and remote_version_data.get(v_key):
                            remote_v = remote_version_data[v_key].get('version', 0)
                            local_v = local_version_data.get(v_key, {}).get('version', 0)
                            if remote_v != 0 and remote_v != local_v:
                                needs_latest = True
                                missing_db_files.append(f"{tag_update}{info['db_path']}")

                    if needs_latest:
                        downloads_list.append((info.get('db_url', ''), db_path, info['db_path']))

                    baseline_dbs = info.get('baseline_dbs')
                    if isinstance(baseline_dbs, dict) and baseline_dbs:
                        has_fallback = all(
                            os.path.isfile(os.path.join(src_dir, b.get('db_path', '')))
                            for b in baseline_dbs.values()
                            if b.get('db_path')
                        )
                    else:
                        has_fallback = bool(baseline_path) and os.path.isfile(baseline_path or '')
                    self.db_status[server] = os.path.exists(db_path)

                    if not has_fallback:
                        is_feature_completely_unavailable = True

                from .schema_resolver import resolve_all_servers_parallel
                resolve_all_servers_parallel(self._server_db_info, root_dir, src_dir, progress_callback=on_table_progress)
                _safe_update_ui(val=100)

                self._task_queue.put(ActionEvent(action=lambda: self._on_check_complete(top, downloads_list, remote_version_data, local_version_path, missing_db_files, on_ready, lang_dict, is_feature_completely_unavailable)))
            except Exception:
                logger.exception("Unexpected error in _check_thread")
                def _handle_check_error() -> None:
                    try:
                        if top.winfo_exists():
                            top.grab_release()
                            top.destroy()
                    except tk.TclError:
                        pass
                    self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
                    if on_ready is not None:
                        on_ready()
                self._task_queue.put(ActionEvent(action=_handle_check_error))

        threading.Thread(target=_check_thread, daemon=True).start()

    def _on_check_complete(self, top: tk.Toplevel, downloads_list: list, remote_version_data: dict, local_version_path: str, missing_db_files: list, on_ready: Callable[..., Any] | None, lang_dict: dict, is_feature_completely_unavailable: bool) -> None:
        """백그라운드 버전 검사 완료 후 UI 업데이트 처리."""
        try:
            if top.winfo_exists():
                top.grab_release()
                top.destroy()
        except tk.TclError:
            pass
        if downloads_list and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_files)
            restriction_msg = (
                lang_dict.get(
                    'db_prompt_restriction_unavailable',
                    "(If you don't download, the 'Event Story Search' feature will be unavailable.)",
                )
                if is_feature_completely_unavailable
                else lang_dict.get(
                    'db_prompt_restriction_outdated',
                    "(If you don't download, the feature is still usable, but recent events may not be searched correctly.)",
                )
            )
            prompt_msg = lang_dict.get(
                'db_download_prompt_msg',
                'Updates or missing database files found:\n\n{paths}\n\nDo you want to automatically download them now?\n{restriction_msg}',
            ).format(paths=paths_str, restriction_msg=restriction_msg)

            if messagebox.askyesno(
                lang_dict.get('db_download_prompt_title', 'Download DB Files'),
                prompt_msg,
                parent=self._master
            ):
                self._start_db_download(downloads_list, remote_version_data, local_version_path, on_ready)
            else:
                self._show_offline_warning(paths_str, lang_dict, reason='cancel', is_feature_completely_unavailable=is_feature_completely_unavailable)
                self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
                if on_ready is not None:
                    on_ready()
        else:
            self.db_check_done = True
            self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
            if on_ready is not None:
                on_ready()

    def _show_offline_warning(self, paths_str: str, lang_dict: dict[str, str], reason: str = 'offline', is_feature_completely_unavailable: bool = True) -> None:
        """오프라인 상태 또는 다운로드 취소 시 경고 메시지 표시.

        Args:
            paths_str: 누락된 DB 파일 경로 목록 문자열.
            lang_dict: 다국어 딕셔너리.
            reason: 경고 발생 이유 ('offline' 또는 'cancel').
            is_feature_completely_unavailable: 기능 사용 완전 제한 여부.
        """
        tag_missing = lang_dict.get('tag_missing', '[Missing] ')
        tag_update = lang_dict.get('tag_update', '[Update] ')
        has_missing = tag_missing in paths_str
        has_update = tag_update in paths_str

        if has_missing and has_update:
            title_key = 'db_mixed_title'
            msg_key = 'db_mixed_msg_unavailable' if is_feature_completely_unavailable else 'db_mixed_msg_outdated'
        elif has_update:
            title_key = 'db_outdated_title'
            msg_key = 'db_outdated_msg'
        else:
            title_key = 'db_not_found_title'
            msg_key = 'db_not_found_msg'

        if reason == 'cancel':
            extra_msg = (
                lang_dict.get(
                    'db_download_cancel_msg_unavailable',
                    "To use the 'Event Story Search' feature, restart the program to automatically download the files (recommended), "
                    "or manually download them from the link below and place them in the correct folders:\n\n"
                    "[Program Folder]\n ├─ master_jp.db\n ├─ master_kr.db\n └─ [src]\n"
                    "     ├─ master_jp_10052900.db\n     ├─ master_jp_10061600.db\n     └─ master_kr_10049000.db\n\n"
                    "https://github.com/Expugn/priconne-database",
                )
                if is_feature_completely_unavailable
                else lang_dict.get(
                    'db_download_cancel_msg_outdated',
                    "For the latest event story search, it is recommended to restart the program later to automatically download the files, "
                    "or manually download them from the link below and place them in the correct folders:\n\n"
                    "[Program Folder]\n ├─ master_jp.db\n ├─ master_kr.db\n └─ [src]\n"
                    "     ├─ master_jp_10052900.db\n     ├─ master_jp_10061600.db\n     └─ master_kr_10049000.db\n\n"
                    "https://github.com/Expugn/priconne-database",
                )
            )
        else:
            extra_msg = (
                lang_dict.get(
                    'db_download_offline_msg_unavailable',
                    "No internet connection or download failed.\n\n"
                    "To use the 'Event Story Search' feature, please download the files manually from the link below and place them in the correct folders:\n\n"
                    "[Program Folder]\n ├─ master_jp.db\n ├─ master_kr.db\n └─ [src]\n"
                    "     ├─ master_jp_10052900.db\n     ├─ master_jp_10061600.db\n     └─ master_kr_10049000.db\n\n"
                    "https://github.com/Expugn/priconne-database",
                )
                if is_feature_completely_unavailable
                else lang_dict.get(
                    'db_download_offline_msg_outdated',
                    "No internet connection or download failed.\n\n"
                    "For the latest event story search, please download the files manually from the link below and place them in the correct folders:\n\n"
                    "[Program Folder]\n ├─ master_jp.db\n ├─ master_kr.db\n └─ [src]\n"
                    "     ├─ master_jp_10052900.db\n     ├─ master_jp_10061600.db\n     └─ master_kr_10049000.db\n\n"
                    "https://github.com/Expugn/priconne-database",
                )
            )

        messagebox.showwarning(
            lang_dict.get(title_key, 'DB Not Found'),
            lang_dict.get(msg_key, '{paths}').format(paths=paths_str) + "\n\n" + extra_msg,
            parent=self._master
        )
        self.db_warning_shown = True

    def _start_db_download(self, downloads_list: list[tuple[str, str, str]], remote_version_data: dict, local_version_path: str, on_ready: Callable[..., Any] | None = None) -> None:
        """누락된 DB 파일의 백그라운드 다운로드 시작.

        Args:
            downloads_list: (다운로드 URL, 저장 경로, 파일명) 형태의 튜플 리스트.
            remote_version_data: 원격지에서 가져온 version.json 데이터.
            local_version_path: 로컬 version.json 파일 저장 경로.
        """
        lang_dict = self._get_lang_dict()
        self._view.set_action_buttons_state("disabled")

        top = tk.Toplevel(self._master)
        top.withdraw()
        top.title(lang_dict.get('db_download_prompt_title', 'Download DB Files'))

        # 화면 가운데 표시
        top.update_idletasks()
        w, h = 360, 105
        x = (top.winfo_screenwidth() // 2) - (w // 2)
        y = (top.winfo_screenheight() // 2) - (h // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.resizable(False, False)

        top.transient(self._master)
        top.grab_set()

        def _on_download_window_close() -> None:
            try:
                if top.winfo_exists():
                    top.grab_release()
                    top.destroy()
            except tk.TclError:
                pass
        top.protocol("WM_DELETE_WINDOW", _on_download_window_close)

        main_frame = ttk.Frame(top, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        lbl = ttk.Label(main_frame, text=lang_dict.get('db_downloading_msg', "Downloading..."), anchor="center", justify="center")
        lbl.pack(fill=tk.X, pady=(10, 12))
        pb = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        pb.pack(fill=tk.X, padx=15, pady=(0, 10))
        pb['value'] = 0
        top.deiconify()

        def _safe_download_update(val: float) -> None:
            def _task(p: float = val) -> None:
                try:
                    if top.winfo_exists() and pb.winfo_exists():
                        pb.configure(value=p)
                except tk.TclError:
                    pass
            try:
                if top.winfo_exists():
                    top.after(0, _task)
            except tk.TclError:
                pass

        def _download_thread() -> None:
            import json
            import urllib.request
            try:
                total_files = len(downloads_list)
                for file_idx, (url, dest_path, fname) in enumerate(downloads_list):
                    if not url:
                        continue
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=30) as response:
                        total_size = response.getheader('content-length')
                        total_size = int(total_size) if total_size else 0
                        downloaded = 0
                        temp_dest_path = f"{dest_path}.tmp"
                        try:
                            with open(temp_dest_path, 'wb') as out_file:
                                while True:
                                    chunk = response.read(16 * 1024)
                                    if not chunk:
                                        break
                                    out_file.write(chunk)
                                    downloaded += len(chunk)
                                    file_prog = (downloaded / total_size * 100) if total_size > 0 else 100
                                    overall_prog = ((file_idx * 100) + file_prog) / max(1, total_files)
                                    _safe_download_update(overall_prog)

                            # 다운로드된 파일의 SQLite DB 유효성 검증
                            with open(temp_dest_path, 'rb') as db_file:
                                header = db_file.read(16)
                            if header != _SQLITE_MAGIC:
                                raise DatabaseIntegrityError(fname, "header mismatch")

                            # 데이터베이스(SQLite) 무결성 검사 실행
                            import sqlite3
                            try:
                                with contextlib.closing(sqlite3.connect(f"file:{temp_dest_path}?mode=ro", uri=True)) as _conn:
                                    _res = _conn.execute("PRAGMA integrity_check").fetchone()
                                    if not _res or _res[0] != "ok":
                                        raise DatabaseIntegrityError(fname, f"integrity check failed: {_res}")
                            except sqlite3.Error as _ie:
                                raise DatabaseIntegrityError(fname, f"integrity check error: {_ie}") from _ie

                            os.replace(temp_dest_path, dest_path)
                        finally:
                            if os.path.exists(temp_dest_path):
                                try:
                                    os.remove(temp_dest_path)
                                except OSError:
                                    pass

                # 모든 다운로드가 성공적으로 완료된 후 version.json 업데이트
                if remote_version_data:
                    with open(local_version_path, "w", encoding="utf-8") as f:
                        json.dump(remote_version_data, f, ensure_ascii=False, indent=4)

                self._task_queue.put(ActionEvent(action=lambda: self._on_download_success(top, on_ready)))
            except Exception as e:
                logger.exception("DB download failed")
                def _on_err(err: Any = e) -> None:
                    self._on_download_error(top, err)
                self._task_queue.put(ActionEvent(action=_on_err))

        t = threading.Thread(target=_download_thread, daemon=True)
        t.start()

    def _on_download_success(self, top: tk.Toplevel, on_ready: Callable[..., Any] | None) -> None:
        """DB 다운로드 성공 시 UI 상태 갱신.

        Args:
            top: 다운로드 진행 상태 대화상자 객체.
            on_ready: 자동 실행 콜백 함수.
        """
        try:
            if top.winfo_exists():
                top.grab_release()
                top.destroy()
        except tk.TclError:
            pass
        lang_dict = self._get_lang_dict()
        messagebox.showinfo(lang_dict.get('db_download_prompt_title', 'Download DB Files'), lang_dict.get('db_download_success_msg', 'Database files have been downloaded successfully.'), parent=self._master)
        self.db_warning_shown = False
        self.db_check_done = False
        self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")

        # 다운로드가 완료되었으므로 check를 다시 호출하면 on_ready가 실행됨
        self.check_and_cache_db_status(on_ready)

    def _on_download_error(self, top: tk.Toplevel, err: Exception) -> None:
        """DB 다운로드 실패 시 에러 메시지 표시.

        Args:
            top: 다운로드 진행 상태 대화상자 객체.
            err: 발생한 예외 객체.
        """
        try:
            if top.winfo_exists():
                top.grab_release()
                top.destroy()
        except tk.TclError:
            pass
        lang_dict = self._get_lang_dict()
        err_msg = lang_dict.get('db_download_error_msg', 'An error occurred during database download:\n{err}').format(err=err)
        messagebox.showerror(lang_dict.get('db_download_error_title', 'Download Error'), err_msg, parent=self._master)
        self.db_check_done = True
        self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
