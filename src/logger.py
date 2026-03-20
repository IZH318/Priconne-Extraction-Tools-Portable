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

from typing import Any, Dict, Optional, Type
from types import TracebackType

def write_error_log(app_info: dict[str, Any], context_name: str, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> str:
    """
    Generates a new timestamped log file and writes the error details in the standard format.
    Returns the absolute path of the generated log file.
    """
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    log_filename = f"ErrorLog_{timestamp_str}.log"
    log_filepath = Path(log_filename).resolve()

    from src.constants import SEPARATOR_LONG
    separator = SEPARATOR_LONG

    # Prepare standard fields
    app_version = app_info.get('APP_VERSION', 'Unknown')
    app_update = app_info.get('APP_LAST_UPDATE', 'Unknown')
    app_dev = app_info.get('APP_DEVELOPER', 'Unknown')
    
    python_ver = platform.python_version()
    os_ver = platform.platform()
    cpu_cores = multiprocessing.cpu_count()
    
    # Exec Path: 메인 실행 파일(main.py)의 절대 경로를 우선 확보
    if getattr(sys, 'frozen', False):
        exec_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        exec_path = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.path.abspath(os.getcwd())

    # Format stack trace
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
    Sets up a global logging system catching all unhandled Python exceptions,
    including those buried inside background threading.Threads and Tkinter callbacks.
    """
    if app_info is None:
        app_info = {}

    # 1. Configure standard console logging for non-critical info
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s | [%(levelname)s] | (%(threadName)s) : %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)

    # 2. Hook into generic unhandled exceptions (Main Thread)
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.error("Unhandled Exception (Main Thread)", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            write_error_log(app_info, "Main Thread", exc_type, exc_value, exc_traceback)
        except Exception as e:
            logging.error(f"Failed to write error log: {e}")

    sys.excepthook = handle_exception

    # 3. Hook into threading exceptions (Background Threads)
    def handle_thread_exception(args):
        thread_name = args.thread.name if args.thread else 'Unknown Thread'
        logging.error(f"Unhandled Thread Exception in {thread_name}", 
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        try:
            write_error_log(app_info, f"Thread '{thread_name}'", args.exc_type, args.exc_value, args.exc_traceback)
        except Exception as e:
            logging.error(f"Failed to write thread error log: {e}")

    threading.excepthook = handle_thread_exception

    # 4. Hook into Tkinter callbacks (GUI Events)
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
            
            # Generate the detailed log file
            try:
                log_path = write_error_log(app_info, "GUI Event Callback", exc_type, exc_value, exc_traceback)
                
                # Show localized error dialog
                err_msg = msg_success.format(log_path=log_path)
                messagebox.showerror(title, err_msg, parent=tk_root)
            except Exception as e:
                logging.error(f"Failed to write GUI error log: {e}")
                err_msg = msg_fail.format(e=e)
                messagebox.showerror(title, err_msg, parent=tk_root)
        
        tk_root.report_callback_exception = handle_tk_exception

    logging.info("Global customized exception logging initialized.")

