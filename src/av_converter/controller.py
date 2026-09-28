from __future__ import annotations
import logging
import queue
import os
import shutil
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from src.cancellation_token import CancellationToken
from src.constants import SEPARATOR_LONG as SEPARATOR, APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, APP_WEBSITE, GUI_POLLING_INTERVAL_MS, SENTINEL_VIDEO_DONE, TabType
from src.languages import AV_CONVERTER_LANGUAGES as LANGUAGES
from src.breadcrumbs import add_breadcrumb
from src.queue_events import (
    QueueEvent, LogEvent, LogBlockEvent, ProgressEvent, CompletionEvent
)
from src.utils.about_dialog import show_about_dialog
from .logic import ConversionLogic, FFmpegDownloader
from .log_renderer import AVLogRenderer
from .preview_handler import AVPreviewHandler
from .view import AVConverterView
from src.queue_polling import QueuePollingMixin
from src.log_history import LogHistoryMixin
from src.utils.file_list_mixin import FileListMixin

class AVConverterController(QueuePollingMixin, LogHistoryMixin, FileListMixin):
    def __init__(self, frame: ttk.Frame, master: tk.Tk | tk.Toplevel, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None, app_temp_dir: str | None = None) -> None:
        """AVConverterController 객체를 초기화합니다.

        Args:
            frame: gui.py의 ttk.Frame 래퍼 (View의 부모 위젯).
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            app_lang_var: 전역 언어 설정 StringVar.
            about_info: About 대화상자에 표시될 정보 딕셔너리.
            app_temp_dir: 미리보기 등을 위한 임시 폴더 경로.
        """
        self.master = master
        
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
        self.lang_var.trace_add("write", self._on_language_change)
        
        from src.utils.base_path import get_application_base_path
        self.base_path = get_application_base_path()
        self.log_queue = queue.Queue()
        self.video_cancel_token = CancellationToken()
        self.audio_cancel_token = CancellationToken()
        self.logic = ConversionLogic(self.log_queue, self.base_path)
        
        self.view = AVConverterView(frame, self)
        
        self.about_info = about_info or {
            'program': "AV Converter", 'version': APP_VERSION, 'updated': APP_LAST_UPDATE,
            'developer': APP_DEVELOPER, 'website': APP_WEBSITE
        }
        
        if app_temp_dir:
            self._preview_temp_dir = app_temp_dir
            self._owns_temp_dir = False
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix='priconne_preview_')
            self._owns_temp_dir = True
        
        self.usmtoolkit_path = None
        self.vgmstream_path = None
        self.video_full_paths = []
        self.audio_full_paths = []
        self.video_total_files = 0
        self.audio_total_files = 0
        self.video_log_history = []
        self.audio_log_history = []

        self._find_tools()
        ffmpeg_parent_dir = self.usmtoolkit_path.parent if self.usmtoolkit_path else self.base_path
        self.ffmpeg_downloader = FFmpegDownloader(self.log_queue, ffmpeg_parent_dir, self.get_lang_dict)
        self.last_log_timestamp = {'video': None, 'audio': None}

        self._log_renderer = AVLogRenderer(
            get_lang_data=self.get_lang_dict,
            add_log_entry=self._add_log_entry,
            add_spacing=self._add_spacing,
            log_queue=self.log_queue,
            logic=self.logic,
            get_tool_paths=lambda: {'usmtoolkit': self.usmtoolkit_path, 'vgmstream': self.vgmstream_path},
            get_ffmpeg_downloader=lambda: self.ffmpeg_downloader,
        )
        self._preview = AVPreviewHandler(
            get_lang_data=self.get_lang_dict,
            get_paths=lambda tab_type: self.audio_full_paths if tab_type == 'audio' else self.video_full_paths,
            logic=self.logic,
            view=self.view,
            preview_temp_dir=self._preview_temp_dir,
            get_tool_paths=lambda: {'usmtoolkit': self.usmtoolkit_path, 'vgmstream': self.vgmstream_path},
        )

        # 참고: video_log_history, audio_log_history는 73-74행에서 이미 초기화됨
        self._log_renderer.log_initial_status()
        self._init_queue_polling(self.view)

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))

    def _on_language_change(self, *args: Any) -> None:
        """언어 변경 이벤트를 처리하고 UI 텍스트 및 로그를 다시 그립니다.

        Args:
            *args: 가변 인자 리스트.
        """
        lang_code = self.lang_var.get()
        if lang_code in LANGUAGES:
            self.view.update_ui_text()
            self.redraw_all_logs()

    def _get_log_configs(self) -> list[tuple[list, Any]]:
        """재렌더링 대상 (히스토리 리스트, Text 위젯) 쌍의 리스트를 반환합니다."""
        return [
            (self.video_log_history, self.view.video_log_text),
            (self.audio_log_history, self.view.audio_log_text),
        ]

    def redraw_all_logs(self) -> None:
        """모든 로그 위젯의 내용을 히스토리 기반으로 재렌더링합니다."""
        configs_with_tabs = [
            ('video', self.video_log_history, self.view.video_log_text),
            ('audio', self.audio_log_history, self.view.audio_log_text),
        ]
        self._log_renderer.redraw_logs(configs_with_tabs, self.last_log_timestamp)

    def _find_tools(self) -> None:
        """UsmToolkit.exe와 vgmstream-cli.exe 파일 경로를 탐색하고 설정합니다."""
        for root, _, files in os.walk(self.base_path.parent):
            lower_files = [f.lower() for f in files]
            if not self.usmtoolkit_path and "usmtoolkit.exe" in lower_files:
                self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "vgmstream-cli.exe" in lower_files and "vgmstream" in str(Path(root)).lower():
                self.vgmstream_path = Path(root) / "vgmstream-cli.exe"
            # 두 도구를 모두 찾았으면 탐색 조기 종료
            if self.usmtoolkit_path and self.vgmstream_path:
                break
        # 도구 탐색 완료 후 호환성 패치 수행
        self._ensure_usmtoolkit_compatibility()

    def _ensure_usmtoolkit_compatibility(self) -> None:
        """UsmToolkit 구버전의 하드코딩된 'test.exe' 참조를 위한 호환성 패치를 수행합니다.

        UsmToolkit의 일부 구버전은 vgmstream을 'test.exe'라는 고정된 이름으로
        호출하므로, vgmstream-cli.exe를 test.exe로 복사하여 호환성을 보장합니다.
        """
        if self.vgmstream_path and self.vgmstream_path.exists():
            test_exe_path = self.vgmstream_path.parent / "test.exe"
            if not test_exe_path.exists():
                try:
                    shutil.copy2(self.vgmstream_path, test_exe_path)
                except OSError:
                    pass

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES.get('ko', {}))
        show_about_dialog(lang_dict, self.about_info, self.view)


    def add_files_cmd(self, tab_type: TabType) -> None:
        """파일 선택 대화상자를 열어 변환 대상 파일을 목록에 추가합니다.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_files(file_types), file_types, full_paths, filenames_var, tab_type)

    def add_folder_cmd(self, tab_type: TabType) -> None:
        """폴더 선택 대화상자를 열어 폴더 내 변환 대상 파일을 목록에 추가합니다.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_folder_and_search(file_types), file_types, full_paths, filenames_var, tab_type)

    def on_dnd_drop(self, event: Any, listbox: tk.Listbox, tab_type: TabType) -> None:
        """드래그 앤 드롭 이벤트를 처리하여 파일을 목록에 추가합니다.

        Args:
            event: Tkinter 드래그 앤 드롭 이벤트.
            listbox: 파일을 추가할 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if tab_type == 'audio':
            full_paths = self.audio_full_paths
            filenames_var = self.view.audio_filenames_var
            file_types = [("CRIWARE Audio", "*.awb")]
            action_btn = self.view.audio_widgets.get('action_btn')
            if action_btn and action_btn.cget('state') == 'disabled':
                return
        else:
            full_paths = self.video_full_paths
            filenames_var = self.view.video_filenames_var
            file_types = [("USM Video files", "*.usm")]
            action_btn = self.view.video_widgets.get('action_btn')
            if action_btn and action_btn.cget('state') == 'disabled':
                return

        paths = self._parse_dnd_paths(self.view.winfo_toplevel(), event.data)
        if not paths:
            return
        self._add_paths_to_list(paths, file_types, full_paths, filenames_var, tab_type)



    def _select_files(self, file_types: list[tuple[str, str]]) -> list[str]:
        """파일 선택 대화상자를 띄우고 선택된 파일 경로 리스트를 반환합니다.

        Args:
            file_types: 파일 필터 유형 리스트.

        Returns:
            선택된 파일 경로 리스트.
        """
        return list(filedialog.askopenfilenames(title=self.get_lang_dict().get('dialog_select_files', 'Select files'), filetypes=file_types) or [])

    def _select_folder_and_search(self, file_types: list[tuple[str, str]]) -> list[str]:
        """폴더 선택 대화상자를 띄우고 선택된 폴더 내 모든 파일 경로 리스트를 반환합니다.

        Args:
            file_types: 검색할 파일 필터 유형 리스트.

        Returns:
            검색된 파일 경로 리스트.
        """
        folder = filedialog.askdirectory(title=self.get_lang_dict().get('dialog_select_folder', 'Select a folder'))
        if not folder:
            return []
        exts = [ext.strip('*.') for _, p in file_types for ext in p.split()]
        found_files = []
        for r, _, fs in os.walk(folder):
            for f in fs:
                if any(f.lower().endswith(f".{ext}") for ext in exts):
                    found_files.append(str(Path(r) / f))
        return found_files

    def _update_listbox(self, fp: list[str], fv: tk.Variable) -> None:
        """파일 경로 리스트를 받아 파일명만 추출하여 리스트박스를 업데이트합니다.

        Args:
            fp: 전체 파일 경로 리스트.
            fv: 리스트박스와 연결된 StringVar 변수.
        """
        fv.set([os.path.basename(p) for p in fp])
        
    def _add_paths_to_list(self, new_paths: list[str], file_types: list[tuple[str, str]], full_paths: list[str], filenames_var: tk.Variable, tab_type: TabType) -> None:
        """선택된 파일 경로들을 중복 검사 후 목록에 추가하고 UI를 갱신합니다.

        Args:
            new_paths: 새로 추가할 파일 경로 리스트.
            file_types: 현재 탭의 파일 필터 유형.
            full_paths: 현재 유지 중인 전체 파일 경로 리스트.
            filenames_var: 리스트박스와 연결된 StringVar 변수.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        if not new_paths:
            return

        added = self._add_paths_to_file_list(new_paths, full_paths)
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
        """목록에서 선택된 항목들을 제거합니다.

        Args:
            listbox: 항목을 제거할 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
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
        """목록의 모든 항목을 제거하여 초기화합니다.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
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
        """비디오 변환 작업을 백그라운드 스레드로 시작합니다.

        Workflow: start_video_conversion → _start_ffmpeg_preparation → _start_actual_video_conversion
        """
        if not self.video_full_paths:
            self._add_log_entry('video', 'error_no_files')
            return
        if not output_dir:
            self._add_log_entry('video', 'error_no_output_video')
            return
        add_breadcrumb("conv", "비디오 변환 시작", {"files": len(self.video_full_paths), "output": output_dir})
        self._start_ffmpeg_preparation(output_dir)

    def _start_ffmpeg_preparation(self, output_dir: str) -> None:
        """비디오 변환 전 FFmpeg의 존재 여부를 확인하고 필요시 다운로드하는 작업을 시작합니다.

        Args:
            output_dir: 변환된 파일이 저장될 출력 디렉터리 경로.
        """
        if not self.usmtoolkit_path:
            self._add_log_entry('video', 'ffmpeg_no_usm_path')
            return

        self.view.set_ui_state('video', 'disabled')
        self._add_log_entry('video', 'ffmpeg_preparing')
        
        download_future = self.ffmpeg_downloader.ensure_ffmpeg_ready()

        def check_ffmpeg_status():
            if download_future.done():
                try:
                    if download_future.result(): 
                        self._start_actual_video_conversion(output_dir)
                    else: 
                        self._add_log_entry('video', 'ffmpeg_prepare_fail')
                        self.view.reset_ui_state('video')
                except (RuntimeError, OSError, ValueError) as e:
                    self._add_log_entry('video', 'ffmpeg_prepare_fail')
                    self._add_log_entry('video', 'conv_log_error_exception', error=e)
                    self.view.reset_ui_state('video')
            else: 
                self.view.after(GUI_POLLING_INTERVAL_MS, check_ffmpeg_status)
                
        self.view.after(GUI_POLLING_INTERVAL_MS, check_ffmpeg_status)
    
    def _start_conversion_thread(self, tab_type: TabType, target_func: Any, args: tuple) -> None:
        """실제 변환 로직을 실행할 백그라운드 스레드를 생성하고 시작합니다.

        Args:
            tab_type: 탭 타입 ('video' 또는 'audio').
            target_func: 백그라운드 스레드에서 실행할 변환 함수.
            args: 변환 함수에 전달할 인자 튜플.
        """
        self._add_spacing(tab_type)
        widgets = self.view.video_widgets if tab_type == 'video' else self.view.audio_widgets
        cancel_token = self.video_cancel_token if tab_type == 'video' else self.audio_cancel_token
        
        self.view.set_ui_state(tab_type, 'disabled')
        cancel_token.reset()
        
        widgets['action_btn'].config(
            state=tk.NORMAL, 
            text=self.get_lang_dict().get('cancel_conversion', 'Cancel'),
            command=cancel_token.cancel
        )
        
        thread = threading.Thread(target=target_func, daemon=True, args=args)
        thread.start()

    def _start_actual_video_conversion(self, output_dir: str) -> None:
        """준비가 완료된 후 실제 비디오 변환 로직 스레드를 시작합니다.

        Args:
            output_dir: 변환된 파일이 저장될 출력 디렉터리 경로.
        """
        self._start_conversion_thread(
            'video',
            self.logic.run_video_conversion,
            (self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.video_cancel_token)
        )

    def start_audio_conversion(self, output_dir: str, overwrite: bool) -> None:
        """오디오 변환 작업을 백그라운드 스레드로 시작합니다."""
        if not self.audio_full_paths:
            self._add_log_entry('audio', 'error_no_files')
            return
        if not output_dir:
            self._add_log_entry('audio', 'error_no_output_audio')
            return

        add_breadcrumb("conv", "오디오 변환 시작", {"files": len(self.audio_full_paths), "output": output_dir})

        self._start_conversion_thread(
            'audio',
            self.logic.run_audio_conversion,
            (self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.audio_cancel_token)
        )

    def _add_log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """새로운 로그 이벤트를 큐에 추가합니다.

        Args:
            target_tab: 로그를 출력할 탭 ('video' 또는 'audio').
            log_key: 다국어 딕셔너리의 로그 메시지 키.
            **kwargs: 메시지 포매팅에 사용할 추가 인자.
        """
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def log_system_message(self, target_tab: TabType, message: str) -> None:
        """시스템 레벨의 메시지(에러 등)를 로그에 직접 추가합니다.
        
        Args:
            target_tab: 로그를 출력할 탭 ('video' 또는 'audio').
            message: 출력할 문자열 메시지.
        """
        self.log_queue.put(LogEvent(target=target_tab, key='raw', kwargs={'text': message}))

    def _add_spacing(self, target_tab: TabType) -> None:
        """로그에 빈 줄(간격)을 추가하는 이벤트를 큐에 넣습니다.

        연속된 spacing 이벤트를 방지하여 이중 줄바꿈이 발생하지 않습니다.

        Args:
            target_tab: 빈 줄을 추가할 탭 ('video' 또는 'audio').
        """
        history = self.video_log_history if target_tab == 'video' else self.audio_log_history
        if history and history[-1][1] == 'spacing':
            return
        self.log_queue.put(LogEvent(target=target_tab, is_spacing=True))

    def _on_poll_cycle(self) -> None:
        """로그 큐에 쌓인 메시지들을 가져와 UI 업데이트 및 이벤트를 처리합니다."""
        for msg in self._drain_queue(self.log_queue):
            if not isinstance(msg, QueueEvent):
                continue

            if isinstance(msg, ProgressEvent) or isinstance(msg, CompletionEvent):
                if isinstance(msg, ProgressEvent): 
                    self._handle_progress_update(msg)
                else: 
                    self._handle_completion_signal(msg)
                continue

            target_tab, log_widget, history = (msg.target, self.view.video_log_text, self.video_log_history) if msg.target == 'video' else (msg.target, self.view.audio_log_text, self.audio_log_history)
            log_widget.config(state=tk.NORMAL)

            if isinstance(msg, LogEvent):
                if msg.is_spacing:
                    history.append((None, 'spacing', {}))
                    log_widget.insert(tk.END, '\n')
                else:
                    timestamp = None if msg.un_timestamped else datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    log_key = msg.key
                    kwargs = msg.kwargs
                    last_ts = self.last_log_timestamp[target_tab]
                    history.append((timestamp, log_key, kwargs))
                    log_widget.insert(tk.END, self._log_renderer.render_log_entry(timestamp, log_key, kwargs, last_ts))
                    
                    logging.info("[AV_%s] %s %s", target_tab.upper(), log_key, kwargs)
                    
                    if timestamp: 
                        self.last_log_timestamp[target_tab] = timestamp
                        
            elif isinstance(msg, LogBlockEvent):
                log_entries = msg.entries
                block_timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                last_ts_before_block = self.last_log_timestamp[target_tab]

                for i, (l_key, l_kwargs) in enumerate(log_entries):
                    last_ts_for_render = last_ts_before_block if i == 0 else block_timestamp
                    history.append((block_timestamp, l_key, l_kwargs))
                    log_widget.insert(tk.END, self._log_renderer.render_log_entry(block_timestamp, l_key, l_kwargs, last_ts_for_render))
                    logging.info("[AV_%s] %s %s", target_tab.upper(), l_key, l_kwargs)

                if log_entries:
                    self.last_log_timestamp[target_tab] = block_timestamp
            
            log_widget.see(tk.END)
            log_widget.config(state=tk.DISABLED)
    
    def _handle_progress_update(self, msg: ProgressEvent) -> None:
        """진행 상황 업데이트 이벤트를 처리하여 프로그레스 바와 상태 텍스트를 갱신합니다.

        Args:
            msg: 처리할 ProgressEvent 객체.
        """
        d = self.get_lang_dict()
        target_tab = msg.target
        widgets = self.view.video_widgets if target_tab == 'video' else self.view.audio_widgets
        
        if msg.is_start:
            total = msg.total
            setattr(self, f'{target_tab}_total_files', total)
            widgets['progress'].config(maximum=total, value=0)
            widgets['status_label'].config(text=d['status_starting'].format(total=total))
        else:
            value = msg.current
            total = getattr(self, f'{target_tab}_total_files')
            widgets['progress']['value'] = value
            widgets['status_label'].config(text=d['status_processing'].format(current=value, total=total))
    
    def _handle_completion_signal(self, msg: CompletionEvent) -> None:
        """변환 완료 이벤트를 처리하여 UI 상태를 복구하고 완료 메시지를 표시합니다.

        Args:
            msg: 처리할 CompletionEvent 객체.
        """
        d = self.get_lang_dict()
        tab_type = 'video' if msg.target == SENTINEL_VIDEO_DONE else 'audio'
        widgets = self.view.video_widgets if tab_type == 'video' else self.view.audio_widgets
        total = getattr(self, f'{tab_type}_total_files')
        current = widgets['progress']['value']
        widgets['status_label'].config(text=d['status_complete'].format(current=current, total=total))
        self.view.reset_ui_state(tab_type)

    def preview_selected(self, listbox: tk.Listbox, tab_type: TabType) -> None:
        """리스트박스에서 선택된 파일의 미리보기를 실행합니다.

        Args:
            listbox: 선택된 항목이 있는 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        self._preview.preview_selected(listbox, tab_type)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다.

        전역 임시 폴더(app_temp_dir)가 주입된 경우에는
        AppContainer.cleanup_shared()에서 통합 관리합니다.
        자체 생성한 임시 폴더인 경우에만 직접 삭제합니다.
        """
        self._stop_polling()
        if self._owns_temp_dir and os.path.exists(self._preview_temp_dir):
            shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
