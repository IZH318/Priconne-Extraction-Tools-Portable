"""Story Viewer 서브 도구의 GUI 진입점 프레임 모듈.

메인 노트북(Notebook) 탭 컨테이너의 하위 프레임으로 배치되며, 내부적으로
StoryViewerController를 생성하여 스토리 뷰어 전체 흐름 제어.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .controller import StoryViewerController


class StoryViewerApp(ttk.Frame):
    """Story Viewer 탭의 진입점 프레임 래퍼 클래스.

    메인 애플리케이션의 Notebook 탭 내에서 ttk.Frame으로 동작하며,
    내부적으로 StoryViewerController를 생성하여 View를 구성하고 이벤트 및 비즈니스 로직
    연결.

    Attributes:
        controller (StoryViewerController): 스토리 뷰어 이벤트 및 동작 제어 컨트롤러.
    """

    def __init__(
        self,
        master: ttk.Frame,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
    ) -> None:
        """StoryViewerApp 탭 프레임 초기화 및 컨트롤러 바인딩.

        Args:
            master (ttk.Frame): 상위 컨테이너 위젯 (Notebook 탭 프레임).
            app_lang_var (tk.StringVar | None): 애플리케이션 공용 언어 상태 변수.
            about_info (dict[str, str | int] | None): 프로그램 정보 딕셔너리.
        """
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        # 컨트롤러에서 View를 생성하여 현재 Frame에 배치
        self.controller = StoryViewerController(self, master.winfo_toplevel(), app_lang_var, about_info)

