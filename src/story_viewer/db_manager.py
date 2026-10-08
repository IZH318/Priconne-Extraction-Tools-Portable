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

    def check_and_cache_db_status(self) -> bool:
        """서버별 SQLite DB 파일의 존재 여부를 확인하고 캐시합니다.

        Returns:
            DB 다운로드가 시작되었으면 True, 아니면 False.
        """
        if self.db_check_done:
            return False
        lang_dict = self._get_lang_dict()
            
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        missing_db_files = []
        
        for server, info in self._server_db_info.items():
            db_path = os.path.join(script_dir, info['db_path'])
            exists = os.path.exists(db_path)
            self.db_status[server] = exists
            if not exists:
                missing_db_files.append(info['db_path'])

        if missing_db_files and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_files)
            if messagebox.askyesno(
                lang_dict.get('db_download_prompt_title', 'Download DB'), 
                lang_dict.get('db_download_prompt_msg', 'Missing:\n{paths}').format(paths=paths_str), 
                parent=self._master
            ):
                self._start_db_download(missing_db_files, script_dir)
                return True
            else:
                self._show_offline_warning(paths_str, lang_dict, reason='cancel')

        self.db_check_done = True
        return False
        
    def _show_offline_warning(self, paths_str: str, lang_dict: dict[str, str], reason: str = 'offline') -> None:
        """오프라인이거나 다운로드를 취소했을 때 경고 메시지를 표시합니다.

        Args:
            paths_str: 누락된 DB 파일 경로 목록 문자열.
            lang_dict: 다국어 딕셔너리.
            reason: 경고 발생 이유 ('offline' 또는 'cancel').
        """
        if reason == 'cancel':
            extra_msg = lang_dict.get('db_download_cancel_msg', '')
        else:
            extra_msg = lang_dict.get('db_download_offline_msg', '')
            
        messagebox.showwarning(
            lang_dict.get('db_not_found_title', 'DB Not Found'), 
            lang_dict.get('db_not_found_msg', '{paths}').format(paths=paths_str) + "\n\n" + extra_msg,
            parent=self._master
        )
        self.db_warning_shown = True

    def _start_db_download(self, files_to_download: list[str], dest_dir: str) -> None:
        """누락된 DB 파일을 서버에서 다운로드하는 백그라운드 작업을 시작합니다.

        Args:
            files_to_download: 다운로드할 파일 이름 리스트.
            dest_dir: 저장할 대상 디렉터리 경로.
        """
        lang_dict = self._get_lang_dict()
        self._view.set_action_buttons_state("disabled")
        
        top = tk.Toplevel(self._master)
        top.title(lang_dict.get('db_download_prompt_title', 'Downloading DB...'))
        
        # 화면 정가운데 표시
        top.update_idletasks()
        w, h = 300, 100
        x = (top.winfo_screenwidth() // 2) - (w // 2)
        y = (top.winfo_screenheight() // 2) - (h // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        
        top.transient(self._master)
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
                    with urllib.request.urlopen(url, timeout=30) as response:
                        with open(dest_path, 'wb') as out_file:
                            shutil.copyfileobj(response, out_file)
                    # 다운로드된 파일이 유효한 SQLite DB인지 무결성 검증
                    with open(dest_path, 'rb') as db_file:
                        header = db_file.read(16)
                    if header != _SQLITE_MAGIC:
                        os.remove(dest_path)
                        raise DatabaseIntegrityError(f, "header mismatch")
                self._task_queue.put(ActionEvent(action=lambda: self._on_download_success(top)))
            except (OSError, DatabaseIntegrityError) as e:
                self._task_queue.put(ActionEvent(action=lambda err=e: self._on_download_error(top, err)))
                
        t = threading.Thread(target=_download_thread, daemon=True)
        t.start()
        
    def _on_download_success(self, top: tk.Toplevel) -> None:
        """DB 다운로드 성공 시 호출되어 UI 상태를 갱신합니다.

        Args:
            top: 다운로드 진행 상태 대화상자 객체.
        """
        top.destroy()
        lang_dict = self._get_lang_dict()
        messagebox.showinfo(lang_dict.get('db_download_prompt_title', 'Complete'), lang_dict.get('db_download_success_msg', 'Success'), parent=self._master)
        self.db_warning_shown = False
        self.db_check_done = False
        self.check_and_cache_db_status()
        self._view.set_action_buttons_state("normal" if self._get_all_files() else "disabled")
        
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
