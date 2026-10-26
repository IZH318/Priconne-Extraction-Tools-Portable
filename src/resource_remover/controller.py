"""Resource Remover 컨트롤러 및 비동기 작업 조정 모듈.

체크박스로 선택된 에셋 확장자 목록을 바탕으로 백그라운드 스레드에서 파일을 탐색하고,
2단계 삭제 확인 대화상자(발견 요약 -> 최종 영구/휴지통 삭제 경고)를 거쳐
삭제를 실행하며, 큐 폴링(QueuePollingMixin)을 통해 UI 상태를 안전하게 갱신.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.breadcrumbs import add_breadcrumb
from src.constants import EXTENSION_CATEGORIES
from src.languages import RESOURCE_REMOVER_LANGUAGES as LANGUAGES
from src.queue_events import CompletionEvent
from src.queue_polling import QueuePollingMixin
from src.shared_state import SharedState
from src.utils.base_path import get_application_base_path

from .logic import ResourceRemoverLogic
from .service import ResourceRemovalService
from .view import ResourceRemoverView


class ResourceRemoverController(QueuePollingMixin):
    """Resource Remover 컨트롤러 클래스."""

    def __init__(
        self,
        frame: ttk.Frame,
        master: tk.Misc,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
    ) -> None:
        """ResourceRemoverController 초기화.

        Args:
            frame (ttk.Frame): 뷰를 배치할 상위 노트북 프레임.
            master (tk.Misc): 부모 Tk 윈도우.
            app_lang_var (tk.StringVar | None): 앱 전역 언어 설정 변수.
            about_info (dict[str, str | int] | None): 어바웃 정보 딕셔너리.
        """
        self.master: tk.Misc = master
        self.logic: ResourceRemoverLogic = ResourceRemoverLogic()
        self.shared_state: SharedState = SharedState()
        self.shared_state.get_lang_dict = self.get_lang_dict
        self.shared_state.get_base_path = lambda: self.target_path_var.get()
        self._removal_service: ResourceRemovalService = ResourceRemovalService(shared_state=self.shared_state, logic=self.logic)
        self.about_info: dict[str, Any] = about_info or {}
        self.target_path_var: tk.StringVar = tk.StringVar(value=str(get_application_base_path()))

        self.use_trash_var: tk.BooleanVar = tk.BooleanVar(value=True)
        self.chk_vars: dict[str, tk.BooleanVar] = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)
        self.status_var: tk.StringVar = tk.StringVar()
        self.is_complete: bool = False
        self._searched_extensions: list[str] = []
        self.task_queue: queue.Queue[Any] = queue.Queue()
        self._state_lock: threading.RLock = threading.RLock()

        if app_lang_var:
            self.lang_var: tk.StringVar = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.view: ResourceRemoverView = ResourceRemoverView(frame, self)

        self.lang_var.trace_add('write', self._on_language_change)

        self.view.update_ui_text()
        self._init_queue_polling(self.view)

    @property
    def is_task_complete(self) -> bool:
        """현재 삭제 작업이 완료 상태인지 여부 반환.

        Returns:
            bool: 작업이 성공적으로 끝났거나 취소되었으면 True.
        """
        return self.is_complete

    @property
    def is_use_trash_enabled(self) -> bool:
        """휴지통 이동 체크박스가 활성화되어 있는지 여부 반환.

        Returns:
            bool: 휴지통 사용이 켜져 있으면 True.
        """
        return self.use_trash_var.get()

    def _on_poll_cycle(self) -> None:
        """백그라운드 스레드에서 발행된 완료 이벤트(검색/삭제)를 큐에서 꺼내 메인 스레드에서 처리."""
        for event in self._drain_queue(self.task_queue):
            if not isinstance(event, CompletionEvent):
                continue
            if event.target == 'search':
                self._handle_search_done(event.result)
            elif event.target == 'delete':
                self._handle_delete_done(event.result)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 사전 딕셔너리 반환 (ModuleController 프로토콜 준수).

        Returns:
            dict[str, str]: 현재 언어의 번역 문자열 맵.
        """
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))  # type: ignore[no-any-return]

    def _on_language_change(self, *args: Any) -> None:
        """전역 언어 변경 이벤트 수신 시 뷰 UI 텍스트 재적용."""
        try:
            self.view.update_ui_text()
        except (tk.TclError, AttributeError):
            pass

    def _get_selected_extensions(self) -> list[str]:
        """체크박스에서 체크된 카테고리의 모든 파일 확장자들을 수집하여 반환.

        Returns:
            list[str]: 허용된 소문자 확장자 문자열 리스트 (예: ['.unity3d', '.acb', '.awb']).
        """
        selected = []
        for cat in EXTENSION_CATEGORIES:
            if self.chk_vars[cat["key"]].get():
                selected.extend(cat["extensions"])
        return selected

    def select_directory(self) -> None:
        """폴더 선택 대화상자를 열어 삭제 대상 디렉터리 변경."""
        lang_dict = self.get_lang_dict()
        selected = filedialog.askdirectory(
            title=lang_dict.get('dialog_select_folder', 'Select Target Folder'),
            initialdir=self.target_path_var.get(),
            parent=self.master,
        )
        if selected:
            self.target_path_var.set(selected)
            self.logic.base_path = Path(selected)

    def start_removal(self) -> None:
        """리소스 삭제 프로세스의 첫 단계인 백그라운드 파일 검색 트리거.

        UI 컨트롤을 비활성화하고 브레드크럼 기록 후 탐색 스레드 시작.
        """
        lang_dict = self.get_lang_dict()

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(
                lang_dict.get('warn_title', 'Warning'),
                lang_dict.get('warn_no_selection', 'Please select at least one file type to delete.'),
                parent=self.view,
            )
            return

        self.is_complete = False
        self._resume_polling()
        self.view.set_control_state('disabled')
        self.status_var.set(lang_dict.get('status_searching', "Searching files..."))
        self.view.set_status_color("blue")
        add_breadcrumb("io", "Started resource removal", {"extensions": selected_exts, "trash": self.use_trash_var.get()})

        threading.Thread(target=self._search_thread, args=(selected_exts,), daemon=True).start()

    def _search_thread(self, selected_exts: list[str]) -> None:
        """백그라운드 스레드에서 대상 폴더를 순회하며 삭제 후보 파일 탐색.

        Args:
            selected_exts (list[str]): 검색 대상 확장자 리스트.
        """
        self._searched_extensions = list(selected_exts)
        target_files = self._removal_service.count_resources(selected_exts)
        self.task_queue.put(CompletionEvent(
            target='search',
            result=target_files,
        ))

    def _handle_search_done(self, target_files: list[str]) -> None:
        """파일 검색 완료 후 사용자에게 발견된 파일 요약을 보여주고 최종 삭제 여부 확인.

        Args:
            target_files (list[str]): 검색된 대상 파일 경로 리스트.
        """
        lang_dict = self.get_lang_dict()
        file_count = len(target_files)

        if file_count == 0:
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            messagebox.showinfo(
                lang_dict.get('info_title', 'Info'),
                lang_dict.get('no_files_found', 'No files found to delete.'),
                parent=self.view,
            )
            return

        target_path = self.target_path_var.get()
        selected_exts = list(self._searched_extensions) if self._searched_extensions else self._get_selected_extensions()
        exts_str = ", ".join(selected_exts)

        # 1차 확인: 대상 경로, 확장자 및 파일 개수 요약
        summary_msg = lang_dict.get(
            'confirm_summary',
            'Target Path:\n{path}\n\nTarget File Types: {extensions}\n\nFiles: {count}\n\nProceed?',
        ).format(path=target_path, extensions=exts_str, count=file_count)

        if not messagebox.askyesno(lang_dict.get('confirm_title', 'Confirm Deletion'), summary_msg, parent=self.view):
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            return

        use_trash = self.use_trash_var.get()
        msg_key = 'confirm_msg_trash' if use_trash else 'confirm_msg_permanent'
        warning_msg = lang_dict.get(msg_key, 'Proceed?').format(count=file_count)

        # 2차 확인: 휴지통 이동 vs 영구 삭제 최종 경고
        if messagebox.askyesno(lang_dict.get('warn_title', 'Warning'), warning_msg, parent=self.view):
            self.status_var.set(lang_dict.get('status_processing', "Processing..."))
            self.view.set_status_color("blue")
            threading.Thread(target=self._delete_thread, args=(target_files, selected_exts, use_trash), daemon=True).start()
        else:
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")

    def _delete_thread(self, target_files: list[str], selected_exts: list[str], use_trash: bool) -> None:
        """백그라운드 스레드에서 파일 삭제 또는 휴지통 이동 수행.

        Args:
            target_files (list[str]): 삭제 대상 파일 경로 리스트.
            selected_exts (list[str]): 삭제된 확장자 리스트 (로그 헤더용).
            use_trash (bool): 휴지통 사용 여부.
        """
        deleted_count, errors, log_filename = self._removal_service.remove_resources(
            target_files=target_files,
            extensions_to_remove=selected_exts,
            use_trash=use_trash,
        )
        self.task_queue.put(CompletionEvent(
            target='delete',
            result={'deleted_count': deleted_count, 'errors': errors, 'log_path': log_filename},
        ))

    def _handle_delete_done(self, result: dict[str, Any]) -> None:
        """파일 삭제 완료 이벤트를 수신하여 UI 결과를 갱신하고 결과 팝업 노출.

        Args:
            result (dict[str, Any]): deleted_count, errors, log_path를 포함하는 결과 딕셔너리.
        """
        lang_dict = self.get_lang_dict()
        errors = result['errors']
        log_filename = result['log_path']

        self.view.set_control_state('normal')
        self.is_complete = True

        if not errors:
            success_txt = lang_dict.get('success_msg', 'Removal completed.\n({log})').replace(
                '{log}', str(os.path.basename(log_filename)) if log_filename else 'None'
            )
            self.status_var.set(success_txt)
            self.view.set_status_color("green")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), success_txt, parent=self.view)
        else:
            error_msg = lang_dict.get('status_error', 'Error during deletion: {error}').format(error=f"{len(errors)} errors")
            self.status_var.set(error_msg)
            self.view.set_status_color("red")
            messagebox.showerror(
                lang_dict.get('error_title', 'Error'),
                lang_dict.get('error_delete_failed', '{count} files failed to delete. See log for details.').format(count=len(errors)),
                parent=self.view,
            )

    def cleanup(self) -> None:
        """앱 종료 시 등록된 after 큐 폴링 타이머 해제 (ModuleController 프로토콜 준수)."""
        self._stop_polling()

