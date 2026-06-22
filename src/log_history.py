from __future__ import annotations
import tkinter as tk
from typing import Any


class LogHistoryMixin:
    """로그 히스토리 관리 및 재렌더링을 위한 공통 Mixin 클래스입니다.

    언어 변경 시 로그 위젯의 내용을 히스토리 기반으로 다시 그리는
    뼈대 로직을 제공합니다. 각 모듈은 _render_single_entry()를 구현하여
    자신만의 포매팅 로직을 적용할 수 있습니다.

    사용 방법:
        1. Controller 클래스에 이 Mixin을 상속합니다.
        2. _get_log_configs()를 구현하여 (히스토리, 위젯) 쌍을 반환합니다.
        3. _render_single_entry()를 구현하여 단일 로그 항목의 포매팅 로직을 정의합니다.
        4. 언어 변경 시 redraw_all_logs()를 호출합니다.
    """

    def redraw_all_logs(self) -> None:
        """모든 로그 위젯의 내용을 히스토리 기반으로 재렌더링합니다.

        _get_log_configs()가 반환하는 (히스토리, 위젯) 쌍을 순회하며,
        각 위젯을 클리어한 뒤 _render_single_entry()로 항목을 다시 그립니다.
        """
        for history, widget in self._get_log_configs():
            widget.config(state=tk.NORMAL)
            widget.delete('1.0', tk.END)

            for i, entry in enumerate(history):
                self._render_single_entry(entry, i, history, widget)

            widget.config(state=tk.DISABLED)
            widget.see(tk.END)

    def _get_log_configs(self) -> list[tuple[list[Any], tk.Text]]:
        """재렌더링 대상 (히스토리 리스트, Text 위젯) 쌍의 리스트를 반환합니다.

        각 모듈의 Controller에서 오버라이드하여 자신의 로그 히스토리와
        위젯 참조를 반환해야 합니다.

        Returns:
            (히스토리 리스트, Text 위젯) 튜플의 리스트.

        Raises:
            NotImplementedError: 서브클래스에서 구현하지 않은 경우.
        """
        raise NotImplementedError("Subclass must implement _get_log_configs()")

    def _render_single_entry(self, entry: Any, index: int, history: list[Any], widget: tk.Text) -> None:
        """단일 로그 항목을 Text 위젯에 포매팅하여 출력합니다.

        각 모듈의 Controller에서 오버라이드하여 자신만의 포매팅 로직을 구현해야 합니다.

        Args:
            entry: 렌더링할 로그 항목 (모듈마다 형태가 다름).
            index: 히스토리 리스트 내에서의 인덱스.
            history: 전체 히스토리 리스트 (컨텍스트 참조용).
            widget: 로그를 출력할 Text 위젯.

        Raises:
            NotImplementedError: 서브클래스에서 구현하지 않은 경우.
        """
        raise NotImplementedError("Subclass must implement _render_single_entry()")
