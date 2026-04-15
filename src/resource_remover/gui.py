from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Any

from .controller import ResourceRemoverController

class ResourceRemoverApp(ttk.Frame):
    """
    Resource Remover 모듈의 얇은 진입점(Entry Point) 래퍼 클래스입니다.
    이 파일은 하위 호환성을 위한 thin wrapper입니다.
    실제 구현은 controller.py와 view.py를 참조하세요.
    """
    def __init__(self, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)
        
        # Controller가 View 인스턴스를 생성하고 자기 자신을 이 Frame의 자식으로 소속시킵니다.
        self.controller = ResourceRemoverController(self, app_lang_var, about_info)

    def _show_about_info(self) -> None:
        """메인 런처(About 메뉴 등) 외부에서 호출될 수 있는 API"""
        self.controller.show_about_info()
