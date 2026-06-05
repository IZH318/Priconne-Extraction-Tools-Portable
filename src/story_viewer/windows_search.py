from __future__ import annotations
# src/story_viewer/windows_search.py
import json
import os
import threading
import concurrent.futures
import sqlite3
import tkinter as tk
import logging
from tkinter import ttk, messagebox, filedialog
from typing import Any, Callable
import queue

from src.languages import STORY_VIEWER_LANGUAGES as LANGUAGES
from src.queue_events import ActionEvent
from .logic import SearchEngine

class SearchWindow(tk.Toplevel):
    """다양한 조건으로 스토리를 검색하는 대화상자 클래스입니다.

    Note:
        Controller와의 순환 참조를 방지하기 위해, Controller 전체를 참조하지 않고
        필요한 콜백과 데이터 접근자만 개별 인자로 주입받습니다.
    """

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        get_lang_dict: Callable[[], dict[str, str]],
        get_lang_code: Callable[[], str],
        search_callback: Callable[[list[str]], None],
        task_queue: queue.Queue[ActionEvent],
        update_status_bar: Callable[..., None],
        all_files_dict: dict[str, str],
        search_data: dict[str, Any],
        db_status: dict[str, bool],
        server_db_info: dict[str, Any],
    ) -> None:
        """SearchWindow 객체를 초기화합니다.

        Args:
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            get_lang_dict: 현재 언어 딕셔너리를 반환하는 콜백.
            get_lang_code: 현재 언어 코드를 반환하는 콜백.
            search_callback: 검색 결과를 전달받을 콜백 함수.
            task_queue: 메인 스레드로 액션을 전달할 큐.
            update_status_bar: 상태바를 업데이트하는 콜백.
            all_files_dict: 전체 스토리 파일 딕셔너리.
            search_data: 콤보박스에 표시할 자동완성 데이터 딕셔너리.
            db_status: 각 지역 DB(JP, KR)의 로드 상태.
            server_db_info: 서버 DB 메타데이터.
        """
        super().__init__(master)
        self._master = master
        self._get_lang_dict = get_lang_dict
        self._get_lang_code = get_lang_code
        self._search_callback = search_callback
        self._task_queue = task_queue
        self._update_status_bar = update_status_bar
        self.all_files_dict = all_files_dict
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        self.search_vars = {
            'filename': tk.StringVar(), 'title': tk.StringVar(), 'outline': tk.StringVar(),
            'char_name': tk.StringVar(), 'char_type': tk.StringVar(), 'content': tk.StringVar(),
            'bgm': tk.StringVar(), 'background': tk.StringVar(), 'event_name': tk.StringVar()
        }
        self.server_var = tk.StringVar(value='JP')

        self.transient(master)
        self.grab_set()
        self._setup_ui()
        self._on_server_selection_change()
        self.focus_set()
        self._center_window(480, 390)

    def _center_window(self, width: int, height: int) -> None:
        """대화상자를 화면 중앙에 배치합니다.

        Args:
            width: 창 너비.
            height: 창 높이.
        """
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self) -> None:
        """대화상자의 UI 요소들을 초기화하고 배치합니다."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.criteria_frame = ttk.LabelFrame(main_frame, text="", padding=5)
        self.criteria_frame.pack(fill=tk.X, expand=False, anchor="n", pady=(0, 10))
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
        self.event_search_frame.pack(fill=tk.X, expand=True, anchor="n")
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
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        
        self.search_button = ttk.Button(button_frame, text="", command=self.start_search)
        self.search_button.pack(side=tk.RIGHT)
        self.reset_button = ttk.Button(button_frame, text="", command=self._reset)
        self.reset_button.pack(side=tk.RIGHT, padx=(0, 5))
        
        self._update_ui_text()

    def _update_ui_text(self) -> None:
        """현재 언어 설정에 맞춰 UI 텍스트를 업데이트합니다."""
        lang_dict = self._get_lang_dict()
        
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

    def _on_server_selection_change(self) -> None:
        """서버(JP/KR) 선택이 변경되었을 때 이벤트 리스트 콤보박스를 업데이트합니다."""
        selected_server = self.server_var.get()
        db_info = self.server_db_info.get(selected_server)
        lang_dict = self._get_lang_dict()
        
        self.event_combobox['values'] = []
        self.search_vars['event_name'].set('')
        
        if not db_info or not self.db_status.get(selected_server):
            self.event_combobox.config(state=tk.DISABLED)
            return
        
        self.event_combobox.config(state='readonly')
        
        try:
            from . import db_helper
            event_names = db_helper.fetch_event_names(db_info)
            self.event_combobox['values'] = event_names
        except sqlite3.Error as e:
            messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=e), parent=self)
            self.event_combobox.config(state=tk.DISABLED)

    def start_search(self) -> None:
        """사용자가 입력한 조건을 바탕으로 백그라운드 검색 작업을 시작합니다."""
        self._update_status_bar('status_searching')
        criteria = {key: var.get() for key, var in self.search_vars.items() if var.get()}
        server = self.server_var.get()
        # destroy() 전에 모든 공유 참조 및 Tk 변수 값을 메인 스레드에서 미리 캡처
        char_type_value = self.search_vars['char_type'].get()
        captured_refs = {
            'all_files_dict': self.all_files_dict,
            'search_callback': self._search_callback,
            'db_status': self.db_status,
            'server_db_info': self.server_db_info,
            'lang_var_value': self._get_lang_code(),
            'task_queue': self._task_queue,
            'update_status_bar': self._update_status_bar,
            'master': self._master,
            'get_lang_dict': self._get_lang_dict,
        }
        
        self.destroy()
        
        thread = threading.Thread(target=self._search_thread, args=(criteria, server, char_type_value, captured_refs))
        thread.daemon = True
        thread.start()

    @staticmethod
    def _search_thread(criteria: dict[str, str], server: str, char_type_value: str, refs: dict[str, Any]) -> None:
        """실제 검색 로직을 백그라운드 스레드에서 수행합니다.

        Args:
            criteria: 사용자가 입력한 검색 조건 딕셔너리.
            server: 선택된 서버 ('JP' 또는 'KR').
            char_type_value: 캐릭터 이름 검색 옵션 ('화자' 또는 '지문 포함').
            refs: 메인 스레드에서 캡처한 참조 객체 딕셔너리.
        """
        from . import db_helper
        all_files_dict = refs['all_files_dict']
        search_callback = refs['search_callback']
        db_status = refs['db_status']
        server_db_info = refs['server_db_info']
        task_queue = refs['task_queue']
        update_status_bar = refs['update_status_bar']
        master_ref = refs['master']
        get_lang_dict_ref = refs['get_lang_dict']
        lang_dict = LANGUAGES.get(refs['lang_var_value'], LANGUAGES.get('ko', {}))
            
        try:
            initial_matched_files = set(all_files_dict.keys())

            if 'event_name' in criteria:
                selected_event_name = criteria['event_name']
                db_info = server_db_info.get(server)
                
                if db_info and db_status.get(server):
                    try:
                        event_story_ids = db_helper.fetch_event_story_ids(db_info, selected_event_name)
                        initial_matched_files.intersection_update(event_story_ids)
                    except sqlite3.Error as e:
                        task_queue.put(ActionEvent(action=lambda exc=e: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=exc), parent=master_ref)))
            
            # event_name은 DB 필터로 이미 처리했으므로, 파일 내용 대조용 기준에서 제외
            content_criteria = {k: v for k, v in criteria.items() if k != 'event_name'}
            final_matched_files = []
            if not content_criteria:
                final_matched_files = list(initial_matched_files)
            else:
                char_type_search = char_type_value
                char_type_speaker = lang_dict['char_type_speaker']
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_to_filename = {
                        executor.submit(SearchEngine.check_file_for_search, filename, content_criteria, char_type_search, char_type_speaker, all_files_dict): filename 
                        for filename in initial_matched_files
                    }
                    for future in concurrent.futures.as_completed(future_to_filename):
                        try:
                            if future.result():
                                final_matched_files.append(future_to_filename[future])
                        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
                            logging.error("SearchEngine future exception: %s", e)
            
            task_queue.put(ActionEvent(action=lambda: search_callback(sorted(final_matched_files))))

        except (OSError, sqlite3.Error) as e:
            # self(Toplevel)는 이미 destroy() 되었으므로 self 참조를 피하고
            # 캡처된 참조만 사용합니다.
            def _show_error(error=e):
                ld = get_lang_dict_ref()
                messagebox.showerror(ld['search_error_title'], ld['search_error_msg'].format(e=error), parent=master_ref)
                update_status_bar('status_bar_ready')
            task_queue.put(ActionEvent(action=_show_error))

    def _reset(self) -> None:
        """검색 조건을 초기화하고 전체 파일 목록을 다시 로드합니다."""
        self._search_callback(list(self.all_files_dict.keys()))
        self.destroy()
