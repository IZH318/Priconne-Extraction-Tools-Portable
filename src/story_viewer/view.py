from __future__ import annotations
import tkinter as tk
from tkinter import ttk, font
from typing import Any


class StoryViewerView(ttk.Frame):
    def __init__(self, master: Any, controller: Any) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.setup_ui()
        self.setup_text_tags()

    def setup_ui(self):
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
        
        self.display_mode_frame = ttk.Frame(self.left_group)
        self.display_mode_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        self.display_mode_label = ttk.Label(self.display_mode_frame, text="")
        self.display_mode_label.pack(side=tk.LEFT, padx=(0, 5))
        self.display_mode_combo = ttk.Combobox(self.display_mode_frame, state="readonly")
        self.display_mode_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.display_mode_combo.bind("<<ComboboxSelected>>", self.controller.on_display_mode_change)
        
        self.search_button = ttk.Button(self.left_group, text="", command=self.controller.open_search_window, state="disabled")
        self.search_button.pack(fill=tk.X, padx=5, pady=(5, 5))
        
        list_scrollbar = ttk.Scrollbar(self.left_group, orient=tk.VERTICAL)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        self.file_listbox = tk.Listbox(self.left_group, selectmode=tk.SINGLE, yscrollcommand=list_scrollbar.set)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=(0, 5))
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<<ListboxSelect>>", self.controller.on_file_select)
        
        right_pane = ttk.Frame(self.paned_window)
        self.paned_window.add(right_pane, weight=right_weight)
        
        self.detail_options_group = ttk.LabelFrame(right_pane, text="", padding=5)
        self.detail_options_group.pack(fill=tk.X, pady=(0, 5))
        self.view_simple_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.controller.view_mode_var, value="simple", command=self.controller.on_view_mode_change)
        self.view_simple_radio.pack(side=tk.LEFT, padx=(5, 10))
        self.view_detailed_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.controller.view_mode_var, value="detailed", command=self.controller.on_view_mode_change)
        self.view_detailed_radio.pack(side=tk.LEFT, padx=5)
        
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
        
        self.btn_export = ttk.Button(self.bottom_frame, text="", command=self.controller.open_export_window, state="disabled")
        self.btn_export.pack(side=tk.RIGHT, padx=(5, 0))
        
        def reapply_weights(event=None):
            try:
                total_width = self.paned_window.winfo_width()
                sash_position = int(total_width * left_weight / (left_weight + right_weight))
                self.paned_window.sashpos(0, sash_position)
                self.paned_window.unbind("<Configure>")
            except tk.TclError: pass
        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self):
        default_font_family = font.nametofont("TkDefaultFont").cget("family")
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A')
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000')
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')
    
    def update_ui_text(self):
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()
            
        self.btn_open_file.config(text=lang_dict['file_open'])
        self.btn_open_folder.config(text=lang_dict['folder_open'])
        self.btn_export.config(text=lang_dict['export'])

        self.open_frame.config(text=lang_dict.get('open_frame_title', '파일 선택'))
        self.detail_options_group.config(text=lang_dict['detail_options_group'])
        
        self.display_mode_label.config(text=lang_dict.get('display_mode_label', '파일 이름 표시:'))
        val1 = lang_dict['display_original_filename']
        val2 = lang_dict['display_title']
        self.display_mode_combo.config(values=[val1, val2])
        if self.controller.display_mode_var.get() == "original":
            self.display_mode_combo.current(0)
        else:
            self.display_mode_combo.current(1)
        
        self.view_simple_radio.config(text=lang_dict['view_simple'])
        self.view_detailed_radio.config(text=lang_dict['view_detailed'])
        self.left_group.config(text=lang_dict['list_group_title'])
        self.right_group.config(text=lang_dict['detail_group_title'])
        self.search_button.config(text=lang_dict['search_button_text'])
        
        self.controller.update_file_list(self.controller.current_filenames_in_list)

    def update_status_bar(self, key, **kwargs):
        """상태바 메시지를 다국어 키 기반으로 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()
        message = lang_dict.get(key, "...")
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError:
                pass
        self.status_bar.config(text=message)

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)
