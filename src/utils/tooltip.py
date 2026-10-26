"""Tkinter 마우스 호버(Hover) 안내 툴팁(ToolTip) 컴포넌트 모듈.

버튼, 입력 필드 등 UI 위젯에 마우스를 올렸을 때 500ms 지연 후
테두리 없는 경량 팝업(wm_overrideredirect) 노출 및 마우스 이탈 또는
위젯 파괴 시 잔여 타이머 안전 취소.
"""
from __future__ import annotations

import tkinter as tk


class ToolTip:
    """Tkinter 위젯 대상 반응형 마우스 안내 툴팁 바인딩 유틸리티 클래스.

    마우스 커서 위젯 진입(<Enter>) 시 500ms 지연 타이머 시작,
    마우스 이탈(<Leave>) 또는 위젯 비활성화(state='disabled') 시
    툴팁 노출 억제.
    """

    def __init__(self, widget: tk.Widget, text: str) -> None:
        """ToolTip 초기화 및 대상 위젯 마우스 이벤트 바인딩.

        Args:
            widget (tk.Widget): 툴팁을 부착할 Tkinter 위젯 인스턴스.
            text (str): 툴팁 팝업에 표시할 도움말 문자열.
        """
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        self.id: str | None = None
        self.x: int = 0
        self.y: int = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<Destroy>", lambda e: self.hide_tip())

    def enter(self, event: tk.Event | None = None) -> None:
        """마우스 커서 위젯 영역 내 진입 시 호출되는 핸들러.

        위젯 화면 절대 좌표 계산 기반 툴팁 위치 설정 및 500ms 후 show_tip 예약.

        Args:
            event (tk.Event | None): Tkinter 마우스 진입 이벤트 객체.
        """
        try:
            if not self.widget.winfo_exists():
                return
            self.x = self.widget.winfo_rootx() + 20
            self.y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            self.id = self.widget.after(500, self.show_tip)
        except tk.TclError:
            return

    def leave(self, event: tk.Event | None = None) -> None:
        """마우스 커서가 위젯 영역 밖으로 벗어날 때 호출되는 핸들러.

        Args:
            event (tk.Event | None): Tkinter 마우스 이탈 이벤트 객체.
        """
        self.hide_tip()

    def show_tip(self) -> None:
        """지연 시간 경과 후 화면 테두리 없는 툴팁 최상위 윈도우(Toplevel) 생성."""
        if self.tip_window or not self.text:
            return
        try:
            if str(self.widget.cget('state')) == 'disabled':
                return
        except tk.TclError:
            return
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{self.x}+{self.y}")

        label = tk.Label(
            self.tip_window,
            text=self.text,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font="TkDefaultFont",
        )
        label.pack(ipadx=1)

    def hide_tip(self) -> None:
        """예약 툴팁 타이머 취소 및 화면 표시 중인 툴팁 윈도우 안전 파기 수행."""
        if self.id:
            try:
                self.widget.after_cancel(self.id)
            except tk.TclError:
                pass
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None

