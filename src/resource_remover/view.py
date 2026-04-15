from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Any

from src.constants import EXTENSION_CATEGORIES

class ResourceRemoverView(ttk.Frame):
    def __init__(self, master: Any, controller: Any) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.chk_widgets = {}
        self._create_widgets()

    def _create_widgets(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        self.lbl_desc = ttk.Label(container, text="", justify=tk.CENTER, font=("TkDefaultFont", 10))
        self.lbl_desc.pack(pady=(10, 10))

        self.chk_frame = ttk.LabelFrame(container, text="", padding=10)
        self.chk_frame.pack(pady=5, padx=40, fill=tk.X)

        for cat in EXTENSION_CATEGORIES:
            chk = ttk.Checkbutton(
                self.chk_frame,
                text="",
                variable=self.controller.chk_vars[cat["key"]],
            )
            chk.pack(anchor=tk.W, pady=2)
            self.chk_widgets[cat["key"]] = chk

        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red", font=("TkDefaultFont", 10))
        self.lbl_warn.pack(pady=(10, 15))

        control_frame = ttk.Frame(container)
        control_frame.pack(fill='x', pady=5)
        
        self.chk_trash = ttk.Checkbutton(control_frame, variable=self.controller.use_trash_var, command=self.update_ui_text)
        self.chk_trash.pack(side='left', padx=5)

        self.btn_start = ttk.Button(control_frame, text="", command=self.controller.start_removal)
        self.btn_start.pack(side='right', padx=5)

        self.lbl_status = ttk.Label(container, textvariable=self.controller.status_var, font=("TkDefaultFont", 10))
        self.lbl_status.pack(side=tk.BOTTOM, pady=10)

    def update_ui_text(self) -> None:
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()

        try:
            self.lbl_desc.config(text=lang_dict['desc'])
            self.chk_frame.config(text=lang_dict['chk_frame_title'])
            if self.controller.use_trash_var.get():
                self.lbl_warn.config(text=lang_dict.get('warn_trash', 'Files will be moved to the Recycle Bin.'), foreground="blue")
            else:
                self.lbl_warn.config(text=lang_dict.get('warn_permanent', 'Files will be permanently deleted.'), foreground="red")
            self.btn_start.config(text=lang_dict['btn_start'])
            self.chk_trash.config(text=lang_dict.get('use_trash', 'Move to Recycle Bin'))
        except AttributeError:
            pass

        if self.chk_widgets:
            for cat in EXTENSION_CATEGORIES:
                self.chk_widgets[cat["key"]].config(text=lang_dict[cat["key"]])

        # 완료 상태면 현재 상태 텍스트를 보존하고, 그 외에는 'ready'로 초기화
        if not self.controller.is_complete:
            if not self.controller.status_var.get():
                self.controller.status_var.set(lang_dict['status_ready'])

    def set_control_state(self, state: str) -> None:
        if hasattr(self, 'btn_start'):
            self.btn_start.config(state=state)
        if hasattr(self, 'chk_trash'):
            self.chk_trash.config(state=state)

    def set_status_color(self, color: str) -> None:
        if hasattr(self, 'lbl_status') and self.lbl_status:
            self.lbl_status.config(foreground=color)
