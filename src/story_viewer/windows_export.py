"""Story Viewer 내보내기 대화상자(Export Dialogs) 모듈.

스토리 대사 텍스트 내보내기 옵션 창(ExportOptionsDialog),
DB 부가 정보(프로필, 보이스, 퀘스트 등) 내보내기 창(OtherExportWindow),
진행률 표시/취소 팝업 대화상자(ExportProgressDialog) 제공.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.utils.tk_safe import safe_after
from src.utils.tooltip import ToolTip


class ExportProgressDialog(tk.Toplevel):
    """데이터 내보내기 진행 상황 실시간 표시 및 취소 지원 진행 팝업 대화상자."""

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        get_lang_dict: Callable[[], dict[str, str]],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)

        self.withdraw()
        self._master = master
        self._get_lang_dict = get_lang_dict
        self._on_cancel = on_cancel
        self.is_cancelled = False

        lang_dict = self._get_lang_dict()
        self.title(lang_dict.get('export_progress_title', 'Exporting Data...'))
        self.geometry("360x105")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._center_window(360, 105)

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.lbl_status = ttk.Label(
            main_frame,
            text=lang_dict.get('status_bar_export_prep', 'Preparing for export...'),
            anchor="center",
            justify="center"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 8))

        self.pb = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        self.pb.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.pb['value'] = 0

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        self.btn_cancel = ttk.Button(
            btn_frame,
            text=lang_dict.get('export_progress_cancel', 'Cancel'),
            command=self._cancel_clicked
        )
        self.btn_cancel.pack(anchor="center")

        self.protocol("WM_DELETE_WINDOW", self._cancel_clicked)
        self.deiconify()

    def _center_window(self, width: int, height: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _cancel_clicked(self) -> None:
        self.is_cancelled = True
        self.btn_cancel.config(state=tk.DISABLED)
        if self._on_cancel:
            self._on_cancel()

    def update_progress(self, current: int, total: int, type_name: str) -> None:
        try:
            percent = (current / total * 100) if total > 0 else 0
            self.pb['value'] = percent
            lang_dict = self._get_lang_dict()
            status_fmt = lang_dict.get('export_progress_status', 'Exporting [{type_name}]... ({current} / {total})')
            self.lbl_status.config(text=status_fmt.format(type_name=type_name, current=current, total=total))
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.grab_release()
            self.destroy()
        except tk.TclError:
            pass


_SCOPE_KEYS = ['current_list', 'all_loaded']
_FORMAT_KEYS = ['txt', 'md']
_VIEW_MODE_KEYS = ['script', 'simple', 'detailed']
_NAMING_KEYS = ['original', 'title', 'id_title']


class ExportWindow(tk.Toplevel):
    """데이터 추출 옵션 설정 대화상자 클래스."""

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        get_lang_dict: Callable[[], dict[str, str]],
        export_func: Callable[..., None],
        update_status_bar: Callable[..., None],
        all_files_dict: dict[str, str],
        search_data: dict[str, Any],
        db_status: dict[str, bool],
        server_db_info: dict[str, Any],
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self._master = master
        self._get_lang_dict = get_lang_dict
        self._export_func = export_func
        self._update_status_bar = update_status_bar
        self.all_files_dict = all_files_dict
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        self.export_options = {
            'story_data': tk.BooleanVar(value=True),
            'filenames': tk.BooleanVar(value=False),
            'character_names': tk.BooleanVar(value=False),
            'bgm_names': tk.BooleanVar(value=False),
            'background_names': tk.BooleanVar(value=False),
            'voice_names': tk.BooleanVar(value=False),
            'event_list_master': tk.BooleanVar(value=False),
            'event_list_jp': tk.BooleanVar(value=False),
            'event_list_kr': tk.BooleanVar(value=False),
            'open_folder_after': tk.BooleanVar(value=False),
        }
        self.story_data_scope = tk.StringVar(value='current_list')
        self.format_var = tk.StringVar(value='txt')
        self.view_mode_var = tk.StringVar(value='script')
        self.naming_var = tk.StringVar(value='original')

        self.transient(master)
        self.grab_set()
        self._setup_ui()
        self.focus_set()
        self._center_window(440, 485)
        self.resizable(False, False)

        self._toggle_story_data_options()
        self._toggle_event_list_options()
        self.deiconify()

    def _center_window(self, width: int, height: int) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self) -> None:
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 스토리 데이터 추출 설정 프레임
        self.story_data_group = ttk.LabelFrame(main_frame, text="", padding="10")
        self.story_data_group.pack(fill=tk.X, pady=(0, 10))

        self.cb_story_data = ttk.Checkbutton(
            self.story_data_group, text="", variable=self.export_options['story_data'],
            command=self._toggle_story_data_options
        )
        self.cb_story_data.pack(anchor="w", pady=(0, 5))

        self.story_sub_frame = ttk.Frame(self.story_data_group, padding="5")
        self.story_sub_frame.pack(fill=tk.X, padx=5)

        # 1-1. 추출 범위 드롭박스
        self.scope_label = ttk.Label(self.story_sub_frame, text="", anchor="w")
        self.scope_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=2)
        self.combo_scope = ttk.Combobox(self.story_sub_frame, state="readonly")
        self.combo_scope.grid(row=0, column=1, sticky="ew", pady=2)
        self.combo_scope.bind("<<ComboboxSelected>>", self._on_scope_selected)

        # 1-2. 파일 형식 드롭박스
        self.format_label = ttk.Label(self.story_sub_frame, text="", anchor="w")
        self.format_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=2)
        self.combo_format = ttk.Combobox(self.story_sub_frame, state="readonly")
        self.combo_format.grid(row=1, column=1, sticky="ew", pady=2)
        self.combo_format.bind("<<ComboboxSelected>>", self._on_format_selected)

        # 1-3. 서식 모드 드롭박스
        self.view_mode_label = ttk.Label(self.story_sub_frame, text="", anchor="w")
        self.view_mode_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=2)
        self.combo_view_mode = ttk.Combobox(self.story_sub_frame, state="readonly")
        self.combo_view_mode.grid(row=2, column=1, sticky="ew", pady=2)
        self.combo_view_mode.bind("<<ComboboxSelected>>", self._on_view_mode_selected)

        # 1-4. 파일명 서식 드롭박스
        self.naming_label = ttk.Label(self.story_sub_frame, text="", anchor="w")
        self.naming_label.grid(row=3, column=0, sticky="w", padx=(0, 10), pady=2)
        self.combo_naming = ttk.Combobox(self.story_sub_frame, state="readonly")
        self.combo_naming.grid(row=3, column=1, sticky="ew", pady=2)
        self.combo_naming.bind("<<ComboboxSelected>>", self._on_naming_selected)

        self.story_sub_frame.columnconfigure(1, weight=1)

        # 2. 기타 데이터 추출 프레임
        self.other_options_frame = ttk.LabelFrame(main_frame, text="", padding="10")
        self.other_options_frame.pack(fill=tk.X, pady=(0, 10))

        self.cb_filenames = ttk.Checkbutton(self.other_options_frame, text="", variable=self.export_options['filenames'])
        self.cb_filenames.pack(anchor="w", pady=1)

        self.cb_character_names = ttk.Checkbutton(self.other_options_frame, text="", variable=self.export_options['character_names'])
        self.cb_character_names.pack(anchor="w", pady=1)

        self.cb_bgm_names = ttk.Checkbutton(self.other_options_frame, text="", variable=self.export_options['bgm_names'])
        self.cb_bgm_names.pack(anchor="w", pady=1)

        self.cb_background_names = ttk.Checkbutton(self.other_options_frame, text="", variable=self.export_options['background_names'])
        self.cb_background_names.pack(anchor="w", pady=1)

        self.cb_voice_names = ttk.Checkbutton(self.other_options_frame, text="", variable=self.export_options['voice_names'])
        self.cb_voice_names.pack(anchor="w", pady=1)

        self.cb_event_list_master = ttk.Checkbutton(
            self.other_options_frame, text="", variable=self.export_options['event_list_master'],
            command=self._toggle_event_list_options
        )
        self.cb_event_list_master.pack(anchor="w", pady=1)

        self.event_list_group_frame = ttk.Frame(self.other_options_frame, padding="0")
        self.event_list_group_frame.pack(fill=tk.X, padx=15, pady=(2, 0))

        self.cb_event_list_jp = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_jp'])
        self.cb_event_list_jp.pack(anchor="w", pady=(1, 2))

        lang_dict = self._get_lang_dict()
        if not self.db_status.get('JP', False):
            ToolTip(self.cb_event_list_jp, text=lang_dict.get('export_db_not_found_tooltip', 'Event DB file not found.'))

        self.cb_event_list_kr = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_kr'])
        self.cb_event_list_kr.pack(anchor="w", pady=(1, 0))
        if not self.db_status.get('KR', False):
            ToolTip(self.cb_event_list_kr, text=lang_dict.get('export_db_not_found_tooltip', 'Event DB file not found.'))

        # 3. 하단 컨트롤 바
        bottom_box = ttk.Frame(main_frame)
        bottom_box.pack(side=tk.BOTTOM, fill=tk.X)

        self.cb_open_folder = ttk.Checkbutton(bottom_box, text="", variable=self.export_options['open_folder_after'])
        self.cb_open_folder.pack(side=tk.LEFT)

        self.export_button = ttk.Button(bottom_box, text="", command=self.start_export)
        self.export_button.pack(side=tk.RIGHT)

        self.cancel_button = ttk.Button(bottom_box, text="", command=self.destroy)
        self.cancel_button.pack(side=tk.RIGHT, padx=(0, 5))

        self._update_ui_text()

    def _on_scope_selected(self, event: Any = None) -> None:
        idx = self.combo_scope.current()
        if 0 <= idx < len(_SCOPE_KEYS):
            self.story_data_scope.set(_SCOPE_KEYS[idx])

    def _on_format_selected(self, event: Any = None) -> None:
        idx = self.combo_format.current()
        if 0 <= idx < len(_FORMAT_KEYS):
            self.format_var.set(_FORMAT_KEYS[idx])

    def _on_view_mode_selected(self, event: Any = None) -> None:
        idx = self.combo_view_mode.current()
        if 0 <= idx < len(_VIEW_MODE_KEYS):
            self.view_mode_var.set(_VIEW_MODE_KEYS[idx])

    def _on_naming_selected(self, event: Any = None) -> None:
        idx = self.combo_naming.current()
        if 0 <= idx < len(_NAMING_KEYS):
            self.naming_var.set(_NAMING_KEYS[idx])

    def _toggle_story_data_options(self) -> None:
        is_selected = self.export_options['story_data'].get()
        combo_state = 'readonly' if is_selected else 'disabled'
        lbl_state = 'normal' if is_selected else 'disabled'

        for lbl in (self.scope_label, self.format_label, self.view_mode_label, self.naming_label):
            try:
                lbl.config(state=lbl_state)
            except tk.TclError:
                pass
        for cb in (self.combo_scope, self.combo_format, self.combo_view_mode, self.combo_naming):
            try:
                cb.config(state=combo_state)
            except tk.TclError:
                pass

    def _toggle_event_list_options(self) -> None:
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

    def _update_ui_text(self) -> None:
        lang_dict = self._get_lang_dict()
        self.title(lang_dict.get('export_window_title', 'Select Export Options'))

        self.story_data_group.config(text=lang_dict.get('export_story_group_frame', 'Story Data Extraction'))
        self.cb_story_data.config(text=lang_dict.get('export_type_story_data', 'Story Data'))

        self.scope_label.config(text=lang_dict.get('export_scope_frame', 'Extraction Scope:'))
        scope_values = [
            lang_dict.get('export_scope_current_list', 'Files in current list only'),
            lang_dict.get('export_scope_all_loaded', 'All loaded files'),
        ]
        self.combo_scope['values'] = scope_values
        cur_scope = self.story_data_scope.get()
        if cur_scope in _SCOPE_KEYS:
            self.combo_scope.current(_SCOPE_KEYS.index(cur_scope))
        else:
            self.combo_scope.current(0)

        self.format_label.config(text=lang_dict.get('export_format_label', 'Format:'))
        format_values = [
            lang_dict.get('export_format_txt', 'Text (.txt)'),
            lang_dict.get('export_format_md', 'Markdown (.md)'),
        ]
        self.combo_format['values'] = format_values
        cur_fmt = self.format_var.get()
        if cur_fmt in _FORMAT_KEYS:
            self.combo_format.current(_FORMAT_KEYS.index(cur_fmt))
        else:
            self.combo_format.current(0)

        self.view_mode_label.config(text=lang_dict.get('export_view_mode_label', 'View Mode:'))
        vm_values = [
            lang_dict.get('export_view_mode_script', 'Script'),
            lang_dict.get('export_view_mode_simple', 'Simple'),
            lang_dict.get('export_view_mode_detailed', 'Detailed'),
        ]
        self.combo_view_mode['values'] = vm_values
        cur_vm = self.view_mode_var.get()
        if cur_vm in _VIEW_MODE_KEYS:
            self.combo_view_mode.current(_VIEW_MODE_KEYS.index(cur_vm))
        else:
            self.combo_view_mode.current(0)

        self.naming_label.config(text=lang_dict.get('export_naming_label', 'Filename:'))
        naming_values = [
            lang_dict.get('display_original_filename', 'Original Filename'),
            lang_dict.get('display_title', 'Title Info'),
            lang_dict.get('display_id_and_title', '[ID] + Title Info'),
        ]
        self.combo_naming['values'] = naming_values
        cur_naming = self.naming_var.get()
        if cur_naming in _NAMING_KEYS:
            self.combo_naming.current(_NAMING_KEYS.index(cur_naming))
        else:
            self.combo_naming.current(0)

        self.other_options_frame.config(text=lang_dict.get('export_type_frame', 'Other Data Extraction'))
        self.cb_filenames.config(text=lang_dict.get('export_type_filenames', 'Filename List (filenames.txt)'))
        self.cb_character_names.config(text=lang_dict.get('export_type_character_names', 'Character Name List (character_names.txt)'))
        self.cb_bgm_names.config(text=lang_dict.get('export_type_bgm_names', 'BGM Filename List (bgm_names.txt)'))
        self.cb_background_names.config(text=lang_dict.get('export_type_background_names', 'Background Filename List (background_names.txt)'))
        self.cb_voice_names.config(text=lang_dict.get('export_type_voice_names', 'Voice Names (voice_names.txt)'))

        self.cb_event_list_master.config(text=lang_dict.get('export_type_event_list_master', 'Event Story Lists'))
        self.cb_event_list_jp.config(text=lang_dict.get('export_type_event_list_jp', 'Japan Server (event_list_jp.txt)'))
        self.cb_event_list_kr.config(text=lang_dict.get('export_type_event_list_kr', 'Korea Server (event_list_kr.txt)'))

        self.cb_open_folder.config(text=lang_dict.get('export_open_folder_after', 'Open folder after export'))
        self.export_button.config(text=lang_dict.get('export_button_text', 'Start Export'))
        self.cancel_button.config(text=lang_dict.get('cancel_button_text', 'Cancel'))

    def start_export(self) -> None:
        lang_dict = self._get_lang_dict()
        selected_options: dict[str, Any] = {k: v.get() for k, v in self.export_options.items()}
        selected_options['story_data_scope'] = self.story_data_scope.get() if selected_options['story_data'] else None
        selected_options['file_format'] = self.format_var.get()
        selected_options['view_mode'] = self.view_mode_var.get()
        selected_options['naming_rule'] = self.naming_var.get()

        actual_selected = {
            k: v for k, v in selected_options.items()
            if k not in ['story_data_scope', 'event_list_master', 'open_folder_after', 'file_format', 'view_mode', 'naming_rule']
        }

        if not any(actual_selected.values()):
            messagebox.showwarning(
                lang_dict.get('msgbox_export_options_title', 'Export Options'),
                lang_dict.get('msgbox_no_export_types_selected', 'Please select at least one item to export.'),
                parent=self
            )
            return

        output_folder = filedialog.askdirectory(title=lang_dict.get('msgbox_export_folder_title', 'Select a folder to save files'), parent=self)
        if not output_folder:
            return

        self._update_status_bar('status_bar_export_prep')

        # 진행 팝업 대화상자 생성 (안 B 연동)
        progress_dialog = ExportProgressDialog(self._master, self._get_lang_dict)

        def _progress_cb(cur: int, tot: int, tname: str) -> None:
            safe_after(self._master, 0, lambda: progress_dialog.update_progress(cur, tot, tname))

        def _check_cancelled() -> bool:
            return bool(progress_dialog.is_cancelled)

        finished = False
        def _on_finish() -> None:
            nonlocal finished
            if not finished:
                finished = True
                safe_after(self._master, 0, progress_dialog.close)

        def _run_export() -> None:
            try:
                self._export_func(selected_options, output_folder, _progress_cb, _check_cancelled, _on_finish)
            finally:
                _on_finish()

        thread = threading.Thread(
            target=_run_export,
            daemon=True
        )
        thread.start()

        self.destroy()


class SingleExportWindow(tk.Toplevel):
    """선택한 단일 스토리 파일 내보내기 옵션 설정 대화상자 클래스."""

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        target_filename: str,
        item_display_title: str,
        get_lang_dict: Callable[[], dict[str, str]],
        export_func: Callable[..., None],
        update_status_bar: Callable[..., None],
        default_view_mode: str = 'script',
        default_naming_rule: str = 'original',
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self._master = master
        self.target_filename = target_filename
        self.item_display_title = item_display_title
        self._get_lang_dict = get_lang_dict
        self._export_func = export_func
        self._update_status_bar = update_status_bar

        self.format_var = tk.StringVar(value='txt')
        self.view_mode_var = tk.StringVar(value=default_view_mode)
        self.naming_var = tk.StringVar(value=default_naming_rule)
        self.open_folder_var = tk.BooleanVar(value=False)

        self.transient(master)
        self.grab_set()
        self._setup_ui()
        self.focus_set()
        self._center_window(440, 265)
        self.resizable(False, False)
        self.deiconify()

    def _center_window(self, width: int, height: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_ui(self) -> None:
        lang_dict = self._get_lang_dict()
        title_fmt = lang_dict.get('single_export_window_title_fmt', '{item} - Export Options')
        self.title(title_fmt.format(item=self.item_display_title))

        main_frame = ttk.Frame(self, padding="15 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 대상 스토리 정보 프레임
        target_group = ttk.LabelFrame(
            main_frame,
            text=lang_dict.get('single_export_target_frame', 'Target Story Information'),
            padding="6"
        )
        target_group.pack(fill=tk.X, pady=(0, 8))

        title_text_fmt = lang_dict.get('single_export_target_title', '• Title: {title}')
        lbl_target_title = ttk.Label(
            target_group,
            text=title_text_fmt.format(title=self.item_display_title),
            anchor="w",
        )
        lbl_target_title.pack(fill=tk.X, pady=(0, 2))

        file_text_fmt = lang_dict.get('single_export_target_file', '• File: {filename}')
        lbl_target_file = ttk.Label(
            target_group,
            text=file_text_fmt.format(filename=self.target_filename),
            anchor="w",
            foreground="#666666"
        )
        lbl_target_file.pack(fill=tk.X)

        # 2. 내보내기 설정 프레임
        opt_group = ttk.LabelFrame(
            main_frame,
            text=lang_dict.get('export_story_group_frame', 'Story Data Extraction'),
            padding="8"
        )
        opt_group.pack(fill=tk.X, pady=(0, 8))

        # 2-1. 파일 형식 드롭박스
        format_label = ttk.Label(opt_group, text=lang_dict.get('export_format_label', 'Format:'), anchor="w")
        format_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        self.combo_format = ttk.Combobox(opt_group, state="readonly")
        self.combo_format.grid(row=0, column=1, sticky="ew", pady=3)
        self.combo_format['values'] = [
            lang_dict.get('export_format_txt', 'Text (.txt)'),
            lang_dict.get('export_format_md', 'Markdown (.md)'),
        ]
        self.combo_format.current(_FORMAT_KEYS.index(self.format_var.get()) if self.format_var.get() in _FORMAT_KEYS else 0)
        self.combo_format.bind("<<ComboboxSelected>>", lambda e: self.format_var.set(_FORMAT_KEYS[self.combo_format.current()]))

        # 2-2. 서식 모드 드롭박스
        vm_label = ttk.Label(opt_group, text=lang_dict.get('export_view_mode_label', 'View Mode:'), anchor="w")
        vm_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=3)
        self.combo_view_mode = ttk.Combobox(opt_group, state="readonly")
        self.combo_view_mode.grid(row=1, column=1, sticky="ew", pady=3)
        self.combo_view_mode['values'] = [
            lang_dict.get('export_view_mode_script', 'Script'),
            lang_dict.get('export_view_mode_simple', 'Simple'),
            lang_dict.get('export_view_mode_detailed', 'Detailed'),
        ]
        self.combo_view_mode.current(_VIEW_MODE_KEYS.index(self.view_mode_var.get()) if self.view_mode_var.get() in _VIEW_MODE_KEYS else 0)
        self.combo_view_mode.bind("<<ComboboxSelected>>", lambda e: self.view_mode_var.set(_VIEW_MODE_KEYS[self.combo_view_mode.current()]))

        # 2-3. 파일명 서식 드롭박스
        naming_label = ttk.Label(opt_group, text=lang_dict.get('export_naming_label', 'Filename:'), anchor="w")
        naming_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=3)
        self.combo_naming = ttk.Combobox(opt_group, state="readonly")
        self.combo_naming.grid(row=2, column=1, sticky="ew", pady=3)
        self.combo_naming['values'] = [
            lang_dict.get('display_original_filename', 'Original Filename'),
            lang_dict.get('display_title', 'Title Info'),
            lang_dict.get('display_id_and_title', '[ID] + Title Info'),
        ]
        self.combo_naming.current(_NAMING_KEYS.index(self.naming_var.get()) if self.naming_var.get() in _NAMING_KEYS else 0)
        self.combo_naming.bind("<<ComboboxSelected>>", lambda e: self.naming_var.set(_NAMING_KEYS[self.combo_naming.current()]))

        opt_group.columnconfigure(1, weight=1)

        # 3. 하단 컨트롤 바
        bottom_box = ttk.Frame(main_frame)
        bottom_box.pack(side=tk.BOTTOM, fill=tk.X)

        self.cb_open_folder = ttk.Checkbutton(
            bottom_box,
            text=lang_dict.get('export_open_folder_after', 'Open folder after export'),
            variable=self.open_folder_var
        )
        self.cb_open_folder.pack(side=tk.LEFT, pady=2)

        self.export_button = ttk.Button(bottom_box, text=lang_dict.get('export_button_text', 'Start Export'), command=self.start_export)
        self.export_button.pack(side=tk.RIGHT, padx=(5, 0))

        self.cancel_button = ttk.Button(bottom_box, text=lang_dict.get('cancel_button_text', 'Cancel'), command=self.destroy)
        self.cancel_button.pack(side=tk.RIGHT)

    def start_export(self) -> None:
        lang_dict = self._get_lang_dict()
        output_folder = filedialog.askdirectory(title=lang_dict.get('msgbox_export_folder_title', 'Select a folder to save files'), parent=self)
        if not output_folder:
            return

        self._update_status_bar('status_bar_export_prep')

        selected_options = {
            'story_data': True,
            'story_data_scope': 'single_file',
            'target_filenames': [self.target_filename],
            'file_format': self.format_var.get(),
            'view_mode': self.view_mode_var.get(),
            'naming_rule': self.naming_var.get(),
            'open_folder_after': self.open_folder_var.get(),
            'filenames': False,
            'character_names': False,
            'bgm_names': False,
            'background_names': False,
            'voice_names': False,
            'event_list_master': False,
            'event_list_jp': False,
            'event_list_kr': False,
        }

        progress_dialog = ExportProgressDialog(self._master, self._get_lang_dict)

        def _progress_cb(cur: int, tot: int, tname: str) -> None:
            safe_after(self._master, 0, lambda: progress_dialog.update_progress(cur, tot, tname))

        def _check_cancelled() -> bool:
            return bool(progress_dialog.is_cancelled)

        finished = False
        def _on_finish() -> None:
            nonlocal finished
            if not finished:
                finished = True
                safe_after(self._master, 0, progress_dialog.close)

        def _run_export() -> None:
            try:
                self._export_func(selected_options, output_folder, _progress_cb, _check_cancelled, _on_finish)
            finally:
                _on_finish()

        thread = threading.Thread(
            target=_run_export,
            daemon=True
        )
        thread.start()

        self.destroy()
