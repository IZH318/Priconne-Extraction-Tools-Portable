"""AV Converter 컨트롤러 모듈.

비디오(.usm) 및 오디오(.awb) 파일 변환 서브 도구의 전반적인 제어 흐름,
툴체인 감지 및 다운로드, 비동기 변환 스레드 수명주기,
QueuePollingMixin 기반의 IPC 큐 폴링 및 안전한 리소스 정리(Cleanup) 담당.
"""

from __future__ import annotations

import os
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.cancellation_token import CancellationToken
from src.constants import (
    APP_DEVELOPER,
    APP_LAST_UPDATE,
    APP_VERSION,
    APP_WEBSITE,
    AV_AUDIO_SUPPORTED_EXTENSIONS,
    AV_CLEANUP_JOIN_TIMEOUT,
    AV_VIDEO_SUPPORTED_EXTENSIONS,
    FFMPEG_MIN_SUPPORTED,
    FFMPEG_TARGET_VERSION,
    TabType,
)
from src.languages import AV_CONVERTER_LANGUAGES as LANGUAGES
from src.languages import pick_language
from src.queue_events import CompletionEvent, LogEvent, ProgressEvent
from src.queue_polling import QueuePollingMixin
from src.shared_state import SharedState
from src.utils.file_list_mixin import FileListMixin

from .conversion_service import AVConversionService
from .log_renderer import AVLogRenderer
from .log_service import AVLogService
from .logic import ConversionLogic, ToolPipelineManager
from .preview_handler import AVPreviewHandler
from .preview_service import AVPreviewService
from .tooling_service import AVToolingService
from .view import AVConverterView


class AVConverterController(QueuePollingMixin, FileListMixin):
    """AV Converter 컨트롤러 클래스.

    QueuePollingMixin을 상속받아 주기적으로 백그라운드 스레드의 로그/진행률 이벤트를 소비하고,
    FileListMixin을 통해 DnD 및 파일/폴더 추가, 중복 제거, 정렬 등 파일 목록 조작 담당.

    Attributes:
        master (tk.Misc): 상위 Tkinter 윈도우 객체.
        lang_var (tk.StringVar): 활성 언어 식별자 추적 StringVar.
        base_path (Path): 애플리케이션 실행 기준 경로.
        log_queue (queue.Queue[Any]): 작업 스레드 간 이벤트 통신용 큐.
        logic (ConversionLogic): 미디어 변환 엔진 인스턴스.
        view (AVConverterView): 바인딩된 GUI 프레임 인스턴스.
        tool_pipeline (ToolPipelineManager): 외부 툴체인 다운로드/준비 매니저.
        shared_state (SharedState): 세부 서비스 계층 간 상태 공유 컨테이너.
    """

    def __init__(
        self,
        frame: ttk.Frame,
        master: tk.Misc,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
        app_temp_dir: Path | str | None = None,
    ) -> None:
        """AVConverterController 인스턴스 초기화 및 서브 서비스 바인딩.

        Args:
            frame (ttk.Frame): View가 배치될 부모 탭 프레임.
            master (tk.Misc): 최상위 애플리케이션 윈도우.
            app_lang_var (tk.StringVar | None): 전역 언어 설정 StringVar.
            about_info (dict[str, str | int] | None): 프로그램 정보 딕셔너리.
            app_temp_dir (Path | str | None): 미리보기용 임시 폴더 경로.
        """
        self.master: tk.Misc = master

        if app_lang_var:
            self.lang_var: tk.StringVar = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
        self.lang_var.trace_add("write", self._on_language_change)

        from src.utils.base_path import get_application_base_path
        self.base_path: Path = get_application_base_path()
        self.log_queue: queue.Queue[Any] = queue.Queue()
        self._conversion_threads: dict[str, threading.Thread | None] = {
            'video': None,

            'audio': None,
        }
        self.video_cancel_token: CancellationToken = CancellationToken()
        self.audio_cancel_token: CancellationToken = CancellationToken()
        self.logic: ConversionLogic = ConversionLogic(self.log_queue, self.base_path)

        self.view: AVConverterView = AVConverterView(frame, self)

        self.about_info: dict[str, str | int] = about_info or {
            'program': "AV Converter", 'version': APP_VERSION, 'updated': APP_LAST_UPDATE,
            'developer': APP_DEVELOPER, 'website': APP_WEBSITE
        }

        if app_temp_dir:
            self._preview_temp_dir: Path | str = app_temp_dir
            self._owns_temp_dir: bool = False
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix='priconne_preview_')
            self._owns_temp_dir = True

        self.usmtoolkit_path: Path | None = None
        self.vgmstream_path: Path | None = None
        self.video_full_paths: list[str] = []
        self.audio_full_paths: list[str] = []
        self.video_log_history: list[Any] = []
        self.audio_log_history: list[Any] = []
        self.video_total_files: int = 0
        self.audio_total_files: int = 0

        self.tool_pipeline: ToolPipelineManager = ToolPipelineManager(
            log_queue=self.log_queue,
            base_path=self.base_path,
            on_tools_updated_callback=self._find_tools,
        )
        self.shared_state: SharedState = SharedState()
        self.shared_state.get_lang_dict = self.get_lang_dict
        self.shared_state.get_lang_data = self.get_lang_dict
        self.shared_state.get_base_path = lambda: self.base_path
        self.shared_state.get_view = lambda: self.view
        self.shared_state.log_queue = self.log_queue
        self.shared_state.tool_pipeline = self.tool_pipeline
        self.shared_state.get_usmtoolkit_path = lambda: self.usmtoolkit_path
        self.shared_state.set_usmtoolkit_path = lambda p: setattr(self, 'usmtoolkit_path', p)
        self.shared_state.get_vgmstream_path = lambda: self.vgmstream_path
        self.shared_state.set_vgmstream_path = lambda p: setattr(self, 'vgmstream_path', p)
        self._tooling: AVToolingService = AVToolingService(
            shared_state=self.shared_state,
        )
        self.shared_state.add_log_entry = self._add_log_entry
        self.shared_state.add_spacing = self._add_spacing
        self.shared_state.get_video_full_paths = lambda: self.video_full_paths
        self.shared_state.get_audio_full_paths = lambda: self.audio_full_paths
        self.shared_state.get_video_cancel_token = lambda: self.video_cancel_token
        self.shared_state.get_audio_cancel_token = lambda: self.audio_cancel_token
        self.shared_state.start_tool_preparation = self._start_tool_preparation
        self.shared_state.set_conversion_thread = lambda tab_type, t: self._conversion_threads.__setitem__(tab_type, t)
        self.shared_state.resume_polling = self._resume_polling
        self.shared_state.is_dotnet_runtime_available = self._is_dotnet_runtime_available
        self.shared_state.logic = self.logic
        self._conversion: AVConversionService = AVConversionService(
            shared_state=self.shared_state,
        )
        self._find_tools()
        self.ffmpeg_downloader: Any = self.tool_pipeline.ffmpeg_downloader
        self.last_log_timestamp: dict[str, str | None] = {'video': None, 'audio': None}
        # FFmpeg 버전 점검은 세션당 1회만 수행
        self._ffmpeg_version_checked: bool = False
        self.view.notebook.bind('<<NotebookTabChanged>>', self._on_av_tab_changed, add='+')

        self.shared_state.get_tool_paths = lambda: {'usmtoolkit': self.usmtoolkit_path, 'vgmstream': self.vgmstream_path}
        self.shared_state.get_ffmpeg_downloader = lambda: self.ffmpeg_downloader
        self._log_renderer: AVLogRenderer = AVLogRenderer(
            get_lang_data=self.get_lang_dict,
            add_log_entry=self._add_log_entry,
            add_spacing=self._add_spacing,
            log_queue=self.log_queue,
            logic=self.logic,
            get_tool_paths=self.shared_state.get_tool_paths,
            get_ffmpeg_downloader=self.shared_state.get_ffmpeg_downloader,
        )
        self.shared_state.get_video_total_files = lambda: self.video_total_files if hasattr(self, 'video_total_files') else 0
        self.shared_state.set_video_total_files = lambda v: setattr(self, 'video_total_files', v)
        self.shared_state.get_audio_total_files = lambda: self.audio_total_files if hasattr(self, 'audio_total_files') else 0
        self.shared_state.set_audio_total_files = lambda v: setattr(self, 'audio_total_files', v)
        self.shared_state.get_converting_state = self.is_converting
        self.shared_state.set_ui_state = self.view.set_ui_state
        self.shared_state.reset_ui_state = self.view.reset_ui_state
        self.shared_state.get_video_widgets = lambda: self.view.video_widgets
        self.shared_state.get_audio_widgets = lambda: self.view.audio_widgets
        self._log_service: AVLogService = AVLogService(
            view=self.view,
            log_queue=self.log_queue,
            get_lang_dict=self.get_lang_dict,
            video_log_history=self.video_log_history,
            audio_log_history=self.audio_log_history,
            last_log_timestamp=self.last_log_timestamp,
            redraw_logs_fn=self._log_renderer.redraw_logs,
            render_log_entry_fn=self._log_renderer.render_log_entry,
            get_base_path=lambda: self.base_path,
            get_video_total_files=lambda: self.video_total_files if hasattr(self, 'video_total_files') else 0,
            set_video_total_files=lambda v: setattr(self, 'video_total_files', v),
            get_audio_total_files=lambda: self.audio_total_files if hasattr(self, 'audio_total_files') else 0,
            set_audio_total_files=lambda v: setattr(self, 'audio_total_files', v),
            get_video_cancel_token=lambda: self.video_cancel_token,
            get_audio_cancel_token=lambda: self.audio_cancel_token,
            reset_ui_state=self.view.reset_ui_state,
            get_video_widgets=lambda: self.view.video_widgets,
            get_audio_widgets=lambda: self.view.audio_widgets,
        )
        self.shared_state.get_paths = lambda tab_type: self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        self.shared_state.preview_temp_dir = str(self._preview_temp_dir)
        self.shared_state.generate_error_log = self._generate_error_log
        self.shared_state.prepare_tools = lambda tab_type, on_success: self._preview_service.prepare_tools_for_preview(tab_type, on_success)
        self._preview: AVPreviewHandler = AVPreviewHandler(
            shared_state=self.shared_state,
            get_lang_data=self.get_lang_dict,
            get_paths=lambda tab_type: self.audio_full_paths if tab_type == 'audio' else self.video_full_paths,
            logic=self.logic,
            view=self.view,
            preview_temp_dir=str(self._preview_temp_dir),
            get_tool_paths=lambda: {'usmtoolkit': self.usmtoolkit_path, 'vgmstream': self.vgmstream_path},
            generate_error_log=self._generate_error_log,
            prepare_tools=lambda tab_type, on_success: self._preview_service.prepare_tools_for_preview(tab_type, on_success),
        )
        self.shared_state.find_tools = self._find_tools
        self.shared_state.preview_selected_fn = lambda lb, tt: self._preview.preview_selected(lb, tt)
        self._preview_service: AVPreviewService = AVPreviewService(
            shared_state=self.shared_state,
        )
        self._log_renderer.log_initial_status()
        self._init_queue_polling(self.view)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리 반환."""
        return pick_language(self.lang_var.get(), LANGUAGES)

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트 처리 및 UI 텍스트/로그 재렌더링 수행.

        Args:
            *args: 가변 인자 리스트.
        """
        lang_code = self.lang_var.get()
        if lang_code in LANGUAGES:
            self.view.update_ui_text()
            self.redraw_all_logs()

    def redraw_all_logs(self) -> None:
        """모든 로그 위젯의 내용 히스토리 기반 재렌더링."""
        self._log_service.redraw_all_logs()

    def _find_tools(self) -> None:
        """usmtoolkit 폴더 및 vgmstream 하위 폴더 대상 도구 실행 파일 경로 탐색 및 설정."""
        self._tooling.find_tools()

    def _on_av_tab_changed(self, event: Any = None) -> None:
        """비디오 탭 최초 진입 시 FFmpeg 버전을 점검한다 (세션당 1회)."""
        try:
            current_tab = self.view.notebook.select()
        except tk.TclError:
            return
        if current_tab != str(self.view.video_tab):
            return
        if self._ffmpeg_version_checked:
            return
        self._ffmpeg_version_checked = True
        try:
            decision, version = self.ffmpeg_downloader.check_version()
        except Exception:  # noqa: BLE001
            return
        self._handle_ffmpeg_version_notice(decision, version)

    def _handle_ffmpeg_version_notice(self, decision: str, version: str) -> None:
        """버전 정책 결과를 로그에 기록하고, 필요 시 안내/경고 팝업을 표시.

        Args:
            decision: classify_ffmpeg_version 결과.
            version: 감지된 FFmpeg 버전 문자열.
        """
        if decision not in ("recommend", "newer", "ok"):
            return
        d = self.get_lang_dict()
        target = FFMPEG_TARGET_VERSION
        min_supported = f"{FFMPEG_MIN_SUPPORTED[0]}.{FFMPEG_MIN_SUPPORTED[1]}"

        if decision == "ok":
            self._add_log_entry('video', 'ffmpeg_version_ok', current=version, target=target)
            return

        if decision == "newer":
            self._add_log_entry('video', 'ffmpeg_version_newer', current=version, target=target)
            title = d.get('ffmpeg_newer_title', 'FFmpeg Version Warning')
            msg = d.get(
                'ffmpeg_newer_msg',
                "Detected FFmpeg version: {current} (recommended: {target}).\n"
                "A newer major version may not be fully validated for compatibility.",
            ).format(current=version, target=target)
            messagebox.showwarning(title, msg, parent=self.master)
            return

        # decision == 'recommend': 최소 지원 이상 ~ 권장 미만 → 사용자 선택(Yes/No)
        title = d.get('ffmpeg_recommend_title', 'FFmpeg Version')
        msg = d.get(
            'ffmpeg_recommend_msg',
            "Detected FFmpeg version: {current}\n"
            "Recommended: {target} / Minimum supported: {min_supported}\n\n"
            "Install and use the recommended version ({target}) now?\n"
            "(Choose No to keep using the current version.)",
        ).format(current=version, target=target, min_supported=min_supported)
        use_recommended = bool(messagebox.askyesno(title, msg, parent=self.master))
        self.ffmpeg_downloader.prefer_target = use_recommended
        if not use_recommended:
            self._add_log_entry('video', 'ffmpeg_version_recommended',
                                current=version, target=target, min_supported=min_supported)

    def _start_tool_preparation(self, tab_type: TabType, output_dir: str, next_func: Callable[[str], None]) -> None:
        """변환 전 필수 도구 존재 여부 확인 및 필요 시 다운로드 시작.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
            output_dir: 변환된 파일이 저장될 출력 디렉터리 경로.
            next_func: 도구 준비 완료 후 실행할 콜백 함수.
        """
        self._tooling.start_tool_preparation(tab_type, output_dir, next_func)

    def _ensure_usmtoolkit_compatibility(self) -> None:
        """UsmToolkit 구버전의 하드코딩된 'test.exe' 참조 호환성 패치 수행.

        UsmToolkit 구버전의 vgmstream 'test.exe' 고정 호출 대응을 위해
        vgmstream-cli.exe를 test.exe로 복사하여 호환성 보장.
        """
        self._tooling._ensure_usmtoolkit_compatibility()

    def _is_dotnet_runtime_available(self) -> bool:
        """.NET Runtime 설치 여부 확인."""
        return self._tooling.is_dotnet_runtime_available()

    def _prepare_tools_for_preview(self, tab_type: TabType, on_success: Callable[[], None]) -> None:
        """미리보기 실행 전 누락 도구 자동 준비.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
            on_success: 도구 준비 성공 시 실행할 미리보기 콜백.
        """
        self._preview_service.prepare_tools_for_preview(tab_type, on_success)

    def is_converting(self, tab_type: TabType) -> bool:
        """해당 탭의 현재 도구 다운로드 또는 변환 작업 진행 여부 확인."""
        return self._conversion.is_converting(tab_type) or self._tooling.is_preparing(tab_type)

    def add_files_cmd(self, tab_type: TabType) -> None:
        """파일 선택 대화상자 표시 후 변환 대상 파일 목록 추가.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_files(file_types), full_paths, filenames_var, tab_type)

    def add_folder_cmd(self, tab_type: TabType) -> None:
        """폴더 선택 대화상자 표시 후 폴더 내 변환 대상 파일 목록 추가.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_folder_and_search(file_types), full_paths, filenames_var, tab_type)

    def on_dnd_drop(self, event: Any, listbox: tk.Listbox, tab_type: TabType) -> None:
        """드래그 앤 드롭 이벤트 처리 및 파일 목록 추가.

        Args:
            event: Tkinter 드래그 앤 드롭 이벤트.
            listbox: 파일을 추가할 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if self.is_converting(tab_type):
            return
        if tab_type == 'audio':
            full_paths = self.audio_full_paths
            filenames_var = self.view.audio_filenames_var
            supported_exts = AV_AUDIO_SUPPORTED_EXTENSIONS
        else:
            full_paths = self.video_full_paths
            filenames_var = self.view.video_filenames_var
            supported_exts = AV_VIDEO_SUPPORTED_EXTENSIONS

        paths = self._parse_dnd_paths(self.view.winfo_toplevel(), event.data)
        if not paths:
            return
        found_paths = self._collect_files_from_paths(paths, supported_exts)
        if not found_paths:
            return
        self._add_paths_to_list(found_paths, full_paths, filenames_var, tab_type)



    def _select_files(self, file_types: list[tuple[str, str]]) -> list[str]:
        """파일 선택 대화상자 표시 및 선택된 파일 경로 리스트 반환.

        Args:
            file_types: 파일 필터 유형 리스트.

        Returns:
            선택된 파일 경로 리스트.
        """
        return list(filedialog.askopenfilenames(title=self.get_lang_dict().get('dialog_select_files', 'Select files'), filetypes=file_types) or [])

    def _select_folder_and_search(self, file_types: list[tuple[str, str]]) -> list[str]:
        """폴더 선택 대화상자 표시 및 폴더 내 검색된 파일 경로 리스트 반환.

        Args:
            file_types: 검색할 파일 필터 유형 리스트.

        Returns:
            검색된 파일 경로 리스트.
        """
        folder = filedialog.askdirectory(title=self.get_lang_dict().get('dialog_select_folder', 'Select a folder'))
        if not folder:
            return []
        exts = tuple(f".{ext.strip('*.')}" for _, p in file_types for ext in p.split())
        # 공용 FileListMixin 헬퍼로 통일 (심볼릭 링크 순환(루프) 방지 + 수집 상한 적용)
        return self._collect_files_from_paths([folder], exts)

    def _update_listbox(self, fp: list[str], fv: tk.Variable) -> None:
        """전체 파일 경로 리스트에서 파일명만 추출하여 리스트박스 갱신.

        Args:
            fp: 전체 파일 경로 리스트.
            fv: 리스트박스와 연결된 StringVar 변수.
        """
        fv.set([os.path.basename(p) for p in fp])

    def _add_paths_to_list(self, new_paths: list[str], full_paths: list[str], filenames_var: tk.Variable, tab_type: TabType) -> None:
        """선택된 파일 경로 중복 검사 후 목록 추가 및 UI 갱신.

        Args:
            new_paths: 새로 추가할 파일 경로 리스트.
            full_paths: 현재 유지 중인 전체 파일 경로 리스트.
            filenames_var: 리스트박스와 연결된 StringVar 변수.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if not new_paths:
            return

        supported_exts = AV_AUDIO_SUPPORTED_EXTENSIONS if tab_type == 'audio' else AV_VIDEO_SUPPORTED_EXTENSIONS
        added = self._add_paths_to_file_list(new_paths, full_paths, supported_exts=supported_exts)
        if not added:
            self._add_spacing(tab_type)
            self._add_log_entry(tab_type, 'alert_files_exist')
            self._add_spacing(tab_type)
            return

        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_files_added', count=len(added))
        self._add_log_entry(tab_type, 'log_total_files', total=len(full_paths))
        self._add_spacing(tab_type)

    def remove_selected_from_list(self, listbox: tk.Listbox, tab_type: TabType) -> None:
        """목록에서 선택된 항목 제거.

        Args:
            listbox: 항목을 제거할 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if self.is_converting(tab_type):
            return
        full_paths = self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if tab_type == 'audio' else self.view.video_filenames_var

        sel_idx = listbox.curselection()
        count = self._remove_selected_from_file_list(full_paths, sel_idx)
        if count > 0:
            self._update_listbox(full_paths, filenames_var)
            self._add_spacing(tab_type)
            self._add_log_entry(tab_type, 'log_files_removed', count=count)
            self._add_spacing(tab_type)

    def clear_list(self, tab_type: TabType) -> None:
        """목록의 모든 항목 제거 및 초기화.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if self.is_converting(tab_type):
            return
        full_paths = self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if tab_type == 'audio' else self.view.video_filenames_var

        count = self._clear_file_list(full_paths)
        if count == 0:
            return

        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_all_files_removed', count=count)
        self._add_spacing(tab_type)

    def start_video_conversion(self, output_dir: str) -> None:
        """비디오 변환 작업 백그라운드 스레드 시작.

        Workflow: start_video_conversion -> _start_tool_preparation -> _start_actual_video_conversion

        Args:
            output_dir: 변환된 파일이 저장될 출력 디렉터리 경로.
        """
        self._conversion.start_video_conversion(output_dir)

    def _start_actual_video_conversion(self, output_dir: str) -> None:
        """도구 준비 완료 후 실제 비디오 변환 로직 스레드 시작.

        Args:
            output_dir: 변환된 파일이 저장될 출력 디렉터리 경로.
        """
        self._conversion._start_actual_video_conversion(output_dir)

    def start_audio_conversion(self, output_dir: str, overwrite: bool) -> None:
        """오디오 변환 작업 백그라운드 스레드 시작."""
        self._conversion.start_audio_conversion(output_dir, overwrite)

    def _start_conversion_thread(self, tab_type: TabType, target_func: Any, args: tuple) -> None:
        """실제 변환 로직 실행용 백그라운드 스레드 생성 및 시작.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
            target_func: 백그라운드 스레드에서 실행할 변환 함수.
            args: 변환 함수에 전달할 인자 튜플.
        """
        self._conversion.start_conversion_thread(tab_type, target_func, args)

    def _add_log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """신규 로그 이벤트 큐 추가.

        Args:
            target_tab: 로그를 출력할 탭 ('video' 또는 'audio').
            log_key: 다국어 딕셔너리의 로그 메시지 키.
            **kwargs: 메시지 포매팅에 사용할 추가 인자.
        """
        if hasattr(self, '_log_service'):
            self._log_service.add_log_entry(target_tab, log_key, **kwargs)
        else:
            self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def log_system_message(self, target_tab: TabType, message: str) -> None:
        """시스템 레벨 메시지(오류 등) 로그 직접 추가.

        Args:
            target_tab: 로그를 출력할 탭 ('video' 또는 'audio').
            message: 출력할 문자열 메시지.
        """
        if hasattr(self, '_log_service'):
            self._log_service.log_system_message(target_tab, message)
        else:
            self.log_queue.put(LogEvent(target=target_tab, key='raw', kwargs={'text': message}))

    def _add_spacing(self, target_tab: TabType) -> None:
        """로그 빈 줄(간격) 추가 이벤트 큐 전송. 연속된 spacing 이벤트 방지로 이중 줄바꿈 방지.

        Args:
            target_tab: 빈 줄을 추가할 탭 ('video' 또는 'audio').
        """
        if hasattr(self, '_log_service'):
            self._log_service.add_spacing(target_tab)
        else:
            history = self.video_log_history if target_tab == 'video' else self.audio_log_history
            if history and history and len(history) > 0 and history[-1][1] == 'spacing':
                return
            self.log_queue.put(LogEvent(target=target_tab, is_spacing=True))

    def _should_poll(self) -> bool:
        """변환/도구 준비 작업이 진행 중일 때만 활성 주기로 폴링 (유휴 시 폴링 대기 간격 적용)."""
        return any(self.is_converting(t) for t in ('video', 'audio'))

    def _on_poll_cycle(self) -> None:
        self._log_service.on_poll_cycle()

    def _handle_progress_update(self, msg: ProgressEvent) -> None:
        self._log_service.handle_progress_update(msg)

    def _handle_completion_signal(self, msg: CompletionEvent) -> None:
        self._log_service.handle_completion_signal(msg)

    def _generate_error_log(self, tab_type: str, failed_files: list[tuple[str, str]]) -> None:
        self._log_service.generate_error_log(tab_type, failed_files)

    def preview_selected(self, listbox: tk.Listbox, tab_type: TabType) -> None:
        """리스트박스 선택 파일 미리보기 실행.

        Args:
            listbox: 선택된 항목이 있는 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        self._preview_service.preview_selected(listbox, tab_type)

    def cleanup(self) -> None:
        """앱 종료 시 호출되는 리소스 및 스레드 정리.

        전역 임시 폴더(app_temp_dir) 주입 시 AppContainer.cleanup_shared()에서 통합 관리하며,
        자체 생성 임시 폴더인 경우에만 직접 삭제.
        """
        self._stop_polling()
        self.tool_pipeline.cleanup()
        self._preview.cleanup()
        for _tab in ('video', 'audio'):
            _token = self.video_cancel_token if _tab == 'video' else self.audio_cancel_token
            _token.cancel()
            _thread = self._conversion_threads.get(_tab)
            if _thread is not None and _thread.is_alive():
                _thread.join(timeout=AV_CLEANUP_JOIN_TIMEOUT)
        if self._owns_temp_dir and os.path.exists(self._preview_temp_dir):
            shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
