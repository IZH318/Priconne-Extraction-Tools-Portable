# src/resource_remover/gui.py
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from .languages import LANGUAGES
from .logic import ResourceRemoverLogic

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
        self.lbl_desc.pack(pady=(10, 5))

        self.lbl_ext = ttk.Label(container, text="", justify=tk.LEFT, font=("", 10, "bold"))
        self.lbl_ext.pack(pady=5)

        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red", font=("", 10))
        self.lbl_warn.pack(pady=(5, 15))

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
        self.lbl_ext.config(text=lang_dict['ext_list'])
        self.lbl_warn.config(text=lang_dict['warn'])
        self.btn_start.config(text=lang_dict['btn_start'])
        
        status_text = self.status_var.get()
        if not status_text or "!" in status_text or "삭제 완료" in status_text or "완료" in status_text or "complete" in status_text or "完了" in status_text:
            pass 
        else:
            self.status_var.set(lang_dict['status_ready'])
            
        if not self.status_var.get():
            self.status_var.set(lang_dict['status_ready'])

    def start_removal(self):
        lang_dict = LANGUAGES[self.lang_var.get()]
        
        if not messagebox.askyesno(lang_dict['confirm_title'], lang_dict['confirm_msg'], parent=self):
            return

        try:
            deleted_count = self.logic.remove_resources()
            self.status_var.set(lang_dict['status_done'].format(count=deleted_count))
            messagebox.showinfo(lang_dict['title'], lang_dict['status_done'].format(count=deleted_count), parent=self)
        except Exception as e:
            self.status_var.set(lang_dict['status_error'].format(error=str(e)))
            messagebox.showerror(lang_dict['title'], lang_dict['status_error'].format(error=str(e)), parent=self)
