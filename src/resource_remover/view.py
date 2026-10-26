"""Resource Remover 그래픽 사용자 인터페이스(View) 모듈.

대상 폴더 경로 입력 필드, 리소스 확장자 카테고리 체크박스(chk_assetbundle, chk_audio, chk_video),
휴지통 이동 여부 토글(use_trash), 실행 버튼 및 상태 라벨을 렌더링하고 다국어 텍스트를 일괄 갱신.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from src.constants import EXTENSION_CATEGORIES

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .controller import ResourceRemoverController


class ResourceRemoverView(ttk.Frame):
    """리소스 파일 안전 삭제 도구의 Tkinter GUI 뷰 컴포넌트."""

    def __init__(self, master: ttk.Frame, controller: ResourceRemoverController) -> None:
        """ResourceRemoverView 초기화 및 위젯 생성/배치.

        Args:
            master (ttk.Frame): 상위 Tkinter 노트북 탭 프레임.
            controller (ResourceRemoverController): 비즈니스 이벤트 처리 및 모델 바인딩을 담당하는 컨트롤러.
        """
        super().__init__(master)
        self.controller = controller
        self.pack(fill=tk.BOTH, expand=True)

        self.chk_widgets: dict[str, Any] = {}
        self._create_widgets()

    def _create_widgets(self) -> None:
        """폴더 선택, 확장자 체크박스 그룹, 제어 버튼 및 상태 라벨 위젯 조립."""
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        self.lbl_desc = ttk.Label(container, text="", justify=tk.CENTER)
        self.lbl_desc.pack(pady=(10, 10))

        # 1. 대상 디렉터리 경로 프레임
        path_frame = ttk.Frame(container)
        path_frame.pack(fill=tk.X, pady=5, padx=40)

        self.entry_path = ttk.Entry(path_frame, textvariable=self.controller.target_path_var, state="readonly")
        self.entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_select_dir = ttk.Button(path_frame, text="", command=self.controller.select_directory)
        self.btn_select_dir.pack(side=tk.RIGHT, padx=(10, 0))

        # 2. 리소스 카테고리 체크박스 그룹
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

        # 3. 위험 경고 라벨 (휴지통 사용 시 파란색 안내, 영구 삭제 시 빨간색 경고)
        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red")
        self.lbl_warn.pack(pady=(10, 15))

        # 4. 제어 옵션 및 실행 버튼 프레임
        control_frame = ttk.Frame(container)
        control_frame.pack(fill=tk.X, pady=5, padx=40)

        self.chk_trash = ttk.Checkbutton(control_frame, variable=self.controller.use_trash_var, command=self.update_ui_text)
        self.chk_trash.pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(control_frame, text="", command=self.controller.start_removal)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

        # 5. 하단 작업 상태 알림 라벨
        self.lbl_status = ttk.Label(container, textvariable=self.controller.status_var, justify=tk.CENTER)
        self.lbl_status.pack(side=tk.BOTTOM, pady=10)

    def update_ui_text(self) -> None:
        """현재 선택된 언어 사전에 따라 모든 라벨, 버튼 및 체크박스의 텍스트 일괄 갱신."""
        lang_dict = self.controller.get_lang_dict()

        try:
            self.lbl_desc.config(text=lang_dict.get('desc', 'Delete the following original resource files, including subdirectories, based on the selected path:'))
            self.btn_select_dir.config(text=lang_dict.get('btn_select_dir', 'Select Folder'))
            self.chk_frame.config(text=lang_dict.get('chk_frame_title', 'Select file types to delete'))
            if self.controller.is_use_trash_enabled:
                self.lbl_warn.config(text=lang_dict.get('warn_trash', '※ Files will be safely moved to the Recycle Bin.'), foreground="blue")
            else:
                self.lbl_warn.config(text=lang_dict.get('warn_permanent', '※ Files are permanently deleted without going to the Recycle Bin.'), foreground="red")
            self.btn_start.config(text=lang_dict.get('btn_start', 'Start Removing Resources'))
            self.chk_trash.config(text=lang_dict.get('use_trash', 'Move to Recycle Bin'))
        except AttributeError as e:
            logger.debug("ResourceRemoverView UI not fully initialized: %s", e)

        if self.chk_widgets:
            for cat in EXTENSION_CATEGORIES:
                self.chk_widgets[cat["key"]].config(text=lang_dict.get(cat["key"], cat["key"]))

        # 작업 완료 상태가 아닌 경우에만 'ready' 상태 문자열로 리셋
        if not self.controller.is_task_complete:
            self.controller.status_var.set(lang_dict.get('status_ready', 'Ready...'))

    def set_control_state(self, state: str) -> None:
        """작업 진행 중 사용자 입력 제어를 위해 시작 버튼, 체크박스들의 활성화 상태 변경.

        Args:
            state (str): 적용할 Tkinter 위젯 상태 ('normal' 또는 'disabled').
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
        """하단 상태 안내 메시지 라벨의 텍스트 색상 동적 변경.

        Args:
            color (str): 설정할 색상 문자열 (예: 'green', 'red', 'black').
        """
        if hasattr(self, 'lbl_status') and self.lbl_status:
            self.lbl_status.config(foreground=color)

