from __future__ import annotations
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import RenamerController

class RenamerView(ttk.Frame):
    """
    MVC 아키텍처 중 View(화면 렌더링)를 전담하는 클래스입니다.
    비즈니스 로직을 전혀 알지 못하며, UI 위젯의 생성과 텍스트 업데이트만 수행합니다.
    버튼 이벤트 등은 Controller에게 전달합니다.
    """
    def __init__(self, master: ttk.Frame, controller: RenamerController) -> None:
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.progress_label_var = tk.StringVar()
        self.create_widgets()

    def create_widgets(self) -> None:
        """뷰의 모든 하위 위젯들을 생성하고 배치합니다."""
        top_frame = ttk.Frame(self)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        
        top_frame.columnconfigure(1, weight=1)
        
        self.folder_label = ttk.Label(top_frame, text="")
        self.folder_label.grid(row=0, column=0, sticky='w', padx=(0, 5), pady=(0, 10))
        
        self.folder_entry_var = tk.StringVar()
        self.folder_entry = ttk.Entry(top_frame, textvariable=self.folder_entry_var, state='readonly')
        self.folder_entry.grid(row=0, column=1, sticky='ew', padx=(0, 5), pady=(0, 10))
        
        self.btn_open_folder = ttk.Button(top_frame, text="", command=self.controller.select_folder)
        self.btn_open_folder.grid(row=0, column=2, sticky='ew', padx=(5, 0), pady=(0, 10))

        self.progress_label = ttk.Label(top_frame, textvariable=self.progress_label_var)
        self.progress_label.grid(row=1, column=0, sticky='w', padx=(0, 5))
        
        self.progress_bar = ttk.Progressbar(top_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.grid(row=1, column=1, sticky='ew', padx=(0, 5))
        
        self.start_button = ttk.Button(top_frame, command=self.controller.start_processing_thread)
        self.start_button.grid(row=1, column=2, sticky='ew', padx=(5, 0))
        
        self.log_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("TkFixedFont", 10), state=tk.DISABLED, padx=5, pady=5)
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    def update_ui_text(self) -> None:
        """현재 선택된 언어에 맞춰 UI 텍스트를 업데이트합니다."""
        d = self.controller.get_lang_dict()
        self.start_button.config(text=d['start_button'])
        self.folder_label.config(text=d['game_client_folder'])
        self.btn_open_folder.config(text=d['folder_open'])
        
    def set_base_path_text(self, path: str) -> None:
        self.folder_entry_var.set(path)
        
    def set_progress_text(self, text: str) -> None:
        self.progress_label_var.set(text)

    def set_progress_value(self, value: float) -> None:
        self.progress_bar['value'] = value
        
    def set_start_button_state(self, state: str) -> None:
        self.start_button.config(state=state)

    def write_log(self, text: str) -> None:
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete('1.0', tk.END)
        self.log_area.insert('1.0', text)
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.see(tk.END)

    def append_log(self, text: str) -> None:
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, text)
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.see(tk.END)
