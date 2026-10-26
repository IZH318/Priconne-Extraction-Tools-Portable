"""AV Converter 탭의 Tkinter GUI 뷰 모듈.

비디오(.usm) 탭과 오디오(.awb/.acb/.hca) 탭으로 분리된 2단 Notebook 인터페이스,
드래그 앤 드롭 지원 파일 리스트박스, 실시간 다국어 로그 ScrolledText, 진행률 바,
다중 스트림 선택 모달 팝업(Treeview) 및 상태 제어 위젯 렌더링.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import Listbox, Menu, filedialog, scrolledtext, ttk
from typing import TYPE_CHECKING, Any

from tkinterdnd2 import DND_FILES  # type: ignore[import-untyped]

from src.constants import TabType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .controller import AVConverterController


class AVConverterView(ttk.Frame):
    """AV Converter의 그래픽 사용자 인터페이스(View) 클래스.

    ttk.Notebook 기반으로 오디오 탭과 비디오 탭을 분리 구성하며,
    각 탭마다 파일 추가/DnD 목록, 출력 폴더 지정, 로그 뷰어, 진행 상태 위젯 및
    우클릭 컨텍스트 메뉴(삭제, 전체 삭제, 미리보기) 제공.

    Attributes:
        controller (AVConverterController): 상위 컨트롤러 인스턴스.
        audio_widgets (dict[str, Any]): 오디오 탭 주요 제어 위젯 맵.
        video_widgets (dict[str, Any]): 비디오 탭 주요 제어 위젯 맵.
        audio_ui_elements (dict[str, str]): 오디오 탭 다국어 갱신 대상 라벨 키 맵.
        video_ui_elements (dict[str, str]): 비디오 탭 다국어 갱신 대상 라벨 키 맵.
        audio_filenames_var (tk.StringVar): 오디오 파일 목록 표시용 문자열 변수.
        video_filenames_var (tk.StringVar): 비디오 파일 목록 표시용 문자열 변수.
        audio_overwrite_var (tk.BooleanVar): 오디오 파일 덮어쓰기 여부 불리언 변수.
    """

    def __init__(self, master: ttk.Frame, controller: AVConverterController) -> None:
        """AVConverterView 인스턴스 초기화 및 UI 컴포넌트 빌드.

        Args:
            master (ttk.Frame): 상위 탭 컨테이너 프레임.
            controller (AVConverterController): 이벤트 및 상태 제어 컨트롤러.
        """
        super().__init__(master)
        self.controller: AVConverterController = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.audio_widgets: dict[str, Any] = {}
        self.video_widgets: dict[str, Any] = {}
        self.audio_ui_elements: dict[str, str] = {}
        self.video_ui_elements: dict[str, str] = {}
        self.audio_filenames_var = tk.StringVar()
        self.video_filenames_var = tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """탭 노트북 및 기본 뷰 레이아웃 구성."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.audio_tab = ttk.Frame(self.notebook)
        self.video_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.audio_tab, text=self.controller.get_lang_dict().get('audio_tab', 'Audio (.awb → .wav)'))
        self.notebook.add(self.video_tab, text=self.controller.get_lang_dict().get('video_tab', 'Video (.usm → .mp4)'))

        self.audio_widgets, self.audio_log_text, self.audio_ui_elements = self._build_conversion_tab_ui(self.audio_tab, 'audio', self.audio_filenames_var)
        self.video_widgets, self.video_log_text, self.video_ui_elements = self._build_conversion_tab_ui(self.video_tab, 'video', self.video_filenames_var)

    def update_ui_text(self) -> None:
        """현재 선택된 언어로 UI 텍스트 갱신."""
        d = self.controller.get_lang_dict()
        self.notebook.tab(self.audio_tab, text=d.get('audio_tab', 'Audio (.awb → .wav)'))
        self.notebook.tab(self.video_tab, text=d.get('video_tab', 'Video (.usm → .mp4)'))

        elem_defaults = {
            'log_frame_container': 'Processing Logs',
            'input_frame': 'Select Files',
            'list_container': 'File List',
            'output_frame': 'Output Folder',
            'action_frame': 'Start Process',
        }

        for tab_type, widgets, ui_elements in [
            ('audio', self.audio_widgets, self.audio_ui_elements),
            ('video', self.video_widgets, self.video_ui_elements),
        ]:
            is_converting = self.controller.is_converting(tab_type)  # type: ignore[arg-type]
            for elem_key, lang_key in ui_elements.items():
                w = getattr(self, f'{tab_type}_ui_{elem_key}', None)
                if w:
                    w.config(text=d.get(lang_key, elem_defaults.get(elem_key, '')))
            widgets['add_files_btn'].config(text=d.get('add_files', 'Open Files'))
            widgets['add_folder_btn'].config(text=d.get('add_folder', 'Open Folder'))
            widgets['browse_btn'].config(text=d.get('browse', 'Browse...'))

            if is_converting:
                widgets['action_btn'].config(text=d.get('cancel_conversion', 'Cancel Conversion'))
            else:
                widgets['action_btn'].config(text=d.get('start_conversion', 'Start Process'))
                widgets['status_label'].config(text=d.get('status_idle', 'Status: Idle'))

            if 'overwrite_check' in widgets:
                widgets['overwrite_check'].config(text=d.get('overwrite_option', 'Overwrite existing files'))

    def _build_conversion_tab_ui(self, parent_tab: ttk.Frame, tab_type: TabType, filenames_var: tk.StringVar) -> tuple[dict, scrolledtext.ScrolledText, dict]:
        """탭 유형별(비디오/오디오) 2열 분할 레이아웃 및 제어 위젯 생성.

        Args:
            parent_tab: 부모 탭 컨테이너 프레임.
            tab_type: 탭 식별자 ('video' 또는 'audio').
            filenames_var: 파일 목록 연동 StringVar.

        Returns:
            위젯 사전, 스크롤 텍스트 위젯, 다국어 갱신 요소 맵 튜플.
        """
        d = self.controller.get_lang_dict()
        is_audio_tab = (tab_type == 'audio')

        main_bottom_controls_frame = ttk.Frame(parent_tab)
        main_bottom_controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=5)

        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(left_pane_frame, weight=1)

        right_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(right_pane_frame, weight=3)

        input_frame = ttk.LabelFrame(left_pane_frame, text=d.get('input_section', 'Select Files'))
        input_frame.pack(fill=tk.X, pady=5, padx=5)

        input_frame.columnconfigure(0, weight=1, uniform='btn')
        input_frame.columnconfigure(1, weight=1, uniform='btn')

        add_files_btn = ttk.Button(input_frame, text=d.get('add_files', 'Open Files'), command=lambda: self.controller.add_files_cmd(tab_type))
        add_files_btn.grid(row=0, column=0, padx=(5, 2), pady=5, sticky='ew')

        add_folder_btn = ttk.Button(input_frame, text=d.get('add_folder', 'Open Folder'), command=lambda: self.controller.add_folder_cmd(tab_type))
        add_folder_btn.grid(row=0, column=1, padx=(2, 5), pady=5, sticky='ew')

        list_container = ttk.LabelFrame(left_pane_frame, text=d.get('file_list_section', 'File List'))
        list_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        try:
            getattr(listbox, "drop_target_register", lambda *a: None)(DND_FILES)
            getattr(listbox, "dnd_bind", lambda *a: None)('<<Drop>>', lambda e, lb=listbox, tt=tab_type: self.controller.on_dnd_drop(e, lb, tt))
        except (RuntimeError, tk.TclError) as ex:
            self.controller.log_system_message(tab_type, f"Drag & Drop disabled: {ex}\n")
            logger.debug("Failed to initialize Drag & Drop on listbox: %s", ex)

        self._create_right_click_menu(listbox, tab_type)

        log_frame_container = ttk.LabelFrame(right_pane_frame, text=d.get('log_section', 'Processing Log'))
        log_frame_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state=tk.DISABLED, font=("TkFixedFont", 10), padx=5, pady=5)
        log_text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5,0))

        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(2,5))

        status_label = ttk.Label(status_frame, text=d.get('status_idle', 'Status: Idle'))
        status_label.pack(side=tk.LEFT)

        progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode='determinate')
        progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5,0))

        action_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d.get('action_section', 'Start Process'))
        action_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        output_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d.get('output_section', 'Output Folder'))
        output_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        browse_btn = ttk.Button(output_frame, text=d.get('browse', 'Browse...'), command=lambda: self._select_output_folder(output_entry))
        browse_btn.pack(side=tk.LEFT, padx=5, pady=5)

        action_button = ttk.Button(action_frame, text=d.get('start_conversion', 'Start Process'))

        widgets_dict = {
            'action_btn': action_button, 'add_files_btn': add_files_btn,
            'add_folder_btn': add_folder_btn, 'output_entry': output_entry,
            'progress': progress_bar, 'status_label': status_label,
            'browse_btn': browse_btn, 'listbox': listbox
        }

        ui_elements_references = {
            'log_frame_container': log_frame_container, 'input_frame': input_frame,
            'list_container': list_container, 'output_frame': output_frame,
            'action_frame': action_frame
        }
        ui_elements_for_lang_update = {
            'log_frame_container': 'log_section', 'input_frame': 'input_section',
            'list_container': 'file_list_section', 'output_frame': 'output_section',
            'action_frame': 'action_section'
        }
        for key, widget in ui_elements_references.items():
            setattr(self, f"{tab_type}_ui_{key}", widget)

        if is_audio_tab:
            action_button.pack(side=tk.LEFT, pady=5, padx=5)
            overwrite_check = ttk.Checkbutton(action_frame, text=d.get('overwrite_option', 'Overwrite existing files'), variable=self.audio_overwrite_var)
            overwrite_check.pack(side=tk.LEFT, pady=5, padx=10)
            action_button.config(command=lambda: self.controller.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get()))
            widgets_dict['overwrite_check'] = overwrite_check
        else:
            action_button.pack(fill=tk.X, pady=5, padx=5)
            action_button.config(command=lambda: self.controller.start_video_conversion(output_entry.get()))

        return widgets_dict, log_text_widget, ui_elements_for_lang_update

    def _select_output_folder(self, entry_widget: ttk.Entry) -> None:
        """출력 폴더 선택 대화상자 표시 및 엔트리 위젯 반영."""
        folder = filedialog.askdirectory(title=self.controller.get_lang_dict().get('dialog_select_output', 'Select an output folder'))
        if folder:
            entry_widget.config(state=tk.NORMAL)
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder)
            entry_widget.config(state='readonly')

    def _create_right_click_menu(self, listbox: Listbox, tab_type: TabType) -> None:
        """파일 목록 리스트박스 우클릭 컨텍스트 메뉴 생성 및 이벤트 바인딩."""
        menu = Menu(listbox, tearoff=0)
        menu.add_command(label="", command=lambda: self.controller.remove_selected_from_list(listbox, tab_type))
        menu.add_command(label="", command=lambda: self.controller.clear_list(tab_type))
        menu.add_separator()
        menu.add_command(label="", command=lambda: self.controller.preview_selected(listbox, tab_type))

        def show_menu(event: Any) -> None:
            if self.controller.is_converting(tab_type):
                return
            d = self.controller.get_lang_dict()
            menu.entryconfig(0, label=d.get('remove_selected', 'Remove Selected'), state=tk.NORMAL if listbox.curselection() else "disabled")
            menu.entryconfig(1, label=d.get('remove_all', 'Remove All'), state=tk.NORMAL if listbox.size() > 0 else "disabled")
            menu.entryconfig(3, label=d.get('preview_menu', 'Preview'), state=tk.NORMAL if listbox.curselection() else "disabled")
            menu.post(event.x_root, event.y_root)

        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self.controller.remove_selected_from_list(listbox, tab_type) if not self.controller.is_converting(tab_type) else None)

    def create_progress_popup(self, width: int = 360, height: int = 105) -> tk.Toplevel:
        """변환 및 미리보기 진행 중 표시할 모달 대기 팝업 창 생성 및 반환."""
        d = self.controller.get_lang_dict()
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title(d.get('preview_menu', 'Preview'))
        sx, sy = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f'{width}x{height}+{sx // 2 - width // 2}+{sy // 2 - height // 2}')
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        popup.resizable(False, False)
        main_frame = ttk.Frame(popup, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text=d.get('preview_converting', 'Converting...'), anchor="center", justify="center").pack(fill=tk.X, pady=(10, 12))
        progress = ttk.Progressbar(main_frame, mode='indeterminate')
        progress.pack(fill=tk.X, padx=15, pady=(0, 10))
        progress.start(15)
        popup.deiconify()
        return popup

    def destroy_popup_safely(self, popup: tk.Toplevel) -> None:
        """모달 팝업 창 안전 파기."""
        try:
            popup.destroy()
        except tk.TclError:
            pass

    def show_track_selector(self, stream_count: int, stream_map_builder: Any, on_double_click_callback: Any) -> None:
        """다중 오디오 스트림 선택용 모달 Treeview 팝업 창 표시."""
        d = self.controller.get_lang_dict()
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title(d.get('preview_track_title', 'Select Track'))
        win_w, win_h = 450, 400
        sx, sy = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f'{win_w}x{win_h}+{sx // 2 - win_w // 2}+{sy // 2 - win_h // 2}')
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        popup.deiconify()

        frame = ttk.Frame(popup)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('num', 'name')
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        tree.heading('num', text=d.get('preview_track_col_num', '#'))
        tree.heading('name', text=d.get('preview_track_col_name', 'Track Name'), anchor='w')
        tree.column('num', width=80, minwidth=60, stretch=False, anchor='center')
        tree.column('name', width=400, minwidth=200, stretch=True, anchor='w')

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill=tk.X, pady=5)
        cancel_btn = ttk.Button(btn_frame, text=d.get('cancel', 'Cancel'), command=popup.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        stream_map_builder(tree)

        def on_double_click(event: Any) -> None:
            on_double_click_callback(tree)

        tree.bind('<Double-Button-1>', on_double_click)

    def set_ui_state(self, tab_type: TabType, state: str) -> None:
        """지정된 탭의 조작 컨트롤 위젯 상태(normal/disabled) 일괄 설정."""
        widgets = self.video_widgets if tab_type == 'video' else self.audio_widgets
        for widget_name, widget in widgets.items():
            if widget_name in ['progress', 'status_label', 'output_entry', 'listbox']:
                continue
            try:
                new_state = 'readonly' if isinstance(widget, ttk.Entry) and state == 'disabled' else state
                widget.config(state=new_state)
            except tk.TclError:
                pass

    def reset_ui_state(self, tab_type: TabType, reset_status: bool = False) -> None:
        """작업 완료 또는 취소 후 지정된 탭의 UI 컨트롤 및 버튼 상태 초기화."""
        d = self.controller.get_lang_dict()
        widgets = self.video_widgets if tab_type == 'video' else self.audio_widgets
        self.set_ui_state(tab_type, 'normal')

        if tab_type == 'video':
            def new_cmd() -> Any:
                return self.controller.start_video_conversion(widgets['output_entry'].get())
        else:
            def new_cmd() -> Any:
                return self.controller.start_audio_conversion(widgets['output_entry'].get(), self.audio_overwrite_var.get())

        widgets['action_btn'].config(text=d.get('start_conversion', 'Start Process'), state=tk.NORMAL, command=new_cmd)
        if reset_status:
            widgets['status_label'].config(text=d.get('status_idle', 'Status: Idle'))
            widgets['progress']['value'] = 0
