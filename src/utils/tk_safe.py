"""Tkinter 위젯 생명주기 안전 조작 및 스레드 마샬링 유틸리티 모듈.

백그라운드 스레드에서 발생한 UI 갱신 요청을 메인 스레드로 안전하게 전달하기 위한
전역 UI 콜백 큐(post_to_ui / drain_ui_callbacks)를 제공한다.
Tkinter/Tcl은 스레드 안전하지 않으므로 워커 스레드는 위젯을 직접 조작하거나
after()/winfo_exists()를 호출해서는 안 되며, 반드시 post_to_ui()로 큐에 추가한 뒤
메인 스레드(QueuePollingMixin._poll_queue 등)에서 drain_ui_callbacks()로 소비해야 한다.
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 워커 스레드 → 메인 스레드 UI 콜백 전달용 전역 큐
_ui_callback_queue: queue.Queue[Callable[[], None]] = queue.Queue()

# 1회 드레인에서 실행할 최대 콜백 수 (콜백이 다시 콜백을 예약하는 경우 UI 독점 방지)
_MAX_CALLBACKS_PER_DRAIN: int = 200


def post_to_ui(callback: Callable[[], None]) -> None:
    """워커 스레드에서 메인 스레드로 UI 콜백 실행을 안전하게 위임.

    메인 스레드에서 호출되면 즉시 실행하고, 그 외 스레드에서 호출되면 전역 큐에
    추가하여 메인 스레드의 drain_ui_callbacks() 호출 시 실행한다.
    Tk 위젯/after()를 워커 스레드에서 직접 호출하지 않기 위한 단일 통로.

    Args:
        callback (Callable[[], None]): 메인 스레드에서 실행할 콜백 함수.
    """
    if threading.current_thread() is threading.main_thread():
        try:
            callback()
        except Exception:
            logger.exception("UI callback failed")
        return
    _ui_callback_queue.put(callback)


def post_to_ui_deferred(callback: Callable[[], None]) -> None:
    """메인 스레드에서 호출해도 다음 드레인 주기로 실행을 미루는 UI 콜백 예약.

    위젯 상태 변경이 현재 처리 중인 UI 흐름과 분리되어야 하는 경우(예: DB 점검 완료
    콜백)에 사용한다. 워커 스레드에서는 post_to_ui와 동일하게 동작한다.

    Args:
        callback (Callable[[], None]): 메인 스레드에서 실행할 콜백 함수.
    """
    _ui_callback_queue.put(callback)


def drain_ui_callbacks() -> None:
    """메인 스레드에서 대기 중인 UI 콜백을 일괄 실행.

    QueuePollingMixin._poll_queue 등 메인 스레드 타이머에서 주기적으로 호출한다.
    개별 콜백에서 예외가 발생해도 다른 콜백 실행에 영향을 주지 않도록 보호하며, 콜백이 다시 콜백을
    예약하는 경우에도 UI 스레드가 한 주기에 독점되지 않도록 처리 개수를 제한한다
    (남은 콜백은 다음 폴링 주기에 이어서 처리).
    """
    for _ in range(_MAX_CALLBACKS_PER_DRAIN):
        try:
            callback = _ui_callback_queue.get_nowait()
        except queue.Empty:
            return
        try:
            callback()
        except Exception:
            logger.exception("Deferred UI callback failed")
