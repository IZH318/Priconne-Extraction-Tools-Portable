"""전역 에러 로깅 및 예외 처리 모듈.

애플리케이션 전역 예외 포착 및 기록:
1. 메인 스레드 미처리 예외 (sys.excepthook)
2. 백그라운드 워커 스레드 예외 (threading.excepthook)
3. Tkinter GUI 이벤트 루프 콜백 예외 (tk_root.report_callback_exception)

시스템 사양, 스택 트레이스, 브레드크럼 기록 및 세션 로그 파일 기록(자동 삭제 없음).
세션 진단 로그도 기존 작업 로그(write_log_header)와 동일한 형식으로 logs/AppLog_*.log 에 기록.
"""
from __future__ import annotations

import logging
import os
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


_ERROR_LOG_WRITE_LOCK = threading.Lock()


def _resolve_log_dir() -> Path:
    """로그 파일 저장 디렉터리(<base>/logs) 결정 및 생성.

    실행 디렉터리에 쓰기 권한이 없어 생성에 실패(OSError/PermissionError)하면
    OS 임시 폴더 하위의 priconne_logs 폴더로 폴백한다.

    Returns:
        Path: 로그 파일을 기록할 디렉터리 경로 (쓰기 가능 상태로 생성 완료).

    Raises:
        OSError: 기본 로그 경로 및 임시 폴더 폴백 생성까지 모두 실패한 경우.
    """
    import tempfile

    from src.utils.base_path import get_application_base_path

    log_dir = get_application_base_path() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        # 실행 디렉터리 쓰기 권한 부재 시 OS 임시 폴더 폴백
        log_dir = Path(tempfile.gettempdir()) / "priconne_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def write_error_log(
    app_info: dict[str, Any],
    context_name: str,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    exc_traceback: TracebackType | None,
) -> str:
    """예외 상세 정보, 시스템 사양 및 최근 동작 이력(Breadcrumbs)을 포함한 에러 로그 파일 생성.

    동일 파일명(같은 초)이 이미 존재하면 이어서 기록(append)하며, 로그는 자동 삭제하지 않는다.

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

    log_dir = _resolve_log_dir()

    now = datetime.now()
    log_filepath = log_dir / f"ErrorLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"

    from src.constants import SEPARATOR_LONG
    from src.utils.error_log import write_log_header, write_log_item

    # 1. 스택 트레이스 포맷팅
    if exc_type is None:
        exc_type = type(exc_value) if exc_value is not None else Exception
    if exc_value is None:
        exc_value = exc_type() if isinstance(exc_type, type) else Exception()
    try:
        stack_trace_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    except (TypeError, ValueError, AttributeError, RuntimeError):
        stack_trace_lines = [f"{exc_type.__name__}: {exc_value}\n"]
    stack_trace_text = "".join(stack_trace_lines).strip() or "No stack trace available."

    # 2. 동일 파일명(같은 초)에는 이어서 기록 (덮어쓰지 않음)
    with _ERROR_LOG_WRITE_LOCK:
        with open(log_filepath, "a", encoding="utf-8") as f:
            write_log_header(
                f,
                f"{context_name} Error Log",
                exec_path,
                app_info,
                extra_report=["[REPORT]  Total Errors:    1"],
            )
            write_log_item(
                f,
                item_header="[ERROR ITEM #{idx}]",
                idx=1,
                timestamp=now,
                context=context_name,
                target=exc_type.__name__ if exc_type else "Unknown",
                message=exc_value,
                detail=stack_trace_text,
            )
            breadcrumb_text = format_breadcrumbs()
            if breadcrumb_text:
                f.write(f"{breadcrumb_text}\n")
                f.write(f"{SEPARATOR_LONG}\n")
            f.flush()

    return str(log_filepath)


class _AppLogFileHandler(logging.Handler):
    """세션 진단 로그를 기존 작업 로그와 동일한 형식으로 파일에 기록하는 핸들러.

    상단에 표준 세션/시스템 헤더(write_log_header)를 기록하고, 각 레코드는
    공통 항목 규격([레벨 ITEM #n] + Target/Message)으로 남긴다.
    파일은 <base>/logs/AppLog_*.log 이며, 같은 파일명(같은 초)이면 이어서 기록한다.
    """

    def __init__(self, app_info: dict[str, Any]) -> None:
        super().__init__()
        self._app_info = app_info
        self._file: Any = None
        self._item_index = 0
        self._open()

    def _open(self) -> None:
        from src.utils.base_path import get_application_base_path
        from src.utils.error_log import write_log_header

        base_path = get_application_base_path()
        log_dir = _resolve_log_dir()

        now = datetime.now()
        filename = f"AppLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"
        self._file = open(log_dir / filename, "a", encoding="utf-8")
        write_log_header(self._file, "Application Log", base_path, self._app_info)
        self._file.flush()

    def emit(self, record: logging.LogRecord) -> None:
        if self._file is None:
            return
        from src.utils.error_log import write_log_item

        try:
            self._item_index += 1
            detail = None
            if record.exc_info:
                detail = "".join(traceback.format_exception(*record.exc_info)).strip()
            write_log_item(
                self._file,
                item_header=f"[{record.levelname} ITEM #{{idx}}]",
                idx=self._item_index,
                timestamp=datetime.now(),
                context=record.threadName or "",
                target=record.name,
                message=record.getMessage(),
                detail=detail,
            )
            self._file.flush()
        except (OSError, ValueError):
            self.handleError(record)

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        super().close()


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

    # 1. 전역 로그 레벨 설정 (환경 변수 PRICONNE_LOG_LEVEL 지원, 기본값: WARNING)
    log_level_name = os.environ.get('PRICONNE_LOG_LEVEL', 'WARNING').upper()
    log_level = getattr(logging, log_level_name, logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 기존 작업 로그와 동일한 형식의 세션 로그 파일 핸들러 부착 (중복 부착 방지)
    if not any(isinstance(h, _AppLogFileHandler) for h in root_logger.handlers):
        try:
            root_logger.addHandler(_AppLogFileHandler(app_info))
        except (OSError, PermissionError) as exc:
            # 로그 파일 생성 실패 시 로그 유실 방지용 NullHandler 폴백 (크래시 금지)
            logger.warning("Failed to attach application log file handler: %s", exc)
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
            except (tk.TclError, RuntimeError, AttributeError):  # 폴백: 위젯 파괴 시점 예외 처리
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


