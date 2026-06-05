from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, Listbox, Menu
from tkinterdnd2 import DND_FILES
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import AVConverterController


class AVConverterView(ttk.Frame):
    def __init__(self, master: ttk.Frame, controller: AVConverterController) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)
        
        self.lang_data = self.controller.get_lang_dict()
        
        self.audio_widgets = {}
        self.video_widgets = {}
        self.audio_ui_elements = {}
        self.video_ui_elements = {}
        self.audio_filenames_var = tk.StringVar()
        self.video_filenames_var = tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.audio_tab = ttk.Frame(self.notebook)
        self.video_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.audio_tab, text=self.lang_data['audio_tab'])
        self.notebook.add(self.video_tab, text=self.lang_data['video_tab'])
        
        self.audio_widgets, self.audio_log_text, self.audio_ui_elements = self._build_conversion_tab_ui(self.audio_tab, 'audio', self.audio_filenames_var)
        self.video_widgets, self.video_log_text, self.video_ui_elements = self._build_conversion_tab_ui(self.video_tab, 'video', self.video_filenames_var)

    def switch_language(self, lang_code: str) -> None:
        """지정된 언어 코드로 UI 언어를 전환합니다."""
        self.lang_data = self.controller.get_lang_dict()
        self._update_ui_text()

    def _update_ui_text(self) -> None:
        d = self.lang_data
        self.notebook.tab(self.audio_tab, text=d['audio_tab'])
        self.notebook.tab(self.video_tab, text=d['video_tab'])
        
        for tab_type, widgets, ui_elements in [
            ('audio', self.audio_widgets, self.audio_ui_elements),
            ('video', self.video_widgets, self.video_ui_elements),
        ]:
            is_converting = widgets['action_btn'].instate(['disabled'])
            for elem_key, lang_key in ui_elements.items():
                w = getattr(self, f'{tab_type}_ui_{elem_key}', None)
                if w:
                    w.config(text=d[lang_key])
            widgets['add_files_btn'].config(text=d['add_files'])
            widgets['add_folder_btn'].config(text=d['add_folder'])
            widgets['browse_btn'].config(text=d['browse'])
            
            if is_converting:
                widgets['action_btn'].config(text=d.get('cancel_conversion', 'Cancel'))
            else:
                widgets['action_btn'].config(text=d['start_conversion'])
                widgets['status_label'].config(text=d['status_idle'])
                
            if 'overwrite_check' in widgets:
                widgets['overwrite_check'].config(text=d['overwrite_option'])

    def _build_conversion_tab_ui(self, parent_tab: ttk.Frame, tab_type: str, filenames_var: tk.StringVar) -> tuple[dict, scrolledtext.ScrolledText, dict]:
        d = self.lang_data
        is_audio_tab = (tab_type == 'audio')

        main_bottom_controls_frame = ttk.Frame(parent_tab)
        main_bottom_controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=5)
        
        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        left_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(left_pane_frame, weight=1)
        
        right_pane_frame = ttk.Frame(tab_pane)
        tab_pane.add(right_pane_frame, weight=3)
        
        input_frame = ttk.LabelFrame(left_pane_frame, text=d['input_section'])
        input_frame.pack(fill=tk.X, pady=5, padx=5)
        
        input_frame.columnconfigure(0, weight=1, uniform='btn')
        input_frame.columnconfigure(1, weight=1, uniform='btn')
        
        add_files_btn = ttk.Button(input_frame, text=d['add_files'], command=lambda: self.controller.add_files_cmd(tab_type))
        add_files_btn.grid(row=0, column=0, padx=(5, 2), pady=5, sticky='ew')
        
        add_folder_btn = ttk.Button(input_frame, text=d['add_folder'], command=lambda: self.controller.add_folder_cmd(tab_type))
        add_folder_btn.grid(row=0, column=1, padx=(2, 5), pady=5, sticky='ew')
        
        list_container = ttk.LabelFrame(left_pane_frame, text=d['file_list_section'])
        list_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        
        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        try:
            listbox.drop_target_register(DND_FILES)
            listbox.dnd_bind('<<Drop>>', lambda e, lb=listbox, tt=tab_type: self.controller.on_dnd_drop(e, lb, tt))
        except (RuntimeError, tk.TclError) as ex:
            self.controller.log_system_message(tab_type, f"Drag & Drop disabled: {ex}\n")

        self._create_right_click_menu(listbox, tab_type)
        
        log_frame_container = ttk.LabelFrame(right_pane_frame, text=d['log_section'])
        log_frame_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state=tk.DISABLED, font=("TkFixedFont", 10), padx=5, pady=5)
        log_text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5,0))
        
        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(2,5))
        
        status_label = ttk.Label(status_frame, text=d['status_idle'])
        status_label.pack(side=tk.LEFT)
        
        progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, mode='determinate')
        progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5,0))
        
        action_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d['action_section'])
        action_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        
        output_frame = ttk.LabelFrame(main_bottom_controls_frame, text=d['output_section'])
        output_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        
        browse_btn = ttk.Button(output_frame, text=d['browse'], command=lambda: self._select_output_folder(output_entry))
        browse_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        action_button = ttk.Button(action_frame, text=d['start_conversion'])
        
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
            overwrite_check = ttk.Checkbutton(action_frame, text=d['overwrite_option'], variable=self.audio_overwrite_var)
            overwrite_check.pack(side=tk.LEFT, pady=5, padx=10)
            action_button.config(command=lambda: self.controller.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get()))
            widgets_dict['overwrite_check'] = overwrite_check
        else:
            action_button.pack(fill=tk.X, pady=5, padx=5)
            action_button.config(command=lambda: self.controller.start_video_conversion(output_entry.get()))

        return widgets_dict, log_text_widget, ui_elements_for_lang_update

    def _select_output_folder(self, entry_widget: ttk.Entry) -> None:
        folder = filedialog.askdirectory(title=self.lang_data.get('dialog_select_output', 'Select an output folder'))
        if folder:
            entry_widget.config(state=tk.NORMAL)
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder)
            entry_widget.config(state='readonly')

    def _create_right_click_menu(self, listbox: Listbox, tab_type: str) -> None:
        menu = Menu(listbox, tearoff=0)
        menu.add_command(label="", command=lambda: self.controller.remove_selected_from_list(listbox, tab_type))
        menu.add_command(label="", command=lambda: self.controller.clear_list(tab_type))
        menu.add_separator()
        menu.add_command(label="", command=lambda: self.controller.preview_selected(listbox, tab_type))
        
        def show_menu(event):
            d = self.lang_data
            menu.entryconfig(0, label=d['remove_selected'], state=tk.NORMAL if listbox.curselection() else "disabled")
            menu.entryconfig(1, label=d['remove_all'], state=tk.NORMAL if listbox.size() > 0 else "disabled")
            menu.entryconfig(3, label=d.get('preview_menu', 'Preview'), state=tk.NORMAL if listbox.curselection() else "disabled")
            menu.post(event.x_root, event.y_root)
            
        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self.controller.remove_selected_from_list(listbox, tab_type))

    def create_progress_popup(self, width: int = 300, height: int = 80) -> tk.Toplevel:
        d = self.lang_data
        popup = tk.Toplevel(self)
        popup.title(d.get('preview_menu', 'Preview'))
        sx, sy = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f'{width}x{height}+{sx // 2 - width // 2}+{sy // 2 - height // 2}')
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        popup.resizable(False, False)
        ttk.Label(popup, text=d.get('preview_converting', 'Converting...')).pack(pady=(15, 5))
        progress = ttk.Progressbar(popup, mode='indeterminate')
        progress.pack(fill=tk.X, padx=20, pady=(0, 10))
        progress.start(15)
        return popup

    def destroy_popup_safely(self, popup: tk.Toplevel) -> None:
        try:
            popup.destroy()
        except tk.TclError:
            pass

    def show_track_selector(self, stream_count: int, stream_map_builder: Any, on_double_click_callback: Any) -> None:
        d = self.lang_data
        popup = tk.Toplevel(self)
        popup.title(d.get('preview_track_title', 'Select Track'))
        win_w, win_h = 450, 400
        sx, sy = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f'{win_w}x{win_h}+{sx // 2 - win_w // 2}+{sy // 2 - win_h // 2}')
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        
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
        
        # 트리뷰에 스트림 항목 추가
        stream_map_builder(tree)
        
        def on_double_click(event):
            on_double_click_callback(tree)
            
        tree.bind('<Double-Button-1>', on_double_click)

    def set_ui_state(self, tab_type: str, state: str) -> None:
        widgets = self.video_widgets if tab_type == 'video' else self.audio_widgets
        for widget_name, widget in widgets.items():
            if widget_name in ['progress', 'status_label', 'output_entry', 'listbox']: 
                continue
            new_state = 'readonly' if isinstance(widget, ttk.Entry) and state == 'disabled' else state
            widget.config(state=new_state)

    def reset_ui_state(self, tab_type: str) -> None:
        d = self.lang_data
        widgets = self.video_widgets if tab_type == 'video' else self.audio_widgets
        self.set_ui_state(tab_type, 'normal')
        
        if tab_type == 'video':
            new_cmd = lambda: self.controller.start_video_conversion(widgets['output_entry'].get())
        else:
            new_cmd = lambda: self.controller.start_audio_conversion(widgets['output_entry'].get(), self.audio_overwrite_var.get())
        
        widgets['action_btn'].config(text=d['start_conversion'], state=tk.NORMAL, command=new_cmd)
        widgets['status_label'].config(text=d['status_idle'])
        widgets['progress']['value'] = 0
