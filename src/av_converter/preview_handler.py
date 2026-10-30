"""AV Converter 미디어 미리보기 핸들러 모듈.

비디오(.usm) 및 오디오(.awb) 단일 파일 재생 미리보기를 위한
뷰 표준 모달 진행 팝업, 다중 오디오 트랙 선택기(Track Selector) 트리뷰 연계,
OS 기본 미디어 플레이어 연동 및 임시 파일 정리 담당.
백그라운드 워커는 결과를 큐에 전달만 하고, Tk 접근은 메인 스레드 큐 폴링에서만 수행.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import shutil
import threading
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox
from typing import Any, cast

from src.constants import AV_PREVIEW_POLL_INTERVAL_MS, AV_PREVIEW_TEMP_MAX_AGE_S, TabType
from src.utils.platform_open import open_with_default_app

from .logic import sanitize_stream_filename

logger = logging.getLogger(__name__)


class AVPreviewHandler:
    """AV Converter의 미디어 파일 미리보기(Preview) 핸들러 클래스.

    컨트롤러와의 상호 의존성을 완화하기 위해 의존성 주입(Dependency Injection) 방식을 채택하며,
    백그라운드 변환 스레드와 Tkinter 모달 팝업을 연계하여 UI 프리징 없는 즉시 재생 환경 제공.

    Attributes:
        _get_lang_data (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _get_paths (Callable[[TabType], list[str]]): 탭별 파일 경로 목록 조회 콜백.
        _logic (Any): 미디어 변환 엔진 인스턴스.
        _view (Any): 상위 Tkinter 뷰 위젯.
        _preview_temp_dir (str): 미리보기용 임시 파일 저장소 경로.
        _get_tool_paths (Callable[[], dict[str, Path | None]]): 외부 툴체인 경로 사전 조회 콜백.
        _generate_error_log (Callable[..., Any]): 오류 로그 파일 작성 콜백.
        _prepare_tools (Callable[[TabType, Callable[[], None]], None]): 툴체인 다운로드/준비 트리거 콜백.
    """

    def __init__(
        self,
        get_lang_data: Callable[[], dict[str, str]],
        get_paths: Callable[[TabType], list[str]],
        logic: Any,
        view: Any,
        preview_temp_dir: str,
        get_tool_paths: Callable[[], dict[str, Path | None]],
        generate_error_log: Callable[..., Any],
        prepare_tools: Callable[[TabType, Callable[[], None]], None],
    ) -> None:
        """AVPreviewHandler 초기화.

        Args:
            get_lang_data (Callable[[], dict[str, str]]): 다국어 딕셔너리 반환 콜백.
            get_paths (Callable[[TabType], list[str]]): 탭 타입별 입력 파일 목록 반환 콜백.
            logic (Any): 변환 로직 인스턴스 (ConversionLogic).
            view (Any): UI 조작용 상위 뷰 객체.
            preview_temp_dir (str): 미리보기 임시 디렉터리 경로.
            get_tool_paths (Callable[[], dict[str, Path | None]]): 도구 실행 경로 맵 반환 콜백.
            generate_error_log (Callable[..., Any]): 에러 로그 파일 생성 콜백.
            prepare_tools (Callable[[TabType, Callable[[], None]], None]): 툴체인 준비 및 완료 콜백.
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
        """리스트박스에서 선택된 파일의 미리보기 실행.

        Args:
            listbox: 선택된 항목이 있는 Listbox 위젯.
            tab_type: 탭 타입 ('video' 또는 'audio').
        """
        lang_dict = self._get_lang_data()
        selected_indices = listbox.curselection()

        if not selected_indices:
            messagebox.showwarning(
                lang_dict.get('preview_menu', 'Preview'),
                lang_dict.get('preview_no_selection', 'Please select a file to preview.'),
                parent=self._view
            )
            return

        selected_idx = selected_indices[0]
        paths = self._get_paths(tab_type)

        if selected_idx >= len(paths):
            return

        file_path = paths[selected_idx]

        if tab_type == 'audio':
            self._preview_audio(file_path)
        elif tab_type == 'video':
            self._preview_video(file_path)

    def _run_preview_task_with_popup(self, worker_func: Callable[[], Any], callback_func: Callable[[Any], None]) -> None:
        """미리보기 생성을 위한 백그라운드 작업 실행 및 진행 팝업 표시.

        진행 팝업은 뷰 표준 팝업(create_progress_popup)을 사용해 기존 표시(제목/문구/크기/애니메이션)를
        그대로 유지하고, 워커 스레드는 결과를 큐에 전달만 한다(Tk 직접 접근 방지).
        폴링(after)은 팝업이 아닌 뷰에 예약하므로 팝업이 먼저 파기되어도 결과가 유실되지 않으며,
        성공/예외와 무관하게 팝업(grab 포함)은 정확히 1회 정리된다.

        Args:
            worker_func: 실제 미리보기를 생성하는 백그라운드 함수.
            callback_func: 작업 완료 후 결과를 받아 처리할 콜백 함수.
        """
        lang_dict = self._get_lang_data()
        popup = self._view.create_progress_popup()
        result_q: queue.Queue[Any] = queue.Queue()
        closed = False

        def close_popup() -> None:
            """진행 팝업 파기를 정확히 1회만 수행 (이미 파기된 경우에도 무해)."""
            nonlocal closed
            if closed:
                return
            closed = True
            self._view.destroy_popup_safely(popup)

        def poll() -> None:
            """메인 스레드에서 워커 결과를 수신해 팝업을 정리하고 콜백을 실행."""
            try:
                result, error = result_q.get_nowait()
            except queue.Empty:
                # 팝업 존재 여부와 무관하게 뷰에 폴링을 재예약 → 팝업이 먼저 닫혀도 결과 유실 방지.
                try:
                    self._view.after(AV_PREVIEW_POLL_INTERVAL_MS, poll)
                except (tk.TclError, RuntimeError, AttributeError):
                    logger.debug("Preview polling stopped: view is unavailable", exc_info=True)
                return

            close_popup()
            if error is None:
                callback_func(result)
                return

            logger.error("AV preview worker failed: %s", error)
            if callable(self._generate_error_log):
                self._generate_error_log('preview', [('', str(error))])
            error_template = lang_dict.get('preview_error', 'Preview failed: {error}')
            try:
                error_message = error_template.format(error=error)
            except (KeyError, IndexError, ValueError):
                error_message = f"{error_template}: {error}"
            messagebox.showerror(
                lang_dict.get('preview_menu', 'Preview'),
                error_message,
                parent=self._view
            )

        def thread_target() -> None:
            result: Any = None
            error: BaseException | None = None
            try:
                result = worker_func()
            except BaseException as exc:
                error = exc
            result_q.put((result, error))

        try:
            self._view.after(AV_PREVIEW_POLL_INTERVAL_MS, poll)
        except (tk.TclError, RuntimeError, AttributeError):
            # 뷰가 없으면 결과 전달이 불가하므로 팝업만 정리하고 중단 (잔류 grab 방지).
            close_popup()
            logger.debug("Preview task aborted: view is unavailable", exc_info=True)
            return
        threading.Thread(target=thread_target, daemon=True).start()

    def _preview_audio(self, file_path: str) -> None:
        """선택된 오디오 파일의 스트림 구조 분석 후 트랙 선택기 표시 또는 즉시 재생.

        Args:
            file_path: 분석할 오디오 파일(AWB 등) 경로.
        """
        lang_dict = self._get_lang_data()
        tool_paths = self._get_tool_paths()
        vgmstream_path = tool_paths.get('vgmstream')

        if not vgmstream_path or not vgmstream_path.exists():
            if messagebox.askyesno(
                lang_dict.get('preview_menu', 'Preview'),
                lang_dict.get('vgmstream_missing_confirm', 'vgmstream is required for audio preview. Would you like to download it now?'),
                parent=self._view
            ):
                self._prepare_tools('audio', lambda: self._preview_audio(file_path))
            return

        def parse_streams_worker() -> list[tuple[int, str]]:
            return cast(list[tuple[int, str]], self._logic.get_audio_streams_info(file_path, vgmstream_path))

        def on_streams_parsed(streams: list[tuple[int, str]]) -> None:
            if not streams:
                messagebox.showerror(
                    lang_dict.get('preview_menu', 'Preview'),
                    lang_dict.get('preview_stream_parse_fail', 'Failed to analyze audio streams or file is corrupted.'),
                    parent=self._view
                )
                return

            if len(streams) == 1:
                stream_num, stream_name = streams[0]
                self._play_audio_stream(file_path, stream_num, vgmstream_path, stream_name)
            else:
                def map_builder(tree: Any) -> None:
                    stream_map = {}
                    name_map = {}
                    for stream_num, name in streams:
                        item_id = tree.insert("", tk.END, values=(stream_num, name))
                        stream_map[item_id] = stream_num
                        name_map[item_id] = name
                    tree.stream_map = stream_map
                    tree.name_map = name_map

                def on_double_click(tree: Any) -> None:
                    item_id = tree.focus()
                    if hasattr(tree, 'stream_map') and item_id in tree.stream_map:
                        self._play_audio_stream(file_path, tree.stream_map[item_id], vgmstream_path, tree.name_map[item_id])

                self._view.show_track_selector(len(streams), map_builder, on_double_click)

        self._run_preview_task_with_popup(parse_streams_worker, on_streams_parsed)

    def _play_audio_stream(self, file_path: str, stream_num: int, vgmstream_path: Path, stream_name: str | None = None) -> None:
        """특정 오디오 스트림을 WAV로 추출하여 기본 플레이어로 재생.

        Args:
            file_path: 원본 오디오 파일 경로.
            stream_num: 재생할 스트림 번호 (1-based index).
            vgmstream_path: vgmstream 실행 파일 경로.
            stream_name: 생성될 임시 파일에 사용할 스트림 이름 (옵션).
        """
        lang_dict = self._get_lang_data()
        clean_name = sanitize_stream_filename(stream_name) if stream_name else ""
        filename = f"{clean_name}.wav" if clean_name else f"preview_{os.path.basename(file_path)}_{stream_num}.wav"
        temp_dir = os.path.join(self._preview_temp_dir, f"audio_{os.path.basename(file_path)}_{stream_num}_{int(time.time() * 1000)}")
        # 잔여 미리보기 정리는 임시 폴더 생성 전에 수행해야 방금 만든 폴더가 지워지지 않는다.
        self._cleanup_old_audio_previews(keep_dir=temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        temp_wav = os.path.join(temp_dir, filename)

        def extract_worker() -> tuple[bool, str | None]:
            return cast(tuple[bool, str | None], self._logic.preview_single_audio(file_path, stream_num, temp_wav, vgmstream_path))

        def on_done(result: Any) -> None:
            success, err_msg = result if isinstance(result, tuple) else (bool(result), None)
            if success and os.path.exists(temp_wav):
                open_with_default_app(temp_wav)
            else:
                self._generate_error_log('audio', [(file_path, err_msg or "Failed to extract audio preview.")])
                messagebox.showerror(
                    lang_dict.get('preview_menu', 'Preview'),
                    lang_dict.get('preview_audio_extract_fail', 'Failed to extract audio preview.'),
                    parent=self._view
                )

        self._run_preview_task_with_popup(extract_worker, on_done)

    def _cleanup_old_audio_previews(self, keep_dir: str | None = None) -> None:
        """기존에 생성된 오디오 미리보기 임시 디렉터리 및 잔여 파일 정리.

        Args:
            keep_dir (str | None): 삭제 대상에서 제외할 현재 작업 디렉터리 경로.
        """
        if not os.path.exists(self._preview_temp_dir):
            return
        current_time = time.time()
        for item in os.listdir(self._preview_temp_dir):
            item_path = os.path.join(self._preview_temp_dir, item)
            if keep_dir is not None and os.path.abspath(item_path) == os.path.abspath(keep_dir):
                continue
            if item.startswith("preview_stream_") and item.endswith(".wav"):
                try:
                    if current_time - os.path.getmtime(item_path) > AV_PREVIEW_TEMP_MAX_AGE_S:
                        os.remove(item_path)
                except OSError:
                    pass
            elif item.startswith("audio_preview_") or item.startswith("audio_"):
                try:
                    shutil.rmtree(item_path, ignore_errors=True)
                except OSError as _e:
                    logger.debug('AV preview cleanup failed: %s', _e)

    def _cleanup_old_video_previews(self, keep_dir: str | None = None) -> None:
        """기존에 생성된 비디오 미리보기 임시 디렉터리 정리.

        Args:
            keep_dir (str | None): 삭제 대상에서 제외할 현재 작업 디렉터리 경로.
        """
        if not os.path.exists(self._preview_temp_dir):
            return
        current_time = time.time()
        for item in os.listdir(self._preview_temp_dir):
            if item.startswith("video_preview_") or item.startswith("video_"):
                item_path = os.path.join(self._preview_temp_dir, item)
                if keep_dir is not None and os.path.abspath(item_path) == os.path.abspath(keep_dir):
                    continue
                try:
                    if current_time - os.path.getmtime(item_path) > AV_PREVIEW_TEMP_MAX_AGE_S:
                        try:
                            shutil.rmtree(item_path, ignore_errors=True)
                        except OSError as exc:
                            logger.debug("Video preview cleanup failed: %s", exc)
                except OSError:
                    pass

    def _preview_video(self, file_path: str) -> None:
        """선택된 비디오 파일을 임시 폴더에 추출하여 기본 플레이어로 재생.

        Args:
            file_path: 원본 비디오 파일(USM) 경로.
        """
        lang_dict = self._get_lang_data()
        tool_paths = self._get_tool_paths()
        usmtoolkit_path = tool_paths.get('usmtoolkit')

        if not usmtoolkit_path or not usmtoolkit_path.exists():
            if messagebox.askyesno(
                lang_dict.get('preview_menu', 'Preview'),
                lang_dict.get('usmtoolkit_missing_confirm', 'UsmToolkit is required for video preview. Would you like to download it now?'),
                parent=self._view
            ):
                self._prepare_tools('video', lambda: self._preview_video(file_path))
            return

        temp_dir = os.path.join(self._preview_temp_dir, f"video_{os.path.basename(file_path)}_{int(time.time() * 1000)}")
        # 잔여 미리보기 정리는 임시 폴더 생성 전에 수행해야 방금 만든 폴더가 지워지지 않는다.
        self._cleanup_old_video_previews(keep_dir=temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        def convert_worker() -> tuple[Path | None, str | None]:
            return cast(tuple[Path | None, str | None], self._logic.preview_single_video(file_path, temp_dir, usmtoolkit_path))

        def on_convert_done(result: Any) -> None:
            video_file, err_msg = result
            if video_file and os.path.exists(str(video_file)):
                open_with_default_app(str(video_file))
            else:
                self._generate_error_log('video', [(file_path, err_msg or "")])
                messagebox.showerror(
                    lang_dict.get('preview_menu', 'Preview'),
                    lang_dict.get('preview_video_demux_fail', 'Failed to extract video preview.'),
                    parent=self._view
                )

        self._run_preview_task_with_popup(convert_worker, on_convert_done)

    def cleanup(self) -> None:
        """임시 미리보기 아티팩트(WAV 및 추출 디렉터리) 정리."""
        with contextlib.suppress(OSError):
            self._cleanup_old_audio_previews()
        with contextlib.suppress(OSError):
            self._cleanup_old_video_previews()
