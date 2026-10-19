from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from .controller import RenamerController

class FileRenamerGUI(ttk.Frame):
    """
    MVC 패턴이 적용된 Renamer 모듈의 진입점(Entry Point) 래퍼 클래스입니다.
    이 파일은 하위 호환성을 위한 thin wrapper입니다.
    실제 구현은 controller.py와 view.py를 참조하세요.
    """
    def __init__(self, master: ttk.Frame, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        # MVC 패턴 핵심: 화면과 로직을 조율할 Controller 인스턴스화
        # frame(self)에는 View가 배치되고, master는 다이얼로그 위치 기준으로 사용됩니다.
        self.controller = RenamerController(self, master, app_lang_var, about_info)

