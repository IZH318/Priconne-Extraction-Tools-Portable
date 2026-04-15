from __future__ import annotations
import tkinter as tk
from tkinter import ttk, Text, Scrollbar, PanedWindow, font
from tkinterdnd2 import DND_FILES
from typing import Any

from .extractor import AssetProcessor

class AssetExtractorView(ttk.Frame):
    def __init__(self, master: Any, controller: Any) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self._type_group_labels = {}
        self.setup_ui()

    def setup_ui(self):
        main_paned_window = PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

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
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind('<<Drop>>', self.controller.on_dnd_drop)
        except Exception:
            pass

        center_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(center_pane, width=200)
        self._build_type_filter_panel(center_pane)

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
        
        self.version_entry = ttk.Entry(self.version_frame, textvariable=self.controller.unity_version_var, width=18, state='disabled')
        self.version_entry.pack(side=tk.LEFT, padx=(2, 5), pady=5)

        self.start_button_container = ttk.LabelFrame(bottom_controls_frame, text="")
        self.start_button_container.grid(row=0, column=2, sticky='ns')
        self.start_button = ttk.Button(self.start_button_container, text="", command=self.controller.start_extraction)
        self.start_button.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.listbox_menu = tk.Menu(self, tearoff=0)
        self.listbox_menu.add_command(label="", command=self.controller.remove_selected_files)
        self.listbox_menu.add_command(label="", command=self.controller.remove_all_files)
        self.listbox_menu.add_separator()
        self.listbox_menu.add_command(label="", command=self.controller.open_asset_browser)
        
        self.file_listbox.bind("<Button-3>", self._show_listbox_menu)
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu)

    def _show_listbox_menu(self, event):
        if self.controller.is_running: return
        d = self.controller.get_lang_dict()
        has_selection = bool(self.file_listbox.curselection())
        self.listbox_menu.entryconfig(0, state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.entryconfig(1, state=tk.NORMAL if self.controller.file_paths else tk.DISABLED)
        self.listbox_menu.entryconfig(3, label=d.get('browse_assets_menu', 'Browse Assets'), state=tk.NORMAL if has_selection else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)

    def _build_type_filter_panel(self, parent):
        self.filter_frame = ttk.LabelFrame(parent, text="")
        self.filter_frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(self.filter_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=(5, 2))
        self.btn_select_all = ttk.Button(btn_frame, text="", command=self.controller.select_all_types)
        self.btn_select_all.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        self.btn_deselect_all = ttk.Button(btn_frame, text="", command=self.controller.deselect_all_types)
        self.btn_deselect_all.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2, 0))

        canvas = tk.Canvas(self.filter_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.filter_frame, orient="vertical", command=canvas.yview)
        self.filter_inner_frame = ttk.Frame(canvas)

        self.filter_inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.filter_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        categories = [
            ("filter_group_textures", ["Texture2D", "Sprite", "Texture2DArray"]),
            ("filter_group_media", ["AudioClip", "MovieTexture", "VideoClip"]),
            ("filter_group_resources", ["TextAsset", "MonoBehaviour", "AnimationClip", "Mesh", "Shader", "Font", "Material"]),
            ("filter_group_components", sorted(AssetProcessor.SKIP_TYPES) + ["_OTHER_"]),
        ]

        default_enabled = AssetProcessor.DEFAULT_ENABLED
        is_first_group = True

        for group_key, type_list in categories:
            if not is_first_group:
                ttk.Separator(self.filter_inner_frame, orient='horizontal').pack(fill=tk.X, pady=(4, 0))
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

    def update_ui_text(self):
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        d = self.controller.get_lang_dict()
        
        self.btn_open_file.config(text=d['file_open'])
        self.btn_open_folder.config(text=d['folder_open'])

        self.list_frame.config(text=d['file_list'])
        self.log_frame.config(text=d['log_history'])
        self.output_frame.config(text=d['output_folder'])
        self.open_frame.config(text=d.get('open_frame_title', 'Open'))
        self.version_frame.config(text=d.get('unity_version_label', 'Unity Version:'))
        
        manual_label = d.get('version_manual_input', 'Manual Input')
        combo_values = self.controller.UNITY_VERSION_PRESETS + [manual_label]
        self.version_combo['values'] = combo_values
        current = self.controller.version_combo_var.get()
        if current not in self.controller.UNITY_VERSION_PRESETS:
            self.controller.version_combo_var.set(manual_label)
        
        self.output_button.config(text=d['browse'])
        self.start_button_container.config(text=d['run'])
        
        if not self.controller.is_running:
            self.start_button.config(text=d['start_extraction'])
        else:
            self.start_button.config(text=d.get('cancel_extraction', 'Cancel'))
            
        self.listbox_menu.entryconfig(0, label=d['remove_selected'])
        self.listbox_menu.entryconfig(1, label=d['remove_all'])
        
        self.filter_frame.config(text=d.get('filter_panel_title', 'Asset Type Filter'))
        self.btn_select_all.config(text=d.get('select_all', 'Select All'))
        self.btn_deselect_all.config(text=d.get('deselect_all', 'Deselect All'))
        for key, label_widget in self._type_group_labels.items():
            label_widget.config(text=d.get(key, key))
        
        self.update_progress_bar()

    def update_progress_bar(self):
        """진행률 바와 라벨을 현재 상태에 맞게 업데이트합니다."""
        d = self.controller.get_lang_dict()
        if self.controller.is_running and self.controller.file_paths:
            total_files = len(self.controller.file_paths)
            self.progress_label.config(text=f"{d['progress']}{self.controller.processed_files_count} / {total_files}")
            self.progress_bar['value'] = self.controller.processed_files_count
        else:
            self.progress_bar['value'] = 0
            self.progress_label.config(text=f"{d['progress']}{d['waiting']}")

    def toggle_controls(self, enabled):
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
            self.version_entry.config(state='normal' if is_manual else 'disabled')
        else:
            self.version_entry.config(state='disabled')
        self.btn_select_all.config(state=state)
        self.btn_deselect_all.config(state=state)
        for widget in self.filter_inner_frame.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                widget.config(state=state)
