from __future__ import annotations
import threading

from src.exceptions import OperationCancelledError

class CancellationToken:
    """
    백그라운드 스레드 및 비동기 작업의 생명주기(취소)를 안전하게 제어하기 위한 표준화된 객체입니다.
    내부적으로 threading.Event()를 래핑하여 의도를 명확하게 표현하는 API를 제공합니다.
    """
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """작업 취소 신호를 발생시킵니다."""
        self._event.set()

    def reset(self) -> None:
        """작업 취소 신호를 초기화합니다. 새로운 작업을 시작할 때 호출해야 합니다."""
        self._event.clear()

    @property
    def is_cancelled(self) -> bool:
        """작업이 취소되었는지 여부를 확인합니다."""
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        """만약 작업이 취소되었다면 자체적인 예외를 발생시킵니다. (선택적)"""
        if self.is_cancelled:
            raise OperationCancelledError()
