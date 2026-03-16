# src/resource_remover/gui.py
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from .languages import LANGUAGES
from .logic import ResourceRemoverLogic

# 확장자 카테고리 정의 (체크박스 단위)
EXTENSION_CATEGORIES = [
    {
        "key": "chk_assetbundle",
        "extensions": [".unity3d"],
    },
    {
        "key": "chk_audio",
        "extensions": [".awb", ".acb"],
    },
    {
        "key": "chk_video",
        "extensions": [".usm"],
    },
]

class ResourceRemoverApp(ttk.Frame):
    def __init__(self, master, app_lang_var=None):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.master = master
        self.logic = ResourceRemoverLogic(base_path=".")
        
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.lang_var.trace_add('write', self._on_language_change_event)

        # 체크박스 변수 초기화
        self.chk_vars = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)

        self.setup_ui()
        self._update_ui_text()

    def _on_language_change_event(self, *args):
        try:
            self._update_ui_text()
        except tk.TclError:
            pass

    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        self.lbl_desc = ttk.Label(container, text="", justify=tk.CENTER, font=("", 11))
        self.lbl_desc.pack(pady=(10, 10))

        # 체크박스 프레임
        self.chk_frame = ttk.LabelFrame(container, text="", padding=10)
        self.chk_frame.pack(pady=5, padx=40, fill=tk.X)

        self.chk_widgets = {}
        for cat in EXTENSION_CATEGORIES:
            chk = ttk.Checkbutton(
                self.chk_frame,
                text="",
                variable=self.chk_vars[cat["key"]],
            )
            chk.pack(anchor=tk.W, pady=2)
            self.chk_widgets[cat["key"]] = chk

        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red", font=("", 10))
        self.lbl_warn.pack(pady=(10, 15))

        self.btn_start = ttk.Button(container, text="", command=self.start_removal)
        self.btn_start.pack(pady=10, ipadx=10, ipady=5)

        self.status_var = tk.StringVar()
        self.lbl_status = ttk.Label(container, textvariable=self.status_var, font=("", 9))
        self.lbl_status.pack(side=tk.BOTTOM, pady=10)

    def _update_ui_text(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']

        self.lbl_desc.config(text=lang_dict['desc'])
        self.chk_frame.config(text=lang_dict['chk_frame_title'])
        self.lbl_warn.config(text=lang_dict['warn'])
        self.btn_start.config(text=lang_dict['btn_start'])

        # 체크박스 라벨 업데이트
        for cat in EXTENSION_CATEGORIES:
            self.chk_widgets[cat["key"]].config(text=lang_dict[cat["key"]])

        status_text = self.status_var.get()
        if not status_text or "!" in status_text or "삭제 완료" in status_text or "완료" in status_text or "complete" in status_text or "完了" in status_text:
            pass 
        else:
            self.status_var.set(lang_dict['status_ready'])
            
        if not self.status_var.get():
            self.status_var.set(lang_dict['status_ready'])

    def _get_selected_extensions(self):
        """체크된 카테고리의 확장자 목록을 반환합니다."""
        selected = []
        for cat in EXTENSION_CATEGORIES:
            if self.chk_vars[cat["key"]].get():
                selected.extend(cat["extensions"])
        return selected

    def start_removal(self):
        lang_dict = LANGUAGES[self.lang_var.get()]

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(lang_dict['title'], lang_dict['warn_no_selection'], parent=self)
            return

        # 삭제 전 대상 파일 수와 경로를 미리 확인하여 사용자에게 표시
        file_count, base_path = self.logic.count_resources(selected_exts)
        confirm_msg = lang_dict['confirm_msg'].format(count=file_count, path=base_path)

        if not messagebox.askyesno(lang_dict['confirm_title'], confirm_msg, parent=self):
            return

        try:
            deleted_count = self.logic.remove_resources(extensions=selected_exts)
            self.status_var.set(lang_dict['status_done'].format(count=deleted_count))
            messagebox.showinfo(lang_dict['title'], lang_dict['status_done'].format(count=deleted_count), parent=self)
        except Exception as e:
            self.status_var.set(lang_dict['status_error'].format(error=str(e)))
            messagebox.showerror(lang_dict['title'], lang_dict['status_error'].format(error=str(e)), parent=self)

