from __future__ import annotations
import queue
from typing import Any

from src.constants import GUI_POLLING_INTERVAL_MS


class QueuePollingMixin:
    """큐 기반 메인-스레드 이벤트 폴링 인프라를 제공하는 Mixin 클래스.

    백그라운드 스레드에서 큐에 넣은 이벤트를 tkinter 메인 스레드에서
    주기적으로 꺼내 처리하는 공통 패턴을 추상화합니다.

    사용법:
        1. Controller 클래스에 이 Mixin을 추가 상속합니다.
        2. __init__에서 ``_init_queue_polling(widget)`` 을 호출합니다.
        3. ``_on_poll_cycle()`` 을 오버라이드하여 이벤트 처리 로직을 구현합니다.
        4. ``cleanup()`` 에서 ``_stop_polling()`` 을 호출합니다.

    각 Controller 인스턴스는 자기만의 Mixin 상태(큐, 타이머 등)를 가지므로,
    여러 모듈 탭이 동시에 작업을 실행해도 완벽하게 독립적으로 작동합니다.
    """

    _polling_active: bool = False
    _polling_widget: Any = None
    _polling_interval_ms: int = GUI_POLLING_INTERVAL_MS

    def _init_queue_polling(self, polling_widget: Any, interval_ms: int = GUI_POLLING_INTERVAL_MS) -> None:
        """큐 폴링 인프라를 초기화하고 첫 폴링 사이클을 예약합니다.

        Args:
            polling_widget: tkinter의 ``after()`` 메서드를 제공하는 위젯
                            (일반적으로 ``self.view`` 또는 ``self.frame``).
            interval_ms: 폴링 간격 (밀리초). 기본값은 ``GUI_POLLING_INTERVAL_MS``.
        """
        self._polling_widget = polling_widget
        self._polling_interval_ms = interval_ms
        self._polling_active = True
        self._polling_widget.after(self._polling_interval_ms, self._poll_queue)

    def _poll_queue(self) -> None:
        """폴링 루프의 한 사이클을 실행합니다.

        ``_on_poll_cycle()`` 을 호출한 뒤, ``_polling_active`` 가 True이면
        다음 사이클을 자동으로 예약합니다. 하위 클래스에서 직접 호출하거나
        오버라이드할 필요가 없습니다.
        """
        if not self._polling_active:
            return
        try:
            self._on_poll_cycle()
        finally:
            if self._polling_active:
                self._polling_widget.after(self._polling_interval_ms, self._poll_queue)

    def _on_poll_cycle(self) -> None:
        """폴링 사이클마다 호출되는 훅 메서드입니다.

        하위 클래스에서 반드시 오버라이드하여, 큐에서 이벤트를 꺼내고
        적절한 처리 로직을 구현해야 합니다. ``_drain_queue()`` 유틸리티를
        활용하면 큐 드레인 보일러플레이트를 줄일 수 있습니다.

        Raises:
            NotImplementedError: 하위 클래스에서 구현하지 않은 경우.
        """
        raise NotImplementedError("하위 클래스에서 _on_poll_cycle()을 구현해야 합니다.")

    def _stop_polling(self) -> None:
        """폴링 루프를 중지합니다.

        ``cleanup()`` 에서 호출하여 앱 종료 시 불필요한 타이머 재등록을 방지합니다.
        """
        self._polling_active = False

    @staticmethod
    def _drain_queue(q: queue.Queue) -> list[Any]:
        """큐에 쌓인 모든 이벤트를 한 번에 꺼내 리스트로 반환합니다.

        ``queue.Empty`` 예외를 내부적으로 처리하므로 호출자가
        별도의 try/except 블록을 작성할 필요가 없습니다.

        Note:
            ``multiprocessing.Queue.empty()`` 는 Python 공식 문서에서
            신뢰할 수 없다고 명시되어 있으므로, ``empty()`` 체크 대신
            ``get_nowait()`` + ``queue.Empty`` 예외 루프를 사용합니다.

        Args:
            q: 이벤트를 꺼낼 큐 객체 (``queue.Queue`` 또는
               ``multiprocessing.Manager().Queue()``).

        Returns:
            큐에서 꺼낸 이벤트의 리스트 (빈 큐인 경우 빈 리스트).
        """
        items: list[Any] = []
        while True:
            try:
                items.append(q.get_nowait())
            except queue.Empty:
                break
        return items
