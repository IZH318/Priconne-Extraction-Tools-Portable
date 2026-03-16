# src/renamer/gui.py
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime
import queue
import threading
import os

from .languages import LANGUAGES
from .logic import RenameHashedFile, SEPARATOR

class FileRenamerGUI(ttk.Frame):
    # --- 프로그램 정보 상수 ---
    ABOUT_INFO = {
        'program': "Manifest File Renamer",
        'version': "2.0.0",
        'updated': "2025-07-26",
        'license': "GNU General Public License v3.0",
        'developer': "(Github) IZH318",
        'website': "https://github.com/IZH318",
    }

    def __init__(self, master, app_lang_var=None):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.master = master
        self.current_lang = 'ko'
        
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value=self.current_lang)
            
        self.lang_var.trace_add("write", self.on_language_change)
        
        self.log_data = []
        
        self.last_progress_info = {'current': 0, 'total': 0}
        self.is_processing = False

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue, self.get_string)
        
        self.GUI_UPDATE_INTERVAL_MS = 10
        
        self.progress_label_var = tk.StringVar()
        self.total_files_count = 0

        self.menubar = None
        self.language_menu = None
        self.create_widgets()
        self.update_ui_language(is_initial_setup=True)

    def get_string(self, key, **kwargs):
        return LANGUAGES[self.current_lang].get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    def set_language(self, lang_code):
        if self.current_lang != lang_code:
            self.current_lang = lang_code
            self.file_processor.set_get_string_func(self.get_string)
            self.update_ui_language()

    def on_language_change(self, *args):
        new_lang = self.lang_var.get()
        self.set_language(new_lang)

    def update_ui_language(self, is_initial_setup=False):
        self.start_button.config(text=self.get_string('start_button'))
        
        if not self.is_processing:
            if self.total_files_count > 0 and self.progress_bar['value'] >= 100:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                 self.progress_label_var.set(self.get_string('status_waiting'))
        else:
            if self.last_progress_info['total'] == 0:
                 self.progress_label_var.set(self.get_string('status_searching'))
            else:
                self.progress_label_var.set(self.get_string('status_processing', **self.last_progress_info))
        
        if is_initial_setup:
            self.log_data.clear()
            self.show_initial_message()
        
        self.re_render_logs()
        
    def create_menubar(self):
        pass

    def show_about_info(self):
        self._add_raw_text(SEPARATOR)
        self._add_log_event('SHOW_ABOUT_INFO')
        self._add_raw_text(SEPARATOR)
        self.re_render_logs()

    def create_widgets(self):
        top_frame = tk.Frame(self)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)

        self.start_button = tk.Button(control_frame, command=self.start_processing_thread)
        self.start_button.pack(side=tk.RIGHT, padx=(10, 0))
        self.progress_label = tk.Label(control_frame, textvariable=self.progress_label_var, width=25)
        self.progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        self.log_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Consolas", 9), state='disabled')
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    def show_initial_message(self):
        self._add_raw_text(SEPARATOR)
        self._add_log_event('program_started')
        self._add_raw_text(SEPARATOR)
        
        folder_lines = []
        folders = self.file_processor.target_folders
        for i, folder in enumerate(folders):
            prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
            folder_lines.append(self.get_string(prefix_key, folder_name=folder))
        
        self._add_log_event('initial_info_db', {'folder_structure': "\n".join(folder_lines)})
        self._add_log_event('initial_info_start')
        self._add_raw_text(SEPARATOR)
        
    def re_render_logs(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)

        output_buffer = []

        for i, (timestamp, key, kwargs) in enumerate(self.log_data):
            if timestamp is None:
                output_buffer.append(key + "\n")
                continue

            message = self.get_string(key, **kwargs)
            if not message:
                continue

            is_same_group = i > 0 and self.log_data[i-1][0] == timestamp
            line_prefix = f"[{timestamp}] " if not is_same_group else ' ' * 13

            if key == 'SHOW_ABOUT_INFO':
                about_lines = [self.get_string('about_header')]
                for info_key, value in self.ABOUT_INFO.items():
                    label_key = f'about_label_{info_key}'
                    label_text = self.get_string(label_key)
                    about_lines.append(f"  - {label_text}\t: {value}")
                output_buffer.append("\n".join(about_lines) + "\n")
            elif key == 'backend_job_summary':
                output_buffer.append(f"\n[{timestamp}] {message}")
            else:
                output_buffer.append(f"{line_prefix}{message}")

        final_text = "".join(output_buffer)
        self.log_area.insert('1.0', final_text)
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def _add_raw_text(self, text):
        self.log_data.append((None, text, None))

    def _add_log_event(self, key, kwargs=None):
        if kwargs is None:
            kwargs = {}
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_data.append((timestamp, key, kwargs))

    def start_processing_thread(self):
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        self.log_data.clear()
        self.show_initial_message()
        self.re_render_logs()
        
        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.last_progress_info = {'current': 0, 'total': 0}
        self.progress_label_var.set(self.get_string('status_searching'))
        
        self.file_processor.set_get_string_func(self.get_string)
        
        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()
        
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread):
        log_items_batch = []
        progress_updates = []
        
        try:
            while not self.log_queue.empty():
                log_items_batch.append(self.log_queue.get_nowait())
            while not self.progress_queue.empty():
                progress_updates.append(self.progress_queue.get_nowait())
        except queue.Empty:
            pass

        if log_items_batch:
            is_first_job_log = self.log_data[-1][1] == SEPARATOR
            if is_first_job_log:
                self._add_raw_text("")
                self._add_raw_text("="*100)

            for key, kwargs in log_items_batch:
                self._add_log_event(key, kwargs)
            self.re_render_logs()

        if progress_updates:
            for progress_val, current, total in progress_updates:
                self.progress_bar['value'] = progress_val
                self.last_progress_info = {'current': current, 'total': total}
                self.progress_label_var.set(self.get_string('status_processing', current=current, total=total))
                self.total_files_count = total

        if thread.is_alive():
            self.after(self.GUI_UPDATE_INTERVAL_MS, lambda: self.monitor_queue(thread))
        else:
            final_log_items = []
            try:
                while True: 
                    final_log_items.append(self.log_queue.get_nowait())
            except queue.Empty: pass
            
            if final_log_items:
                for key, kwargs in final_log_items:
                    self._add_log_event(key, kwargs)
            
            self.re_render_logs()

            self.is_processing = False
            self.progress_bar['value'] = 100
            if self.total_files_count > 0:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                self.progress_label_var.set(self.get_string('status_complete'))
            self.start_button.config(state=tk.NORMAL)
