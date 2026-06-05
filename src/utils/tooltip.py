from __future__ import annotations
import tkinter as tk

class ToolTip:
    """Tkinter 위젯에 툴팁을 추가하는 유틸리티 클래스입니다."""
    
    def __init__(self, widget: tk.Widget, text: str) -> None:
        """ToolTip 객체를 초기화합니다.

        Args:
            widget: 툴팁을 추가할 Tkinter 위젯.
            text: 툴팁에 표시할 텍스트.
        """
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = 0
        self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event: tk.Event | None = None) -> None:
        """마우스가 위젯 영역에 들어올 때 호출되는 이벤트 핸들러입니다.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
        """
        self.x = self.widget.winfo_rootx() + 20
        self.y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.id = self.widget.after(500, self.show_tip)

    def leave(self, event: tk.Event | None = None) -> None:
        """마우스가 위젯 영역에서 나갈 때 호출되는 이벤트 핸들러입니다.

        Args:
            event: Tkinter 이벤트 객체 (기본값: None).
        """
        self.hide_tip()

    def show_tip(self) -> None:
        """지정된 딜레이 후 툴팁 창을 화면에 표시합니다."""
        if self.tip_window or not self.text:
            return
        if str(self.widget.cget('state')) == 'disabled':
            return
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{self.x}+{self.y}")

        label = tk.Label(self.tip_window, text=self.text, background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font="TkDefaultFont")
        label.pack(ipadx=1)

    def hide_tip(self) -> None:
        """표시된 툴팁 창을 숨기거나 예약된 툴팁 표시 이벤트를 취소합니다."""
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None
