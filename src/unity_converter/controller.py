"""유니티 변환기(Unity Converter) 컨트롤러 모듈.

멀티프로세싱 기반 에셋 추출 워커 풀, UI 이벤트 처리,
에셋 카테고리 필터링, 유니티 엔진 버전 프리셋, 드래그 앤 드롭 파일 등록,
에셋 상세 브라우저 창 연동 등 유니티 변환기 탭의 전반적인 제어 흐름 조율.
"""

from __future__ import annotations

import atexit
import concurrent.futures
import contextlib
import logging
import multiprocessing
import os
import threading
import tkinter as tk
from multiprocessing import Manager
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.breadcrumbs import add_breadcrumb
from src.cancellation_token import CancellationToken
from src.constants import DEFAULT_UNITY_VERSION, UNITY_VERSION_PRESETS
from src.constants import UNITY_SUPPORTED_EXTENSIONS as SUPPORTED_EXTENSIONS
from src.languages import UNITY_CONVERTER_LANGUAGES as LANGUAGES
from src.languages import pick_language
from src.queue_events import CompletionEvent, LogEvent
from src.queue_polling import QueuePollingMixin
from src.shared_state import SharedState
from src.utils.file_list_mixin import FileListMixin
from src.utils.log_history import new_log_timestamp
from src.utils.task_pool import register_process_pool, unregister_process_pool

from .asset_browser import AssetBrowserWindow
from .extractor import AssetProcessor, process_file_batch
from .service import UnityExtractionService
from .view import AssetExtractorView

logger = logging.getLogger(__name__)


class AssetExtractorController(QueuePollingMixin, FileListMixin):
    """Unity Converter MVC 컨트롤러.

    프레젠테이션 뷰, 멀티프로세싱 에셋 추출 워커 풀, IPC 큐 이벤트 폴링,
    드래그 앤 드롭 파일 등록, 에셋 브라우저 창 연동 관리.

    Attributes:
        frame: 뷰를 배치하는 탭 컨테이너 프레임.
        master: 최상위 애플리케이션 윈도우.
        app_temp_dir: 전역 애플리케이션 임시 디렉터리 경로.
        base_path: 애플리케이션 루트 실행 경로.
        file_paths: 처리 대상 .unity3d 번들 파일 경로 목록.
        output_path: 추출된 에셋 저장 대상 디렉터리 경로.
        is_running: 에셋 추출 워커 동작 여부 플래그.
        processed_files_count: 현재 실행 세션에서 처리 완료된 번들 파일 수.
        base_input_path: 중첩 폴더 추출 시 기준이 되는 공통 루트 디렉터리 경로.
        log_events: LogEvent 객체 메모리 내 로그 히스토리 버퍼.
        unity_version_var: 선택 또는 직접 입력된 유니티 버전 문자열 추적 StringVar.
        version_combo_var: 프리셋 드롭다운 선택값 추적 StringVar.
        cancel_token: 워커 프로세스 중단용 협조적 취소 토큰.
        about_info: 프로그램 메타데이터 딕셔너리.
        asset_type_vars: 에셋 유형별 활성화 상태(BooleanVar) 매핑 딕셔너리.
        lang_var: 전역 애플리케이션 언어 코드 추적 StringVar.
        view: UI 위젯 관리 프레젠테이션 뷰.
        shared_state: 콜백 주입용 공유 상태 객체.
        _extraction_service: 배치 분할 및 오류 로그 생성 관리 서비스.
    """

    # cleanup() 시 데몬 추출 스레드 조인 대기 상한(초).
    _EXTRACTION_JOIN_TIMEOUT: float = 5.0

    def __init__(
        self,
        frame: ttk.Frame,
        master: tk.Misc,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
        app_temp_dir: Path | str | None = None,
    ) -> None:
        """AssetExtractorController 및 하위 의존성 초기화.

        Args:
            frame: 뷰를 포함하는 부모 ttk.Frame 래퍼.
            master: 루트 Tk 또는 Toplevel 애플리케이션 윈도우.
            app_lang_var: 언어 변경 감지 전역 StringVar.
            about_info: 프로그램 메타데이터 딕셔너리(선택 사항).
            app_temp_dir: 루트 임시 캐시 디렉터리 경로(선택 사항).
        """
        self.frame: ttk.Frame = frame
        self.master: tk.Misc = master
        self.app_temp_dir: Path | str | None = app_temp_dir
        from src.utils.base_path import get_application_base_path
        self.base_path: Path = get_application_base_path()
        self.file_paths: list[str] = []
        self.output_path: str = ""
        self.is_running: bool = False
        self.processed_files_count: int = 0
        self.total_extracted_assets: int = 0
        self.failed_files: list[tuple[str, str]] = []
        self.base_input_path: str | None = None
        self.log_events: list[Any] = []
        self.unity_version_var: tk.StringVar = tk.StringVar(value=DEFAULT_UNITY_VERSION)
        self.version_combo_var: tk.StringVar = tk.StringVar(value=DEFAULT_UNITY_VERSION)
        self.cancel_token: CancellationToken = CancellationToken()
        self.about_info: dict[str, str | int] = about_info or {}
        self.asset_type_vars: dict[str, tk.BooleanVar] = {}

        if app_lang_var:
            self.lang_var: tk.StringVar = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self._manager: Any = None
        self._atexit_registered: bool = False
        self._log_queue: Any = None
        self._completion_queue: Any = None
        self._extraction_thread: threading.Thread | None = None
        self._executor: concurrent.futures.ProcessPoolExecutor | None = None
        self._worker_pids: set[int | None] = set()
        self._extraction_done_fallback: bool = False
        self._finalize_done: bool = False
        self.UNITY_VERSION_PRESETS = list(UNITY_VERSION_PRESETS)

        self.view = AssetExtractorView(frame, self)

        self.shared_state: SharedState = SharedState()
        self.shared_state.get_lang_dict = self.get_lang_dict
        self.shared_state.get_base_path = lambda: self.base_path
        self.shared_state.get_view = lambda: self.view
        self._extraction_service: UnityExtractionService = UnityExtractionService(shared_state=self.shared_state, controller=self)

        self.lang_var.trace_add('write', self._on_language_change)

        self.view.update_ui_text()
        self._log('program_started')
        self._init_queue_polling(self.frame)

    @property
    def manager(self) -> Any:
        """multiprocessing.Manager 인스턴스 지연 생성 및 반환."""
        if self._manager is None:
            self._manager = Manager()
            if not self._atexit_registered:
                atexit.register(self.cleanup)
                self._atexit_registered = True
        return self._manager

    @property
    def log_queue(self) -> Any:
        """워커 프로세스로부터 LogEvent 항목을 수신하는 IPC 큐 반환."""
        if self._log_queue is None:
            self._log_queue = self.manager.Queue()
        return self._log_queue

    @property
    def completion_queue(self) -> Any:
        """워커 프로세스로부터 CompletionEvent 항목을 수신하는 IPC 큐 반환."""
        if self._completion_queue is None:
            self._completion_queue = self.manager.Queue()
        return self._completion_queue

    def cleanup(self) -> None:
        """실행 중 추출 취소/워커 종료, 큐 폴링 중단 및 multiprocessing Manager 정상 종료."""
        self._cancel_running_extraction()
        self._stop_polling()
        if self._manager is not None:
            try:
                self._manager.shutdown()
            except (OSError, EOFError):
                pass
            self._manager = None
            self._log_queue = None
            self._completion_queue = None
            try:
                if self._atexit_registered:
                    atexit.unregister(self.cleanup)
                    self._atexit_registered = False
            except (ValueError, RuntimeError) as _exc:
                logger.debug("Failed to unregister atexit cleanup: %s", _exc)

    def _terminate_pool_workers(self) -> None:
        """현재 추출 작업 풀에 속한 워커 프로세스를 강제 종료."""
        worker_pids = set(self._worker_pids)
        processes = getattr(self._executor, "_processes", None)
        if processes:
            with contextlib.suppress(OSError, RuntimeError, AttributeError):
                worker_pids.update(p.pid for p in processes.values() if p.pid is not None)
        if not worker_pids:
            return
        for p in multiprocessing.active_children():
            if p.pid in worker_pids:
                try:
                    p.terminate()
                except (OSError, ProcessLookupError) as _exc:
                    logger.debug("Failed to terminate worker process: %s", _exc)

    def _cancel_running_extraction(self) -> None:
        """실행 중인 추출 작업 취소, 워커 프로세스 종료 및 추출 스레드 조인.

        실행 중인 추출이 없으면 아무 동작도 수행하지 않음. 취소 신호를 전파한 뒤
        ProcessPoolExecutor 워커를 강제 종료하고, 데몬 추출 스레드가 완료 이벤트
        (`__EXTRACTION_DONE__`)를 발행할 시간을 확보하도록 짧은 타임아웃으로 조인.
        """
        thread = self._extraction_thread
        executor = self._executor
        if thread is None and executor is None and not self.is_running:
            return

        with contextlib.suppress(RuntimeError, AttributeError, OSError):
            self.cancel_token.cancel()

        self._terminate_pool_workers()

        if executor is not None:
            with contextlib.suppress(RuntimeError, AttributeError, OSError):
                executor.shutdown(wait=False, cancel_futures=True)

        if thread is not None and thread.is_alive():
            thread.join(timeout=self._EXTRACTION_JOIN_TIMEOUT)

    def _get_enabled_types(self) -> set[str]:
        """필터 체크박스에서 현재 활성화된 에셋 유형 집합 수집 및 반환.

        Returns:
            활성화된 에셋 유형 이름 문자열 집합.
        """
        return {name for name, var in self.asset_type_vars.items() if var.get()}

    @property
    def asset_skip_types(self) -> set[str]:
        """내보내기 미지원 기본 유니티 컴포넌트 유형 집합 반환."""
        return AssetProcessor.SKIP_TYPES

    @property
    def asset_default_enabled(self) -> set[str]:
        """기본 활성화 대상 에셋 유형 집합 반환."""
        return AssetProcessor.DEFAULT_ENABLED

    def select_all_types(self) -> None:
        """모든 에셋 유형 필터 체크박스 선택 활성화."""
        for var in self.asset_type_vars.values():
            var.set(True)

    def deselect_all_types(self) -> None:
        """모든 에셋 유형 필터 체크박스 선택 해제."""
        for var in self.asset_type_vars.values():
            var.set(False)

    def on_version_selection_change(self, event: Any = None) -> None:
        """유니티 엔진 버전 콤보박스 선택 변경 이벤트 처리.

        '직접 입력' 선택 시 수동 버전 입력 엔트리를 활성화하고,
        프리셋 선택 시 해당 버전으로 고정 및 비활성화.

        Args:
            event: Tkinter 이벤트 객체(선택 사항).
        """
        selected = self.version_combo_var.get()
        if selected in self.UNITY_VERSION_PRESETS:
            self.unity_version_var.set(selected)
            self.view.set_version_entry_state('disabled')
        else:
            self.view.set_version_entry_state('normal')
            if self.unity_version_var.get() in self.UNITY_VERSION_PRESETS:
                self.unity_version_var.set("")
            self.view.set_version_entry_state('normal', focus=True)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 언어 설정에 맞는 다국어 번역 문자열 딕셔너리 조회 및 반환.

        Returns:
            번역 키와 다국어 문자열 매핑 딕셔너리.
        """
        return pick_language(self.lang_var.get(), LANGUAGES)

    def _on_language_change(self, *args: str) -> None:
        """애플리케이션 언어 StringVar 변경 시 호출되는 콜백.

        Args:
            *args: Tkinter trace 콜백 가변 인자.
        """
        try:
            self.view.update_ui_text()
            self.redraw_all_logs()
        except tk.TclError:
            pass

    def redraw_all_logs(self) -> None:
        """누적된 LogEvent 히스토리를 UI 텍스트 위젯에 재렌더링."""
        try:
            self.view.log_text.config(state=tk.NORMAL)
            self.view.log_text.delete('1.0', tk.END)
            for event in self.log_events:
                self._render_log_event(event)
            self.view.log_text.config(state=tk.DISABLED)
            self.view.log_text.see(tk.END)
        except tk.TclError:
            pass

    def _add_log_event(
        self,
        message_key: str,
        level: str = 'INFO',
        format_args: dict[str, Any] | None = None,
        prefix: str | None = None,
    ) -> LogEvent:
        """타임스탬프가 포함된 LogEvent 생성 및 반환.

        Args:
            message_key: 다국어 번역 사전 키.
            level: 로그 심각도 수준('INFO', 'WARNING', 'ERROR', 'SUCCESS').
            format_args: 문자열 보간용 서식화 인자 딕셔너리(선택 사항).
            prefix: 대상 접두사(예: 파일명, 선택 사항).

        Returns:
            신규 생성된 LogEvent 인스턴스.
        """
        return LogEvent(
            target=prefix or "",
            key=message_key,
            level=level,
            kwargs=format_args or {},
            un_timestamped=False,
            timestamp=new_log_timestamp()
        )

    def _render_log_event(self, event: LogEvent, widget: Any = None) -> None:
        """색상 태그와 타임스탬프가 적용된 메시지를 로그 Text 위젯에 추가 출력.

        Args:
            event: 렌더링 대상 LogEvent 객체.
            widget: 출력 대상 Text 위젯(미지정 시 self.view.log_text 사용).
        """
        target_widget = widget or self.view.log_text
        timestamp = event.timestamp or new_log_timestamp()
        prefix = event.target
        message_key = event.key
        level = event.level
        format_args = event.kwargs

        lang = self.lang_var.get()
        message_template = pick_language(lang, LANGUAGES).get(message_key, message_key)

        if message_key == 'raw_text':
            message = format_args.get('text', '') if format_args else ''
        else:
            message = message_template.format(**format_args) if format_args else message_template

        log_prefix = f"[{prefix}] " if prefix else ""
        full_message = f"[{timestamp}] {log_prefix}{message}\n"

        logger.info("[Unity Converter] %s%s", log_prefix, message)

        target_widget.config(state=tk.NORMAL)
        target_widget.insert(tk.END, full_message, level)
        target_widget.config(state=tk.DISABLED)

    def _log(
        self,
        message_key: str,
        level: str = 'INFO',
        format_args: dict[str, Any] | None = None,
        prefix: str | None = None,
    ) -> None:
        """LogEvent 생성, 히스토리 버퍼 추가 및 UI 즉시 출력.

        Args:
            message_key: 번역 딕셔너리 키.
            level: 로그 심각도 문자열.
            format_args: 템플릿 서식화 딕셔너리.
            prefix: 메시지 접두사 문자열(선택 사항).
        """
        event = self._add_log_event(message_key, level, format_args, prefix)
        self.log_events.append(event)
        self._render_log_event(event)
        self.view.log_text.see(tk.END)

    def _should_poll(self) -> bool:
        """에셋 추출 작업이 진행 중일 때만 활성 주기로 폴링 (유휴 시 폴링 대기 간격 적용)."""
        return bool(self.is_running)

    def _on_poll_cycle(self) -> None:
        """주기적 UI 타이머 틱: IPC 로그 및 완료 큐 비우기 및 UI 상태 동기화."""
        if self.is_running and self.cancel_token.is_cancelled:
            # 취소 요청 시 현재 배치 완료를 기다리지 않고 워커 프로세스를 즉시 종료
            self._terminate_pool_workers()
        if self._extraction_done_fallback:
            # 큐 사용이 불가능한 상태에서도 UI 잠금이 남지 않도록 폴링 틱에서 직접 완료 처리한다.
            self._extraction_done_fallback = False
            self._on_extraction_complete()
            return
        log_batch = self._drain_queue(self.log_queue)

        completion_batch_size = 0
        is_extraction_done = False
        for event in self._drain_queue(self.completion_queue):
            if getattr(event, 'target', '') == '__EXTRACTION_DONE__':
                is_extraction_done = True
                continue
            completion_batch_size += 1
            if hasattr(event, 'result') and isinstance(event.result, int):
                self.total_extracted_assets += event.result

        if log_batch:
            self.view.log_text.config(state=tk.NORMAL)
            for log_item in log_batch:
                if isinstance(log_item, LogEvent):
                    if log_item.key == 'raw_text':
                        event = self._add_log_event('raw_text', log_item.level, {'text': log_item.kwargs.get('text', '')})
                    else:
                        if log_item.key == 'worker_process_error':
                            error_msg = str(log_item.kwargs.get('error', 'Unknown Error'))
                            self.failed_files.append((log_item.target, error_msg))
                        event = self._add_log_event(log_item.key, log_item.level, log_item.kwargs, log_item.target)
                    self.log_events.append(event)
                    self._render_log_event(event)
            self.view.log_text.config(state=tk.DISABLED)
            self.view.log_text.see(tk.END)

        if completion_batch_size > 0:
            self.processed_files_count += completion_batch_size
            self.view.update_progress_bar()

        if is_extraction_done:
            self._on_extraction_complete()

    def select_files(self) -> None:
        """복수 .unity3d 파일 선택 대화상자 표시 및 목록 추가."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        paths = filedialog.askopenfilenames(
            title=d.get('file_dialog_title', 'Select Unity3D files'),
            filetypes=((d.get('file_dialog_type', 'Unity3D Files'), "*.unity3d"),)
        )
        if paths:
            self.base_input_path = None
            self._add_files_to_list(paths)

    def select_folder(self) -> None:
        """폴더 선택 대화상자 표시 및 .unity3d 파일 재귀 탐색 후 목록 추가."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        folder_path = filedialog.askdirectory(title=d.get('folder_dialog_title', 'Select a folder containing Unity3D files'))
        if folder_path:
            self.base_input_path = folder_path
            # 공용 FileListMixin 헬퍼로 통일 (심볼릭 링크 순환(루프) 방지 + 수집 상한 적용)
            found_paths = self._collect_files_from_paths([folder_path], SUPPORTED_EXTENSIONS)
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log('no_files_to_process', "WARNING")

    def on_dnd_drop(self, event: Any) -> None:
        """파일 드래그 앤 드롭 목록 추가 이벤트 처리.

        Args:
            event: 드롭된 파일 경로 데이터를 포함하는 Tkinter DnD 이벤트 객체.
        """
        if self.is_running:
            return
        paths = self._parse_dnd_paths(self.view.winfo_toplevel(), event.data)

        found_paths = self._collect_files_from_paths(paths, SUPPORTED_EXTENSIONS)
        for path in paths:
            if os.path.isdir(path):
                self.base_input_path = path if not self.base_input_path else self.base_input_path
                break

        if found_paths:
            self._add_files_to_list(found_paths)
        else:
            self._log('no_files_to_process', "WARNING")

    def _add_files_to_list(self, new_paths: Any) -> None:
        """검증된 파일 경로를 대상 목록에 추가하고 Listbox 위젯 갱신.

        Args:
            new_paths: 추가할 파일 경로 시퀀스.
        """
        added = self._add_paths_to_file_list(new_paths, self.file_paths)
        added_count = len(added)

        if added_count > 0:
            self.file_paths.sort()
            self.view.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.view.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('added_files', format_args={'count': added_count, 'total': len(self.file_paths)})

    def remove_selected_files(self, event: Any = None) -> None:
        """파일 목록 Listbox에서 선택된 항목 제거.

        Args:
            event: Tkinter 이벤트 객체(선택 사항).
        """
        if self.is_running:
            return
        selected_indices = self.view.file_listbox.curselection()
        count = self._remove_selected_from_file_list(self.file_paths, selected_indices)
        if count > 0:
            self.view.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.view.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('removed_selected_files', format_args={'count': count, 'total': len(self.file_paths)})

    def remove_all_files(self) -> None:
        """가져온 전체 파일 목록 제거 및 초기화."""
        if self.is_running:
            return
        if not self.file_paths:
            return
        count = self._clear_file_list(self.file_paths)
        self.view.file_listbox.delete(0, tk.END)
        self.base_input_path = None
        self._log('removed_all_files', format_args={'count': count})

    def open_asset_browser(self) -> None:
        """선택된 번들 파일 대상 대화형 에셋 브라우저(AssetBrowserWindow) 모달 창 실행."""
        selection = self.view.file_listbox.curselection()
        if not selection or selection[0] >= len(self.file_paths):
            return
        file_path = str(self.file_paths[selection[0]])
        d = self.get_lang_dict()
        unity_version = self.unity_version_var.get().strip() or DEFAULT_UNITY_VERSION
        AssetBrowserWindow(
            self.view.winfo_toplevel(),
            file_path,
            d,
            unity_version,
            self.app_temp_dir,
            generate_error_log=self._generate_error_log,
        )

    def select_output_dir(self) -> None:
        """에셋 추출 결과 저장 대상 폴더 선택 대화상자 표시 및 경로 설정."""
        if self.is_running:
            return
        d = self.get_lang_dict()
        path = filedialog.askdirectory(title=d.get('output_folder', 'Output Folder'))
        if path:
            self.output_path = path
            self.view.output_entry.config(state=tk.NORMAL)
            self.view.output_entry.delete(0, tk.END)
            self.view.output_entry.insert(0, path)
            self.view.output_entry.config(state='readonly')
            self._log('output_dir_set', format_args={'path': path})

    def start_extraction(self) -> None:
        """설정값 검증 후 백그라운드 에셋 추출 시작."""
        d = self.get_lang_dict()
        ok, reason = self._extraction_service.validate_start(self.file_paths, self.output_path)
        if not ok:
            if reason == "no_files":
                messagebox.showwarning(
                    d.get('warn_no_files_title', 'Cannot Start'),
                    d.get('warn_no_files_msg', 'No files to extract in the list.'),
                    parent=self.view,
                )
            elif reason == "no_output":
                messagebox.showwarning(
                    d.get('warn_no_output_title', 'Cannot Start'),
                    d.get('warn_no_output_msg', 'Please specify an output folder.'),
                    parent=self.view,
                )
            return

        self.is_running = True
        self._resume_polling()
        self.cancel_token.reset()
        add_breadcrumb("conv", "Started asset extraction", {"files": len(self.file_paths), "output": self.output_path})
        self.view.toggle_controls(False)
        self.processed_files_count = 0
        self.total_extracted_assets = 0
        self.failed_files = []
        self._extraction_done_fallback = False
        self._finalize_done = False
        self.view.progress_bar.config(maximum=len(self.file_paths))
        self.view.update_progress_bar()
        self._current_enabled_types: set[str] = self._get_enabled_types()
        unity_version = self.unity_version_var.get().strip()
        if not unity_version: unity_version = DEFAULT_UNITY_VERSION
        self._current_unity_version: str = unity_version
        self._extraction_thread = threading.Thread(target=self._run_process_pool, daemon=True)
        self._extraction_thread.start()

    def _run_process_pool(self) -> None:
        """워커 스레드 진입점: ProcessPoolExecutor 배치 워커 풀 관리 및 취소 토큰 처리."""
        completion_queue: Any = None
        try:
            # 종료 시 completion_queue 프로퍼티가 이미 shutdown 된 Manager 를 대체 생성하지 않도록 1회만 확보.
            completion_queue = self.completion_queue
            batches = self._extraction_service.prepare_batches(self.file_paths)
            if not batches:
                batches = [list(self.file_paths)]
            num_workers = len(batches)
            self.log_queue.put(LogEvent(target="", key='processing_started', level='INFO', kwargs={'num_workers': num_workers}))

            unity_version = self._current_unity_version
            enabled_types = self._current_enabled_types
            baseline_pids = {p.pid for p in multiprocessing.active_children()}

            executor = register_process_pool(concurrent.futures.ProcessPoolExecutor(max_workers=num_workers))
            try:
                self._executor = executor
                future_to_batch = {
                    executor.submit(
                        process_file_batch, batch, self.output_path, self.base_input_path,
                        self.log_queue, completion_queue, unity_version, enabled_types
                    ): batch
                    for batch in batches
                }
                worker_pids = {p.pid for p in multiprocessing.active_children()} - baseline_pids
                self._worker_pids = worker_pids
                for future in concurrent.futures.as_completed(future_to_batch):
                    if self.cancel_token.is_cancelled:
                        self.log_queue.put(LogEvent(target="", key='extraction_cancelled', level='ERROR'))
                        self._terminate_pool_workers()
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        exc = future.exception()
                        if exc:
                            batch = future_to_batch[future]
                            for file_p in batch:
                                b_name = os.path.basename(file_p)
                                self.log_queue.put(LogEvent(target=b_name, key='worker_process_error', level='ERROR', kwargs={'error': str(exc)}))
                                completion_queue.put(CompletionEvent(success=False, result=0))
                    except (OSError, RuntimeError, ValueError, TypeError) as future_err:
                        batch = future_to_batch.get(future, [])
                        for file_p in (batch or ["unknown"]):
                            b_name = os.path.basename(file_p) if file_p != "unknown" else "unknown"
                            self.log_queue.put(LogEvent(target=b_name, key='worker_process_error', level='ERROR', kwargs={'error': str(future_err)}))
                            completion_queue.put(CompletionEvent(success=False, result=0))
            finally:
                unregister_process_pool(executor)
                # 컨텍스트 매니저 종료 시의 암묵적 wait=True 조인을 피하고 논블로킹(Non-blocking) 종료로 고정
                with contextlib.suppress(RuntimeError, AttributeError, OSError):
                    executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:  # noqa: BLE001
            logger.exception("ProcessPoolExecutor encountered an unexpected failure: %s", e)
        finally:
            self._worker_pids = set()
            self._executor = None
            self._extraction_thread = None
            with contextlib.suppress(RuntimeError, AttributeError):
                self.cancel_token.finish()
            if completion_queue is not None:
                try:
                    completion_queue.put(CompletionEvent(target='__EXTRACTION_DONE__'))
                except Exception as exc:  # noqa: BLE001
                    # 센티넬 전달이 불가능한 경우에도 폴링 루프가 UI 잠금을 해제하도록 폴백 플래그를 세운다.
                    logger.debug("Failed to publish extraction completion event: %s", exc)
                    self._extraction_done_fallback = True
            else:
                logger.debug("Completion queue unavailable; falling back to poll-cycle completion.")
                self._extraction_done_fallback = True

    def _on_extraction_complete(self) -> None:
        """모든 워커 배치가 종료되었을 때 호출되는 콜백 예약."""
        self.frame.after(200, self._finalize_completion)

    def _finalize_completion(self) -> None:
        """오류 발생 시 에러 로그 리포트 생성 및 UI 조작 컨트롤 재활성화.

        동일 실행에 대해 두 번 호출되더라도(센티넬과 폴백 신호의 중복 전달) 한 번만 수행한다.
        """
        if self._finalize_done:
            return
        self._finalize_done = True
        if len(self.failed_files) > 0:
            self._generate_error_log(self.failed_files)
            from tkinter import messagebox
            d = self.get_lang_dict()
            title = d.get('msgbox_error_log_saved_title', 'Error Log Created')
            text = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
            messagebox.showwarning(title, text, parent=self.view)

        self._log("raw_text", format_args={'text': "========================================"})
        if self.total_extracted_assets > 0:
            self._log("total_extracted_assets", format_args={'count': self.total_extracted_assets})
        if not self.cancel_token.is_cancelled:
            self._log('all_tasks_completed', "SUCCESS")
        self.is_running = False
        self.frame.after(0, lambda: self.view.toggle_controls(True))

    def _generate_error_log(self, failed_files: list[tuple[str, str]], context: str = "Asset Extraction") -> None:
        """추출 서비스로 오류 보고서 작성 위임."""
        self._extraction_service.generate_error_log(
            failed_files,
            getattr(self, "base_input_path", None),
            getattr(self, "output_path", None),
            context,
        )
