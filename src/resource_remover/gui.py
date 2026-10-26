from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .controller import ResourceRemoverController


class ResourceRemoverApp(ttk.Frame):
    """Resource Remover 탭 컨테이너 프레임 및 GUI 래퍼 클래스.

    메인 애플리케이션 Notebook 위젯에 독립 탭으로 임베드.
    ResourceRemoverController와 연동하여 뷰 배치 및 수명주기 관리.

    Attributes:
        controller: ResourceRemoverController 인스턴스.
    """

    def __init__(
        self,
        master: ttk.Frame,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
    ) -> None:
        """Resource Remover 탭 프레임 및 컨트롤러 초기화.

        Args:
            master: 부모 위젯 (ttk.Notebook 탭 프레임).
            app_lang_var: 전역 언어 설정 추적 Tk 변수 ('ko', 'en', 'ja').
            about_info: 프로그램 정보 대화상자용 메타데이터 딕셔너리.
        """
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        # 컨트롤러 초기화 및 뷰 연결
        self.controller = ResourceRemoverController(self, master, app_lang_var, about_info)
