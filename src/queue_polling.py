"""Tkinter 메인 스레드 이벤트 큐 폴링(Queue Polling) 인프라 모듈.

Tkinter 단일 스레드 제약 극복을 위해, 백그라운드 스레드 및 멀티프로세스가
이벤트 큐에 적재한 메시지를 메인 GUI 스레드에서 주기적으로 꺼내 처리(Drain)하는
QueuePollingMixin 클래스 제공.
"""
from __future__ import annotations

import logging
import queue
import tkinter as tk
from typing import Any

from src.constants import GUI_POLLING_INTERVAL_MS

logger = logging.getLogger(__name__)


class QueuePollingMixin:
    """큐 기반 메인-스레드 이벤트 폴링 인프라 제공 믹스인(Mixin) 클래스.

    백그라운드 스레드나 프로세스에서 큐에 넣은 이벤트(QueueEvent)를
    Tkinter 메인 이벤트 루프(after) 활용 논블로킹 방식으로 주기적 수신.

    사용법:
        1. Controller 클래스 선언부에 QueuePollingMixin 다중 상속.
        2. __init__에서 self._init_queue_polling(widget) 호출로 폴링 시작.
        3. _on_poll_cycle() 메서드 오버라이드로 큐 이벤트 처리 및 뷰 갱신 구현.
        4. Controller의 cleanup()에서 self._stop_polling() 호출로 타이머 해제.

    Thread Safety:
        각 Controller 인스턴스는 독자적 타이머 ID(_polling_after_id)와 활성 플래그를 유지하므로,
        다수 탭(모듈) 동시 백그라운드 작업 실행 시 상호 간섭 없는 독립 동작 보장.
    """

    def _init_queue_polling(self, polling_widget: Any, interval_ms: int = GUI_POLLING_INTERVAL_MS) -> None:
        """큐 폴링 인프라 초기화 및 첫 번째 폴링 사이클 등록.

        Args:
            polling_widget (Any): after() 메서드를 제공하는 Tkinter 위젯 (예: Controller view 또는 frame).
            interval_ms (int): 폴링 반복 주기 (밀리초 단위). 기본값 constants.GUI_POLLING_INTERVAL_MS (100ms).
        """
        self._polling_widget = polling_widget
        self._polling_interval_ms = interval_ms
        self._polling_active = True
        self._polling_after_id = None
        if polling_widget is not None:
            try:
                self._polling_after_id = polling_widget.after(interval_ms, self._poll_queue)
            except (tk.TclError, RuntimeError):
                self._polling_active = False

    def _is_polling_needed(self) -> bool:
        """하위 호환성 유지용 메서드. 항상 True(상시 폴링 모드) 반환.

        Returns:
            bool: 항상 True.
        """
        return True

    def _resume_polling(self) -> None:
        """폴링 일시 중지 또는 비활성 상태 시 폴링 사이클 재개."""
        if not getattr(self, "_polling_active", False):
            self._polling_active = True
            widget = getattr(self, "_polling_widget", None)
            interval = getattr(self, "_polling_interval_ms", GUI_POLLING_INTERVAL_MS)
            if widget is not None:
                try:
                    self._polling_after_id = widget.after(interval, self._poll_queue)
                except (tk.TclError, RuntimeError):
                    self._polling_active = False

    def _poll_queue(self) -> None:
        """폴링 루프 단일 사이클 실행.

        하위 클래스 _on_poll_cycle() 안전 호출 후,
        _polling_active 플래그 유지 시 다음 사이클 after() 예약.
        """
        if not getattr(self, "_polling_active", False):
            return
        try:
            self._on_poll_cycle()
        except Exception:
            logger.exception("Poll cycle failed")
        finally:
            if getattr(self, "_polling_active", False):
                try:
                    widget = getattr(self, "_polling_widget", None)
                    interval = getattr(self, "_polling_interval_ms", GUI_POLLING_INTERVAL_MS)
                    if widget is not None:
                        self._polling_after_id = widget.after(interval, self._poll_queue)
                except (tk.TclError, RuntimeError):
                    self._polling_active = False

    def _on_poll_cycle(self) -> None:
        """폴링 주기마다 호출되는 추상 훅(Hook) 메서드.

        하위 클래스(Controller) 필수 오버라이드 대상. 큐 이벤트 처리 및 UI 갱신 로직 구현 필요.

        Raises:
            NotImplementedError: 하위 클래스에서 이 메서드를 오버라이드하지 않은 경우.
        """
        raise NotImplementedError("Subclass must implement _on_poll_cycle().")

    def _stop_polling(self) -> None:
        """진행 중 폴링 루프 즉시 중지 및 예약 after 타이머 취소 수행.

        Controller cleanup() 단계 호출로 위젯 파괴 후 타이머 콜백 실행 방지(Tkinter TclError 방어).
        """
        self._polling_active = False
        after_id = getattr(self, "_polling_after_id", None)
        widget = getattr(self, "_polling_widget", None)
        if after_id is not None and widget is not None:
            try:
                widget.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
        self._polling_after_id = None

    @staticmethod
    def _drain_queue(q: queue.Queue) -> list[Any]:
        """큐 누적 이벤트 논블로킹(Non-blocking) 일괄 드레인 및 리스트 반환.

        queue.Empty 예외 내부 처리 및 프로세스 종료 시 발생 가능한
        BrokenPipeError, EOFError, OSError 안전 흡수.

        Note:
            multiprocessing.Queue.empty() 경쟁 상태(Race Condition) 회피를 위해
            empty() 검사 대신 get_nowait() 및 예외 트랩 루프 적용.

        Args:
            q (queue.Queue): 이벤트를 드레인할 큐 객체 (queue.Queue 또는 multiprocessing.Queue).

        Returns:
            list[Any]: 큐에서 꺼낸 모든 이벤트 객체 리스트 (빈 큐인 경우 빈 리스트).
        """
        items: list[Any] = []
        while True:
            try:
                items.append(q.get_nowait())
            except (queue.Empty, EOFError, OSError, BrokenPipeError):
                break
        return items

