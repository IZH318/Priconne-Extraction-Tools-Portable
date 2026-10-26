"""Manifest File Renamer 컨트롤러 모듈.

사용자 이벤트, 폴더 선택 대화상자, 다국어 갱신, 백그라운드 작업 스레드 수명 주기,
정기 큐 폴링(QueuePollingMixin)을 조정하여 UI 상태와 비즈니스 로직 동기화.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, ClassVar

from src.breadcrumbs import add_breadcrumb
from src.constants import (
    APP_DEVELOPER,
    APP_LAST_UPDATE,
    APP_VERSION,
    APP_WEBSITE,
    GUI_UPDATE_INTERVAL_MS,
)
from src.languages import RENAMER_LANGUAGES as LANGUAGES
from src.queue_polling import QueuePollingMixin
from src.shared_state import SharedState

from .log_renderer import RenamerLogRenderer
from .queue_handler import RenamerQueueHandler
from .service import RenameService
from .view import RenamerView

logger = logging.getLogger(__name__)


class RenamerController(QueuePollingMixin):
    """Manifest File Renamer MVC 컨트롤러 클래스.

    UI 상태 관리, 폴더 선택, 다국어 전환, 백그라운드 스레드 병렬 처리,
    이벤트 큐 폴링 및 UI 상태 동기화 관리.

    Attributes:
        master: 최상위 Tk 또는 Toplevel 윈도우 참조.
        view: UI 레이아웃 및 위젯 렌더링을 담당하는 RenamerView 인스턴스.
        about_info: 프로그램 정보 대화상자용 메타데이터 딕셔너리.
        lang_var: 현재 활성화된 언어 코드를 추적하는 Tkinter StringVar.
        is_processing: 파일 이름 복원 작업 진행 중 여부 플래그.
        total_files_count: 대상 디렉터리에서 감지된 전체 후보 파일 수.
        log_queue: 작업 스레드로부터 LogEvent 데이터클래스를 수신하는 큐.
        progress_queue: 작업 스레드로부터 ProgressEvent 데이터클래스를 수신하는 큐.
        shared_state: 의존성 주입을 위한 공유 매개변수 객체.
        file_processor: 활성 RenameHashedFile 인스턴스.
        log_manager: 로그 포맷팅 및 이력 유지를 전담하는 RenamerLogRenderer 인스턴스.
        queue_handler: UI 타이머 주기마다 큐를 비우고 UI를 갱신하는 RenamerQueueHandler 인스턴스.
    """

    _DEFAULT_ABOUT_INFO: ClassVar[dict[str, str | int]] = {
        'program': "Manifest File Renamer",
        'version': APP_VERSION,
        'updated': APP_LAST_UPDATE,
        'license': "GNU General Public License v3.0",
        'developer': APP_DEVELOPER,
        'website': APP_WEBSITE,
    }

    def __init__(
        self,
        frame: ttk.Frame,
        master: tk.Misc,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
    ) -> None:
        """RenamerController 인스턴스 및 의존성 객체 초기화.

        Args:
            frame: Renamer 탭에 할당된 컨테이너 프레임.
            master: 메인 Tk 애플리케이션 윈도우.
            app_lang_var: 전역 언어 설정 감지용 StringVar.
            about_info: 프로그램 메타데이터 딕셔너리.
        """
        self.master: tk.Misc = master
        self.view = RenamerView(frame, self)
        self.about_info: dict[str, str | int] = about_info or self._DEFAULT_ABOUT_INFO

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
        self.lang_var.trace_add("write", self._on_language_change)

        self.last_progress_info = {'current': 0, 'total': 0}
        self.is_processing = False
        self.total_files_count = 0
        self._active_thread: threading.Thread | None = None
        self._processing_processor: Any = None

        self.log_queue: queue.Queue[Any] = queue.Queue()
        self.progress_queue: queue.Queue[Any] = queue.Queue()

        self._base_path: Path | None = None

        self.shared_state: SharedState = SharedState()
        self.shared_state.get_string = self.get_string
        self.shared_state.get_lang_dict = self.get_lang_dict
        self.shared_state.log_queue = self.log_queue
        self.shared_state.progress_queue = self.progress_queue
        self.shared_state.base_path_provider = lambda: self._base_path
        self._rename_service = RenameService(
            shared_state=self.shared_state,
            get_string=self.get_string,
            log_queue=self.log_queue,
            progress_queue=self.progress_queue,
            base_path_provider=lambda: self._base_path,
        )
        self.file_processor = self._rename_service.ensure_processor()

        self.log_manager = RenamerLogRenderer(
            get_string=self.get_string,
            get_lang_dict=self.get_lang_dict,
            get_lang_code=lambda: self.lang_var.get(),
            target_folders_provider=lambda: self.file_processor.target_folders,
            view=self.view,
        )
        self.log_data = self.log_manager.log_data
        self._render_cache = self.log_manager._render_cache

        self.queue_handler = RenamerQueueHandler(self, self.log_manager, self._rename_service, self.view)

        self.update_ui_language(is_initial_setup=True)
        self.view.set_base_path_text("")

        self._init_queue_polling(self.view, interval_ms=GUI_UPDATE_INTERVAL_MS)

    def get_string(self, key: str, **kwargs: Any) -> str:
        """현재 활성화된 언어 사전에서 지정된 키에 대응하는 포맷팅된 번역 문자열 반환.

        Args:
            key: 번역 메시지 키.
            **kwargs: 번역 문자열 포맷팅 파라미터.

        Returns:
            포맷팅 완료된 번역 문자열 (조회 실패 시 키 자체 반환).
        """
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))
        template = lang_dict.get(key)
        if template is None:
            template = LANGUAGES.get('en', {}).get(key, key)
        try:
            return str(template).format(**kwargs)
        except (KeyError, ValueError, IndexError, TypeError):
            return str(template)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 활성화된 언어의 전체 번역 딕셔너리 반환.

        Returns:
            번역 키와 템플릿 문자열 매핑 딕셔너리.
        """
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))  # type: ignore[no-any-return]

    def _on_language_change(self, *args: Any) -> None:
        """전역 언어 변경 이벤트 수신 시 콜백 처리."""
        self._rename_service.get_string = self.get_string
        self.file_processor.set_get_string_func(self.get_string)
        self._rename_service.ensure_processor()
        self.update_ui_language()

    def update_ui_language(self, is_initial_setup: bool = False) -> None:
        """뷰 위젯 및 로그 콘솔 전반의 다국어 텍스트 일괄 갱신.

        Args:
            is_initial_setup: True인 경우 로그 버퍼를 초기화하고 시작 안내 메시지 출력.
        """
        self.view.update_ui_text()

        if not self.is_processing:
            total_processed = getattr(self.file_processor, 'processed_count_rename', 0) + getattr(self.file_processor, 'processed_count_check', 0)
            has_error = getattr(self.file_processor, 'has_error', False)
            if has_error:
                if self.total_files_count > 0 and total_processed > 0:
                    self.view.set_progress_text(f"{self.get_string('error_title')}: {total_processed} / {self.total_files_count}")
                else:
                    self.view.set_progress_text(self.get_string('error_title'))
            elif self.total_files_count > 0:
                if total_processed >= self.total_files_count:
                    self.view.set_progress_text(self.get_string('status_complete_count', count=self.total_files_count))
                elif total_processed > 0:
                    self.view.set_progress_text(f"{self.get_string('status_complete')} ({total_processed} / {self.total_files_count})")
                else:
                    self.view.set_progress_text(f"{self.get_string('error_title')} (0 / {self.total_files_count})")
            else:
                self.view.set_progress_text(self.get_string('status_waiting'))
        else:
            if self.last_progress_info['total'] == 0:
                self.view.set_progress_text(self.get_string('status_searching'))
            else:
                self.view.set_progress_text(self.get_string('status_processing', **self.last_progress_info))

        if is_initial_setup:
            self.log_data.clear()
            self.show_initial_message()

        self.redraw_all_logs()

    def show_initial_message(self) -> None:
        """로그 매니저를 통해 초기 안내 메시지 출력 위임."""
        self.log_manager.show_initial_message()

    def _format_log_entry(self, timestamp: str | None, key: str, kwargs: dict[str, Any] | None, is_same_group: bool) -> tuple[str, str]:
        """로그 매니저로 로그 엔트리 포맷팅 위임."""
        return self.log_manager._format_log_entry(timestamp, key, kwargs, is_same_group)

    def redraw_all_logs(self) -> None:
        """로그 매니저로 전체 로그 재렌더링 위임."""
        self.log_manager.redraw_all_logs()

    def _add_raw_text(self, text: str) -> None:
        """포맷팅되지 않은 텍스트를 로그 이력에 직접 추가."""
        self.log_manager._add_raw_text(text)

    def _add_log_event(self, key: str, kwargs: dict[str, Any] | None = None) -> None:
        """구조화된 로그 이벤트를 로그 이력에 추가."""
        self.log_manager._add_log_event(key, kwargs)

    def select_folder(self) -> None:
        """폴더 선택 대화상자를 열어 게임 클라이언트 대상 디렉터리 설정."""
        if self.is_processing:
            return
        from tkinter import filedialog
        initial_dir = str(self._base_path) if self._base_path else "/"
        folder_selected = filedialog.askdirectory(title=self.get_string('dialog_select_folder'), initialdir=initial_dir)
        if folder_selected:
            self._base_path = Path(folder_selected)
            self.file_processor = self._rename_service.ensure_processor()
            self.view.set_base_path_text(str(self._base_path))

            self.log_data.clear()
            self.show_initial_message()
            self.redraw_all_logs()

    def start_processing_thread(self) -> None:
        """요구 조건 검증 후 백그라운드 파일 이름 복원 스레드 시작.

        대상 폴더 선택 여부 및 매니페스트 DB/폴더 존재 여부 확인 후 작업자 스레드 시작.
        """
        from tkinter import messagebox
        if self.is_processing:
            return
        if self._base_path is None:
            messagebox.showerror(self.get_string('error_title'), self.get_string('dialog_select_folder'))
            return

        ok, _ = self._rename_service.validate_manifest()
        if not ok:
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return

        self.log_data.clear()
        self.show_initial_message()
        self.redraw_all_logs()
        add_breadcrumb("conv", "Started renamer task", {"path": str(self._base_path)})

        self.is_processing = True
        self._processing_processor = self._rename_service.ensure_processor()
        self._resume_polling()
        self.view.set_start_button_state(tk.DISABLED)
        self.view.set_folder_button_state(tk.DISABLED)
        self.view.set_progress_value(0)
        self.last_progress_info = {'current': 0, 'total': 0}
        self.view.set_progress_text(self.get_string('status_searching'))

        self.file_processor = self._processing_processor
        self.file_processor.set_get_string_func(self.get_string)
        self._active_thread = self._rename_service.start_processing()

    def _on_poll_cycle(self) -> None:
        """정기 타이머 폴링 주기를 큐 핸들러로 위임."""
        self.queue_handler.on_poll_cycle()

    def cleanup(self) -> None:
        """탭 파기 또는 종료 시 큐 폴링 중단 및 작업 스레드 안전 종료 대기 (ModuleController 프로토콜 준수)."""
        self._stop_polling()
        if self._active_thread is not None and self._active_thread.is_alive():
            self._active_thread.join(timeout=3.0)
            if self._active_thread.is_alive():
                logger.warning("Renamer worker thread did not terminate in time")
