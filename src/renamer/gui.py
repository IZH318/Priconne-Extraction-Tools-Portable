"""Manifest File Renamer 탭 컨테이너 프레임 모듈.

메인 애플리케이션 노트북 위젯의 독립 탭으로 마운트되며,
하위 컨트롤러(RenamerController)에 비즈니스 및 프레젠테이션 로직을 위임.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .controller import RenamerController


class FileRenamerGUI(ttk.Frame):
    """Manifest File Renamer 탭 컨테이너 프레임 및 엔트리포인트 래퍼 클래스.

    메인 애플리케이션 Notebook 위젯에 독립 탭으로 통합되며,
    작업 흐름 제어를 RenamerController에 위임.

    Attributes:
        controller: RenamerController 인스턴스.
    """

    def __init__(
        self,
        master: ttk.Frame,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
    ) -> None:
        """FileRenamerGUI 초기화 및 컨트롤러 연결.

        Args:
            master: 부모 Tk 위젯 (일반적으로 ttk.Notebook 탭 프레임).
            app_lang_var: 전역 언어 설정 감지용 StringVar ('ko', 'en', 'ja' 등).
            about_info: 어바웃 다이얼로그용 프로그램 메타데이터 딕셔너리.
        """
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        # 컨트롤러 초기화 및 뷰 연결
        self.controller = RenamerController(self, master, app_lang_var, about_info)
