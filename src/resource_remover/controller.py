"""Resource Remover 컨트롤러 및 비동기 작업 조정 모듈.

체크박스로 선택된 에셋 확장자 목록을 바탕으로 백그라운드 스레드에서 파일을 탐색하고,
2단계 삭제 확인 대화상자(발견 요약 -> 최종 영구/휴지통 삭제 경고)를 거쳐
삭제를 실행하며, 큐 폴링(QueuePollingMixin)을 통해 UI 상태를 안전하게 갱신.

추가 안전장치:
    - 삭제 확정 전 대상 경로/확장자/파일 수 요약 확인 및 처리 결과 삭제 로그 기록.
    - 종료(cleanup) 시 취소 신호 전송 후 워커 스레드 조인으로 진행 중인 탐색/삭제 작업 중단.
    - 기준 경로 resolve 정규화로 logic과 UI 경로 기준 일치 보장.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
import unicodedata
from collections.abc import Callable
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from src.breadcrumbs import add_breadcrumb
from src.constants import DEFAULT_LANG, EXTENSION_CATEGORIES, RESOURCE_REMOVER_CLEANUP_JOIN_TIMEOUT
from src.languages import RESOURCE_REMOVER_LANGUAGES as LANGUAGES
from src.languages import format_text, pick_language
from src.queue_events import CompletionEvent
from src.queue_polling import QueuePollingMixin
from src.utils.base_path import get_application_base_path

from .logic import ResourceRemoverLogic
from .service import ResourceRemovalService
from .view import ResourceRemoverView

# 이 수량 이상 삭제 시 토큰 입력(DELETE) 추가 확인을 요구하는 대량 삭제 임계치
_BULK_DELETE_CONFIRM_THRESHOLD: int = 500

logger = logging.getLogger(__name__)


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
        self._removal_service: ResourceRemovalService = ResourceRemovalService(get_lang_dict=self.get_lang_dict, logic=self.logic)
        self.about_info: dict[str, Any] = about_info or {}
        self.target_path_var: tk.StringVar = tk.StringVar(value="")

        self.use_trash_var: tk.BooleanVar = tk.BooleanVar(value=True)
        self.chk_vars: dict[str, tk.BooleanVar] = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)
        self.status_var: tk.StringVar = tk.StringVar()
        self.is_complete: bool = False
        # 완료/취소/오류 상태 문구를 현재 언어로 다시 생성하기 위한 빌더 (언어 변경 대응)
        self._final_status_builder: Callable[[], str] | None = None
        self._searched_extensions: list[str] = []
        self.task_queue: queue.Queue[Any] = queue.Queue()
        # 종료 시 조인 대상이 되는 진행 중 워커 스레드 (탐색/삭제)
        self._worker_threads: list[threading.Thread] = []

        if app_lang_var:
            self.lang_var: tk.StringVar = app_lang_var
        else:
            self.lang_var = tk.StringVar(value=DEFAULT_LANG)

        self.view: ResourceRemoverView = ResourceRemoverView(frame, self)
        self.lang_var.trace_add('write', self._on_language_change)
        self.target_path_var.trace_add('write', self._on_target_path_change)

        self.view.update_ui_text()
        self._on_target_path_change()
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

    @property
    def _dialog_parent(self) -> tk.Misc:
        """다이얼로그를 앱 창 기준 중앙에 배치하기 위한 부모 위젯 반환.

        노트북 탭 프레임(self.view)은 다른 탭으로 전환되면 unmapped 상태가 되어
        simpledialog가 화면 중앙으로 폴백되므로, 항상 mapped 상태인 최상위 창을
        부모로 사용해 모든 확인 대화상자가 앱 창 가운데에 뜨도록 보장한다.

        Returns:
            tk.Misc: 대화상자 부모로 사용할 최상위 창(또는 폴백 위젯).
        """
        try:
            return self.master.winfo_toplevel()
        except (tk.TclError, AttributeError):
            return self.view

    def _on_poll_cycle(self) -> None:
        """백그라운드 스레드에서 발행된 완료 이벤트(검색/삭제)를 큐에서 꺼내 메인 스레드에서 처리."""
        for event in self._drain_queue(self.task_queue):
            if not isinstance(event, CompletionEvent):
                continue
            try:
                if event.target == 'search':
                    self._handle_search_done(event.result)
                elif event.target == 'delete':
                    self._handle_delete_done(event.result)
            except Exception:
                # 핸들러 예외로 탭이 잠긴 채 남지 않도록 컨트롤 상태를 복구
                logger.exception("Failed to handle resource removal event: %s", event.target)
                self.view.set_control_state('normal')
                self.view.set_cancel_button_state(tk.DISABLED)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 사전 딕셔너리 반환 (ModuleController 프로토콜 준수).

        Returns:
            dict[str, str]: 현재 언어의 번역 문자열 맵.
        """
        return pick_language(self.lang_var.get(), LANGUAGES)

    def _on_language_change(self, *args: Any) -> None:
        """전역 언어 변경 이벤트 수신 시 뷰 UI 텍스트 재적용.

        완료/취소/오류 상태 문구는 뷰 갱신 대상에서 제외되므로, 마지막 결과 문구를
        현재 언어로 다시 생성해 하단 상태 라벨이 이전 언어로 남지 않도록 한다.
        """
        try:
            self.view.update_ui_text()
            if self.is_complete:
                builder = self._final_status_builder
                self.status_var.set(
                    builder() if builder is not None else self.get_lang_dict().get('status_ready', 'Ready...')
                )
        except (tk.TclError, AttributeError):
            pass

    def _on_target_path_change(self, *args: Any) -> None:
        """대상 경로 입력 변경 시 시작 버튼 활성 상태를 동기화."""
        try:
            self.view.set_start_button_enabled(bool(self.target_path_var.get().strip()))
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
        """폴더 선택 대화상자를 열어 삭제 대상 디렉터리 변경.

        선택 경로는 즉시 resolve() 정규화되어 logic 기준 경로와 UI 표시가 일치한다.
        """
        lang_dict = self.get_lang_dict()
        selected = filedialog.askdirectory(
            title=lang_dict.get('dialog_select_folder', 'Select Target Folder'),
            initialdir=self.target_path_var.get() or str(get_application_base_path()),
            parent=self._dialog_parent,
        )
        if not selected:
            return

        # 정규화된 절대 경로로 기준 경로 할당 (base_path 세터가 resolve 수행)
        self.logic.base_path = selected
        self.target_path_var.set(str(self.logic.base_path))

    def start_removal(self) -> None:
        """리소스 삭제 프로세스의 첫 단계인 백그라운드 파일 검색 트리거.

        검색 직전 target_path_var 값을 logic.base_path로 재동기화(정규화)하여 기준 일치.
        새 작업 시작 전 이전 취소 신호 초기화.

        UI 컨트롤을 비활성화하고 브레드크럼 기록 후 탐색 스레드 시작.
        """
        lang_dict = self.get_lang_dict()

        target_path = self.target_path_var.get().strip()
        if not target_path:
            messagebox.showwarning(
                lang_dict.get('warn_title', 'Warning'),
                lang_dict.get('warn_no_target_path', 'Please select a target folder first.'),
                parent=self._dialog_parent,
            )
            return

        self.logic.base_path = target_path

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(
                lang_dict.get('warn_title', 'Warning'),
                lang_dict.get('warn_no_selection', 'Please select at least one file type to delete.'),
                parent=self._dialog_parent,
            )
            return

        self.logic.reset_cancel()

        self.is_complete = False
        self._final_status_builder = None
        self._resume_polling()
        self.view.set_control_state('disabled')
        self.view.set_cancel_button_state(tk.NORMAL)
        self.status_var.set(lang_dict.get('status_searching', "Searching files..."))
        self.view.set_status_color("blue")
        add_breadcrumb("io", "Started resource removal", {"extensions": selected_exts, "trash": self.use_trash_var.get()})

        search_thread = threading.Thread(target=self._search_thread, args=(selected_exts,), daemon=True)
        self._worker_threads.append(search_thread)
        search_thread.start()

    def cancel_removal(self) -> None:
        """진행 중인 탐색/삭제 작업에 취소 신호를 전파하고 취소 버튼을 비활성화."""
        self.logic.request_cancel()
        self.view.set_cancel_button_state(tk.DISABLED)
        self.status_var.set(self.get_lang_dict().get('status_cancelling', 'Cancelling...'))
        self.view.set_status_color("orange")

    def _search_thread(self, selected_exts: list[str]) -> None:
        """백그라운드 스레드에서 대상 폴더를 순회하며 삭제 후보 파일 탐색.

        후보 목록은 대화상자에 표시하지 않으며, 삭제 결과만 삭제 로그로 기록한다.

        Args:
            selected_exts (list[str]): 검색 대상 확장자 리스트.
        """
        self._searched_extensions = list(selected_exts)
        target_files = self._removal_service.count_resources(selected_exts)
        self.task_queue.put(CompletionEvent(
            target='search',
            result={
                'files': [str(f) for f in target_files],
                'cancelled': self.logic.is_cancelled,
            },
        ))

    def _handle_search_done(self, result: dict[str, Any]) -> None:
        """파일 검색 완료 후 삭제 요약을 보여주고 최종 삭제 여부 확인.

        확인 질문(confirm_question)은 요약 마지막 줄에 배치한다.
        탐색 중 취소된 경우 삭제 단계로 진행하지 않고 상태를 복원.

        Args:
            result (dict[str, Any]): files, cancelled를 포함하는 검색 결과 딕셔너리.
        """
        lang_dict = self.get_lang_dict()
        target_files: list[str] = result.get('files', [])
        # 후보 검토 단계로 전환되므로 취소 버튼은 비활성화 (삭제 시작 시 다시 활성화)
        self.view.set_cancel_button_state(tk.DISABLED)

        if result.get('cancelled'):
            self.is_complete = True
            self.view.set_control_state('normal')
            cancelled_count = len(target_files)

            def _build_search_cancelled() -> str:
                """탐색 취소 문구를 현재 언어로 생성 (언어 변경 시 재사용)."""
                return format_text(
                    self.get_lang_dict(),
                    'status_cancelled',
                    'Cancelled. ({count} files processed)',
                    count=cancelled_count,
                )

            self._final_status_builder = _build_search_cancelled
            self.status_var.set(_build_search_cancelled())
            self.view.set_status_color("orange")
            return

        file_count = len(target_files)

        if file_count == 0:
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            messagebox.showinfo(
                lang_dict.get('info_title', 'Info'),
                lang_dict.get('no_files_found', 'No files found to delete.'),
                parent=self._dialog_parent,
            )
            return

        target_path = self.target_path_var.get()
        selected_exts = list(self._searched_extensions) if self._searched_extensions else self._get_selected_extensions()
        exts_str = ", ".join(selected_exts)

        # 1차 확인: 요약 본문 + 질문 (파일 목록은 대화상자에 나열하지 않음)
        body_msg = format_text(
            lang_dict,
            'confirm_summary',
            'Target Path:\n{path}\n\nTarget File Types: {extensions}\n\nFiles: {count}',
            path=target_path,
            extensions=exts_str,
            count=file_count,
        )
        question_msg = lang_dict.get('confirm_question', 'Proceed?')
        summary_msg = f"{body_msg}\n\n{question_msg}"

        if not messagebox.askyesno(lang_dict.get('confirm_title', 'Confirm Deletion'), summary_msg, parent=self._dialog_parent):
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            return

        # 대량 삭제는 오조작 위험이 크므로 임계치 이상이면 토큰 입력을 추가로 요구
        if file_count >= _BULK_DELETE_CONFIRM_THRESHOLD:
            typed = simpledialog.askstring(
                format_text(lang_dict, 'bulk_confirm_title', 'Bulk Deletion Confirmation'),
                format_text(
                    lang_dict,
                    'bulk_confirm_msg',
                    'You are about to delete {count} files.\nType DELETE to continue.',
                    count=file_count,
                ),
                parent=self._dialog_parent,
            )
            # 전각 문자(일본어 IME 등)와 대소문자 차이를 흡수하도록 NFKC 정규화 후 비교.
            # 취소(typed is None)는 조용히 중단하고, 잘못 입력한 경우에만 안내한다.
            if unicodedata.normalize('NFKC', typed or '').strip().upper() != 'DELETE':
                self.is_complete = True
                self.view.set_control_state('normal')
                self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
                self.view.set_status_color("black")
                if typed is not None:
                    messagebox.showwarning(
                        lang_dict.get('warn_title', 'Warning'),
                        format_text(
                            lang_dict,
                            'bulk_confirm_invalid_msg',
                            'The input was incorrect, so the bulk deletion was cancelled.\nPlease type DELETE exactly to continue.',
                        ),
                        parent=self._dialog_parent,
                    )
                return

        use_trash = self.use_trash_var.get()
        msg_key = 'confirm_msg_trash' if use_trash else 'confirm_msg_permanent'
        warning_msg = format_text(lang_dict, msg_key, 'Proceed?', count=file_count)

        # 2차 확인: 휴지통 이동 vs 영구 삭제 최종 경고
        if messagebox.askyesno(lang_dict.get('warn_title', 'Warning'), warning_msg, parent=self._dialog_parent):
            self.view.set_cancel_button_state(tk.NORMAL)
            self.status_var.set(lang_dict.get('status_processing', "Processing..."))
            self.view.set_status_color("blue")
            delete_thread = threading.Thread(
                target=self._delete_thread, args=(target_files, selected_exts, use_trash), daemon=True
            )
            self._worker_threads.append(delete_thread)
            delete_thread.start()
        else:
            self.is_complete = True
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")

    def _delete_thread(self, target_files: list[str], selected_exts: list[str], use_trash: bool) -> None:
        """백그라운드 스레드에서 파일 삭제 또는 휴지통 이동 수행.

        취소 신호가 설정되면 logic.remove_resources()가 파일 간 루프를 중단한다.

        Args:
            target_files (list[str]): 삭제 대상 파일 경로 리스트.
            selected_exts (list[str]): 삭제된 확장자 리스트 (로그 헤더용).
            use_trash (bool): 휴지통 사용 여부.
        """
        try:
            deleted_count, errors, log_filename = self._removal_service.remove_resources(
                target_files=target_files,
                extensions_to_remove=selected_exts,
                use_trash=use_trash,
                progress_cb=self._post_delete_progress,
            )
        except BaseException as exc:  # noqa: BLE001
            # 워커 예외로 탭이 '처리 중' 상태에 고착되지 않도록 완료 이벤트를 반드시 발행
            logger.exception("Resource removal worker failed")
            deleted_count, errors, log_filename = 0, [str(exc)], ""
        self.task_queue.put(CompletionEvent(
            target='delete',
            result={
                'deleted_count': deleted_count,
                'errors': errors,
                'log_path': log_filename,
                'cancelled': self.logic.last_run_cancelled,
            },
        ))

    def _post_delete_progress(self, done: int, total: int) -> None:
        """삭제 진행률을 메인 스레드 상태 표시줄로 안전하게 전달."""
        from src.utils.tk_safe import post_to_ui

        def _apply() -> None:
            base = self.get_lang_dict().get('status_processing', 'Processing...')
            self.status_var.set(f"{base} ({done}/{total})")

        post_to_ui(_apply)

    def _handle_delete_done(self, result: dict[str, Any]) -> None:
        """파일 삭제 완료 이벤트를 수신하여 UI 결과를 갱신하고 결과 팝업 노출.

        사용자 취소로 중단된 경우 부분 처리 결과와 로그를 안내.

        Args:
            result (dict[str, Any]): deleted_count, errors, log_path, cancelled를 포함하는 결과 딕셔너리.
        """
        lang_dict = self.get_lang_dict()
        errors = result['errors']
        log_filename = result['log_path']
        deleted_count = result.get('deleted_count', 0)

        self.view.set_control_state('normal')
        self.view.set_cancel_button_state(tk.DISABLED)
        self.is_complete = True

        if result.get('cancelled'):
            def _build_cancelled() -> str:
                """취소 결과 문구를 현재 언어로 생성 (언어 변경 시 재사용)."""
                lang = self.get_lang_dict()
                text = format_text(
                    lang, 'status_cancelled', 'Cancelled. ({count} files processed)', count=deleted_count
                )
                # 취소 시에도 부분 실패 건수를 함께 안내 (로그에만 남기지 않음)
                if errors:
                    text += "\n" + format_text(
                        lang,
                        'error_delete_failed',
                        '{count} files failed to delete. See log for details.',
                        count=len(errors),
                    )
                if log_filename:
                    text += f"\n({os.path.basename(log_filename)})"
                return text

            self._final_status_builder = _build_cancelled
            cancelled_txt = _build_cancelled()
            self.status_var.set(cancelled_txt)
            self.view.set_status_color("orange")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), cancelled_txt, parent=self._dialog_parent)
            return

        if not errors:
            def _build_success() -> str:
                """완료 결과 문구를 현재 언어로 생성 (언어 변경 시 재사용)."""
                lang = self.get_lang_dict()
                return lang.get('success_msg', 'Removal completed.\n({log})').replace(
                    '{log}', str(os.path.basename(log_filename)) if log_filename else 'None'
                )

            self._final_status_builder = _build_success
            success_txt = _build_success()
            self.status_var.set(success_txt)
            self.view.set_status_color("green")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), success_txt, parent=self._dialog_parent)
        else:
            error_count = len(errors)

            def _build_error() -> str:
                """오류 결과 문구를 현재 언어로 생성 (언어 변경 시 재사용)."""
                lang = self.get_lang_dict()
                detail = format_text(
                    lang,
                    'error_delete_failed',
                    '{count} files failed to delete. See log for details.',
                    count=error_count,
                )
                return format_text(lang, 'status_error', 'Error during deletion: {error}', error=detail)

            self._final_status_builder = _build_error
            error_msg = _build_error()
            self.status_var.set(error_msg)
            self.view.set_status_color("red")
            messagebox.showerror(
                lang_dict.get('error_title', 'Error'),
                format_text(
                    lang_dict,
                    'error_delete_failed',
                    '{count} files failed to delete. See log for details.',
                    count=error_count,
                ),
                parent=self._dialog_parent,
            )

    def cleanup(self) -> None:
        """앱 종료 시 진행 중 작업 취소 신호 전송, 워커 스레드 조인 및 큐 폴링 타이머 해제.

        삭제/탐색 루프는 파일 간 취소 신호로 중단되며, 제한 시간 내 종료를 기다린 뒤 폴링을 멈춘다.
        (ModuleController 프로토콜 준수)
        """
        self.logic.request_cancel()
        for worker in list(self._worker_threads):
            if worker.is_alive():
                worker.join(timeout=RESOURCE_REMOVER_CLEANUP_JOIN_TIMEOUT)
        self._worker_threads.clear()
        self._stop_polling()

