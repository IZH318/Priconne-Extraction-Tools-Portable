"""AV Converter 서브 도구의 GUI 진입점 프레임 모듈.

메인 노트북(Notebook) 탭 컨테이너의 하위 프레임으로 배치되며, 내부적으로
AVConverterController를 인스턴스화하여 오디오/비디오 변환 생명주기 구성.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .controller import AVConverterController


class AVConverterApp(ttk.Frame):
    """AV Converter 탭의 진입점 프레임 래퍼 클래스.

    메인 애플리케이션의 Notebook 탭 내에서 ttk.Frame으로 동작하며,
    내부적으로 AVConverterController를 인스턴스화하여 View 생성 및 비즈니스 로직
    바인딩 연결.

    Attributes:
        controller (AVConverterController): 변환기 수명주기 및 이벤트 제어 컨트롤러.
    """

    def __init__(
        self,
        master: ttk.Frame,
        app_lang_var: tk.StringVar | None = None,
        about_info: dict[str, str | int] | None = None,
        app_temp_dir: Path | str | None = None,
    ) -> None:
        """AVConverterApp 탭 프레임 초기화 및 컨트롤러 바인딩.

        Args:
            master (ttk.Frame): 상위 컨테이너 위젯 (Notebook 탭 프레임).
            app_lang_var (tk.StringVar | None): 애플리케이션 공용 언어 상태 변수.
            about_info (dict[str, str | int] | None): 프로그램 정보 딕셔너리.
            app_temp_dir (Path | str | None): 미디어 미리보기 등에 사용할 임시 디렉터리 경로.
        """
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        # 컨트롤러 및 뷰 초기화
        self.controller = AVConverterController(self, master, app_lang_var, about_info, app_temp_dir)

