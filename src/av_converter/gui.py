# src/av_converter/gui.py
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, Listbox, Menu
from datetime import datetime
import queue
import threading
from pathlib import Path
from tkinterdnd2 import DND_FILES
from .logic import ConversionLogic, FFmpegDownloader, SEPARATOR
from .languages import LANGUAGES

class App(ttk.Frame):
    def __init__(self, master, app_lang_var=None, about_info=None):
        # 초기화 (사용하지 않는 언어 키 정리)
        for lang in LANGUAGES.values(): lang.pop('env_check_footer', None)
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)
        
        # 멤버 변수 초기화
        self.master = master
        self.lang_data = LANGUAGES['ko']
        self.usmtoolkit_path, self.vgmstream_path = None, None
        self.video_full_paths, self.audio_full_paths = [], []
        self.video_filenames_var, self.audio_filenames_var = tk.StringVar(), tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)
        self.video_total_files, self.audio_total_files = 0, 0
        self.video_log_history, self.audio_log_history = [], []
        self.base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent)) # PyInstaller 호환 경로
        self.log_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.logic = ConversionLogic(self.log_queue, self.base_path)
        self.about_info = about_info or {}

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
            
        self.lang_var.trace_add('write', self._on_language_change_event)

        # UI 및 로직 설정
        self._find_tools()
        ffmpeg_parent_dir = self.usmtoolkit_path.parent if self.usmtoolkit_path else self.base_path
        self.ffmpeg_downloader = FFmpegDownloader(self.log_queue, ffmpeg_parent_dir, lambda: self.lang_data)
        self.last_log_timestamp = {'video': None, 'audio': None}
        self._setup_ui()
        self._log_initial_status()
        self._process_log_queue()
    
    def _on_language_change_event(self, *args):
        self.switch_language(self.lang_var.get())

    def _configure_window(self):
        """삭제됨 (메인 런처에서 크기 및 중앙 정렬 관리)."""
        pass

    def _find_tools(self):
        """프로그램 실행 경로 하위에서 필요한 외부 도구들을 탐색합니다."""
        for root, _, files in os.walk(self.base_path.parent): # Search in the main project folder
            lower_files = [f.lower() for f in files]
            if not self.usmtoolkit_path and "usmtoolkit.exe" in lower_files:
                self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "test.exe" in lower_files and "vgmstream" in str(Path(root)).lower():
                self.vgmstream_path = Path(root) / "test.exe"

    def _setup_ui(self):
        """메인 메뉴와 탭 구조 등 기본 UI를 설정합니다."""
        # 메인 메뉴 생성 제거 (런처에 위임)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.video_tab = ttk.Frame(self.notebook)
        self.audio_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.video_tab, text=self.lang_data['video_tab'])
        self.notebook.add(self.audio_tab, text=self.lang_data['audio_tab'])
        
        self.video_widgets, self.video_log_text, self.video_ui_elements = self._build_conversion_tab_ui(self.video_tab, 'video')
        self.audio_widgets, self.audio_log_text, self.audio_ui_elements = self._build_conversion_tab_ui(self.audio_tab, 'audio')

    def _create_main_menu(self):
        """독립 메뉴 대신 비어있는 함수로 대체합니다."""
        pass

    def switch_language(self, lang_code):
        """선택된 언어로 UI 텍스트와 로그를 갱신합니다."""
        if lang_code in LANGUAGES:
            self.lang_data = LANGUAGES[lang_code]
            self._update_ui_text()
            self._redraw_logs()

    def _update_ui_text(self):
        """UI의 모든 텍스트 요소를 현재 언어로 업데이트합니다."""
        d = self.lang_data
        
        self.notebook.tab(self.video_tab, text=d['video_tab'])
        self.notebook.tab(self.audio_tab, text=d['audio_tab'])
        
        # 비디오 탭 UI 텍스트 업데이트
        is_video_converting = self.video_widgets['action_btn']['state'] == tk.DISABLED
        for elem_key, lang_key in self.video_ui_elements.items():
            widget_to_update = getattr(self, f'video_ui_{elem_key}', None)
            if widget_to_update:
                 widget_to_update.config(text=d[lang_key])

        self.video_widgets['add_files_btn'].config(text=d['add_files'])
        self.video_widgets['add_folder_btn'].config(text=d['add_folder'])
        self.video_widgets['browse_btn'].config(text=d['browse'])
        self.video_widgets['action_btn'].config(text=d['start_conversion'])
        if not is_video_converting: 
            self.video_widgets['status_label'].config(text=d['status_idle'])

        # 오디오 탭 UI 텍스트 업데이트
        is_audio_converting = self.audio_widgets['action_btn']['state'] == tk.DISABLED
        for elem_key, lang_key in self.audio_ui_elements.items():
            widget_to_update = getattr(self, f'audio_ui_{elem_key}', None)
            if widget_to_update:
                widget_to_update.config(text=d[lang_key])

        self.audio_widgets['add_files_btn'].config(text=d['add_files'])
        self.audio_widgets['add_folder_btn'].config(text=d['add_folder'])
        self.audio_widgets['browse_btn'].config(text=d['browse'])
        self.audio_widgets['overwrite_check'].config(text=d['overwrite_option'])
        self.audio_widgets['action_btn'].config(text=d['start_conversion'])
        if not is_audio_converting: 
            self.audio_widgets['status_label'].config(text=d['status_idle'])
        
    def _show_about_info(self):
        """'정보' 메뉴 클릭 시 로그를 통해 프로그램 정보를 표시합니다."""
        try:
            # 현재 활성화된 탭 확인
            selected_tab = self.notebook.select()
            target_tab = 'video' if selected_tab == str(self.video_tab) else 'audio'
        except tk.TclError:
            target_tab = 'video' # 기본값
        
        # 정보 표시 이벤트를 큐에 넣음 (언어 변경에 대응하기 위해 키를 전송)
        self.log_queue.put(('log_un-timestamped', target_tab, 'raw', {'text': f"\n{SEPARATOR}"}))
        self.log_queue.put(('log_un-timestamped', target_tab, 'about_header', {}))
        for key, value in self.about_info.items():
            self.log_queue.put(('log_un-timestamped', target_tab, 'about_line_key', {'label_key': f'about_label_{key}', 'value': value}))
        self.log_queue.put(('log_un-timestamped', target_tab, 'raw', {'text': f"{SEPARATOR}\n"}))

    def _build_conversion_tab_ui(self, parent_tab, tab_type):
        """비디오/오디오 탭 내부의 공통 UI 레이아웃을 생성합니다."""
        d = self.lang_data
        is_audio_tab = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio_tab else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio_tab else self.video_full_paths
        filenames_var = self.audio_filenames_var if is_audio_tab else self.video_filenames_var

        # UI 위젯 생성 및 배치
        main_bottom_controls_frame = ttk.Frame(parent_tab)
        main_bottom_controls_frame.pack(side='bottom', fill='x', pady=5, padx=5)
        
        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(side='top', fill=tk.BOTH, expand=True)
        
        left_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(left_pane_frame, weight=1)
        
        right_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(right_pane_frame, weight=3)
        
        input_frame = ttk.LabelFrame(left_pane_frame, text=d['input_section'])
        input_frame.pack(fill='x', pady=5, padx=5)
        
        add_files_btn_cmd = lambda: self._add_files(file_types, full_paths, filenames_var, tab_type)
        add_files_btn = ttk.Button(input_frame, text=d['add_files'], command=add_files_btn_cmd)
        add_files_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        add_folder_btn_cmd = lambda: self._add_folder(file_types, full_paths, filenames_var, tab_type)
        add_folder_btn = ttk.Button(input_frame, text=d['add_folder'], command=add_folder_btn_cmd)
        add_folder_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        
        list_container = ttk.LabelFrame(left_pane_frame, text=d['file_list_section'])
        list_container.pack(fill='both', expand=True, pady=5, padx=5)
        
        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side='left', fill='both', expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
        scrollbar.pack(side='right', fill='y')
        
        listbox.config(yscrollcommand=scrollbar.set)

        # 드래그 앤 드롭 바인딩
        try:
            listbox.drop_target_register(DND_FILES)
            listbox.dnd_bind('<<Drop>>', lambda e, lb=listbox, fp=full_paths, fv=filenames_var, tt=tab_type: self._on_dnd_drop(e, lb, fp, fv, tt))
        except Exception as ex:
            self.log_queue.put(('log_entry', tab_type, 'raw', {'text': f"Drag & Drop disabled: {ex}\n"}))

        self._create_right_click_menu(listbox, full_paths, filenames_var, tab_type)
        
        log_frame_container = ttk.LabelFrame(right_pane_frame, text=d['log_section'])
        log_frame_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state='disabled', font=("TkFixedFont", 10))
        log_text_widget.pack(fill="both", expand=True, padx=5, pady=(5,0))
        
        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=(2,5))
        
        status_label = ttk.Label(status_frame, text=d['status_idle'])
        status_label.pack(side='left')
        
        progress_bar = ttk.Progressbar(status_frame, orient='horizontal', mode='determinate')
        progress_bar.pack(side='left', fill='x', expand=True, padx=(5,0))
        
        action_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d['action_section'])
        action_frame.pack(side='right', fill='y', padx=(5, 0))
        
        output_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d['output_section'])
        output_frame.pack(side='left', fill='x', expand=True)
        
        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        
        browse_btn_cmd = lambda: self._select_output_folder(output_entry)
        browse_btn = ttk.Button(output_frame, text=d['browse'], command=browse_btn_cmd)
        browse_btn.pack(side='left', padx=5, pady=5)
        
        action_button = ttk.Button(action_frame, text=d['start_conversion'])
        
        # 탭별 특화 위젯 및 커맨드 설정
        widgets_dict = {
            'action_btn': action_button, 'add_files_btn': add_files_btn,
            'add_folder_btn': add_folder_btn, 'output_entry': output_entry,
            'progress': progress_bar, 'status_label': status_label,
            'browse_btn': browse_btn
        }
        
        ui_elements_references = {
            'log_frame_container': log_frame_container, 'input_frame': input_frame,
            'list_container': list_container, 'output_frame': output_frame,
            'action_frame': action_frame
        }
        # 언어 변경 시 텍스트를 업데이트해야 할 위젯과 언어 키를 매핑
        ui_elements_for_lang_update = {
            'log_frame_container': 'log_section', 'input_frame': 'input_section',
            'list_container': 'file_list_section', 'output_frame': 'output_section',
            'action_frame': 'action_section'
        }
        # App 인스턴스에 위젯 참조를 저장
        for key, widget in ui_elements_references.items():
            setattr(self, f"{tab_type}_ui_{key}", widget)
        
        if is_audio_tab:
            action_button.pack(side='left', pady=5, padx=5)
            
            overwrite_check = ttk.Checkbutton(action_frame, text=d['overwrite_option'], variable=self.audio_overwrite_var)
            overwrite_check.pack(side='left', pady=5, padx=10)
            
            audio_conv_cmd = lambda: self.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get())
            action_button.config(command=audio_conv_cmd)
            widgets_dict['overwrite_check'] = overwrite_check
        else:
            action_button.pack(fill='x', pady=5, padx=5)
            video_conv_cmd = lambda: self.start_video_conversion(output_entry.get())
            action_button.config(command=video_conv_cmd)

        return widgets_dict, log_text_widget, ui_elements_for_lang_update

    def _log_initial_status(self):
        """프로그램 시작 시, 필요한 외부 도구의 존재 여부를 확인하고 결과를 로깅합니다."""
        self.video_log_history.clear()
        self.audio_log_history.clear()
        
        # 공통 시작 메시지
        for tab in ['video', 'audio']:
            self.log_queue.put(('log_un-timestamped', tab, 'raw', {'text': SEPARATOR}))
            self._add_log_entry(tab, 'program_started')
            self.log_queue.put(('log_un-timestamped', tab, 'raw', {'text': SEPARATOR}))

        # 비디오 환경 점검
        self._add_log_entry('video', 'env_check_header')
        if self.usmtoolkit_path:
            self._add_log_entry('video', 'env_success', tool_name="UsmToolkit.exe")
            self._add_log_entry('video', 'env_path', path=self.logic._get_relative_path(self.usmtoolkit_path))
            if self.ffmpeg_downloader.ffmpeg_path.exists():
                self._add_log_entry('video', 'env_success', tool_name="FFmpeg (ffmpeg.exe)")
                self._add_log_entry('video', 'env_path', path=self.logic._get_relative_path(self.ffmpeg_downloader.ffmpeg_path))
            else:
                self._add_log_entry('video', 'env_error', tool_name="FFmpeg (ffmpeg.exe)")
                self._add_log_entry('video', 'env_error_desc_ffmpeg_auto_download')
        else:
            self._add_log_entry('video', 'env_error', tool_name="UsmToolkit.exe")
            self._add_log_entry('video', 'env_error_desc_video')
        self.log_queue.put(('log_un-timestamped', 'video', 'raw', {'text': SEPARATOR}))
        self._add_log_entry('video', 'max_worker_log', count=self.logic.MAX_WORKERS)
        self.log_queue.put(('log_un-timestamped', 'video', 'raw', {'text': SEPARATOR}))
        self._add_spacing('video')

        # 오디오 환경 점검
        self._add_log_entry('audio', 'env_check_header')
        if self.vgmstream_path:
            self._add_log_entry('audio', 'env_success', tool_name="vgmstream(test.exe)")
            self._add_log_entry('audio', 'env_path', path=self.logic._get_relative_path(self.vgmstream_path))
        else:
            self._add_log_entry('audio', 'env_error', tool_name="vgmstream(test.exe)")
            self._add_log_entry('audio', 'env_error_desc_audio')
        self.log_queue.put(('log_un-timestamped', 'audio', 'raw', {'text': SEPARATOR}))
        self._add_log_entry('audio', 'max_worker_log', count=self.logic.MAX_WORKERS)
        self.log_queue.put(('log_un-timestamped', 'audio', 'raw', {'text': SEPARATOR}))
        self._add_spacing('audio')
        
    def _create_right_click_menu(self, listbox, full_paths, filenames_var, tab_type):
        """파일 목록 리스트박스의 우클릭 컨텍스트 메뉴를 생성합니다."""
        menu = Menu(listbox, tearoff=0)
        
        remove_cmd = lambda: self._remove_selected_from_list(listbox, full_paths, filenames_var, tab_type)
        menu.add_command(label="", command=remove_cmd)
        
        clear_cmd = lambda: self._clear_list(full_paths, filenames_var, tab_type)
        menu.add_command(label="", command=clear_cmd)
        
        def show_menu(event):
            d = self.lang_data
            menu.entryconfig(0, label=d['remove_selected'], state="normal" if listbox.curselection() else "disabled")
            menu.entryconfig(1, label=d['remove_all'], state="normal" if listbox.size() > 0 else "disabled")
            menu.post(event.x_root, event.y_root)
            
        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self._remove_selected_from_list(listbox, full_paths, filenames_var, tab_type))

    def _set_ui_state(self, widgets, state):
        """탭 내의 모든 컨트롤의 상태(활성화/비활성화)를 일괄 변경합니다."""
        for widget_name, widget in widgets.items():
            if widget_name in ['progress', 'status_label', 'output_entry']: 
                continue
            
            new_state = 'readonly' if isinstance(widget, ttk.Entry) and state == 'disabled' else state
            widget.config(state=new_state)

    def _reset_video_ui_state(self):
        """비디오 탭의 UI를 작업 대기 상태로 초기화합니다."""
        d = self.lang_data
        self._set_ui_state(self.video_widgets, 'normal')
        
        new_cmd = lambda: self.start_video_conversion(self.video_widgets['output_entry'].get())
        self.video_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=new_cmd)
        
        self.video_widgets['status_label'].config(text=d['status_idle'])
        self.video_widgets['progress']['value'] = 0

    def _reset_audio_ui_state(self):
        """오디오 탭의 UI를 작업 대기 상태로 초기화합니다."""
        d = self.lang_data
        self._set_ui_state(self.audio_widgets, 'normal')
        
        new_cmd = lambda: self.start_audio_conversion(self.audio_widgets['output_entry'].get(), self.audio_overwrite_var.get())
        self.audio_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=new_cmd)
        
        self.audio_widgets['status_label'].config(text=d['status_idle'])
        self.audio_widgets['progress']['value'] = 0

    # --- 파일/폴더 선택 및 목록 관리 헬퍼 함수들 ---
    def _on_dnd_drop(self, event, listbox, full_paths, filenames_var, tab_type):
        """드래그 앤 드롭 이벤트를 처리하여 파싱된 경로를 목록에 추가합니다."""
        if self.audio_widgets.get('action_btn', tk.Button).cget('state') == 'disabled': return # 실행 중 방지
        paths = self._parse_dnd_files(event.data)
        if not paths: return
        file_types = getattr(self.logic, f"supported_{tab_type}_extensions")
        self._add_paths_to_list(paths, file_types, full_paths, filenames_var, tab_type)

    def _parse_dnd_files(self, data):
        """TkinterDnD의 Drop 데이터를 파싱하여 리스트로 반환합니다."""
        try:
            return self.master.root.tk.splitlist(data) if hasattr(self.master, 'root') else self.tk.splitlist(data)
        except AttributeError:
            # Fallback parsing for curly braced paths
            import re
            return [p.strip() for p in re.findall(r'\{[^{}]*\}|[^ ]+', data) if p.strip()]

    def _select_files(self, file_types): 
        return list(filedialog.askopenfilenames(title=self.lang_data.get('dialog_select_files', '파일을 선택하세요'), filetypes=file_types) or [])
    
    def _select_folder_and_search(self, file_types):
        folder = filedialog.askdirectory(title=self.lang_data.get('dialog_select_folder', '폴더를 선택하세요'))
        if not folder: 
            return []
        
        exts = [ext.strip('*.') for _, p in file_types for ext in p.split()]
        found_files = []
        for r, _, fs in os.walk(folder):
            for f in fs:
                if any(f.lower().endswith(f".{ext}") for ext in exts):
                    found_files.append(str(Path(r) / f))
        return found_files
    
    def _select_output_folder(self, entry_widget):
        folder = filedialog.askdirectory(title=self.lang_data.get('dialog_select_output', '저장할 폴더를 선택하세요'))
        if folder:
            entry_widget.config(state='normal')
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder)
            entry_widget.config(state='readonly')

    def _update_listbox(self, fp, fv): 
        fv.set([os.path.basename(p) for p in fp])
        
    def _add_paths_to_list(self, new_paths, full_paths, tab_type, filenames_var):
        if not new_paths: 
            return
            
        unique_new_paths = [p for p in new_paths if p not in set(full_paths)]
        if not unique_new_paths:
            self._add_spacing(tab_type)
            self._add_log_entry(tab_type, 'alert_files_exist')
            self._add_spacing(tab_type)
            return
            
        full_paths.extend(unique_new_paths)
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_files_added', count=len(unique_new_paths))
        self._add_log_entry(tab_type, 'log_total_files', total=len(full_paths))
        self._add_spacing(tab_type)
        
    def _add_files(self, file_types, full_paths, filenames_var, tab_type): 
        self._add_paths_to_list(self._select_files(file_types), full_paths, tab_type, filenames_var)
        
    def _add_folder(self, file_types, full_paths, filenames_var, tab_type): 
        self._add_paths_to_list(self._select_folder_and_search(file_types), full_paths, tab_type, filenames_var)
        
    def _remove_selected_from_list(self, listbox, full_paths, filenames_var, tab_type):
        sel_idx = listbox.curselection()
        if not sel_idx: 
            return
        
        for i in sorted(sel_idx, reverse=True): 
            del full_paths[i]
            
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_files_removed', count=len(sel_idx))
        self._add_spacing(tab_type)
        
    def _clear_list(self, full_paths, filenames_var, tab_type):
        if not full_paths: 
            return
        
        count = len(full_paths)
        full_paths.clear()
        
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_all_files_removed', count=count)
        self._add_spacing(tab_type)

    # --- 변환 시작 로직 ---
    def start_video_conversion(self, output_dir):
        """비디오 변환 시작 (유효성 검사 및 FFmpeg 준비 단계 호출)."""
        if not self.video_full_paths:
            self._add_log_entry('video', 'error_no_files')
            return
        if not output_dir:
            self._add_log_entry('video', 'error_no_output_video')
            return
        self._start_ffmpeg_preparation(output_dir)

    def _start_ffmpeg_preparation(self, output_dir):
        """FFmpeg 다운로더를 실행하고, 완료되면 실제 변환을 시작합니다."""
        if not self.usmtoolkit_path:
            self._add_log_entry('video', 'ffmpeg_no_usm_path')
            return

        self._set_ui_state(self.video_widgets, 'disabled')
        self._add_log_entry('video', 'ffmpeg_preparing')
        
        download_future = self.ffmpeg_downloader.ensure_ffmpeg_ready()

        def check_ffmpeg_status(): # Future 객체를 폴링하여 다운로드 완료 확인
            if download_future.done():
                try:
                    if download_future.result(): 
                        self._start_actual_video_conversion(output_dir)
                    else: 
                        self._add_log_entry('video', 'ffmpeg_prepare_fail')
                        self._reset_video_ui_state()
                except Exception as e:
                    self._add_log_entry('video', 'ffmpeg_prepare_fail')
                    self._add_log_entry('video', 'conv_log_error_exception', error=e)
                    self._reset_video_ui_state()
            else: 
                self.after(100, check_ffmpeg_status)
                
        self.after(100, check_ffmpeg_status)
    
    def _start_actual_video_conversion(self, output_dir):
        """백그라운드 스레드에서 실제 비디오 변환 로직을 실행합니다."""
        self._add_spacing('video')
        self.cancel_event.clear()
        
        self.video_widgets['action_btn'].config(
            state='normal', 
            text=self.lang_data.get('cancel_conversion', 'Cancel'),
            command=self.cancel_event.set
        )
        
        thread = threading.Thread(
            target=self.logic.run_video_conversion, 
            daemon=True, 
            args=(self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.cancel_event)
        )
        thread.start()

    def start_audio_conversion(self, output_dir, overwrite):
        """오디오 변환 시작 (유효성 검사 및 백그라운드 스레드 실행)."""
        if not self.audio_full_paths: 
            self._add_log_entry('audio', 'error_no_files')
            return
        if not output_dir: 
            self._add_log_entry('audio', 'error_no_output_audio')
            return

        self._add_spacing('audio')
        self._set_ui_state(self.audio_widgets, 'disabled')
        self.cancel_event.clear()

        self.audio_widgets['action_btn'].config(
            state='normal', 
            text=self.lang_data.get('cancel_conversion', 'Cancel'),
            command=self.cancel_event.set
        )
        
        thread = threading.Thread(
            target=self.logic.run_audio_conversion, 
            daemon=True, 
            args=(self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.cancel_event)
        )
        thread.start()

    # --- 로그 큐 처리 및 UI 업데이트 로직 ---
    def _render_log_entry(self, timestamp, key, kwargs, last_ts=None):
        """로그 데이터를 포맷팅하여 실제 출력될 문자열로 만듭니다."""
        if key == 'spacing': 
            return "\n"

        # 언어 데이터 기반으로 메시지 생성
        content = ""
        if key == 'raw':
            content = kwargs.get('text', '')
        elif key == 'about_header':
            content = self.lang_data.get(key, '[ Program Information ]') + '\n'
        elif key == 'about_line_key':
            label_key = kwargs.get('label_key')
            label = self.lang_data.get(label_key, label_key)
            value = kwargs.get('value', '')
            content = self.lang_data.get('about_line', "  - {label}\t: {value}").format(label=label, value=value)
        else:
            template = self.lang_data.get(key)
            if template:
                try: 
                    content = template.format(**kwargs)
                except (KeyError, TypeError) as e: 
                    content = f"<{key}: formatting error {e}>"
            else: 
                content = f"<{key} not found in language data>"

        # 타임스탬프 포맷팅 (동일 시간대에는 생략)
        first_line_prefix = ""
        subsequent_line_prefix = ""
        if timestamp:
            if timestamp != last_ts: 
                first_line_prefix = f"[{timestamp}] "
            else: 
                first_line_prefix = " " * 13 # len("[HH:MM:SS.ms] ")
            subsequent_line_prefix = " " * 13
        
        lines = content.splitlines()
        if not lines: 
            if key not in ('about_line_key'):
                return first_line_prefix.rstrip() + '\n'
            else:
                return first_line_prefix.rstrip()

        processed_lines = [f"{first_line_prefix}{lines[0]}"]
        processed_lines.extend([f"{subsequent_line_prefix}{line}" for line in lines[1:]])
        
        final_message = '\n'.join(processed_lines)
        return final_message + '\n'
        
    def _add_log_entry(self, target_tab, log_key, **kwargs):
        self.log_queue.put(('log_entry', target_tab, log_key, kwargs))

    def _add_raw_log(self, target_tab, text, **kwargs):
        self.log_queue.put(('log_entry', target_tab, 'raw', {'text': text, **kwargs}))

    def _add_spacing(self, target_tab):
        self.log_queue.put(('log_spacing', target_tab))
    
    def _redraw_logs(self):
        """언어 변경 시, 저장된 로그 기록을 새 언어로 다시 렌더링합니다."""
        log_configs = [
            ('video', self.video_log_history, self.video_log_text),
            ('audio', self.audio_log_history, self.audio_log_text)
        ]
        for tab, history_list, log_widget in log_configs:
            log_widget.config(state='normal')
            log_widget.delete('1.0', tk.END)
            last_ts = None
            
            # 히스토리의 모든 로그를 순회하며 다시 그림
            block_ts_map = {} # (timestamp, key) 튜플을 키로 사용하여 블록을 식별
            for i, (timestamp, key, kwargs) in enumerate(history_list):
                # 타임스탬프가 있는 로그만 블록의 시작으로 간주
                if timestamp:
                    # 현재 로그와 이전 로그의 타임스탬프가 같고, 둘 다 블록의 일부인 경우 중복으로 간주
                    if i > 0 and timestamp == history_list[i-1][0] and key != 'raw' and history_list[i-1][1] != 'raw':
                         # 현재 블록의 시작 타임스탬프를 last_ts로 사용
                         render_ts = timestamp
                         last_ts_for_render = block_ts_map.get((timestamp, key), timestamp)
                    else:
                         render_ts = timestamp
                         last_ts_for_render = last_ts
                         # 새 블록의 시작으로 간주하고, 타임스탬프를 맵에 기록
                         block_ts_map[(timestamp, key)] = timestamp
                else:
                    render_ts = None
                    last_ts_for_render = last_ts
                
                message = self._render_log_entry(render_ts, key, kwargs, last_ts_for_render)
                log_widget.insert(tk.END, message)
                
                if render_ts: 
                    last_ts = render_ts

            self.last_log_timestamp[tab] = last_ts
            log_widget.config(state='disabled')
            log_widget.see(tk.END)

    def _process_log_queue(self):
        """주기적으로 로그 큐를 확인하여 UI를 업데이트하는 메인 루프입니다."""
        try:
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                msg_type = msg[0]

                # 진행률 또는 완료 신호 처리
                if msg_type.startswith(('progress', '__')):
                    if msg_type.startswith('progress'): 
                        self._handle_progress_update(msg)
                    else: 
                        self._handle_completion_signal(msg)
                    continue

                # 로그 메시지 처리
                target_tab, log_widget, history = (msg[1], self.video_log_text, self.video_log_history) if msg[1] == 'video' else (msg[1], self.audio_log_text, self.audio_log_history)
                log_widget.config(state='normal')

                if msg_type in ('log_entry', 'log_un-timestamped'):
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3] if msg_type == 'log_entry' else None
                    _, _, log_key, kwargs = msg
                    last_ts = self.last_log_timestamp[target_tab]
                    history.append((timestamp, log_key, kwargs))
                    log_widget.insert(tk.END, self._render_log_entry(timestamp, log_key, kwargs, last_ts))
                    if timestamp: 
                        self.last_log_timestamp[target_tab] = timestamp
                elif msg_type == 'log_spacing':
                    history.append((None, 'spacing', {}))
                    log_widget.insert(tk.END, '\n')
                elif msg_type == 'log_block':
                    _, _, log_entries = msg
                    block_timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    # 블록이 시작되기 전의 마지막 타임스탬프를 가져옴
                    last_ts_before_block = self.last_log_timestamp[target_tab]

                    for i, (l_key, l_kwargs) in enumerate(log_entries):
                        # 첫 번째 항목은 이전 블록의 타임스탬프와 비교
                        # 그 외 항목은 현재 블록의 타임스탬프와 비교하여 중복을 제거
                        last_ts_for_render = last_ts_before_block if i == 0 else block_timestamp
                        
                        history.append((block_timestamp, l_key, l_kwargs))
                        log_widget.insert(tk.END, self._render_log_entry(block_timestamp, l_key, l_kwargs, last_ts_for_render))

                    # 블록 전체가 처리된 후, 마지막 타임스탬프를 업데이트
                    if log_entries:
                        self.last_log_timestamp[target_tab] = block_timestamp
                
                log_widget.see(tk.END)
                log_widget.config(state='disabled')

        except queue.Empty: 
            pass
        finally: 
            self.after(100, self._process_log_queue)
    
    def _handle_progress_update(self, msg):
        """진행률 관련 큐 메시지를 처리하여 UI를 업데이트합니다."""
        d = self.lang_data
        msg_type, *args = msg
        
        if msg_type == 'progress_start':
            target_tab, total = args
            widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
            
            if target_tab == 'video': 
                self.video_total_files = total
            else: 
                self.audio_total_files = total
                
            widgets['progress'].config(maximum=total, value=0)
            widgets['status_label'].config(text=d['status_starting'].format(total=total))
            
        elif msg_type == 'progress_update':
            target_tab, value = args
            widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
            total = self.video_total_files if target_tab == 'video' else self.audio_total_files
            
            widgets['progress']['value'] = value
            widgets['status_label'].config(text=d['status_processing'].format(current=value, total=total))
    
    def _handle_completion_signal(self, msg):
        """작업 완료 신호를 처리하여 UI를 최종 상태로 업데이트합니다."""
        d = self.lang_data
        msg_type, = msg
        
        if msg_type == '__VIDEO_DONE__':
            widgets = self.video_widgets
            total = self.video_total_files
            current = widgets['progress']['value']
            
            widgets['status_label'].config(text=d['status_complete'].format(current=current, total=total))
            self._reset_video_ui_state()
            
        elif msg_type == '__AUDIO_DONE__':
            widgets = self.audio_widgets
            total = self.audio_total_files
            current = widgets['progress']['value']
            
            widgets['status_label'].config(text=d['status_complete'].format(current=current, total=total))
            self._reset_audio_ui_state()
