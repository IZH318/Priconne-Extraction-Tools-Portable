"""Manifest File Renamer 프레젠테이션 뷰(View) 모듈.

대상 폴더 선택 바, 프로그레스 바, 시작 버튼 및 읽기 전용 스크롤 로그 콘솔을 렌더링하고,
위젯 레이아웃 구성 및 다국어 텍스트 반영을 전담.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .controller import RenamerController


class RenamerView(ttk.Frame):
    """Renamer 탭의 그래픽 UI 프레젠테이션 뷰 컴포넌트 클래스.

    대상 폴더 선택 입력창, 프로그레스바, 실행 버튼, 스크롤 로그 텍스트 영역을 배치하고
    사용자 조작 이벤트를 컨트롤러로 위임.

    Attributes:
        controller: 상위 MVC 이벤트 조정 컨트롤러 인스턴스.
        progress_label_var: 진행률 상태 텍스트용 StringVar.
        folder_label: 대상 폴더 라벨 위젯.
        folder_entry_var: 현재 작업 대상 디렉터리 경로를 보유하는 StringVar.
        folder_entry: 디렉터리 경로 표시용 읽기 전용 Entry 위젯.
        btn_open_folder: 폴더 선택 다이얼로그 호출 버튼.
        progress_label: 현재 작업 진행 상태 또는 퍼센트 표시 라벨.
        progress_bar: 작업 진행률을 나타내는 프로그레스바 위젯.
        start_button: 파일 이름 복원 작업을 시작하는 실행 버튼.
        log_area: 실행 로그 출력용 ScrolledText 위젯.
    """

    def __init__(self, master: ttk.Frame, controller: RenamerController) -> None:
        """RenamerView 프레임 및 하위 위젯 초기화.

        Args:
            master: 부모 Tk 컨테이너 프레임.
            controller: 사용자 조작 및 데이터 흐름을 처리하는 RenamerController 인스턴스.
        """
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.progress_label_var = tk.StringVar()
        self.create_widgets()

    def create_widgets(self) -> None:
        """프레임 내부의 모든 하위 위젯 생성 및 레이아웃 배치."""
        top_frame = ttk.Frame(self)
        top_frame.pack(padx=10, pady=10, fill=tk.X)

        top_frame.columnconfigure(1, weight=1)

        # 대상 디렉터리 선택 행
        self.folder_label = ttk.Label(top_frame, text="")
        self.folder_label.grid(row=0, column=0, sticky='w', padx=(0, 5), pady=(0, 10))

        self.folder_entry_var = tk.StringVar()
        self.folder_entry = ttk.Entry(top_frame, textvariable=self.folder_entry_var, state='readonly')
        self.folder_entry.grid(row=0, column=1, sticky='ew', padx=(0, 5), pady=(0, 10))

        self.btn_open_folder = ttk.Button(top_frame, text="", command=self.controller.select_folder)
        self.btn_open_folder.grid(row=0, column=2, sticky='ew', padx=(5, 0), pady=(0, 10))

        # 진행률 표시 및 실행 버튼 행
        self.progress_label = ttk.Label(top_frame, textvariable=self.progress_label_var)
        self.progress_label.grid(row=1, column=0, sticky='w', padx=(0, 5))

        self.progress_bar = ttk.Progressbar(top_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress_bar.grid(row=1, column=1, sticky='ew', padx=(0, 5))

        self.start_button = ttk.Button(top_frame, command=self.controller.start_processing_thread)
        self.start_button.grid(row=1, column=2, sticky='ew', padx=(5, 0))

        # 스크롤 가능한 콘솔 로그 텍스트 영역
        self.log_area = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, font=("TkFixedFont", 10), state=tk.DISABLED, padx=5, pady=5
        )
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    def update_ui_text(self) -> None:
        """다국어 사전에 맞추어 모든 라벨 및 버튼 텍스트 일괄 갱신."""
        d = self.controller.get_lang_dict()
        self.start_button.config(text=d.get('start_button', 'Start Process'))
        self.folder_label.config(text=d.get('game_client_folder', 'Select Game Client Folder:'))
        self.btn_open_folder.config(text=d.get('folder_open', 'Open Folder'))

    def set_base_path_text(self, path: str) -> None:
        """대상 디렉터리 경로 입력 위젯 텍스트 갱신.

        Args:
            path: 대상 디렉터리 경로 문자열.
        """
        self.folder_entry_var.set(path)

    def set_progress_text(self, text: str) -> None:
        """프로그레스바 옆 상태 안내 메시지 라벨 텍스트 설정.

        Args:
            text: 상태 안내 또는 파일 수 설명 문자열.
        """
        self.progress_label_var.set(text)

    def set_progress_value(self, value: float) -> None:
        """프로그레스바 게이지 진행률 값 설정 (0.0 - 100.0).

        Args:
            value: 진행률 수치 (0.0 ~ 100.0).
        """
        self.progress_bar['value'] = value

    def set_start_button_state(self, state: str) -> None:
        """시작 버튼의 활성화/비활성화 상태 설정.

        Args:
            state: Tkinter 위젯 상태 ('normal' 또는 'disabled').
        """
        self.start_button.config(state=state)

    def set_folder_button_state(self, state: str) -> None:
        """폴더 탐색 버튼의 활성화/비활성화 상태 설정.

        Args:
            state: Tkinter 위젯 상태 ('normal' 또는 'disabled').
        """
        self.btn_open_folder.config(state=state)

    def write_log(self, text: str) -> None:
        """로그 콘솔의 전체 내용을 주어진 텍스트로 대체하고 최하단으로 스크롤.

        Args:
            text: 출력할 전체 텍스트 내용.
        """
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete('1.0', tk.END)
        self.log_area.insert('1.0', text)
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.see(tk.END)

    def append_log(self, text: str) -> None:
        """로그 콘솔 끝에 새로운 텍스트를 추가하고 최하단으로 스크롤.

        Args:
            text: 추가 출력할 로그 텍스트.
        """
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, text)
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.see(tk.END)
