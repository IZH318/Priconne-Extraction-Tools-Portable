# src/story_viewer/windows_export.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from .languages import LANGUAGES

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = 0
        self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.x = self.widget.winfo_rootx() + 20
        self.y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.id = self.widget.after(500, self.show_tip)

    def leave(self, event=None):
        self.hide_tip()

    def show_tip(self):
        if self.tip_window or not self.text:
            return
        if str(self.widget.cget('state')) == 'disabled':
            return
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{self.x}+{self.y}")

        label = tk.Label(self.tip_window, text=self.text, background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None

class ExportWindow(tk.Toplevel):
    def __init__(self, app, all_files_dict, story_data_cache, search_data, db_status, server_db_info):
        super().__init__(app.master)
        self.app = app
        self.all_files_dict = all_files_dict
        self.story_data_cache = story_data_cache
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        self.export_options = {
            'story_data': tk.BooleanVar(value=True),
            'filenames': tk.BooleanVar(value=False),
            'character_names': tk.BooleanVar(value=False),
            'bgm_names': tk.BooleanVar(value=False),
            'background_names': tk.BooleanVar(value=False),
            'event_list_master': tk.BooleanVar(value=False),
            'event_list_jp': tk.BooleanVar(value=False),
            'event_list_kr': tk.BooleanVar(value=False),
        }
        self.story_data_scope = tk.StringVar(value='current_list') 

        self.transient(app.master)
        self.grab_set()
        self._setup_ui()
        self.focus_set()
        self._center_window(400, 420)

        self._toggle_story_data_options()
        self._toggle_event_list_options()

    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        self.options_frame = ttk.LabelFrame(main_frame, text="", padding="10")
        self.options_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.cb_story_data = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['story_data'],
                                            command=self._toggle_story_data_options)
        self.cb_story_data.pack(anchor="w", pady=2)
        
        self.story_data_scope_frame = ttk.LabelFrame(self.options_frame, text="", padding="5")
        self.story_data_scope_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.story_data_scope_current_list_radio = ttk.Radiobutton(
            self.story_data_scope_frame, text="", variable=self.story_data_scope, value="current_list"
        )
        self.story_data_scope_current_list_radio.pack(anchor="w")

        self.story_data_scope_all_loaded_radio = ttk.Radiobutton(
            self.story_data_scope_frame, text="", variable=self.story_data_scope, value="all_loaded"
        )
        self.story_data_scope_all_loaded_radio.pack(anchor="w")
        
        self.cb_filenames = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['filenames'])
        self.cb_filenames.pack(anchor="w", pady=2)

        self.cb_character_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['character_names'])
        self.cb_character_names.pack(anchor="w", pady=2)

        self.cb_bgm_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['bgm_names'])
        self.cb_bgm_names.pack(anchor="w", pady=2)

        self.cb_background_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['background_names'])
        self.cb_background_names.pack(anchor="w", pady=2)
        
        self.cb_event_list_master = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['event_list_master'],
                                                    command=self._toggle_event_list_options)
        self.cb_event_list_master.pack(anchor="w", pady=2)

        self.event_list_group_frame = ttk.LabelFrame(self.options_frame, text="", padding="5")
        self.event_list_group_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.cb_event_list_jp = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_jp'])
        self.cb_event_list_jp.pack(anchor="w", pady=2)
        try:
            lang_dict = LANGUAGES[self.app.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
        
        if not self.db_status.get('JP', False):
            self.cb_event_list_jp.tooltip = ToolTip(self.cb_event_list_jp, text=lang_dict['export_db_not_found_tooltip'])

        self.cb_event_list_kr = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_kr'])
        self.cb_event_list_kr.pack(anchor="w", pady=2)
        if not self.db_status.get('KR', False):
            self.cb_event_list_kr.tooltip = ToolTip(self.cb_event_list_kr, text=lang_dict['export_db_not_found_tooltip'])

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x")

        self.export_button = ttk.Button(button_frame, text="", command=self.start_export)
        self.export_button.pack(side="right")

        self.cancel_button = ttk.Button(button_frame, text="", command=self.destroy)
        self.cancel_button.pack(side="right", padx=(0, 5))

        self._update_ui_text()

    def _toggle_story_data_options(self):
        is_story_data_selected = self.export_options['story_data'].get()
        state_str = 'normal' if is_story_data_selected else 'disabled'
        
        for child in self.story_data_scope_frame.winfo_children():
            child.config(state=state_str)
        if state_str == 'disabled':
            self.story_data_scope.set('')
        elif is_story_data_selected and not self.story_data_scope.get():
            self.story_data_scope.set('current_list')

    def _toggle_event_list_options(self):
        is_master_selected = self.export_options['event_list_master'].get()

        jp_can_be_enabled = self.db_status.get('JP', False)
        jp_final_state = 'normal' if is_master_selected and jp_can_be_enabled else 'disabled'
        self.cb_event_list_jp.config(state=jp_final_state)
        if jp_final_state == 'disabled':
            self.export_options['event_list_jp'].set(False)

        kr_can_be_enabled = self.db_status.get('KR', False)
        kr_final_state = 'normal' if is_master_selected and kr_can_be_enabled else 'disabled'
        self.cb_event_list_kr.config(state=kr_final_state)
        if kr_final_state == 'disabled':
            self.export_options['event_list_kr'].set(False)

    def _update_ui_text(self):
        try:
            lang_dict = LANGUAGES[self.app.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
        self.title(lang_dict['export_window_title'])
        self.options_frame.config(text=lang_dict['export_type_frame'])
        
        self.cb_story_data.config(text=lang_dict['export_type_story_data'])
        self.story_data_scope_frame.config(text=lang_dict['export_scope_frame'])
        self.story_data_scope_current_list_radio.config(text=lang_dict['export_scope_current_list'])
        self.story_data_scope_all_loaded_radio.config(text=lang_dict['export_scope_all_loaded'])

        self.cb_filenames.config(text=lang_dict['export_type_filenames'])
        self.cb_character_names.config(text=lang_dict['export_type_character_names'])
        self.cb_bgm_names.config(text=lang_dict['export_type_bgm_names'])
        self.cb_background_names.config(text=lang_dict['export_type_background_names'])
        
        self.cb_event_list_master.config(text=lang_dict['export_type_event_list_master'])
        self.event_list_group_frame.config(text=lang_dict['export_type_event_list_frame'])
        self.cb_event_list_jp.config(text=lang_dict['export_type_event_list_jp'])
        self.cb_event_list_kr.config(text=lang_dict['export_type_event_list_kr'])
        
        self.export_button.config(text=lang_dict['export_button_text'])
        self.cancel_button.config(text=lang_dict['cancel_button_text'])

        if not self.db_status.get('JP', False) and hasattr(self.cb_event_list_jp, 'tooltip'):
            self.cb_event_list_jp.tooltip.text = lang_dict['export_db_not_found_tooltip']
        if not self.db_status.get('KR', False) and hasattr(self.cb_event_list_kr, 'tooltip'):
            self.cb_event_list_kr.tooltip.text = lang_dict['export_db_not_found_tooltip']

    def start_export(self):
        try:
            lang_dict = LANGUAGES[self.app.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
        selected_options = {k: v.get() for k, v in self.export_options.items()}
        selected_options['story_data_scope'] = self.story_data_scope.get() if selected_options['story_data'] else None
        actual_selected_exports = {k: v for k,v in selected_options.items() if k not in ['story_data_scope', 'event_list_master']}

        if not any(actual_selected_exports.values()):
            messagebox.showwarning(lang_dict['msgbox_export_options_title'], lang_dict['msgbox_no_export_types_selected'], parent=self)
            return

        output_folder = filedialog.askdirectory(title=lang_dict['msgbox_export_folder_title'], parent=self)
        if not output_folder:
            return

        self.app._update_status_bar('status_bar_export_prep')
        
        thread = threading.Thread(target=self.app._export_master_thread, args=(selected_options, output_folder))
        thread.daemon = True
        thread.start()
        
        self.destroy()
