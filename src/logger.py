from __future__ import annotations
import sys
import logging
import threading
import traceback
import platform
import os
import multiprocessing
from datetime import datetime
from pathlib import Path

from typing import Any
from types import TracebackType

def write_error_log(app_info: dict[str, Any], context_name: str, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> str:
    """
    타임스탬프가 포함된 새 로그 파일을 생성하고 오류 상세 정보를 표준 형식으로 기록합니다.
    생성된 로그 파일의 절대 경로를 반환합니다.
    """
    # 실행 경로: 메인 실행 파일(main.py)의 절대 경로를 우선 확보
    if getattr(sys, 'frozen', False):
        exec_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        exec_path = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.path.abspath(os.getcwd())
    
    log_dir = Path(exec_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    log_filename = f"ErrorLog_{timestamp_str}.log"
    log_filepath = log_dir / log_filename

    from src.constants import SEPARATOR_LONG
    separator = SEPARATOR_LONG

    # 표준 필드 준비
    app_version = app_info.get('APP_VERSION', 'Unknown')
    app_update = app_info.get('APP_LAST_UPDATE', 'Unknown')
    app_dev = app_info.get('APP_DEVELOPER', 'Unknown')
    
    python_ver = platform.python_version()
    os_ver = platform.platform()
    cpu_cores = multiprocessing.cpu_count()

    # 스택 트레이스 포맷팅
    stack_trace_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    stack_trace_text = "".join(stack_trace_lines).strip()

    with open(log_filepath, 'w', encoding='utf-8') as f:
        f.write(f"{separator}\n")
        f.write(f"[SESSION] {context_name} Error Log Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
        f.write(f"{separator}\n")
        f.write(f"[TOOL]    App Version:     {app_version} ({app_update})\n")
        f.write(f"[TOOL]    Developer:       {app_dev}\n")
        f.write(f"[ENGINE]  Python Version:  {python_ver}\n")
        f.write(f"[SYSTEM]  OS Version:      {os_ver}\n")
        f.write(f"[SYSTEM]  Processor Count: {cpu_cores} Cores\n")
        f.write(f"[PATH]    Exec Path:       {exec_path}\n")
        f.write(f"[REPORT]  Total Errors:    1\n")
        f.write(f"{separator}\n\n")

        f.write(f"[ERROR ITEM #1]\n")
        f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
        f.write(f"Context   : {context_name}\n")
        f.write(f"Exception : {exc_type.__name__ if exc_type else 'Unknown'}\n")
        f.write(f"Message   : {str(exc_value)}\n")
        f.write("Stack Trace :\n")
        f.write(f"{stack_trace_text if stack_trace_text else 'No stack trace available.'}\n")
        f.write(f"{separator}\n\n")
        
    return str(log_filepath)

def setup_global_logging(tk_root: Any = None, app_info: dict[str, Any] | None = None, lang_var: Any = None, lang_data_map: dict[str, Any] | None = None) -> None:
    """
    Python의 처리되지 않은 모든 예외를 포착하는 전역 로깅 시스템을 설정합니다.
    백그라운드 threading.Thread 및 Tkinter 콜백 내부의 예외도 포함합니다.
    """
    if app_info is None:
        app_info = {}

    # 1. NullHandler를 설정하여 모든 표준 출력을 억제 (콘솔 로깅 비활성화)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    
    if not root_logger.handlers:
        root_logger.addHandler(logging.NullHandler())

    # 2. 처리되지 않은 예외에 대한 훅 설정 (메인 스레드)
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.error("Unhandled Exception (Main Thread)", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            write_error_log(app_info, "Main Thread", exc_type, exc_value, exc_traceback)
        except Exception as e:
            logging.error("Failed to write error log: %s", e)

    sys.excepthook = handle_exception

    # 3. 스레드 예외에 대한 훅 설정 (백그라운드 스레드)
    def handle_thread_exception(args):
        thread_name = args.thread.name if args.thread else 'Unknown Thread'
        logging.error("Unhandled Thread Exception in %s", thread_name,
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        try:
            write_error_log(app_info, f"Thread '{thread_name}'", args.exc_type, args.exc_value, args.exc_traceback)
        except Exception as e:
            logging.error("Failed to write thread error log: %s", e)

    threading.excepthook = handle_thread_exception

    # 4. Tkinter 콜백 예외에 대한 훅 설정 (GUI 이벤트)
    if tk_root:
        from tkinter import messagebox

        def handle_tk_exception(exc_type, exc_value, exc_traceback):
            logging.error("Unhandled Tkinter GUI Exception", exc_info=(exc_type, exc_value, exc_traceback))
            
            # 언어 설정 가져오기 (기본값 'en')
            lang_code = lang_var.get() if lang_var else 'en'
            if lang_data_map and lang_code in lang_data_map:
                lang_data = lang_data_map[lang_code]
            else:
                lang_data = lang_data_map.get('en', {}) if lang_data_map else {}
                
            title = lang_data.get('error_title', 'Error')
            msg_success = lang_data.get('error_msg_success', 'An error occurred.\nDetails are in the log file:\n{log_path}')
            msg_fail = lang_data.get('error_msg_fail', 'An error occurred, log file creation failed.\n{e}')
            
            # 상세 로그 파일 생성
            try:
                log_path = write_error_log(app_info, "GUI Event Callback", exc_type, exc_value, exc_traceback)
                
                # 다국어 오류 대화상자 표시
                err_msg = msg_success.format(log_path=log_path)
                messagebox.showerror(title, err_msg, parent=tk_root)
            except Exception as e:
                logging.error("Failed to write GUI error log: %s", e)
                err_msg = msg_fail.format(e=e)
                messagebox.showerror(title, err_msg, parent=tk_root)
        
        tk_root.report_callback_exception = handle_tk_exception

    logging.info("Global customized exception logging initialized.")

