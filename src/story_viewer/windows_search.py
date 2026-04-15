from __future__ import annotations
# src/story_viewer/windows_search.py
import os
import threading
import concurrent.futures
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from src.languages import STORY_VIEWER_LANGUAGES as LANGUAGES
from src.queue_events import ActionEvent
from .logic import SearchEngine

class SearchWindow(tk.Toplevel):
    def __init__(self, app, all_files_dict, search_callback, search_data, db_status, server_db_info):
        super().__init__(app.master)
        self.app = app
        self.all_files_dict = all_files_dict
        self.search_callback = search_callback
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        self.search_vars = {
            'filename': tk.StringVar(), 'title': tk.StringVar(), 'outline': tk.StringVar(),
            'char_name': tk.StringVar(), 'char_type': tk.StringVar(), 'content': tk.StringVar(),
            'bgm': tk.StringVar(), 'background': tk.StringVar(), 'event_name': tk.StringVar()
        }
        self.server_var = tk.StringVar(value='JP')

        self.transient(app.master)
        self.grab_set()
        self._setup_ui()
        self._on_server_selection_change()
        self.focus_set()
        self._center_window(480, 390)

    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.criteria_frame = ttk.LabelFrame(main_frame, text="", padding=5)
        self.criteria_frame.pack(fill="x", expand=False, anchor="n", pady=(0, 10))
        self.criteria_frame.columnconfigure(1, weight=1)
        self.criteria_frame.columnconfigure(3, weight=1)

        pady_value = 4
        
        self.filename_label = ttk.Label(self.criteria_frame, text="")
        self.filename_label.grid(row=0, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['filename'], values=self.search_data.get('filenames', [])).grid(row=0, column=1, columnspan=3, sticky="ew")

        self.title_label = ttk.Label(self.criteria_frame, text="")
        self.title_label.grid(row=1, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['title']).grid(row=1, column=1, columnspan=3, sticky="ew")

        self.outline_label = ttk.Label(self.criteria_frame, text="")
        self.outline_label.grid(row=2, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['outline']).grid(row=2, column=1, columnspan=3, sticky="ew")

        self.char_name_label = ttk.Label(self.criteria_frame, text="")
        self.char_name_label.grid(row=3, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_name'], values=self.search_data.get('character_names', [])).grid(row=3, column=1, sticky="ew")
        
        self.char_type_label = ttk.Label(self.criteria_frame, text="")
        self.char_type_label.grid(row=3, column=2, sticky="e", padx=(5,0))
        
        self.char_type_combobox = ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_type'], width=15, state='readonly')
        self.char_type_combobox.grid(row=3, column=3, sticky="e", padx=(5,0))

        self.content_label = ttk.Label(self.criteria_frame, text="")
        self.content_label.grid(row=4, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['content']).grid(row=4, column=1, columnspan=3, sticky="ew")

        self.bgm_label = ttk.Label(self.criteria_frame, text="")
        self.bgm_label.grid(row=5, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['bgm'], values=self.search_data.get('bgms', [])).grid(row=5, column=1, columnspan=3, sticky="ew")

        self.background_label = ttk.Label(self.criteria_frame, text="")
        self.background_label.grid(row=6, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['background'], values=self.search_data.get('backgrounds', [])).grid(row=6, column=1, columnspan=3, sticky="ew")

        self.event_search_frame = ttk.LabelFrame(main_frame, text="", padding="5")
        self.event_search_frame.pack(fill="x", expand=True, anchor="n")
        self.event_search_frame.columnconfigure(1, weight=1)

        server_frame = ttk.Frame(self.event_search_frame, padding="5")
        server_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,5))
        server_frame.columnconfigure(0, weight=1)
        server_frame.columnconfigure(1, weight=1)
        self.jp_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="JP", command=self._on_server_selection_change)
        self.jp_radio.grid(row=0, column=0, padx=5, sticky="w")
        self.kr_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="KR", command=self._on_server_selection_change)
        self.kr_radio.grid(row=0, column=1, padx=5, sticky="w")

        self.event_list_label = ttk.Label(self.event_search_frame, text="")
        self.event_list_label.grid(row=1, column=0, sticky="w", pady=3)
        self.event_combobox = ttk.Combobox(self.event_search_frame, textvariable=self.search_vars['event_name'], state='readonly')
        self.event_combobox.grid(row=1, column=1, columnspan=2, sticky="ew")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        self.search_button = ttk.Button(button_frame, text="", command=self.start_search)
        self.search_button.pack(side="right")
        self.reset_button = ttk.Button(button_frame, text="", command=self._reset)
        self.reset_button.pack(side="right", padx=(0, 5))
        
        self._update_ui_text()

    def _update_ui_text(self):
        lang_dict = LANGUAGES.get(self.app.lang_var.get(), LANGUAGES['ko'])
        
        self.title(lang_dict['search_window_title'])
        self.criteria_frame.config(text=lang_dict['basic_search_criteria_frame'])
        self.filename_label.config(text=lang_dict['filename_label'])
        self.title_label.config(text=lang_dict['title_label'])
        self.outline_label.config(text=lang_dict['outline_label'])
        self.char_name_label.config(text=lang_dict['char_name_label'])
        self.char_type_label.config(text=lang_dict['char_type_label'])
        self.content_label.config(text=lang_dict['content_label'])
        self.bgm_label.config(text=lang_dict['bgm_label'])
        self.background_label.config(text=lang_dict['background_label'])
        
        char_types = [lang_dict['char_type_speaker'], lang_dict['char_type_mentioned_in_dialogue']]
        self.char_type_combobox.config(values=char_types)
        if not self.search_vars['char_type'].get():
            self.search_vars['char_type'].set(char_types[0])

        self.event_search_frame.config(text=lang_dict['event_search_frame'])
        self.jp_radio.config(text=lang_dict['jp_server_radio'])
        self.kr_radio.config(text=lang_dict['kr_server_radio'])
        self.event_list_label.config(text=lang_dict['event_list_label'])

        self.search_button.config(text=lang_dict['search_button'])
        self.reset_button.config(text=lang_dict['reset_button'])

    def _on_server_selection_change(self):
        selected_server = self.server_var.get()
        db_info = self.server_db_info.get(selected_server)
        lang_dict = LANGUAGES.get(self.app.lang_var.get(), LANGUAGES['ko'])
        
        self.event_combobox['values'] = []
        self.search_vars['event_name'].set('')
        
        if not db_info or not self.db_status.get(selected_server):
            self.event_combobox.config(state='disabled')
            return
        
        self.event_combobox.config(state='readonly')
        
        try:
            from . import db_helper
            event_names = db_helper.fetch_event_names(db_info)
            self.event_combobox['values'] = event_names
        except sqlite3.Error as e:
            messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=e), parent=self)
            self.event_combobox.config(state='disabled')

    def start_search(self):
        self.app.view.update_status_bar('status_searching')
        criteria = {key: var.get() for key, var in self.search_vars.items() if var.get()}
        server = self.server_var.get()
        # destroy() 전에 모든 공유 참조 및 Tk 변수 값을 메인 스레드에서 미리 캡처
        char_type_value = self.search_vars['char_type'].get()
        captured_refs = {
            'app': self.app,
            'all_files_dict': self.all_files_dict,
            'search_callback': self.search_callback,
            'db_status': self.db_status,
            'server_db_info': self.server_db_info,
            'lang_var_value': self.app.lang_var.get(),
        }
        
        self.destroy()
        
        thread = threading.Thread(target=self._search_thread, args=(criteria, server, char_type_value, captured_refs))
        thread.daemon = True
        thread.start()

    def _search_thread(self, criteria, server, char_type_value, refs):
        from . import db_helper
        app = refs['app']
        all_files_dict = refs['all_files_dict']
        search_callback = refs['search_callback']
        db_status = refs['db_status']
        server_db_info = refs['server_db_info']
        lang_dict = LANGUAGES.get(refs['lang_var_value'], LANGUAGES['ko'])
            
        try:
            initial_matched_files = set(all_files_dict.keys())

            if 'event_name' in criteria:
                selected_event_name = criteria.pop('event_name')
                db_info = server_db_info.get(server)
                
                if db_info and db_status.get(server):
                    try:
                        event_story_ids = db_helper.fetch_event_story_ids(db_info, selected_event_name)
                        initial_matched_files.intersection_update(event_story_ids)
                    except sqlite3.Error as e:
                        app.task_queue.put(ActionEvent(action=lambda exc=e: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=exc), parent=app.master)))
            
            final_matched_files = []
            if not criteria:
                final_matched_files = list(initial_matched_files)
            else:
                char_type_search = char_type_value
                char_type_speaker = lang_dict['char_type_speaker']
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_to_filename = {
                        executor.submit(SearchEngine.check_file_for_search, filename, criteria, char_type_search, char_type_speaker, all_files_dict): filename 
                        for filename in initial_matched_files
                    }
                    for future in concurrent.futures.as_completed(future_to_filename):
                        if future.result():
                            final_matched_files.append(future_to_filename[future])
            
            app.task_queue.put(ActionEvent(action=lambda: search_callback(sorted(final_matched_files))))

        except (OSError, sqlite3.Error) as e:
            # self(Toplevel)는 이미 destroy() 되었으므로 self 참조를 피하고
            # 캡처된 app(컨트롤러) 참조만 사용합니다.
            def _show_error(error=e, app_ref=app):
                lang_dict = LANGUAGES.get(app_ref.lang_var.get(), LANGUAGES['ko'])
                messagebox.showerror(lang_dict['search_error_title'], lang_dict['search_error_msg'].format(e=error), parent=app_ref.master)
                app_ref.view.update_status_bar('status_bar_ready')
            app.task_queue.put(ActionEvent(action=_show_error))

    def _reset(self):
        self.search_callback(list(self.all_files_dict.keys()))
        self.destroy()
