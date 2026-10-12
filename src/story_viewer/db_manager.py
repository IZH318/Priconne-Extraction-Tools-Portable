from __future__ import annotations
import os
import shutil
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, TYPE_CHECKING
from urllib.parse import urlparse
import queue

from src.constants import DB_DOWNLOAD_BASE_URL
from src.queue_events import ActionEvent
from src.exceptions import DatabaseIntegrityError

if TYPE_CHECKING:
    from .view import StoryViewerView

# SQLite 파일 식별을 위한 매직 바이트 (16바이트 헤더)
_SQLITE_MAGIC = b'SQLite format 3\x00'


class StoryDBManager:
    """Story Viewer의 DB 다운로드 및 상태 관리를 전담하는 클래스입니다.

    서버별 SQLite DB 파일의 존재 여부 확인, 자동 다운로드,
    무결성 검증 등을 담당합니다.

    Note:
        Controller와의 순환 참조를 방지하기 위해, Controller 전체를 참조하지 않고
        필요한 콜백과 데이터 접근자만 개별 인자로 주입받습니다.
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
        """StoryDBManager를 초기화합니다.

        Args:
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            server_db_info: 서버별 DB 테이블/컬럼 매핑 정보.
            get_lang_dict: 현재 언어 딕셔너리를 반환하는 콜백.
            task_queue: 메인 스레드로 액션을 전달할 큐.
            view: StoryViewerView 인스턴스 (UI 조작용).
            get_all_files: 로드된 파일 딕셔너리를 반환하는 콜백.
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

    def check_and_cache_db_status(self, on_ready: callable = None) -> None:
        """서버별 SQLite DB 파일의 존재 여부 및 업데이트를 확인하고 캐시합니다.
        
        Args:
            on_ready: 검사 및 다운로드가 모두 끝난 후 실행할 콜백 함수.
        """
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root_dir = os.path.dirname(src_dir)
        
        if self.db_check_done:
            missing = False
            for server, info in self._server_db_info.items():
                if isinstance(info, dict) and 'db_path' in info:
                    if self.db_status.get(server, False):
                        db_path = os.path.join(root_dir, info['db_path'])
                        if not os.path.exists(db_path):
                            missing = True
                            break
            if not missing:
                if on_ready:
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
        w, h = 340, 100
        x = (top.winfo_screenwidth() // 2) - (w // 2)
        y = (top.winfo_screenheight() // 2) - (h // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.resizable(False, False)
        
        top.transient(self._master)
        top.grab_set()
        lbl = ttk.Label(top, text=lang_dict.get('db_checking_msg', "Checking for updates and parsing schemas..."))
        lbl.pack(pady=10)
        pb = ttk.Progressbar(top, mode='determinate', maximum=100)
        pb.pack(fill=tk.X, padx=20)
        pb['value'] = 0
        top.deiconify()
        
        def _check_thread():
            import urllib.request
            import json
            import logging
            
            local_version_path = os.path.join(root_dir, "version.json")
            local_version_data = {}
            if os.path.exists(local_version_path):
                try:
                    with open(local_version_path, "r", encoding="utf-8") as f:
                        local_version_data = json.load(f)
                except Exception:
                    pass
                    
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
                    remote_version_data = json.loads(base64.b64decode(data['content']).decode('utf-8'))
            except Exception:
                try:
                    # 2순위: Raw URL (API 제한 시 fallback, 5분 캐시 있음)
                    req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        remote_version_data = json.loads(response.read().decode('utf-8'))
                except Exception as e:
                    log_msg = lang_dict.get('log_remote_version_fail', 'Failed to check remote version.json: {e}').format(e=e)
                    logging.warning(log_msg)

            top.after(0, lambda: pb.configure(value=10))

            missing_db_files = [] # 누락 메시지용 문자열 리스트
            downloads_list = []   # (url, dest_path, dest_filename) 튜플 리스트
            
            from .schema_resolver import resolve_server_config
            
            tag_missing = lang_dict.get('tag_missing', '[Missing] ')
            tag_update = lang_dict.get('tag_update', '[Update] ')
            is_feature_completely_unavailable = False
            
            servers = [s for s, i in self._server_db_info.items() if isinstance(i, dict) and 'db_path' in i]
            # Calculate total tables across servers dynamically
            total_steps = 0
            for s, i in self._server_db_info.items():
                if isinstance(i, dict) and 'db_path' in i:
                    total_steps += 7 + (1 if i.get('alchemy_story_detail_table') else 0) + (1 if i.get('sekai_top_data_table') else 0) + (1 if i.get('sekai_top_story_data_table') else 0)
            total_steps = max(1, total_steps)
            step_size = 90 / total_steps
            current_progress = 10
            
            def on_table_progress(server_key: str, table_key: str) -> None:
                nonlocal current_progress
                current_progress += step_size
                fmt_str = lang_dict.get('db_parsing_table', '{server} schema resolved: {table}')
                msg = fmt_str.format(server=server_key, table=table_key)
                top.after(0, lambda p=current_progress, m=msg: (pb.configure(value=p), lbl.configure(text=m)))
            
            for server, info in self._server_db_info.items():
                if not isinstance(info, dict) or 'db_path' not in info:
                    continue
                
                db_path = os.path.join(root_dir, info['db_path'])
                baseline_path = os.path.join(src_dir, info.get('baseline_db_path', ''))
                
                # Baseline 확인 (단일 및 다중 기준점 전수 검사)
                baseline_dbs = info.get('baseline_dbs')
                if isinstance(baseline_dbs, dict) and baseline_dbs:
                    for b_key, b_item in baseline_dbs.items():
                        b_fname = b_item.get('db_path', '')
                        b_url = b_item.get('db_url', '')
                        b_full_path = os.path.join(src_dir, b_fname)
                        if b_fname and not os.path.exists(b_full_path):
                            missing_db_files.append(f"{tag_missing}src/{b_fname}")
                            if b_url:
                                downloads_list.append((b_url, b_full_path, b_fname))
                else:
                    if not os.path.exists(baseline_path):
                        missing_db_files.append(f"{tag_missing}src/{info.get('baseline_db_path', '')}")
                        downloads_list.append((info.get('baseline_db_url', ''), baseline_path, info.get('baseline_db_path', '')))
                    
                # 최신 DB 확인 및 버전 비교
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
                
                # 다운로드 중이 아니더라도, 취소 시 사용 가능한 DB(없으면 baseline)로 기능 사용 가능 여부 확인
                has_fallback = os.path.exists(baseline_path)
                self.db_status[server] = os.path.exists(db_path)
                    
                if not has_fallback:
                    is_feature_completely_unavailable = True

            # 모든 서버의 파일 상태 및 버전 확인 완료 후, 멀티프로세스 병렬로 스키마 일괄 역난독화 분석 실행
            from .schema_resolver import resolve_all_servers_parallel
            resolve_all_servers_parallel(self._server_db_info, root_dir, src_dir, progress_callback=on_table_progress)
            top.after(0, lambda: pb.configure(value=100))

            self._task_queue.put(ActionEvent(action=lambda: self._on_check_complete(top, downloads_list, remote_version_data, local_version_path, missing_db_files, on_ready, lang_dict, is_feature_completely_unavailable)))

        threading.Thread(target=_check_thread, daemon=True).start()

    def _on_check_complete(self, top: tk.Toplevel, downloads_list: list, remote_version_data: dict, local_version_path: str, missing_db_files: list, on_ready: callable, lang_dict: dict, is_feature_completely_unavailable: bool) -> None:
        """백그라운드 버전 검사가 완료된 후 UI 업데이트를 처리합니다."""
        top.destroy()
        if downloads_list and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_files)
            restriction_msg = lang_dict.get('db_prompt_restriction_unavailable', '') if is_feature_completely_unavailable else lang_dict.get('db_prompt_restriction_outdated', '')
            prompt_msg = lang_dict.get('db_download_prompt_msg', 'Updates or missing files:\n{paths}\n{restriction_msg}').format(paths=paths_str, restriction_msg=restriction_msg)
            
            if messagebox.askyesno(
                lang_dict.get('db_download_prompt_title', 'Download DB'), 
                prompt_msg, 
                parent=self._master
            ):
                self._start_db_download(downloads_list, remote_version_data, local_version_path, on_ready)
            else:
                self._show_offline_warning(paths_str, lang_dict, reason='cancel', is_feature_completely_unavailable=is_feature_completely_unavailable)
                self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
                if on_ready:
                    on_ready()
        else:
            self.db_check_done = True
            self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
            if on_ready:
                on_ready()
        
    def _show_offline_warning(self, paths_str: str, lang_dict: dict[str, str], reason: str = 'offline', is_feature_completely_unavailable: bool = True) -> None:
        """오프라인이거나 다운로드를 취소했을 때 경고 메시지를 표시합니다.

        Args:
            paths_str: 누락된 DB 파일 경로 목록 문자열.
            lang_dict: 다국어 딕셔너리.
            reason: 경고 발생 이유 ('offline' 또는 'cancel').
            is_feature_completely_unavailable: 기능 사용이 완전히 제한되는지 여부.
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
            extra_msg = lang_dict.get('db_download_cancel_msg_unavailable', '') if is_feature_completely_unavailable else lang_dict.get('db_download_cancel_msg_outdated', '')
        else:
            extra_msg = lang_dict.get('db_download_offline_msg_unavailable', '') if is_feature_completely_unavailable else lang_dict.get('db_download_offline_msg_outdated', '')
            
        messagebox.showwarning(
            lang_dict.get(title_key, 'DB Not Found'), 
            lang_dict.get(msg_key, '{paths}').format(paths=paths_str) + "\n\n" + extra_msg,
            parent=self._master
        )
        self.db_warning_shown = True

    def _start_db_download(self, downloads_list: list[tuple[str, str, str]], remote_version_data: dict, local_version_path: str, on_ready: callable = None) -> None:
        """누락된 DB 파일을 서버에서 다운로드하는 백그라운드 작업을 시작합니다.

        Args:
            downloads_list: (다운로드 URL, 저장 경로, 파일명) 형태의 튜플 리스트.
            remote_version_data: 원격지에서 가져온 version.json 데이터.
            local_version_path: 로컬 version.json 파일 저장 경로.
        """
        lang_dict = self._get_lang_dict()
        self._view.set_action_buttons_state("disabled")
        
        top = tk.Toplevel(self._master)
        top.withdraw()
        top.title(lang_dict.get('db_download_prompt_title', 'Downloading DB...'))
        
        # 화면 정가운데 표시
        top.update_idletasks()
        w, h = 300, 100
        x = (top.winfo_screenwidth() // 2) - (w // 2)
        y = (top.winfo_screenheight() // 2) - (h // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.resizable(False, False)
        
        top.transient(self._master)
        top.grab_set()
        lbl = ttk.Label(top, text=lang_dict.get('db_downloading_msg', "Downloading..."))
        lbl.pack(pady=10)
        pb = ttk.Progressbar(top, mode='determinate', maximum=100)
        pb.pack(fill=tk.X, padx=20)
        pb['value'] = 0
        top.deiconify()
        
        def _download_thread():
            import urllib.request
            import json
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
                        with open(dest_path, 'wb') as out_file:
                            while True:
                                chunk = response.read(16 * 1024)
                                if not chunk:
                                    break
                                out_file.write(chunk)
                                downloaded += len(chunk)
                                file_prog = (downloaded / total_size * 100) if total_size > 0 else 100
                                overall_prog = ((file_idx * 100) + file_prog) / max(1, total_files)
                                top.after(0, lambda p=overall_prog: pb.configure(value=p))
                                
                    # 다운로드된 파일이 유효한 SQLite DB인지 무결성 검증
                    with open(dest_path, 'rb') as db_file:
                        header = db_file.read(16)
                    if header != _SQLITE_MAGIC:
                        os.remove(dest_path)
                        raise DatabaseIntegrityError(fname, "header mismatch")
                
                # 모든 다운로드가 성공적으로 완료된 후 version.json 업데이트
                if remote_version_data:
                    with open(local_version_path, "w", encoding="utf-8") as f:
                        json.dump(remote_version_data, f, ensure_ascii=False, indent=4)
                        
                self._task_queue.put(ActionEvent(action=lambda: self._on_download_success(top, on_ready)))
            except (OSError, DatabaseIntegrityError) as e:
                self._task_queue.put(ActionEvent(action=lambda err=e: self._on_download_error(top, err)))
                
        t = threading.Thread(target=_download_thread, daemon=True)
        t.start()
        
    def _on_download_success(self, top: tk.Toplevel, on_ready: callable) -> None:
        """DB 다운로드 성공 시 호출되어 UI 상태를 갱신합니다.

        Args:
            top: 다운로드 진행 상태 대화상자 객체.
            on_ready: 자동 실행 콜백 함수.
        """
        top.destroy()
        lang_dict = self._get_lang_dict()
        messagebox.showinfo(lang_dict.get('db_download_prompt_title', 'Complete'), lang_dict.get('db_download_success_msg', 'Success'), parent=self._master)
        self.db_warning_shown = False
        self.db_check_done = False
        self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
        
        # 다운로드가 끝났으므로 check를 다시 호출하면 이번엔 on_ready를 타게 됨
        self.check_and_cache_db_status(on_ready)
        
    def _on_download_error(self, top: tk.Toplevel, err: Exception) -> None:
        """DB 다운로드 실패 시 에러 메시지를 표시합니다.

        Args:
            top: 다운로드 진행 상태 대화상자 객체.
            err: 발생한 예외 객체.
        """
        top.destroy()
        messagebox.showerror(self._get_lang_dict().get('db_download_error_title', 'Download Error'), str(err), parent=self._master)
        self.db_check_done = True
        self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
