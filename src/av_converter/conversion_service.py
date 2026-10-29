"""AV Converter 변환 서비스 모듈.

비디오(.usm) 및 오디오(.awb) 변환 작업의 전처리 유효성 검사,
백그라운드 변환 스레드 생성과 취소 토큰(CancellationToken) 연결 및 변환 제어.
(.NET Runtime 및 외부 툴체인 준비는 백그라운드 파이프라인이 담당)
"""

from __future__ import annotations

import contextlib
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

from src.constants import SENTINEL_AUDIO_DONE, SENTINEL_VIDEO_DONE
from src.queue_events import CompletionEvent


class AVConversionService:
    """비디오/오디오 변환 스레드 및 UI 상태 관리 서비스.

    생성자로 주입된 의존성(뷰, 변환 로직, 콜백, 취소 토큰, 툴 준비 파이프라인)만 사용하며,
    동시 실행을 방지하기 위한 _start_lock을 적용하여 안정적인 백그라운드 작업 실행.

    Attributes:
        _view (Any): UI 제어 뷰 인스턴스.
        _logic (Any): 실제 비디오/오디오 파일 변환 알고리즘 인스턴스.
        _log_queue (Any): 변환 로직 및 로그 서비스와 공유하는 이벤트/완료 신호 전달용 큐.
        _converting (dict[str, bool]): 탭별('video', 'audio') 변환 작업 진행 여부 플래그.
        _start_lock (threading.Lock): 변환 스레드 중복 생성 방지용 락.
    """

    def __init__(
        self,
        view: Any,
        logic: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        add_log_entry: Callable[..., None],
        add_spacing: Callable[..., None],
        log_queue: Any,
        get_video_full_paths: Callable[[], list[str]],
        get_audio_full_paths: Callable[[], list[str]],
        get_usmtoolkit_path: Callable[[], Any],
        get_vgmstream_path: Callable[[], Any],
        get_video_cancel_token: Callable[[], Any],
        get_audio_cancel_token: Callable[[], Any],
        start_tool_preparation: Callable[..., None],
        set_conversion_thread: Callable[[Any, Any], None],
        resume_polling: Callable[[], None],
    ) -> None:
        """AVConversionService 초기화.

        Args:
            view (Any): UI 제어 뷰.
            logic (Any): 비디오/오디오 변환 엔진.
            get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
            add_log_entry (Callable[..., None]): 로그 이벤트 발행 콜백.
            add_spacing (Callable[..., None]): 로그 구분선 발행 콜백.
            log_queue (Any): 완료 신호 전달용 큐(없으면 logic.log_queue 폴백).
            get_video_full_paths (Callable[[], list[str]]): 비디오 입력 경로 조회.
            get_audio_full_paths (Callable[[], list[str]]): 오디오 입력 경로 조회.
            get_usmtoolkit_path (Callable[[], Any]): UsmToolkit 경로 조회.
            get_vgmstream_path (Callable[[], Any]): vgmstream 경로 조회.
            get_video_cancel_token (Callable[[], Any]): 비디오 취소 토큰 조회.
            get_audio_cancel_token (Callable[[], Any]): 오디오 취소 토큰 조회.
            start_tool_preparation (Callable[..., None]): 툴 준비 트리거 콜백.
            set_conversion_thread (Callable[[Any, Any], None]): 변환 스레드 등록 콜백.
            resume_polling (Callable[[], None]): 폴링 재개 콜백.
        """
        self._view: Any = view if view is not None else {}
        self._logic = logic
        self._get_lang_dict: Callable[[], dict[str, str]] = get_lang_dict if callable(get_lang_dict) else dict
        self._add_log_entry = add_log_entry if callable(add_log_entry) else (lambda *a, **k: None)
        self._add_spacing = add_spacing if callable(add_spacing) else (lambda *a, **k: None)
        self._log_queue: Any = log_queue if log_queue is not None else getattr(logic, "log_queue", None)
        self._get_video_full_paths: Callable[[], list[str]] = get_video_full_paths if callable(get_video_full_paths) else list
        self._get_audio_full_paths: Callable[[], list[str]] = get_audio_full_paths if callable(get_audio_full_paths) else list
        self._get_usmtoolkit_path = get_usmtoolkit_path if callable(get_usmtoolkit_path) else (lambda: None)
        self._get_vgmstream_path = get_vgmstream_path if callable(get_vgmstream_path) else (lambda: None)
        self._get_video_cancel_token = get_video_cancel_token if callable(get_video_cancel_token) else (lambda: None)
        self._get_audio_cancel_token = get_audio_cancel_token if callable(get_audio_cancel_token) else (lambda: None)
        self._start_tool_preparation = start_tool_preparation if callable(start_tool_preparation) else (lambda *a, **k: None)
        self._set_conversion_thread = set_conversion_thread if callable(set_conversion_thread) else (lambda *a, **k: None)
        self._resume_polling = resume_polling if callable(resume_polling) else (lambda: None)
        self._converting: dict[str, bool] = {"video": False, "audio": False}
        self._start_lock: threading.Lock = threading.Lock()

    def start_video_conversion(self, output_dir: str) -> None:
        """비디오 변환 전 파일 목록, 출력 경로 검증 및 변환 준비 시작.

        .NET Runtime 및 외부 툴체인 준비는 백그라운드 파이프라인에서 자동 수행된다.

        Args:
            output_dir (str): 변환된 비디오 파일들을 저장할 대상 폴더 경로.
        """
        video_full_paths = self._get_video_full_paths()
        if not video_full_paths:
            self._add_log_entry("video", "error_no_files")
            return
        if not output_dir:
            self._add_log_entry("video", "error_no_output_video")
            return
        from src.breadcrumbs import add_breadcrumb

        add_breadcrumb("conv", "Started video conversion", {"files": len(video_full_paths), "output": output_dir})
        self._start_tool_preparation("video", output_dir, self._start_actual_video_conversion)

    def _start_actual_video_conversion(self, output_dir: str) -> None:
        """도구 준비 완료 후 실제 비디오 변환 스레드 시작.

        Args:
            output_dir (str): 변환 대상 출력 폴더 경로.
        """
        self.start_conversion_thread(
            "video",
            self._logic.run_video_conversion,
            (self._get_video_full_paths()[:], output_dir, self._get_usmtoolkit_path(), self._get_video_cancel_token()),
        )

    def start_audio_conversion(self, output_dir: str, overwrite: bool) -> None:
        """오디오 변환 전 파일 목록 및 출력 경로 검증 및 변환 준비 시작.

        Args:
            output_dir (str): 변환된 오디오 파일들을 저장할 대상 폴더 경로.
            overwrite (bool): 기존 변환 파일이 존재할 경우 덮어쓸지 여부.
        """
        audio_full_paths = self._get_audio_full_paths()
        if not audio_full_paths:
            self._add_log_entry("audio", "error_no_files")
            return
        if not output_dir:
            self._add_log_entry("audio", "error_no_output_audio")
            return
        from src.breadcrumbs import add_breadcrumb

        add_breadcrumb("conv", "Started audio conversion", {"files": len(audio_full_paths), "output": output_dir})

        def _do_start_audio(out_dir: str) -> None:
            """오디오 툴체인 준비 완료 후 실제 변환 스레드를 실행하는 콜백."""
            self.start_conversion_thread(
                "audio",
                self._logic.run_audio_conversion,
                (audio_full_paths[:], out_dir, self._get_vgmstream_path(), overwrite, self._get_audio_cancel_token()),
            )

        self._start_tool_preparation("audio", output_dir, _do_start_audio)

    def start_conversion_thread(self, tab_type: Any, target_func: Callable[..., Any], args: tuple[Any, ...]) -> None:
        """변환 작업 스레드 생성 실행 및 UI 버튼을 '취소' 상태로 전환.

        동시 실행 방지를 위해 Lock으로 진입을 보호하며, 작업 종료 시 finally 블록에서
        상태 플래그 해제 및 취소 토큰 마무리 수행. 변환 함수가 예외로 중단되어도
        완료 신호를 큐에 전달하여 UI가 비활성화 상태로 남지 않도록 복구.

        Args:
            tab_type (Any): 대상 탭 식별자 ('video' 또는 'audio').
            target_func (Callable[..., Any]): 백그라운드 스레드에서 실행할 변환 함수.
            args (tuple[Any, ...]): 변환 함수에 전달할 위치 인자 튜플.
        """
        with self._start_lock:
            if self.is_converting(tab_type):
                return

            self._add_spacing(tab_type)
            view = self._view
            widgets = view.video_widgets if tab_type == "video" else view.audio_widgets
            cancel_token: Any = self._get_video_cancel_token() if tab_type == "video" else self._get_audio_cancel_token()
            view.set_ui_state(tab_type, "disabled")
            cancel_token.reset()
            widgets["action_btn"].config(
                state=tk.NORMAL,
                text=self._get_lang_dict().get("cancel_conversion", "Cancel Conversion"),
                command=cancel_token.cancel,
            )

            def _run() -> None:
                """백그라운드 변환 스레드 엔트리포인트."""
                try:
                    target_func(*args)
                except BaseException as e:
                    # 예외 발생 시에도 완료 이벤트를 큐에 전달해 UI 상태 복구
                    with contextlib.suppress(Exception):
                        self._add_log_entry(tab_type, "conv_log_error_exception", error=str(e))
                    self._emit_failure_completion(tab_type)
                finally:
                    # 상태 플래그 해제 전 토큰을 먼저 정리하여 재시작 시 경쟁 상태(Race Condition) 방지
                    with contextlib.suppress(RuntimeError, AttributeError):
                        cancel_token.finish()
                    self._converting[str(tab_type)] = False

            thread = threading.Thread(target=_run, daemon=True)
            self._converting[str(tab_type)] = True
            self._set_conversion_thread(tab_type, thread)
            self._resume_polling()
            thread.start()

    def _emit_failure_completion(self, tab_type: Any) -> None:
        """변환 스레드 예외 시 실패 CompletionEvent를 큐에 전달하여 UI 상태를 복원.

        Args:
            tab_type (Any): 대상 탭 식별자 ('video' 또는 'audio').
        """
        if self._log_queue is None:
            return
        sentinel = SENTINEL_VIDEO_DONE if str(tab_type) == "video" else SENTINEL_AUDIO_DONE
        self._log_queue.put(CompletionEvent(target=sentinel, success=False, result=[]))

    def is_converting(self, tab_type: Any) -> bool:
        """지정된 탭의 변환 스레드가 현재 실행 중인지 반환.

        Args:
            tab_type (Any): 대상 탭 식별자 ('video' 또는 'audio').

        Returns:
            bool: 변환 스레드가 활성화되어 작업 중이면 True.
        """
        return bool(self._converting.get(str(tab_type), False))
