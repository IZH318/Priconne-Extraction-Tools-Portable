from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
import logging

from src.constants import EXTENSION_CATEGORIES

if TYPE_CHECKING:
    from .controller import ResourceRemoverController

class ResourceRemoverView(ttk.Frame):
    """리소스 삭제 기능의 UI(View)를 담당하는 클래스입니다."""

    def __init__(self, master: ttk.Frame, controller: ResourceRemoverController) -> None:
        """ResourceRemoverView 객체를 초기화합니다.

        Args:
            master: 부모 Tkinter 위젯.
            controller: 비즈니스 로직을 처리하는 컨트롤러 객체.
        """
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.chk_widgets = {}
        self._create_widgets()

    def _create_widgets(self) -> None:
        """뷰의 모든 하위 위젯들을 생성하고 배치합니다."""
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        self.lbl_desc = ttk.Label(container, text="", justify=tk.CENTER)
        self.lbl_desc.pack(pady=(10, 10))

        path_frame = ttk.Frame(container)
        path_frame.pack(fill=tk.X, pady=5, padx=40)
        
        self.entry_path = ttk.Entry(path_frame, textvariable=self.controller.target_path_var, state="readonly")
        self.entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_select_dir = ttk.Button(path_frame, text="", command=self.controller.select_directory)
        self.btn_select_dir.pack(side=tk.RIGHT, padx=(10, 0))

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

        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red")
        self.lbl_warn.pack(pady=(10, 15))

        control_frame = ttk.Frame(container)
        control_frame.pack(fill=tk.X, pady=5, padx=40)
        
        self.chk_trash = ttk.Checkbutton(control_frame, variable=self.controller.use_trash_var, command=self.update_ui_text)
        self.chk_trash.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(control_frame, text="", command=self.controller.start_removal)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        self.lbl_status = ttk.Label(container, textvariable=self.controller.status_var, justify=tk.CENTER)
        self.lbl_status.pack(side=tk.BOTTOM, pady=10)

    def update_ui_text(self) -> None:
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        lang_dict = self.controller.get_lang_dict()

        try:
            self.lbl_desc.config(text=lang_dict.get('desc', 'Description'))
            self.btn_select_dir.config(text=lang_dict.get('btn_select_dir', 'Select Folder'))
            self.chk_frame.config(text=lang_dict.get('chk_frame_title', 'Categories'))
            if self.controller.is_use_trash_enabled:
                self.lbl_warn.config(text=lang_dict.get('warn_trash', 'Files will be moved to the Recycle Bin.'), foreground="blue")
            else:
                self.lbl_warn.config(text=lang_dict.get('warn_permanent', 'Files will be permanently deleted.'), foreground="red")
            self.btn_start.config(text=lang_dict.get('btn_start', 'Start'))
            self.chk_trash.config(text=lang_dict.get('use_trash', 'Move to Recycle Bin'))
        except AttributeError as e:
            logging.debug("ResourceRemoverView UI not fully initialized: %s", e)

        if self.chk_widgets:
            for cat in EXTENSION_CATEGORIES:
                self.chk_widgets[cat["key"]].config(text=lang_dict.get(cat["key"], cat["key"]))

        # 완료 상태면 현재 상태 텍스트를 보존하고, 그 외에는 'ready'로 초기화
        if not self.controller.is_task_complete:
            self.controller.status_var.set(lang_dict.get('status_ready', 'Ready'))

    def set_control_state(self, state: str) -> None:
        """컨트롤(버튼, 체크박스 등)의 활성화/비활성화 상태를 설정합니다.

        Args:
            state: 설정할 상태 문자열 ('normal', 'disabled' 등).
        """
        if hasattr(self, 'btn_start'):
            self.btn_start.config(state=state)
        if hasattr(self, 'chk_trash'):
            self.chk_trash.config(state=state)
        if hasattr(self, 'btn_select_dir'):
            self.btn_select_dir.config(state=state)
        if hasattr(self, 'chk_widgets'):
            for chk in self.chk_widgets.values():
                chk.config(state=state)

    def set_status_color(self, color: str) -> None:
        """상태 메시지 라벨의 텍스트 색상을 설정합니다.

        Args:
            color: 설정할 색상 문자열 (예: 'red', 'black').
        """
        if hasattr(self, 'lbl_status') and self.lbl_status:
            self.lbl_status.config(foreground=color)
