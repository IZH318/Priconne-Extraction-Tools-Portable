from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any
import queue
import threading
import os
from pathlib import Path
from tkinter import filedialog

from src.languages import RESOURCE_REMOVER_LANGUAGES as LANGUAGES
from src.breadcrumbs import add_breadcrumb
from src.constants import EXTENSION_CATEGORIES
from src.queue_events import CompletionEvent
from src.queue_polling import QueuePollingMixin
from src.utils.base_path import get_application_base_path
from .logic import ResourceRemoverLogic
from .view import ResourceRemoverView

class ResourceRemoverController(QueuePollingMixin):
    """Resource Remover 모듈의 비즈니스 로직과 UI를 연결하는 컨트롤러 클래스입니다."""

    def __init__(self, frame: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        """ResourceRemoverController 객체를 초기화합니다.

        Args:
            frame: gui.py의 ttk.Frame 래퍼 (View의 부모 위젯).
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            app_lang_var: 앱 전역 언어 상태 변수 (기본값: None).
            about_info: 프로그램 정보 대화상자에 표시될 메타데이터 (기본값: None).
        """
        self.master = master
        self.logic = ResourceRemoverLogic()
        self.about_info = about_info or {}
        self.target_path_var = tk.StringVar(value=str(get_application_base_path()))
        
        self.use_trash_var = tk.BooleanVar(value=True)
        self.chk_vars = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar()
        self.is_complete = False
        self.task_queue = queue.Queue()

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.view = ResourceRemoverView(frame, self)
        
        self.lang_var.trace_add('write', self._on_language_change)

        self.view.update_ui_text()
        self._init_queue_polling(self.view)

    @property
    def is_task_complete(self) -> bool:
        """작업이 완료되었는지 여부를 반환합니다."""
        return self.is_complete

    @property
    def is_use_trash_enabled(self) -> bool:
        """휴지통 사용 옵션이 활성화되어 있는지 여부를 반환합니다."""
        return self.use_trash_var.get()

    def _on_poll_cycle(self) -> None:
        """태스크 큐에 쌓인 이벤트(검색 완료, 삭제 완료 등)를 처리합니다."""
        for event in self._drain_queue(self.task_queue):
            if not isinstance(event, CompletionEvent):
                continue
            if event.target == 'search':
                self._handle_search_done(event.result)
            elif event.target == 'delete':
                self._handle_delete_done(event.result)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트를 처리하고 UI 텍스트를 업데이트합니다.

        Args:
            *args: 가변 인자 리스트.
        """
        try:
            self.view.update_ui_text()
        except (tk.TclError, AttributeError):
            pass

    def _get_selected_extensions(self) -> list[str]:
        """체크박스에서 선택된 확장자 목록을 반환합니다.

        Returns:
            선택된 확장자 문자열 리스트.
        """
        selected = []
        for cat in EXTENSION_CATEGORIES:
            if self.chk_vars[cat["key"]].get():
                selected.extend(cat["extensions"])
        return selected

    def select_directory(self) -> None:
        """삭제 대상 폴더를 선택하는 다이얼로그를 엽니다."""
        lang_dict = self.get_lang_dict()
        selected = filedialog.askdirectory(
            title=lang_dict.get('dialog_select_folder', 'Select Folder'),
            initialdir=self.target_path_var.get(),
            parent=self.master
        )
        if selected:
            self.target_path_var.set(selected)
            self.logic.base_path = Path(selected)

    def start_removal(self) -> None:
        """선택된 카테고리의 리소스 파일 삭제를 시작합니다."""
        lang_dict = self.get_lang_dict()

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(lang_dict.get('warn_title', 'Warning'), lang_dict.get('warn_no_selection', 'No categories selected.'), parent=self.view)
            return
            
        self.is_complete = False
        self.view.set_control_state('disabled')
        self.status_var.set(lang_dict.get('status_searching', "Searching..."))
        self.view.set_status_color("blue")
        add_breadcrumb("io", "Started resource removal", {"extensions": selected_exts, "trash": self.use_trash_var.get()})
        
        threading.Thread(target=self._search_thread, args=(selected_exts,), daemon=True).start()

    def _search_thread(self, selected_exts: list[str]) -> None:
        """삭제할 리소스 파일을 백그라운드 스레드에서 검색합니다.

        Args:
            selected_exts: 검색할 대상 확장자 리스트.
        """
        target_files = self.logic.count_resources(selected_exts)
        self.task_queue.put(CompletionEvent(
            target='search',
            result=target_files
        ))

    def _handle_search_done(self, target_files: list[str]) -> None:
        """파일 검색 완료 이벤트를 처리하고 삭제 확인 대화상자를 표시합니다.

        Args:
            target_files: 검색된 삭제 대상 파일 경로 리스트.
        """
        lang_dict = self.get_lang_dict()
        file_count = len(target_files)
        
        if file_count == 0:
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), lang_dict.get('no_files_found', 'No files found to delete.'), parent=self.view)
            return

        target_path = self.target_path_var.get()
        selected_exts = self._get_selected_extensions()
        exts_str = ", ".join(selected_exts)

        # 1단계: 요약 정보 표시
        summary_msg = lang_dict.get('confirm_summary', 'Target Path:\n{path}\n\nTarget File Types: {extensions}\n\nFound Files: {count}\n\nProceed?').format(path=target_path, extensions=exts_str, count=file_count)
        
        if not messagebox.askyesno(lang_dict.get('confirm_title', 'Confirm Deletion'), summary_msg, parent=self.view):
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            return

        # 2단계: 휴지통 옵션 기반 경고
        use_trash = self.use_trash_var.get()
        msg_key = 'confirm_msg_trash' if use_trash else 'confirm_msg_permanent'
        warning_msg = lang_dict.get(msg_key, 'Proceed?').format(count=file_count)

        if messagebox.askyesno(lang_dict.get('warn_title', 'Warning'), warning_msg, parent=self.view):
            self.status_var.set(lang_dict.get('status_processing', "Processing..."))
            self.view.set_status_color("blue")
            threading.Thread(target=self._delete_thread, args=(target_files, selected_exts, use_trash), daemon=True).start()
        else:
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")

    def _delete_thread(self, target_files: list[str], selected_exts: list[str], use_trash: bool) -> None:
        """선택된 리소스 파일을 백그라운드 스레드에서 삭제(또는 휴지통으로 이동)합니다.

        Args:
            target_files: 삭제 대상 파일 경로 리스트.
            selected_exts: 삭제된 확장자 리스트 (로그용).
            use_trash: 휴지통 사용 여부.
        """
        deleted_count, errors, log_filename = self.logic.remove_resources(target_files=target_files, extensions_to_remove=selected_exts, use_trash=use_trash)
        self.task_queue.put(CompletionEvent(
            target='delete',
            result={'deleted_count': deleted_count, 'errors': errors, 'log_path': log_filename}
        ))

    def _handle_delete_done(self, result: dict[str, Any]) -> None:
        """파일 삭제 완료 이벤트를 처리하고 결과 메시지를 표시합니다.

        Args:
            result: 삭제 결과 딕셔너리 (deleted_count, errors, log_path).
        """
        lang_dict = self.get_lang_dict()
        errors = result['errors']
        log_filename = result['log_path']

        self.view.set_control_state('normal')
        self.is_complete = True
            
        if not errors:
            success_txt = lang_dict.get('success_msg', 'Deletion complete.').replace('{log}', str(os.path.basename(log_filename)) if log_filename else 'None')
            self.status_var.set(success_txt)
            self.view.set_status_color("green")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), success_txt, parent=self.view)
        else:
            error_msg = lang_dict.get('status_error', 'Error: {error}').format(error=f"{len(errors)} errors")
            self.status_var.set(error_msg)
            self.view.set_status_color("red")
            messagebox.showerror(lang_dict.get('error_title', 'Error'), lang_dict.get('error_delete_failed', '{count} files failed.').format(count=len(errors)), parent=self.view)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다."""
        self._stop_polling()
