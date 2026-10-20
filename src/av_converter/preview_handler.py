from __future__ import annotations
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable
from pathlib import Path

from src.constants import TabType

from src.utils.platform_open import open_with_default_app


class AVPreviewHandler:
    """AV Converter의 미리보기(Preview) 기능을 전담하는 핸들러 클래스입니다.

    Controller에서 미리보기 관련 로직을 분리하여 코드 가독성과
    유지보수성을 향상시킵니다.

    Note:
        Controller와의 순환 참조를 방지하기 위해, Controller 전체를 참조하지 않고
        필요한 콜백과 데이터 접근자만 개별 인자로 주입받습니다.
    """

    def __init__(
        self,
        get_lang_data: Callable[[], dict[str, str]],
        get_paths: Callable[[str], list[str]],
        logic: Any,
        view: Any,
        preview_temp_dir: str,
        get_tool_paths: Callable[[], dict[str, Path | None]],
        generate_error_log: Callable[[str, list[tuple[str, str]]], None] | None = None,
        prepare_tools: Callable[[TabType, Callable[[], None]], None] | None = None,
    ) -> None:
        """AVPreviewHandler를 초기화합니다.

        Args:
            get_lang_data: 현재 언어 딕셔너리를 반환하는 콜백.
            get_paths: 탭 타입('video'/'audio')에 해당하는 경로 리스트를 반환하는 콜백.
            logic: ConversionLogic 인스턴스.
            view: AVConverterView 인스턴스 (UI 조작용).
            preview_temp_dir: 미리보기 임시 파일 디렉터리 경로.
            get_tool_paths: 도구 경로 딕셔너리를 반환하는 콜백.
            generate_error_log: 에러 로그 파일 생성 콜백.
            prepare_tools: 누락된 도구를 자동 다운로드 및 준비하는 콜백.
        """
        self._get_lang_data = get_lang_data
        self._get_paths = get_paths
        self._logic = logic
        self._view = view
        self._preview_temp_dir = preview_temp_dir
        self._get_tool_paths = get_tool_paths
        self._generate_error_log = generate_error_log
        self._prepare_tools = prepare_tools

    def preview_selected(self, listbox: tk.Listbox, tab_type: TabType) -> None:
        """리스트박스에서 선택된 파일의 미리보기를 실행합니다.

        Args:
            listbox: 선택된 항목이 있는 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        full_paths = self._get_paths(tab_type)
        selection = listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(full_paths):
            return
        file_path = full_paths[idx]
        
        if tab_type == 'audio':
            self._preview_audio(file_path)
        else:
            self._preview_video(file_path)

    def _run_preview_task(self, worker_func: Any, callback_func: Any) -> None:
        """미리보기 생성을 위한 백그라운드 작업을 실행하고 진행 팝업을 표시합니다.

        Args:
            worker_func: 실제 미리보기를 생성하는 백그라운드 함수.
            callback_func: 작업 완료 후 결과를 받아 처리할 콜백 함수.
        """
        popup = self._view.create_progress_popup()
        def thread_target():
            result = worker_func()
            def update_ui():
                self._view.destroy_popup_safely(popup)
                callback_func(result)
            self._view.after(0, update_ui)
        threading.Thread(target=thread_target, daemon=True).start()

    def _preview_audio(self, file_path: str) -> None:
        """선택된 오디오 파일의 스트림 구조를 분석하고 트랙 선택기를 띄우거나 바로 재생합니다.

        Args:
            file_path: 분석할 오디오 파일(AWB 등) 경로.
        """
        d = self._get_lang_data()
        tool_paths = self._get_tool_paths()
        vgmstream_path = tool_paths.get('vgmstream')
        if not vgmstream_path:
            if self._prepare_tools:
                self._prepare_tools('audio', lambda: self._preview_audio(file_path))
                return
            messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_no_tool_audio', 'vgmstream not found.'), parent=self._view)
            return
        
        def on_analyze_done(streams_info: list[tuple[int, str]]) -> None:
            if not streams_info:
                if self._generate_error_log:
                    self._generate_error_log('audio', [(file_path, 'No audio streams found or vgmstream stream analysis failed.')])
                title = d.get('preview_menu', 'Preview')
                fail_msg = d.get('preview_error', 'Preview failed: {error}').format(error=os.path.basename(file_path))
                notice_msg = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
                messagebox.showwarning(title, f"{fail_msg}\n\n{notice_msg}", parent=self._view)
                return
            
            if len(streams_info) == 1:
                stream_num, stream_name = streams_info[0]
                self._play_audio_stream(file_path, stream_num, vgmstream_path, stream_name)
            else:
                def map_builder(tree):
                    stream_map = {}
                    name_map = {}
                    for stream_num, name in streams_info:
                        item_id = tree.insert('', tk.END, values=(stream_num, name))
                        stream_map[item_id] = stream_num
                        name_map[item_id] = name
                    tree.stream_map = stream_map
                    tree.name_map = name_map
                    
                def on_double_click(tree):
                    item_id = tree.focus()
                    if hasattr(tree, 'stream_map') and item_id in tree.stream_map:
                        self._play_audio_stream(file_path, tree.stream_map[item_id], vgmstream_path, tree.name_map[item_id])
                        
                self._view.show_track_selector(len(streams_info), map_builder, on_double_click)
        
        self._run_preview_task(
            lambda: self._logic.get_audio_streams_info(file_path, vgmstream_path),
            on_analyze_done
        )

    def _play_audio_stream(self, file_path: str, stream_num: int, vgmstream_path: Path, stream_name: str | None = None) -> None:
        """특정 오디오 스트림을 WAV로 추출하여 기본 플레이어로 재생합니다.

        Args:
            file_path: 원본 오디오 파일 경로.
            stream_num: 재생할 스트림 번호 (1-based index).
            vgmstream_path: vgmstream 실행 파일 경로.
            stream_name: 생성될 임시 파일에 사용할 스트림 이름 (옵션).
        """
        d = self._get_lang_data()
        self._cleanup_old_audio_previews()
        filename = f"{stream_name}.wav" if stream_name else f"preview_{os.path.basename(file_path)}_{stream_num}.wav"
        temp_wav = os.path.join(self._preview_temp_dir, filename)
        if os.path.exists(temp_wav):
            try: os.remove(temp_wav)
            except OSError: pass
        
        def on_done(result):
            success, error_reason = result if isinstance(result, tuple) else (result, None)
            if success:
                open_with_default_app(temp_wav)
            else:
                if self._generate_error_log:
                    self._generate_error_log('audio', [(file_path, error_reason or 'Audio preview failed')])
                title = d.get('preview_menu', 'Preview')
                fail_msg = d.get('preview_error', 'Preview failed: {error}').format(error=os.path.basename(file_path))
                notice_msg = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
                messagebox.showwarning(title, f"{fail_msg}\n\n{notice_msg}", parent=self._view)
        
        self._run_preview_task(
            lambda: self._logic.preview_single_audio(file_path, stream_num, temp_wav, vgmstream_path),
            on_done
        )

    def _cleanup_old_audio_previews(self) -> None:
        """기존에 생성된 오디오 미리보기 임시 WAV 파일들을 안전하게 정리합니다."""
        if not os.path.exists(self._preview_temp_dir):
            return
        for item in os.listdir(self._preview_temp_dir):
            if item.endswith(".wav"):
                item_path = os.path.join(self._preview_temp_dir, item)
                if os.path.isfile(item_path):
                    try:
                        os.remove(item_path)
                    except OSError:
                        pass

    def _cleanup_old_video_previews(self) -> None:
        """기존에 생성된 비디오 미리보기 임시 디렉터리들을 안전하게 정리합니다."""
        if not os.path.exists(self._preview_temp_dir):
            return
        for item in os.listdir(self._preview_temp_dir):
            if item.startswith("video_"):
                item_path = os.path.join(self._preview_temp_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)

    def _preview_video(self, file_path: str) -> None:
        """선택된 비디오 파일을 임시 폴더에 추출하여 기본 플레이어로 재생합니다.

        Args:
            file_path: 원본 비디오 파일(USM) 경로.
        """
        d = self._get_lang_data()
        tool_paths = self._get_tool_paths()
        usmtoolkit_path = tool_paths.get('usmtoolkit')
        if not usmtoolkit_path:
            if self._prepare_tools:
                self._prepare_tools('video', lambda: self._preview_video(file_path))
                return
            messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_no_tool_video', 'UsmToolkit not found.'), parent=self._view)
            return
        
        self._cleanup_old_video_previews()
        temp_dir = os.path.join(self._preview_temp_dir, f"video_{os.path.basename(file_path)}_{int(time.time() * 1000)}")
        os.makedirs(temp_dir, exist_ok=True)
        
        def on_convert_done(result):
            result_path, error_reason = result if isinstance(result, tuple) else (result, None)
            if result_path:
                open_with_default_app(str(result_path))
            else:
                if self._generate_error_log:
                    self._generate_error_log('video', [(file_path, error_reason or 'Video preview failed')])
                title = d.get('preview_menu', 'Preview')
                fail_msg = d.get('preview_error', 'Preview failed: {error}').format(error=os.path.basename(file_path))
                notice_msg = d.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
                messagebox.showwarning(title, f"{fail_msg}\n\n{notice_msg}", parent=self._view)
        
        self._run_preview_task(
            lambda: self._logic.preview_single_video(file_path, temp_dir, usmtoolkit_path),
            on_convert_done
        )
