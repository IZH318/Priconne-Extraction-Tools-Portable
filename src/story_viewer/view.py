from __future__ import annotations
import tkinter as tk
from tkinter import ttk, font
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import StoryViewerController


class StoryViewerView(ttk.Frame):
    def __init__(self, master: ttk.Frame, controller: StoryViewerController) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.setup_ui()
        self.setup_text_tags()

    def setup_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        
        left_weight, right_weight = 35, 65

        left_pane = ttk.Frame(self.paned_window)
        self.paned_window.add(left_pane, weight=left_weight)

        self.open_frame = ttk.LabelFrame(left_pane, text="")
        self.open_frame.pack(fill=tk.X, pady=(0, 5))
        self.btn_open_file = ttk.Button(self.open_frame, text="", command=self.controller.open_files)
        self.btn_open_file.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 2), pady=5)
        self.btn_open_folder = ttk.Button(self.open_frame, text="", command=self.controller.open_folder)
        self.btn_open_folder.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 5), pady=5)


        self.left_group = ttk.LabelFrame(left_pane, text="")
        self.left_group.pack(fill=tk.BOTH, expand=True)

        self.options_frame = ttk.Frame(self.left_group)
        self.options_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        self.options_frame.columnconfigure(1, weight=1)
        
        # Row 0: Server selection
        self.server_label = ttk.Label(self.options_frame, text="")
        self.server_label.grid(row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 5))
        
        self.server_frame = ttk.Frame(self.options_frame)
        self.server_frame.grid(row=0, column=1, sticky="w", pady=(0, 5))
        self.jp_radio = ttk.Radiobutton(self.server_frame, text="", variable=self.controller.server_var, value="JP", command=self.controller.on_server_change, state=tk.DISABLED)
        self.jp_radio.pack(side=tk.LEFT, padx=(0, 5))
        self.kr_radio = ttk.Radiobutton(self.server_frame, text="", variable=self.controller.server_var, value="KR", command=self.controller.on_server_change, state=tk.DISABLED)
        self.kr_radio.pack(side=tk.LEFT, padx=(5, 0))
        
        # Row 1: Display mode selection
        self.display_mode_label = ttk.Label(self.options_frame, text="")
        self.display_mode_label.grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(0, 5))
        
        self.display_mode_combo = ttk.Combobox(self.options_frame, state=tk.DISABLED)
        self.display_mode_combo.grid(row=1, column=1, sticky="ew", pady=(0, 5))
        self.display_mode_combo.bind("<<ComboboxSelected>>", self.controller.on_display_mode_change)
        
        self.search_button = ttk.Button(self.left_group, text="", command=self.controller.open_search_window, state=tk.DISABLED)
        self.search_button.pack(fill=tk.X, padx=5, pady=(5, 3))

        # 인라인 빠른 필터 프레임
        self.filter_frame = ttk.Frame(self.left_group)
        self.filter_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.filter_entry = ttk.Entry(self.filter_frame, textvariable=self.controller.filter_var)
        self.filter_entry.pack(fill=tk.X, expand=True)
        self.filter_entry.bind("<Escape>", lambda e: self.controller.clear_filter())
        
        list_scrollbar = ttk.Scrollbar(self.left_group, orient=tk.VERTICAL)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        self.file_listbox = tk.Listbox(self.left_group, selectmode=tk.SINGLE, yscrollcommand=list_scrollbar.set)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=(0, 5))
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<<ListboxSelect>>", self.controller.on_file_select)
        
        right_pane = ttk.Frame(self.paned_window)
        self.paned_window.add(right_pane, weight=right_weight)
        
        self.detail_options_group = ttk.LabelFrame(right_pane, text="")
        self.detail_options_group.pack(fill=tk.X, pady=(0, 5))
        self.view_mode_combo = ttk.Combobox(self.detail_options_group, state="readonly")
        self.view_mode_combo.pack(fill=tk.X, padx=5, pady=7)
        self.view_mode_combo.bind("<<ComboboxSelected>>", self.controller.on_view_mode_change)
        
        self.right_group = ttk.LabelFrame(right_pane, text="")
        self.right_group.pack(fill=tk.BOTH, expand=True)
        text_scrollbar = ttk.Scrollbar(self.right_group, orient=tk.VERTICAL)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.story_text = tk.Text(self.right_group, wrap=tk.WORD, state=tk.DISABLED, spacing1=2, padx=10, pady=10, yscrollcommand=text_scrollbar.set)
        self.story_text.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        text_scrollbar.config(command=self.story_text.yview)

        self.bottom_frame = ttk.Frame(self)
        self.bottom_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        
        self.status_bar = ttk.Label(self.bottom_frame, text="", anchor=tk.W, padding=5)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.btn_export = ttk.Button(self.bottom_frame, text="", command=self.controller.open_export_window, state=tk.DISABLED)
        self.btn_export.pack(side=tk.RIGHT, padx=(5, 0))

        self.btn_copy = ttk.Button(self.bottom_frame, text="", command=self.controller.copy_script_to_clipboard, state=tk.DISABLED)
        self.btn_copy.pack(side=tk.RIGHT, padx=(5, 0))
        
        def reapply_weights(event=None):
            try:
                total_width = self.paned_window.winfo_width()
                sash_position = int(total_width * left_weight / (left_weight + right_weight))
                self.paned_window.sashpos(0, sash_position)
                self.paned_window.unbind("<Configure>")
            except tk.TclError: pass
        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self) -> None:
        default_font_family = font.nametofont("TkDefaultFont").cget("family")
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A')
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000')
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')

        # 대본 모드(script) 전용 폰트 및 컬러 태그
        self.story_text.tag_configure('script_title', font=(default_font_family, 13, 'bold'), foreground='#1A365D')
        self.story_text.tag_configure('script_speaker', font=(default_font_family, 11, 'bold'), foreground='#0D5C75')
        self.story_text.tag_configure('script_dialogue', font=(default_font_family, 11), foreground='#1A202C')
        self.story_text.tag_configure('script_narration', font=(default_font_family, 10, 'italic'), foreground='#4A5568')
        self.story_text.tag_configure('script_place', font=(default_font_family, 10, 'bold'), foreground='#744210')
        self.story_text.tag_configure('script_choice', font=(default_font_family, 11, 'bold'), foreground='#C53030')
        self.story_text.tag_configure('script_choice_tag', font=(default_font_family, 10, 'italic'), foreground='#718096')
        self.story_text.tag_configure('script_branch', font=(default_font_family, 10, 'bold'), foreground='#9C4221')
        self.story_text.tag_configure('script_outline_header', font=(default_font_family, 10, 'bold'), foreground='#2C5282')
        self.story_text.tag_configure('script_divider', font=(default_font_family, 9), foreground='#A0AEC0')
    
    def update_ui_text(self) -> None:
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()
            
        self.btn_open_file.config(text=lang_dict['file_open'])
        self.btn_open_folder.config(text=lang_dict['folder_open'])
        self.btn_export.config(text=lang_dict['export'])
        self.btn_copy.config(text=lang_dict.get('btn_copy_script', '대본 복사'))

        self.open_frame.config(text=lang_dict.get('open_frame_title', 'Open'))
        self.detail_options_group.config(text=lang_dict['detail_options_group'])
        
        self.display_mode_label.config(text=lang_dict.get('display_mode_label', 'Display Filename As:'))
        val1 = lang_dict['display_original_filename']
        val2 = lang_dict['display_title']
        val3 = lang_dict.get('display_id_and_title', '[ID] + title 정보')
        self.display_mode_combo.config(values=[val1, val2, val3])
        cur_mode = self.controller.display_mode_var.get()
        if cur_mode == "original":
            self.display_mode_combo.current(0)
        elif cur_mode == "title":
            self.display_mode_combo.current(1)
        elif cur_mode == "id_title":
            self.display_mode_combo.current(2)
        
        view_modes = [
            lang_dict.get('view_script', '대본 모드 (대사·지문·선택지 위주의 읽기 쉬운 형식)'),
            lang_dict.get('view_simple', '간단히 표시 (주요 연출, 대사 및 선택지 분기 요약)'),
            lang_dict.get('view_detailed', '자세히 표시 (모든 씬 번호, 오프코드 및 원본 파라미터 전체)'),
        ]
        self.view_mode_combo.config(values=view_modes)
        cur_view_mode = self.controller.view_mode_var.get()
        if cur_view_mode == "script":
            self.view_mode_combo.current(0)
        elif cur_view_mode == "simple":
            self.view_mode_combo.current(1)
        elif cur_view_mode == "detailed":
            self.view_mode_combo.current(2)
        self.left_group.config(text=lang_dict['list_group_title'])
        self.right_group.config(text=lang_dict['detail_group_title'])
        self.search_button.config(text=lang_dict['search_button_text'])
        
        self.server_label.config(text=lang_dict.get('game_server_label', 'Game Server:'))
        self.jp_radio.config(text=lang_dict.get('jp_server_radio', 'JP'))
        self.kr_radio.config(text=lang_dict.get('kr_server_radio', 'KR'))
        
        self.controller.update_file_list(self.controller.current_filenames_in_list)

    def update_status_bar(self, key, **kwargs) -> None:
        """상태바 메시지를 다국어 키 기반으로 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()
        message = lang_dict.get(key, "...")
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError:
                pass
        self.status_bar.config(text=message)

    def update_story_text(self, content_list: list[tuple[str, str | None]]) -> None:
        """스토리 텍스트 표시 영역을 주어진 콘텐츠로 업데이트합니다.

        Args:
            content_list: (텍스트, 태그명) 튜플 리스트. 태그가 None이면 기본 스타일 적용.
        """
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)
        self.btn_copy.config(state=tk.NORMAL if content_list else tk.DISABLED)

    def set_action_buttons_state(self, state: str) -> None:
        """검색 및 내보내기 버튼의 상태를 설정합니다.

        Args:
            state: 위젯 상태 ('normal', 'disabled' 등).
        """
        self.search_button.config(state=state)
        self.btn_export.config(state=state)
