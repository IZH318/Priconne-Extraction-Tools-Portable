"""전역 에러 로깅 및 3계층 크래시 덤프(Crash Dump) 시스템 모듈.

애플리케이션 전역 발생 예외 3계층 가로채기(Intercept) 기록:
1. 메인 스레드 미처리 예외 (sys.excepthook)
2. 백그라운드 워커 스레드 예외 (threading.excepthook)
3. Tkinter GUI 이벤트 루프 콜백 예외 (tk_root.report_callback_exception)

시스템 사양, 스택 트레이스, 브레드크럼 기록 및 최근 50개 로그 유지.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from src.breadcrumbs import format_breadcrumbs

logger = logging.getLogger("priconne")


_LOG_FILENAME_COUNTER: list[int] = [0]
_LOG_FILENAME_COUNTER_LOCK = threading.Lock()


def write_error_log(
    app_info: dict[str, Any],
    context_name: str,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    exc_traceback: TracebackType | None,
) -> str:
    """예외 상세 정보, 시스템 사양 및 사용자 궤적을 포함한 에러 로그 파일 생성.

    .tmp 임시 파일에 기록 후 os.replace로 원자적 교체.
    50개 초과 시 오래된 로그부터 자동 삭제.

    Args:
        app_info (dict[str, Any]): 앱 버전, 빌드 날짜, 개발자 정보 등을 담은 딕셔너리.
        context_name (str): 오류 발생 실행 맥락 (예: 'Main Thread', 'Thread-1', 'GUI Event Callback').
        exc_type (type[BaseException] | None): 발생 예외 클래스 타입.
        exc_value (BaseException | None): 예외 인스턴스.
        exc_traceback (TracebackType | None): 예외 트레이스백 객체.

    Returns:
        str: 디스크에 생성된 최종 에러 로그 파일 절대 경로 문자열.
    """
    from src.utils.base_path import get_application_base_path
    base_path = get_application_base_path()
    exec_path = str(base_path)

    import tempfile
    import uuid
    log_dir = base_path / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        # 실행 디렉터리 쓰기 권한 부재 시 OS 임시 폴더 폴백
        log_dir = Path(tempfile.gettempdir()) / "priconne_logs"
        log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S_%f")
    # 동일 마이크로초 내 다중 스레드 동시 에러 시 파일명 충돌 방지용 카운터
    with _LOG_FILENAME_COUNTER_LOCK:
        _LOG_FILENAME_COUNTER[0] += 1
        counter = _LOG_FILENAME_COUNTER[0]
    log_filename = f"ErrorLog_{timestamp_str}_{counter}_{uuid.uuid4().hex[:8]}.log"
    log_filepath = log_dir / log_filename

    from src.constants import SEPARATOR_LONG
    separator = SEPARATOR_LONG

    # 1. 시스템 환경 및 메타데이터 수집
    app_version = app_info.get('APP_VERSION', 'Unknown')
    app_update = app_info.get('APP_LAST_UPDATE', 'Unknown')
    app_dev = app_info.get('APP_DEVELOPER', 'Unknown')

    python_ver = platform.python_version()
    os_ver = platform.platform()
    cpu_cores = os.cpu_count() or 1

    # 2. 스택 트레이스 포맷팅
    if exc_type is None:
        exc_type = type(exc_value) if exc_value is not None else Exception
    if exc_value is None:
        exc_value = exc_type() if isinstance(exc_type, type) else Exception()
    try:
        stack_trace_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    except (TypeError, ValueError, AttributeError, RuntimeError):
        stack_trace_lines = [f"{exc_type.__name__}: {exc_value}\n"]
    stack_trace_text = "".join(stack_trace_lines).strip()

    # 3. 로그 본문 조립
    _lines = []
    _lines.append(f"{separator}\n")
    _lines.append(f"[SESSION] {context_name} Error Log Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
    _lines.append(f"{separator}\n")
    _lines.append(f"[TOOL]    App Version:     {app_version} ({app_update})\n")
    _lines.append(f"[TOOL]    Developer:       {app_dev}\n")
    _lines.append(f"[ENGINE]  Python Version:  {python_ver}\n")
    _lines.append(f"[SYSTEM]  OS Version:      {os_ver}\n")
    _lines.append(f"[SYSTEM]  Processor Count: {cpu_cores} Cores\n")
    _lines.append(f"[PATH]    Exec Path:       {exec_path}\n")
    _lines.append("[REPORT]  Total Errors:    1\n")
    _lines.append(f"{separator}\n\n")

    _lines.append("[ERROR ITEM #1]\n")
    _lines.append(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
    _lines.append(f"Context   : {context_name}\n")
    _lines.append(f"Exception : {exc_type.__name__ if exc_type else 'Unknown'}\n")
    _lines.append(f"Message   : {exc_value!s}\n")
    _lines.append("Stack Trace :\n")
    _lines.append(f"{stack_trace_text if stack_trace_text else 'No stack trace available.'}\n")
    _lines.append(f"{separator}\n\n")

    # 4. 최근 사용자 조작 궤적(Breadcrumbs) 첨부
    breadcrumb_text = format_breadcrumbs()
    if breadcrumb_text:
        _lines.append(f"{breadcrumb_text}\n")
        _lines.append(f"{separator}\n\n")

    content = "".join(_lines)

    # 5. 임시 파일 작성 후 교체 (원자적 쓰기)
    tmp_path = log_filepath.with_suffix(log_filepath.suffix + ".tmp")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, log_filepath)

    # 6. 임시 파일 정리 및 오래된 에러 로그 로테이션 (최대 50개 유지)
    try:
        for tmp_file in log_dir.glob("ErrorLog_*.tmp"):
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
        log_files = list(log_dir.glob("ErrorLog_*.log"))
        entries: list[tuple[float, Path]] = []
        for p in log_files:
            try:
                entries.append((p.stat().st_mtime, p))
            except OSError as _exc:
                logger.debug("Failed to stat error log %s: %s", p, _exc)
                continue
        entries.sort(key=lambda x: x[0])
        while len(entries) > 50:
            _, oldest = entries.pop(0)
            try:
                oldest.unlink()
            except OSError as exc:
                logger.warning("Failed to remove old error log %s: %s", oldest, exc)
                continue
    except OSError as exc:
        logger.warning("Failed to rotate error logs in %s: %s", log_dir, exc)

    return str(log_filepath)


def setup_global_logging(
    tk_root: Any = None,
    app_info: dict[str, Any] | None = None,
    lang_var: Any = None,
    lang_data_map: dict[str, Any] | None = None,
) -> None:
    """메인 스레드, 백그라운드 스레드 및 Tkinter 콜백 전역 예외 훅 설정.

    Args:
        tk_root (Any): Tkinter 루트 윈도우 인스턴스 (report_callback_exception 등록용).
        app_info (dict[str, Any] | None): 로그 파일 헤더에 기록할 앱 메타데이터.
        lang_var (Any): 현재 선택된 언어 코드를 보관하는 tk.StringVar 인스턴스.
        lang_data_map (dict[str, Any] | None): 에러 다이얼로그 번역 메시지 딕셔너리.
    """
    if app_info is None:
        app_info = {}

    # 1. 전역 로그 레벨 설정 (환경 변수 PRICONNE_LOG_LEVEL 지원, 기본값: ERROR)
    log_level_name = os.environ.get('PRICONNE_LOG_LEVEL', 'ERROR').upper()
    log_level = getattr(logging, log_level_name, logging.ERROR)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        root_logger.addHandler(logging.NullHandler())

    # 2. 메인 스레드 미처리 예외 훅
    def handle_exception(
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            exc_type = type(exc_value) if exc_value is not None else Exception
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)  # type: ignore[arg-type]
            return

        logger.error("Unhandled Exception (Main Thread)", exc_info=(exc_type, exc_value, exc_traceback))  # type: ignore[arg-type]
        try:
            write_error_log(app_info, "Main Thread", exc_type, exc_value, exc_traceback)
        except (OSError, UnicodeError, ValueError, TypeError, RuntimeError) as e:
            logger.error("Failed to write error log: %s", e)

    sys.excepthook = handle_exception

    # 3. 백그라운드 스레드 미처리 예외 훅 (Python 3.8+)
    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        exc_type = args.exc_type
        exc_value = args.exc_value
        exc_traceback = args.exc_traceback
        if exc_type is None:
            exc_type = type(exc_value) if exc_value is not None else Exception
        thread_name = args.thread.name if args.thread else 'Unknown Thread'
        logger.error(
            "Unhandled Thread Exception in %s",
            thread_name,
            exc_info=(exc_type, exc_value, exc_traceback) if exc_value is not None else None,
        )
        try:
            write_error_log(app_info, f"Thread '{thread_name}'", exc_type, exc_value, exc_traceback)
        except (OSError, UnicodeError, ValueError, TypeError, RuntimeError) as e:
            logger.error("Failed to write thread error log: %s", e)

    threading.excepthook = handle_thread_exception

    # 4. Tkinter 이벤트 루프 콜백 예외 훅
    if tk_root:
        from tkinter import messagebox

        def handle_tk_exception(
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
        ) -> None:
            if exc_type is None:
                exc_type = type(exc_value) if exc_value is not None else Exception
            logger.error("Unhandled Tkinter GUI Exception", exc_info=(exc_type, exc_value, exc_traceback))  # type: ignore[arg-type]

            # 언어 설정 가져오기 (기본값 'en')
            try:
                lang_code = lang_var.get() if lang_var else 'en'
            except (tk.TclError, RuntimeError, AttributeError):  # 폴백: 위젯 파괴 시점 예외 방어
                lang_code = 'en'
            if lang_data_map and 'main_menu' in lang_data_map:
                menu_data = lang_data_map['main_menu']
            else:
                menu_data = lang_data_map or {}

            if not isinstance(menu_data, dict):
                menu_data = {}
            lang_data = menu_data.get(lang_code, menu_data.get('en', {})) if isinstance(menu_data, dict) else {}
            if not isinstance(lang_data, dict):
                lang_data = {}

            title = lang_data.get('error_title', 'Error') if isinstance(lang_data, dict) else 'Error'
            msg_success = lang_data.get('error_msg_success', 'An error occurred.\nDetails are in the log file:\n{log_path}') if isinstance(lang_data, dict) else 'An error occurred.\nDetails are in the log file:\n{log_path}'
            msg_fail = lang_data.get('error_msg_fail', 'An error occurred, log file creation failed.\n{e}') if isinstance(lang_data, dict) else 'An error occurred, log file creation failed.\n{e}'

            # 상세 에러 로그 파일 생성 및 알림 대화상자 노출
            try:
                log_path = write_error_log(app_info, "GUI Event Callback", exc_type, exc_value, exc_traceback)
                try:
                    err_msg = msg_success.format(log_path=log_path)
                except (KeyError, ValueError, TypeError, AttributeError, IndexError):
                    err_msg = msg_success
                try:
                    messagebox.showerror(title, err_msg, parent=tk_root)
                except (tk.TclError, RuntimeError) as _exc:
                    logger.debug("Failed to show GUI error dialog: %s", _exc)
            except (OSError, UnicodeError, ValueError, TypeError, RuntimeError) as e:
                logger.error("Failed to write GUI error log: %s", e)
                try:
                    err_msg = msg_fail.format(e=e)
                except (KeyError, ValueError, TypeError, AttributeError, IndexError):
                    err_msg = msg_fail
                try:
                    messagebox.showerror(title, err_msg, parent=tk_root)
                except (tk.TclError, RuntimeError) as _exc:
                    logger.debug("Failed to show GUI error dialog: %s", _exc)

        tk_root.report_callback_exception = handle_tk_exception


