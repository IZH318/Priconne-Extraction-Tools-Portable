import sys
import logging
import threading
import traceback
from datetime import datetime
from pathlib import Path

# Set up the base logger
def setup_global_logging(tk_root=None):
    """
    Sets up a global logging system catching all unhandled Python exceptions,
    including those buried inside background threading.Threads and Tkinter callbacks.
    """
    # 1. Configure the primary logger
    log_file = Path("app_error.log")
    
    # We use a FileHandler with utf-8 to correctly store localized errors
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    console_handler = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter(
        '%(asctime)s | [%(levelname)s] | (%(threadName)s) : %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)  # We only care about ERRORS or CRITICAL right now
    
    # Prevent duplicate handlers if called multiple times
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    # 2. Hook into generic unhandled exceptions (Main Thread)
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.error("Unhandled Exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    # 3. Hook into threading exceptions (Background Threads)
    # Python 3.8+ supports threading.excepthook
    def handle_thread_exception(args):
        logging.error(f"Unhandled Thread Exception in {args.thread.name if args.thread else 'Unknown Thread'}", 
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = handle_thread_exception

    # 4. Hook into Tkinter callbacks (GUI Events)
    # Tkinter catches its own exceptions. We must override `report_callback_exception`.
    if tk_root:
        def handle_tk_exception(exc_type, exc_value, exc_traceback):
            logging.error("Unhandled Tkinter GUI Exception", exc_info=(exc_type, exc_value, exc_traceback))
        
        tk_root.report_callback_exception = handle_tk_exception

    logging.info("Global exception logging initialized.")
