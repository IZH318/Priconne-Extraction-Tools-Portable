from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Text, Scrollbar, PanedWindow
from typing import Any
import queue
import threading
import concurrent.futures
from multiprocessing import Manager, cpu_count
from datetime import datetime
import os
import sys
from tkinterdnd2 import DND_FILES

from .languages import LANGUAGES
from .extractor import process_single_file, AssetProcessor
from .asset_browser import AssetBrowserWindow

from src.constants import UNITY_SUPPORTED_EXTENSIONS as SUPPORTED_EXTENSIONS

class AssetExtractorApp(ttk.Frame):
    def __init__(self, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        """
        AssetExtractorApp 인스턴스 초기화.

        Args:
            master (tk.Tk | ttk.Notebook): Tkinter의 자식/부모 위젯.
            app_lang_var (tk.StringVar): 중앙 언어 변수.
        """
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.root = master
        self.file_paths = [] # 처리할 파일 경로 리스트
        self.output_path = "" # 출력 폴더 경로
        self.is_running = False # 작업 실행 여부 플래그
        self.processed_files_count = 0 # 처리 완료된 파일 수
        self.base_input_path = None # 폴더 열기 시 기준 경로
        self.log_events = [] # 로그 재표시를 위한 이벤트 저장소
        self.unity_version_var = tk.StringVar(value="2021.3.20f1") # 유니티 강제 버전 값
        self.version_combo_var = tk.StringVar(value="2021.3.20f1") # 드롭다운 선택 값
        self.cancel_event = threading.Event()
        self.about_info = about_info or {}
        
        # 에셋 타입별 체크박스 변수 초기화
        self.asset_type_vars = {}

        if app_lang_var:
            self.lang = app_lang_var
        else:
            self.lang = tk.StringVar(value='ko') # 언어 설정 변수
            
        self.lang.trace_add('write', self._on_language_change)

        # 멀티프로세싱 통신을 위한 Manager 큐 (Lazy 초기화)
        self._manager = None
        self._log_queue = None
        self._completion_queue = None

        self._setup_ui()
        self.root.after(100, self._process_queues)

    @property
    def manager(self):
        """멀티프로세싱 Manager를 지연 초기화하여 불필요한 프로세스 생성을 방지합니다."""
        if self._manager is None:
            self._manager = Manager()
        return self._manager

    @property
    def log_queue(self):
        if self._log_queue is None:
            self._log_queue = self.manager.Queue()
        return self._log_queue

    @property
    def completion_queue(self):
        if self._completion_queue is None:
            self._completion_queue = self.manager.Queue()
        return self._completion_queue

    def _setup_ui(self):
        """Tkinter 위젯들을 생성하고 배치합니다."""
        # 메인 레이아웃 (좌: 파일 목록, 우: 로그)
        main_paned_window = PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 좌측 패널 (파일 목록)
        left_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(left_pane, width=240)
        
        # 파일/폴더 열기 버튼 (그룹박스로 묶음)
        self.open_frame = ttk.LabelFrame(left_pane, text="")
        self.open_frame.pack(fill=tk.X, pady=(0, 5))
        self.btn_open_file = ttk.Button(self.open_frame, text="", command=self._select_files)
        self.btn_open_file.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 2), pady=5)
        self.btn_open_folder = ttk.Button(self.open_frame, text="", command=self._select_folder)
        self.btn_open_folder.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 5), pady=5)

        self.list_frame = ttk.LabelFrame(left_pane, text="")
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(self.list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.file_listbox = tk.Listbox(self.list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<Delete>", self._remove_selected_files)

        # 중앙 패널 (에셋 타입 필터)
        center_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(center_pane, width=200)
        self._build_type_filter_panel(center_pane)

        # 우측 패널 (로그 및 진행률)
        self.log_frame = ttk.LabelFrame(main_paned_window, text="")
        main_paned_window.add(self.log_frame)
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        log_text_frame = ttk.Frame(self.log_frame)
        log_text_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        log_text_frame.grid_rowconfigure(0, weight=1)
        log_text_frame.grid_columnconfigure(0, weight=1)
        log_scrollbar = Scrollbar(log_text_frame)
        log_scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text = Text(log_text_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state='disabled', padx=5, pady=5)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_scrollbar.config(command=self.log_text.yview)
        
        # 로그 레벨별 태그 설정
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", background="#FFF3CD", foreground="#856404")
        self.log_text.tag_config("ERROR", background="#F8D7DA", foreground="#721C24")
        self.log_text.tag_config("SUCCESS", background="#D4EDDA", foreground="#155724")

        progress_info_frame = ttk.Frame(self.log_frame)
        progress_info_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))
        progress_info_frame.grid_columnconfigure(1, weight=1)
        self.progress_label = ttk.Label(progress_info_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.progress_bar = ttk.Progressbar(progress_info_frame, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=0, column=1, sticky='ew')
        
        # 하단 컨트롤 (출력 폴더, 시작 버튼)
        bottom_controls_frame = ttk.Frame(self)
        bottom_controls_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom_controls_frame.grid_columnconfigure(0, weight=1)
        self.output_frame = ttk.LabelFrame(bottom_controls_frame, text="")
        self.output_frame.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.output_entry = ttk.Entry(self.output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(self.output_frame, text="", command=self._select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)
        
        # 유니티 버전 선택 프레임 (드롭다운 + 수동입력 지원)
        self.version_frame = ttk.LabelFrame(bottom_controls_frame, text="")
        self.version_frame.grid(row=0, column=1, sticky='ns', padx=(0, 10))
        
        self.UNITY_VERSION_PRESETS = ["2021.3.20f1", "6000.0.58.57061"]
        self.MANUAL_INPUT_KEY = "__MANUAL__"  # 내부 식별용 키
        
        self.version_combo = ttk.Combobox(self.version_frame, textvariable=self.version_combo_var,
                                          state='readonly', width=18)
        self.version_combo.pack(side=tk.LEFT, padx=(5, 2), pady=5)
        self.version_combo.bind("<<ComboboxSelected>>", self._on_version_selection_change)
        
        self.version_entry = ttk.Entry(self.version_frame, textvariable=self.unity_version_var, width=18, state='disabled')
        self.version_entry.pack(side=tk.LEFT, padx=(2, 5), pady=5)

        self.start_button_container = ttk.LabelFrame(bottom_controls_frame, text="")
        self.start_button_container.grid(row=0, column=2, sticky='ns')
        self.start_button = ttk.Button(self.start_button_container, text="", command=self._start_extraction)
        self.start_button.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 파일 목록 컨텍스트 메뉴
        self.listbox_menu = tk.Menu(self, tearoff=0)
        self.listbox_menu.add_command(label="", command=self._remove_selected_files)
        self.listbox_menu.add_command(label="", command=self._remove_all_files)
        self.listbox_menu.add_separator()
        self.listbox_menu.add_command(label="", command=self._open_asset_browser)
        self.file_listbox.bind("<Button-3>", self._show_listbox_menu)
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu)

        self._update_ui_text() # UI 텍스트 초기화
        self._log('program_started')

    def _build_type_filter_panel(self, parent):
        """에셋 타입 필터 체크박스 패널을 생성합니다."""
        self.filter_frame = ttk.LabelFrame(parent, text="")
        self.filter_frame.pack(fill=tk.BOTH, expand=True)

        # 전체 선택 / 해제 버튼
        btn_frame = ttk.Frame(self.filter_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=(5, 2))
        self.btn_select_all = ttk.Button(btn_frame, text="", command=self._select_all_types)
        self.btn_select_all.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        self.btn_deselect_all = ttk.Button(btn_frame, text="", command=self._deselect_all_types)
        self.btn_deselect_all.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 0))

        # 스크롤 가능한 체크박스 영역
        canvas = tk.Canvas(self.filter_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.filter_frame, orient="vertical", command=canvas.yview)
        self.filter_inner_frame = ttk.Frame(canvas)

        self.filter_inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.filter_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # 마우스 휠 스크롤 지원 (필터 영역 위에서만 작동)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        # 카테고리별 체크박스 생성 (Unity 표준 용어 기반 분류)
        self._type_group_labels = {}  # 레이블 위젯 참조 저장 (UI 텍스트 업데이트용)
        categories = [
            ("filter_group_textures", ["Texture2D", "Sprite", "Texture2DArray"]),
            ("filter_group_media", ["AudioClip", "MovieTexture", "VideoClip"]),
            ("filter_group_resources", ["TextAsset", "MonoBehaviour", "AnimationClip", "Mesh", "Shader", "Font", "Material"]),
            ("filter_group_components", sorted(AssetProcessor.SKIP_TYPES) + ["_OTHER_"]),
        ]

        default_enabled = AssetProcessor.DEFAULT_ENABLED
        is_first_group = True

        for group_key, type_list in categories:
            # 그룹 구분선 (첫 그룹 제외)
            if not is_first_group:
                ttk.Separator(self.filter_inner_frame, orient='horizontal').pack(fill=tk.X, pady=(4, 0))
            is_first_group = False

            # 그룹 레이블
            group_label = ttk.Label(self.filter_inner_frame, text="", font=("TkDefaultFont", 10, "bold"))
            group_label.pack(anchor="w", pady=(4, 1))
            self._type_group_labels[group_key] = group_label

            # 체크박스
            for type_name in type_list:
                var = tk.BooleanVar(value=(type_name in default_enabled))
                self.asset_type_vars[type_name] = var
                display_name = type_name
                if type_name == "_OTHER_":
                    display_name = "Other (Generic JSON)"
                cb = ttk.Checkbutton(self.filter_inner_frame, text=display_name, variable=var)
                cb.pack(anchor="w", padx=(12, 0))

    def _get_enabled_types(self):
        """체크된 에셋 타입들의 집합을 반환합니다."""
        return {name for name, var in self.asset_type_vars.items() if var.get()}

    def _select_all_types(self):
        """모든 체크박스를 선택합니다."""
        for var in self.asset_type_vars.values():
            var.set(True)

    def _deselect_all_types(self):
        """모든 체크박스를 해제합니다."""
        for var in self.asset_type_vars.values():
            var.set(False)

    def _on_version_selection_change(self, event=None):
        """Combobox 선택 변경 시 호출되어 Entry 상태와 값을 업데이트합니다."""
        selected = self.version_combo_var.get()
        if selected in self.UNITY_VERSION_PRESETS:
            # 프리셋 선택: 값을 Entry에 반영하고 비활성화
            self.unity_version_var.set(selected)
            self.version_entry.config(state='disabled')
        else:
            # 수동입력 선택: Entry 활성화 및 기존 값 초기화
            self.version_entry.config(state='normal')
            if self.unity_version_var.get() in self.UNITY_VERSION_PRESETS:
                self.unity_version_var.set("")
            self.version_entry.focus_set()

    def _on_language_change(self, *args):
        """언어 변경 시 UI 텍스트 업데이트 및 로그 재표시를 호출합니다."""
        self._update_ui_text()
        self._redisplay_logs()

    def _update_ui_text(self):
        """UI의 모든 텍스트 요소를 현재 선택된 언어로 갱신합니다."""
        lang = self.lang.get()
        d = LANGUAGES[lang]
        
        self.btn_open_file.config(text=d['file_open'])
        self.btn_open_folder.config(text=d['folder_open'])

        self.list_frame.config(text=d['file_list'])
        self.log_frame.config(text=d['log_history'])
        self.output_frame.config(text=d['output_folder'])
        self.open_frame.config(text=d.get('open_frame_title', 'Open'))
        self.version_frame.config(text=d.get('unity_version_label', 'Unity Version:'))
        
        # Combobox 항목 업데이트 (언어 변경 시 수동입력 텍스트 반영)
        manual_label = d.get('version_manual_input', 'Manual Input')
        combo_values = self.UNITY_VERSION_PRESETS + [manual_label]
        self.version_combo['values'] = combo_values
        # 현재 항목이 수동입력이었다면 새 언어의 수동입력 텍스트로 갱신
        current = self.version_combo_var.get()
        if current not in self.UNITY_VERSION_PRESETS:
            self.version_combo_var.set(manual_label)
        
        self.output_button.config(text=d['browse'])
        self.start_button_container.config(text=d['run'])
        self.start_button.config(text=d['start_extraction'])
        self.listbox_menu.entryconfig(0, label=d['remove_selected'])
        self.listbox_menu.entryconfig(1, label=d['remove_all'])
        
        # 필터 패널 텍스트 업데이트
        self.filter_frame.config(text=d.get('filter_panel_title', 'Asset Type Filter'))
        self.btn_select_all.config(text=d.get('select_all', 'Select All'))
        self.btn_deselect_all.config(text=d.get('deselect_all', 'Deselect All'))
        for key, label_widget in self._type_group_labels.items():
            label_widget.config(text=d.get(key, key))
        
        self._update_progress_bar()

    def _redisplay_logs(self):
        """언어 변경 시, 저장된 로그 이벤트를 새 언어로 다시 렌더링합니다."""
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        for event in self.log_events:
            self._render_log_event(event)
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)

    def _add_log_event(self, message_key, level='INFO', format_args=None, prefix=None):
        """로그 이벤트를 내부 리스트에 저장하고 반환합니다."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event = (timestamp, prefix, message_key, level, format_args)
        self.log_events.append(event)
        return event

    def _render_log_event(self, event, widget=None):
        """단일 로그 이벤트를 로그 위젯에 렌더링합니다."""
        target_widget = widget or self.log_text
        timestamp, prefix, message_key, level, format_args = event
        
        if message_key == 'show_about_info':
            self._display_about_info_in_log(target_widget)
            return

        lang = self.lang.get()
        message_template = LANGUAGES[lang].get(message_key, message_key)
        
        if message_key == 'raw_text':
            message = format_args.get('text', '') if format_args else ''
        else:
            message = message_template.format(**format_args) if format_args else message_template
        
        log_prefix = f"[{prefix}] " if prefix else ""
        full_message = f"[{timestamp}] {log_prefix}{message}\n"
        
        target_widget.config(state='normal')
        target_widget.insert(tk.END, full_message, level)
        target_widget.config(state='disabled')

    def _log(self, message_key, level='INFO', format_args=None, prefix=None):
        """로그를 기록하고 즉시 화면에 표시합니다."""
        event = self._add_log_event(message_key, level, format_args, prefix)
        self._render_log_event(event)
        self.log_text.see(tk.END)

    def _show_about_info(self):
        """'정보' 메뉴 클릭 시 로그 기록을 트리거합니다."""
        self._log('show_about_info', level='INFO')

    def _display_about_info_in_log(self, widget):
        """'정보' 내용을 로그 위젯에 특수 포맷으로 표시합니다."""
        lang = self.lang.get()
        d = LANGUAGES[lang]
        separator = "-" * 70 + "\n"
        
        widget.config(state='normal')
        widget.insert(tk.END, separator, "INFO")
        
        header_text = f"{d['about_header']}\n"
        widget.insert(tk.END, header_text, "INFO")
        
        about_lines = []
        for key, value in self.about_info.items():
            label_key = f'about_label_{key}'
            label_text = d.get(label_key, key.capitalize())
            about_lines.append(f"  - {label_text} : {value}")
        
        widget.insert(tk.END, "\n".join(about_lines) + "\n", "INFO")
        widget.insert(tk.END, separator, "INFO")
        widget.config(state='disabled')

    def _process_queues(self):
        """
        주기적으로 실행되어 워커 프로세스로부터 온 메시지를 GUI에 반영합니다.
        GUI가 멈추지 않도록 비동기적으로 작동하는 핵심 부분입니다.
        """
        log_batch = []
        completion_batch_size = 0

        try:
            # 성능을 위해 메시지를 일괄 처리
            while not self.log_queue.empty():
                log_batch.append(self.log_queue.get_nowait())
            while not self.completion_queue.empty():
                self.completion_queue.get_nowait()
                completion_batch_size += 1
        except queue.Empty:
            pass

        # 로그 일괄 렌더링
        if log_batch:
            self.log_text.config(state='normal')
            for log_item in log_batch:
                log_type, *data = log_item
                if log_type == 'log':
                    prefix, message_key, level, format_args = data
                    event = self._add_log_event(message_key, level, format_args, prefix)
                    self._render_log_event(event)
                elif log_type == 'raw':
                    text, level = data
                    event = self._add_log_event('raw_text', level, {'text': text})
                    self._render_log_event(event)
            self.log_text.config(state='disabled')
            self.log_text.see(tk.END)

        # 진행률 일괄 업데이트
        if completion_batch_size > 0:
            self.processed_files_count += completion_batch_size
            self._update_progress_bar()

        # 다음 폴링 예약
        self.root.after(100, self._process_queues)
    
    def _update_progress_bar(self):
        """진행률 표시줄과 레이블의 상태를 현재 진행 상황에 맞게 업데이트합니다."""
        d = LANGUAGES[self.lang.get()]
        if self.is_running and self.file_paths:
            total_files = len(self.file_paths)
            self.progress_label.config(text=f"{d['progress']}{self.processed_files_count} / {total_files}")
            self.progress_bar['value'] = self.processed_files_count
        else:
            self.progress_bar['value'] = 0
            self.progress_label.config(text=f"{d['progress']}{d['waiting']}")

    def _toggle_controls(self, enabled):
        """작업 시작/종료 시 UI 컨트롤들의 활성화/비활성화 상태를 전환합니다."""
        state = 'normal' if enabled else 'disabled'
        
        # 만약 시작하는 중이면(enabled=False) 취소 버튼 기능으로 변경
        if not enabled:
            d = LANGUAGES[self.lang.get()]
            self.start_button.config(state='normal', text=d.get('cancel_extraction', 'Cancel'), command=self.cancel_event.set)
        else:
            d = LANGUAGES[self.lang.get()]
            self.start_button.config(state='normal', text=d['start_extraction'], command=self._start_extraction)
            
        self.output_button.config(state=state)
        self.btn_open_file.config(state=state)
        self.btn_open_folder.config(state=state)
        self.version_combo.config(state='readonly' if enabled else 'disabled')
        # 수동입력 모드일 때만 entry 활성화
        if enabled:
            current = self.version_combo_var.get()
            is_manual = current not in self.UNITY_VERSION_PRESETS
            self.version_entry.config(state='normal' if is_manual else 'disabled')
        else:
            self.version_entry.config(state='disabled')
        self.btn_select_all.config(state=state)
        self.btn_deselect_all.config(state=state)
        # 체크박스 활성화/비활성화
        for widget in self.filter_inner_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)
    
    def _select_files(self):
        """'파일 열기' 대화상자를 통해 파일을 선택하고 목록에 추가합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        paths = filedialog.askopenfilenames(
            title=d['file_dialog_title'],
            filetypes=((d['file_dialog_type'], "*.unity3d"),)
        )
        if paths:
            self.base_input_path = None
            self._add_files_to_list(paths)
        
    def _select_folder(self):
        """'폴더 열기' 대화상자를 통해 폴더 내의 모든 지원 파일을 목록에 추가합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        folder_path = filedialog.askdirectory(title=d['folder_dialog_title'])
        if folder_path:
            self.base_input_path = folder_path
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log('no_files_to_process', "WARNING")
            
    def _on_dnd_drop(self, event):
        """드래그 앤 드롭 이벤트를 처리하여 파싱된 경로를 목록에 추가합니다."""
        if self.is_running: return
        try:
            paths = self.master.root.tk.splitlist(event.data) if hasattr(self.master, 'root') else self.tk.splitlist(event.data)
        except AttributeError:
            import re
            paths = [p.strip() for p in re.findall(r'\{[^{}]*\}|[^ ]+', event.data) if p.strip()]
            
        found_paths = []
        for path in paths:
            if os.path.isfile(path) and path.lower().endswith(SUPPORTED_EXTENSIONS):
                found_paths.append(path)
            elif os.path.isdir(path):
                self.base_input_path = path if not self.base_input_path else self.base_input_path
                found_paths.extend([os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)])
                
        if found_paths:
            self._add_files_to_list(found_paths)
        else:
            self._log('no_files_to_process', "WARNING")

    def _add_files_to_list(self, new_paths):
        """새 파일들을 중복 없이 정렬하여 목록과 리스트 박스에 추가합니다."""
        current_paths_set = set(self.file_paths)
        added_count = 0
        for path in new_paths:
            if path not in current_paths_set:
                self.file_paths.append(path)
                current_paths_set.add(path)
                added_count += 1
        
        if added_count > 0:
            self.file_paths.sort()
            self.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.file_listbox.insert(tk.END, os.path.basename(path))
            self._log('added_files', format_args={'count': added_count, 'total': len(self.file_paths)})
            
    def _remove_selected_files(self, event=None):
        """리스트 박스에서 선택된 항목들을 목록과 리스트 박스에서 제거합니다."""
        if self.is_running: return
        selected_indices = self.file_listbox.curselection()
        if not selected_indices: return
        
        count = len(selected_indices)
        for index in sorted(selected_indices, reverse=True):
            del self.file_paths[index]
            self.file_listbox.delete(index)
        self._log('removed_selected_files', format_args={'count': count, 'total': len(self.file_paths)})
        
    def _remove_all_files(self):
        """모든 파일을 목록에서 제거합니다."""
        if self.is_running: return
        if not self.file_paths: return
        count = len(self.file_paths)
        self.file_paths.clear()
        self.file_listbox.delete(0, tk.END)
        self.base_input_path = None
        self._log('removed_all_files', format_args={'count': count})
        
    def _show_listbox_menu(self, event):
        """파일 목록에서 우클릭 시 컨텍스트 메뉴를 표시합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        has_selection = bool(self.file_listbox.curselection())
        self.listbox_menu.entryconfig(0, state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.entryconfig(1, state=tk.NORMAL if self.file_paths else tk.DISABLED)
        # index 2 = separator
        self.listbox_menu.entryconfig(3, label=d.get('browse_assets_menu', 'Browse Assets'), state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)

    def _open_asset_browser(self):
        """선택된 파일의 에셋 탐색기를 엽니다."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.file_paths):
            return
        file_path = str(self.file_paths[idx])
        d = LANGUAGES[self.lang.get()]
        unity_version = self.unity_version_var.get().strip() or "2021.3.20f1"
        AssetBrowserWindow(self.winfo_toplevel(), file_path, d, unity_version)
        
    def _select_output_dir(self):
        """'출력 폴더' 대화상자를 열고 선택된 경로를 저장합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        path = filedialog.askdirectory(title=d['output_folder'])
        if path:
            self.output_path = path
            self.output_entry.config(state='normal')
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)
            self.output_entry.config(state='readonly')
            self._log('output_dir_set', format_args={'path': path})

    def _start_extraction(self):
        """'작업 시작' 버튼 클릭 시 유효성 검사 후 백엔드 처리를 시작합니다."""
        d = LANGUAGES[self.lang.get()]
        if not self.file_paths:
            messagebox.showwarning(d['warn_no_files_title'], d['warn_no_files_msg'])
            return
        if not self.output_path:
            messagebox.showwarning(d['warn_no_output_title'], d['warn_no_output_msg'])
            return
            
        self.is_running = True
        self.cancel_event.clear()
        self._toggle_controls(False)
        self.processed_files_count = 0
        self.progress_bar.config(maximum=len(self.file_paths))
        self._update_progress_bar()
        # Tk 변수를 메인 스레드에서 미리 캡처 (BooleanVar/StringVar는 Tk 스레드에서만 접근 가능)
        self._current_enabled_types = self._get_enabled_types()
        unity_version = self.unity_version_var.get().strip()
        if not unity_version:
            unity_version = "2021.3.20f1"
        self._current_unity_version = unity_version
        thread = threading.Thread(target=self._run_process_pool, daemon=True)
        thread.start()

    def _run_process_pool(self):
        """ProcessPoolExecutor를 생성하고 파일 처리 작업을 워커 프로세스에 제출합니다."""
        num_workers = min(cpu_count(), len(self.file_paths))
        self._log('processing_started', format_args={'num_workers': num_workers})
        
        unity_version = self._current_unity_version
        enabled_types = self._current_enabled_types

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_path = {
                executor.submit(process_single_file, file_path, self.output_path, self.base_input_path, self.log_queue, self.completion_queue, unity_version, enabled_types): file_path 
                for file_path in self.file_paths
            }
            for future in concurrent.futures.as_completed(future_to_path):
                if self.cancel_event.is_set():
                    self._log('extraction_cancelled', "ERROR")
                    break
        
        # 취소 시 진행 중인 작업을 종료시키기 위해 wait=True로 남은 future를 취소(실행 중 자식 프로세스는 즉시 종료 안됨)
        executor.shutdown(wait=True, cancel_futures=True)

        self.root.after(0, self._on_extraction_complete)

    def _on_extraction_complete(self):
        """모든 워커 프로세스가 종료된 후 호출됩니다."""
        self.root.after(200, self._finalize_completion) # 큐에 남은 메시지 처리를 위해 약간의 지연

    def _finalize_completion(self):
        """최종 완료 로그를 남기고 UI 컨트롤을 다시 활성화합니다."""
        self._log("raw_text", format_args={'text': "========================================"})
        self._log('all_tasks_completed', "SUCCESS")
        self.is_running = False
        self.root.after(0, self._toggle_controls, True)

class TextRedirector:
    def __init__(self, app_instance, tag="INFO"):
        """
        TextRedirector 인스턴스 초기화.

        Args:
            app_instance (AssetExtractorApp): GUI 애플리케이션의 인스턴스.
            tag (str): 리디렉션된 텍스트에 적용할 기본 로그 레벨 태그.
        """
        self.app = app_instance
        self.tag = tag
    def write(self, text):
        """표준 출력을 가로채서 GUI의 로그 큐로 전송합니다."""
        # 빈 줄은 무시하고, 텍스트가 있을 경우에만 큐에 넣음
        if text.strip():
            self.app.log_queue.put(('raw', text.strip(), self.tag))
    def flush(self):
        """`flush` 호출을 처리하기 위한 빈 메서드 (호환성 목적)."""
        pass
