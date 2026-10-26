"""유니티 변환기(Unity Converter) 프레젠테이션 뷰 모듈.

파일 관리, 에셋 카테고리 필터, 색상 구분 로그 콘솔,
배치 진행률 추적 UI를 포함하는 3분할 그래픽 인터페이스 구성 및 관리.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import PanedWindow, Scrollbar, Text, font, ttk
from typing import TYPE_CHECKING, Any

from tkinterdnd2 import DND_FILES  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from .controller import AssetExtractorController


class AssetExtractorView(ttk.Frame):
    """유니티 변환기 탭의 3분할 레이아웃 관리 프레젠테이션 뷰.

    구성 요소:
    - 좌측 패널: 파일/폴더 추가 버튼 및 드래그 앤 드롭 지원 파일 목록(Listbox).
    - 중앙 패널: 추출 대상 에셋 유형 필터 체크박스 목록(스크롤 지원).
    - 우측 패널: 색상 태그 지원 ScrolledText 로그 콘솔 및 진행률 표시줄.
    - 하단 툴바: 출력 대상 디렉터리 경로 선택, 유니티 엔진 버전 드롭다운, 시작/취소 토글 버튼.

    Attributes:
        controller: 이벤트 처리 및 백그라운드 작업 조율 담당 MVC 컨트롤러.
        file_listbox: 추출 대상 후보 번들 파일 목록 표시 위젯.
        log_text: 실행 로그 메시지 출력용 Scrolled Text 위젯.
        progress_bar: 추출 파일 수 기반 진행률 표시줄.
        output_entry: 선택된 출력 폴더 경로 표시 읽기 전용 엔트리 위젯.
        version_combo: 유니티 엔진 프리셋 버전 선택 또는 직접 입력 전환 콤보박스.
        version_entry: '직접 입력' 선택 시 활성화되는 유니티 버전 입력 엔트리.
        start_button: 시작/취소 상태 토글 버튼.
    """

    def __init__(self, master: ttk.Frame, controller: AssetExtractorController) -> None:
        """AssetExtractorView 컨테이너 초기화 및 위젯 생성.

        Args:
            master: 부모 컨테이너 프레임.
            controller: 사용자 상호작용 및 추출 작업 제어 컨트롤러.
        """
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self._type_group_labels: dict[str, ttk.Label] = {}
        self.setup_ui()

    def setup_ui(self) -> None:
        """3분할 PanedWindow 기반 전체 UI 위젯 생성 및 배치."""
        main_paned_window = PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 1. 좌측 패널: 파일 선택 및 목록 위젯
        left_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(left_pane, width=240)

        self.open_frame = ttk.LabelFrame(left_pane, text="")
        self.open_frame.pack(fill=tk.X, pady=(0, 5))
        self.btn_open_file = ttk.Button(self.open_frame, text="", command=self.controller.select_files)
        self.btn_open_file.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 2), pady=5)
        self.btn_open_folder = ttk.Button(self.open_frame, text="", command=self.controller.select_folder)
        self.btn_open_folder.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 5), pady=5)

        self.list_frame = ttk.LabelFrame(left_pane, text="")
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(self.list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.file_listbox = tk.Listbox(self.list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<Delete>", self.controller.remove_selected_files)

        try:
            self.file_listbox.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.file_listbox.dnd_bind('<<Drop>>', self.controller.on_dnd_drop)  # type: ignore[attr-defined]
        except (tk.TclError, RuntimeError):
            pass

        # 2. 중앙 패널: 에셋 유형 필터 체크박스 목록
        center_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(center_pane, width=200)
        self._build_type_filter_panel(center_pane)

        # 3. 우측 패널: 색상 태그 지원 로그 콘솔 및 진행률 표시줄
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
        self.log_text = Text(log_text_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state=tk.DISABLED, padx=5, pady=5)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_scrollbar.config(command=self.log_text.yview)

        # 로그 스타일 지정을 위한 색상 태그 설정
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", background="#FFF3CD", foreground="#856404")
        self.log_text.tag_config("ERROR", background="#F8D7DA", foreground="#721C24")
        self.log_text.tag_config("SUCCESS", background="#D4EDDA", foreground="#155724")

        progress_info_frame = ttk.Frame(self.log_frame)
        progress_info_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))
        progress_info_frame.grid_columnconfigure(1, weight=1)
        self.progress_label = ttk.Label(progress_info_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.progress_bar = ttk.Progressbar(progress_info_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.grid(row=0, column=1, sticky='ew')

        # 4. 하단 툴바: 출력 대상 경로, 유니티 엔진 버전 및 실행 버튼
        bottom_controls_frame = ttk.Frame(self)
        bottom_controls_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom_controls_frame.grid_columnconfigure(0, weight=1)
        self.output_frame = ttk.LabelFrame(bottom_controls_frame, text="")
        self.output_frame.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.output_entry = ttk.Entry(self.output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(self.output_frame, text="", command=self.controller.select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)

        self.version_frame = ttk.LabelFrame(bottom_controls_frame, text="")
        self.version_frame.grid(row=0, column=1, sticky='ns', padx=(0, 10))

        self.version_combo = ttk.Combobox(self.version_frame, textvariable=self.controller.version_combo_var, state='readonly', width=18)
        self.version_combo.pack(side=tk.LEFT, padx=(5, 2), pady=5)
        self.version_combo.bind("<<ComboboxSelected>>", self.controller.on_version_selection_change)

        self.version_entry = ttk.Entry(self.version_frame, textvariable=self.controller.unity_version_var, width=18, state=tk.DISABLED)
        self.version_entry.pack(side=tk.LEFT, padx=(2, 5), pady=5)

        self.start_button_container = ttk.LabelFrame(bottom_controls_frame, text="")
        self.start_button_container.grid(row=0, column=2, sticky='ns')
        self.start_button = ttk.Button(self.start_button_container, text="", command=self.controller.start_extraction)
        self.start_button.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 파일 목록 우클릭 컨텍스트 메뉴
        self.listbox_menu = tk.Menu(self, tearoff=0)
        self.listbox_menu.add_command(label="", command=self.controller.remove_selected_files)
        self.listbox_menu.add_command(label="", command=self.controller.remove_all_files)
        self.listbox_menu.add_separator()
        self.listbox_menu.add_command(label="", command=self.controller.open_asset_browser)

        self.file_listbox.bind("<Button-3>", self._show_listbox_menu)
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu)

    def _show_listbox_menu(self, event: Any) -> None:
        """파일 목록 우클릭 컨텍스트 메뉴 표시.

        Args:
            event: Tkinter 마우스 클릭 이벤트 객체.
        """
        if self.controller.is_running:
            return
        d = self.controller.get_lang_dict()
        has_selection = bool(self.file_listbox.curselection())
        self.listbox_menu.entryconfig(0, state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.entryconfig(1, state=tk.NORMAL if self.controller.file_paths else tk.DISABLED)
        self.listbox_menu.entryconfig(3, label=d.get('browse_assets_menu', 'Browse Assets'), state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)

    def _build_type_filter_panel(self, parent: ttk.Frame) -> None:
        """에셋 유형 필터링을 위한 스크롤 가능 체크박스 그룹 생성.

        Args:
            parent: 필터 패널 배치 부모 컨테이너 프레임.
        """
        self.filter_frame = ttk.LabelFrame(parent, text="")
        self.filter_frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(self.filter_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=(5, 2))
        self.btn_select_all = ttk.Button(btn_frame, text="", command=self.controller.select_all_types)
        self.btn_select_all.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        self.btn_deselect_all = ttk.Button(btn_frame, text="", command=self.controller.deselect_all_types)
        self.btn_deselect_all.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 0))

        canvas = tk.Canvas(self.filter_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.filter_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.filter_inner_frame = ttk.Frame(canvas)

        self.filter_inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.filter_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # 캔버스 및 내부 프레임 대상 마우스 휠 이벤트 직접 바인딩(bind_all 미사용)
        canvas.bind("<MouseWheel>", _on_mousewheel)
        self.filter_inner_frame.bind("<MouseWheel>", _on_mousewheel)

        # 내부 프레임의 자식 위젯 대상 마우스 휠 이벤트 전파 바인딩
        def _bind_to_children(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                child.bind("<MouseWheel>", _on_mousewheel)
                _bind_to_children(child)

        # 위젯 생성 완료 대기를 위해 100ms 지연 후 바인딩 실행
        self.after(100, lambda: _bind_to_children(self.filter_inner_frame))

        categories = [
            ("filter_group_textures", ["Texture2D", "Sprite", "Texture2DArray"]),
            ("filter_group_media", ["AudioClip", "MovieTexture", "VideoClip"]),
            ("filter_group_resources", ["TextAsset", "MonoBehaviour", "AnimationClip", "Mesh", "Shader", "Font", "Material"]),
            ("filter_group_components", sorted(self.controller.asset_skip_types) + ["_OTHER_"]),
        ]

        default_enabled = self.controller.asset_default_enabled
        is_first_group = True

        for group_key, type_list in categories:
            if not is_first_group:
                ttk.Separator(self.filter_inner_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 0))
            is_first_group = False

            bold_font = font.Font(font="TkDefaultFont", weight="bold")
            group_label = ttk.Label(self.filter_inner_frame, text="", font=bold_font)
            group_label.pack(anchor="w", pady=(4, 1))
            self._type_group_labels[group_key] = group_label

            for type_name in type_list:
                var = tk.BooleanVar(value=(type_name in default_enabled))
                self.controller.asset_type_vars[type_name] = var
                display_name = type_name
                if type_name == "_OTHER_":
                    display_name = "Other (Generic JSON)"
                cb = ttk.Checkbutton(self.filter_inner_frame, text=display_name, variable=var)
                cb.pack(anchor="w", padx=(12, 0))

    def update_ui_text(self) -> None:
        """현재 활성화된 다국어 사전을 적용하여 모든 정적 라벨, 버튼, 메뉴 텍스트 갱신."""
        d = self.controller.get_lang_dict()

        self.btn_open_file.config(text=d.get('file_open', 'Open Files'))
        self.btn_open_folder.config(text=d.get('folder_open', 'Open Folder'))

        self.list_frame.config(text=d.get('file_list', 'File List'))
        self.log_frame.config(text=d.get('log_history', 'Extraction Logs'))
        self.output_frame.config(text=d.get('output_folder', 'Output Folder'))
        self.open_frame.config(text=d.get('open_frame_title', 'Open'))
        self.version_frame.config(text=d.get('unity_version_label', 'Unity Version:'))

        manual_label = d.get('version_manual_input', 'Manual Input')
        combo_values = self.controller.UNITY_VERSION_PRESETS + [manual_label]
        self.version_combo['values'] = combo_values
        current = self.controller.version_combo_var.get()
        if current not in self.controller.UNITY_VERSION_PRESETS:
            self.controller.version_combo_var.set(manual_label)

        self.output_button.config(text=d.get('browse', 'Browse...'))
        self.start_button_container.config(text=d.get('run', 'Start Process'))

        if not self.controller.is_running:
            self.start_button.config(text=d.get('start_extraction', 'Start Process'))
        else:
            self.start_button.config(text=d.get('cancel_extraction', 'Cancel Extraction'))

        self.listbox_menu.entryconfig(0, label=d.get('remove_selected', 'Remove Selected'))
        self.listbox_menu.entryconfig(1, label=d.get('remove_all', 'Remove All'))

        self.filter_frame.config(text=d.get('filter_panel_title', 'Asset Type Filter'))
        self.btn_select_all.config(text=d.get('select_all', 'Select All'))
        self.btn_deselect_all.config(text=d.get('deselect_all', 'Deselect All'))
        for key, label_widget in self._type_group_labels.items():
            label_widget.config(text=d.get(key, key))

        self.update_progress_bar()

    def update_progress_bar(self) -> None:
        """컨트롤러의 현재 진행 상태를 기반으로 진행률 표시줄 및 상태 텍스트 동기화."""
        d = self.controller.get_lang_dict()
        if self.controller.is_running and self.controller.file_paths:
            total_files = len(self.controller.file_paths)
            self.progress_label.config(text=f"{d.get('progress', 'Progress: ')}{self.controller.processed_files_count} / {total_files}")
            self.progress_bar['value'] = self.controller.processed_files_count
        else:
            self.progress_bar['value'] = 0
            self.progress_label.config(text=f"{d.get('progress', 'Progress: ')}{d.get('waiting', 'Waiting')}")

    def toggle_controls(self, enabled: bool) -> None:
        """대기 상태와 작업 실행 상태 간 위젯 조작 가능 여부 토글.

        추출 실행 중(비활성화)에는 시작 버튼의 명령을 취소 토큰 트리거로 전환하고,
        입력 및 버전 제어 위젯 비활성화.

        Args:
            enabled: 편집/가져오기 컨트롤 활성화 여부(True: 활성화, False: 실행 중 잠금).
        """
        state = 'normal' if enabled else 'disabled'
        self.update_ui_text()
        if not enabled:
            self.start_button.config(command=self.controller.cancel_token.cancel)
        else:
            self.start_button.config(command=self.controller.start_extraction)

        self.output_button.config(state=state)
        self.btn_open_file.config(state=state)
        self.btn_open_folder.config(state=state)
        self.version_combo.config(state='readonly' if enabled else 'disabled')
        if enabled:
            current = self.controller.version_combo_var.get()
            is_manual = current not in self.controller.UNITY_VERSION_PRESETS
            self.version_entry.config(state=tk.NORMAL if is_manual else 'disabled')
        else:
            self.version_entry.config(state=tk.DISABLED)
        self.btn_select_all.config(state=state)
        self.btn_deselect_all.config(state=state)
        for widget in self.filter_inner_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)

    def set_version_entry_state(self, state: str, focus: bool = False) -> None:
        """유니티 버전 수동 입력 엔트리의 활성화/비활성화 상태 갱신.

        Args:
            state: Tkinter 상태 상수('normal' 또는 'disabled').
            focus: True 전달 시 엔트리로 키보드 포커스 이동.
        """
        self.version_entry.config(state=state)
        if focus:
            self.version_entry.focus_set()
