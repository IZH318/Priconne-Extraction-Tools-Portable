"""AV Converter 도구 준비 및 호환성 관리 서비스 모듈.

USM/CRI 비디오 디먹싱 및 HCA/AWB 오디오 디코딩에 필요한 외부 실행 파일
(UsmToolkit.exe, vgmstream-cli.exe, .NET 런타임 등)의 감지, 복사 호환성 보장 및
비동기 다운로드 파이프라인과의 폴링 연계 담당.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tkinter as tk
from tkinter import messagebox
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.av_converter.logic import ConversionLogic
from src.constants import FFMPEG_MIN_SUPPORTED, FFMPEG_TARGET_VERSION, GUI_POLLING_INTERVAL_MS, USMTOOLKIT_VERSION_PROBE_TIMEOUT, TabType
from src.subprocess_runner import SubprocessRunner
from src.utils.lang_dict import safe_lang_dict

logger = logging.getLogger(__name__)


class AVToolingService:
    """외부 바이너리 툴체인 관리 및 준비 서비스.

    UsmToolkit, vgmstream 등의 외부 바이너리 경로를 탐색하여 주입된 setter로 등록하고,
    누락된 도구가 있는 경우 비동기 다운로드를 실행하여 Tkinter 폴링 루프로 완료 여부 감시.

    Attributes:
        _base_path (Path | None): 실행 파일 기준 루트 경로.
        _log_queue (Any): 로그 이벤트 전달용 큐.
        _view (Any): UI 상태 제어 및 after 타이머 호출용 뷰 위젯.
        _polling_interval_ms (int): 도구 다운로드 상태 폴링 주기(ms).
        _preparing (dict[str, bool]): 탭별(video/audio) 툴체인 준비 진행 여부 플래그.
    """

    def __init__(
        self,
        view: Any,
        base_path: Path | None,
        log_queue: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        get_usmtoolkit_path: Callable[[], Any],
        set_usmtoolkit_path: Callable[[Any], None],
        get_vgmstream_path: Callable[[], Any],
        set_vgmstream_path: Callable[[Any], None],
        tool_pipeline: Any,
        add_log_entry: Callable[..., None] | None,
        polling_interval_ms: int = GUI_POLLING_INTERVAL_MS,
    ) -> None:
        """AVToolingService 초기화.

        Args:
            view (Any): UI 제어/after 타이머용 뷰.
            base_path (Path | None): 실행 파일 기준 루트 경로.
            log_queue (Any): 로그 이벤트 전달용 큐.
            get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
            get_usmtoolkit_path (Callable[[], Any]): UsmToolkit 경로 조회.
            set_usmtoolkit_path (Callable[[Any], None]): UsmToolkit 경로 설정.
            get_vgmstream_path (Callable[[], Any]): vgmstream 경로 조회.
            set_vgmstream_path (Callable[[Any], None]): vgmstream 경로 설정.
            tool_pipeline (Any): 도구 준비 파이프라인(Future 반환).
            add_log_entry (Callable[..., None]): 로그 이벤트 발행 콜백.
            polling_interval_ms (int): 다운로드 비동기 상태 확인 폴링 주기(밀리초).
        """
        self._view: Any = view if view is not None else {}
        self._base_path = base_path
        self._log_queue = log_queue
        self._get_lang_dict = get_lang_dict if callable(get_lang_dict) else dict
        self._get_usmtoolkit_path = get_usmtoolkit_path if callable(get_usmtoolkit_path) else (lambda: None)
        self._set_usmtoolkit_path = set_usmtoolkit_path if callable(set_usmtoolkit_path) else (lambda *a, **k: None)
        self._get_vgmstream_path = get_vgmstream_path if callable(get_vgmstream_path) else (lambda: None)
        self._set_vgmstream_path = set_vgmstream_path if callable(set_vgmstream_path) else (lambda *a, **k: None)
        self._tool_pipeline = tool_pipeline
        self._add_log_entry_cb = add_log_entry if callable(add_log_entry) else None
        self._polling_interval_ms = polling_interval_ms
        self._preparing: dict[str, bool] = {"video": False, "audio": False}

    def is_preparing(self, tab_type: TabType | str) -> bool:
        """지정된 탭의 필수 바이너리 도구 다운로드/준비 작업이 현재 진행 중인지 반환.

        Args:
            tab_type (TabType | str): 검사할 탭 식별자 ('video' 또는 'audio').

        Returns:
            bool: 도구 다운로드/압축 해제 작업이 백그라운드에서 진행 중이면 True.
        """
        return bool(self._preparing.get(str(tab_type), False))

    def _get_lang_dict_safe(self) -> dict[str, str]:
        """다국어 문자열 딕셔너리 안전 반환(예외 발생 시 빈 딕셔너리 반환).

        Returns:
            dict[str, str]: 현재 선택된 언어 키-문자열 맵.
        """
        return safe_lang_dict(self._get_lang_dict)

    def find_tools(self) -> None:
        """기준 경로 하위에서 UsmToolkit 및 vgmstream 실행 파일 존재 여부 탐색 및 등록.

        탐색 경로:
        - UsmToolkit: <base_path>/usmtoolkit/UsmToolkit.exe
        - vgmstream: <base_path>/usmtoolkit/vgmstream/vgmstream-cli.exe

        경로 탐색 후 setter로 경로를 등록하고, UsmToolkit 호환용 test.exe 링크 검증.
        """
        base_path = self._base_path or Path(".")
        usm_dir = base_path / "usmtoolkit"
        vgm_dir = usm_dir / "vgmstream"
        cand_usm = usm_dir / "UsmToolkit.exe"
        if cand_usm.is_file():
            self._set_usmtoolkit_path(cand_usm)
        else:
            self._set_usmtoolkit_path(None)
        cand_vgm = vgm_dir / "vgmstream-cli.exe"
        if cand_vgm.is_file():
            self._set_vgmstream_path(cand_vgm)
        else:
            self._set_vgmstream_path(None)
        self._ensure_usmtoolkit_compatibility()

    def _ensure_usmtoolkit_compatibility(self) -> None:
        """UsmToolkit 구버전이 기대하는 test.exe 이름을 vgmstream 실행 파일로부터 사본 생성.

        vgmstream의 초기 CLI 이름이 test.exe였으므로, vgmstream-cli.exe가 존재할 때
        동일 디렉터리에 test.exe 사본이 없으면 복사하여 바이너리 참조 오류 방지.
        """
        vgm = self._get_vgmstream_path()
        if vgm is not None and hasattr(vgm, "exists") and vgm.exists():
            test_exe = vgm.parent / "test.exe"
            if not test_exe.exists():
                try:
                    shutil.copy2(vgm, test_exe)
                except OSError:
                    pass

    def is_dotnet_runtime_available(self) -> bool:
        """UsmToolkit 실행에 필요한 .NET 런타임 환경 시스템 설치 여부 검증.

        UsmToolkit 실행 파일이 존재하면 --version 서브프로세스를 시험 실행하며,
        실행에 실패하면 dotnet --list-runtimes 출력을 파싱하여 런타임 설치 여부로 재판별한다.

        Returns:
            bool: .NET 런타임이 유효하게 사용 가능하면 True.
        """
        usm = self._get_usmtoolkit_path()
        if usm is not None and hasattr(usm, "exists") and usm.exists():
            try:
                res = SubprocessRunner.run([str(usm), "--version"], timeout=USMTOOLKIT_VERSION_PROBE_TIMEOUT)
                if res.returncode == 0:
                    return True
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                pass
        runtimes = ConversionLogic.get_installed_dotnet_runtimes()
        # 롤포워드는 전방 전용이므로 netcoreapp3.1 앱은 3.1 이상 런타임이 있어야 구동된다
        for entry in runtimes:
            parts = entry.split()
            if len(parts) < 2:
                continue
            try:
                major_minor = tuple(int(part) for part in parts[1].split('.')[:2])
            except ValueError:
                continue
            if len(major_minor) == 2 and major_minor >= (3, 1):
                return True
        return False

    def start_tool_preparation(self, tab_type: TabType, output_dir: str, next_func: Callable[[str], None]) -> None:
        """필수 도구 다운로드를 트리거하고 완료 시까지 GUI 이벤트 루프로 상태 감시.

        도구 준비가 완료되면 등록된 next_func 콜백을 호출하여 중단되었던 변환 작업 재개.

        Args:
            tab_type (TabType): 대상 탭 ('video' 또는 'audio').
            output_dir (str): 변환 대상 출력 폴더 경로.
            next_func (Callable[[str], None]): 도구 준비 완료 후 실행할 후속 변환 함수.

        Raises:
            RuntimeError: 도구 다운로드 파이프라인(tool_pipeline)이 초기화되지 않은 경우.
        """
        self._preparing[str(tab_type)] = True
        view = self._view
        view.set_ui_state(tab_type, "disabled")
        if callable(self._add_log_entry_cb):
            self._add_log_entry_cb(tab_type, "tools_preparing")
        if self._tool_pipeline is None:
            self._preparing[str(tab_type)] = False
            raise RuntimeError("tool pipeline is not initialized")
        try:
            download_future = self._tool_pipeline.ensure_tools_ready(tab_type)
        except Exception:
            self._preparing[str(tab_type)] = False
            raise

        def check_tool_status() -> None:
            """비동기 다운로드 Future의 완료 여부를 폴링하여 UI 및 후속 작업 처리."""
            if download_future.done():
                self._preparing[str(tab_type)] = False
                try:
                    if download_future.result():
                        self.find_tools()
                        next_func(output_dir)
                    else:
                        view.reset_ui_state(tab_type, reset_status=True)
                        self._notify_prepare_failure()
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
                    if callable(self._add_log_entry_cb):
                        self._add_log_entry_cb(tab_type, "conv_log_error_exception", error=str(e))
                    view.reset_ui_state(tab_type, reset_status=True)
                    self._notify_prepare_failure()
            else:
                try:
                    view.after(self._polling_interval_ms, check_tool_status)
                except (tk.TclError, RuntimeError):
                    self._preparing[str(tab_type)] = False
                    logger.debug("view.after failed in start_tool_preparation", exc_info=True)

        try:
            view.after(self._polling_interval_ms, check_tool_status)
        except (tk.TclError, RuntimeError):
            self._preparing[str(tab_type)] = False
            logger.debug("view.after failed in start_tool_preparation", exc_info=True)

    def _notify_prepare_failure(self) -> None:
        """도구 준비 실패 시 실패한 도구를 안내하는 팝업을 표시.

        FFmpeg 실패인 경우 수동 배치 안내와 권장/최소 지원 버전을 함께 표시.
        """
        lang = self._get_lang_dict() if callable(self._get_lang_dict) else {}
        fail_key_raw = getattr(self._tool_pipeline, "last_prepare_fail", None) if self._tool_pipeline is not None else None
        fail_key: str = fail_key_raw if isinstance(fail_key_raw, str) else ""
        tool = {
            'usmtoolkit_prepare_fail': 'UsmToolkit',
            'vgmstream_prepare_fail': 'vgmstream',
            'ffmpeg_prepare_fail': 'FFmpeg',
        }.get(fail_key, 'Unknown')

        title = lang.get('tools_prepare_fail_title', 'Tool Preparation Failed')
        msg = lang.get(
            'tools_prepare_fail_msg',
            "Cannot start conversion because tool preparation failed.\n\n- Failed tool: {tool}",
        ).format(tool=tool)

        if fail_key == 'ffmpeg_prepare_fail':
            hint = lang.get('ffmpeg_manual_place_hint')
            if hint:
                min_display = f"{FFMPEG_MIN_SUPPORTED[0]}.{FFMPEG_MIN_SUPPORTED[1]}"
                msg = msg + "\n\n" + hint.format(target=FFMPEG_TARGET_VERSION, min_supported=min_display)

        try:
            messagebox.showwarning(title, msg, parent=self._view)
        except (tk.TclError, TypeError, AttributeError):
            logger.debug("Failed to show prepare-failure dialog", exc_info=True)

    def _add_log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """로그 콜백 또는 로그 큐를 통해 UI 로그 렌더러에 이벤트 발행.

        Args:
            target_tab (TabType): 대상 탭.
            log_key (str): 번역 다국어 키.
            **kwargs: 포맷팅 파라미터.
        """
        if callable(self._add_log_entry_cb):
            self._add_log_entry_cb(target_tab, log_key, **kwargs)
        elif self._log_queue is not None:
            from src.queue_events import LogEvent

            self._log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))
