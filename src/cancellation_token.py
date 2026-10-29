"""협력적 비동기/스레드 취소 제어 토큰 모듈.

장시간 실행되는 백그라운드 작업(파일 변환, 해시 대조, 에셋 언패킹 등)의
취소 신호를 스레드 안전하게 전파하고 진행 중인 작업(In-Flight) 상태를 추적.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class CancellationToken:
    """백그라운드 스레드 및 비동기 작업 취소 제어 토큰.

    내부 threading.Event 및 threading.Lock을 기반으로 다음 기능 제공:
    1. 원자적(Atomic) 취소 신호 전파 (cancel)
    2. 중복 실행 방지를 위한 진행 상태(_in_flight) 추적
    3. 협력적 폴링(is_cancelled)

    Thread Safety:
        모든 상태 변경 및 조회 메서드는 내부 락(_lock)으로 보호되므로
        다중 스레드 환경에서 안전하게 호출 가능.
    """

    def __init__(self) -> None:
        """취소 토큰 초기화."""
        self._event = threading.Event()
        self._lock = threading.Lock()
        # 진행 중인 작업 여부 추적용 플래그
        self._in_flight = False

    def cancel(self) -> None:
        """작업 취소 신호 발생(Event set).

        백그라운드 워커 스레드는 is_cancelled 속성을 주기적으로 확인하여
        안전하게 조기 종료 루틴을 수행해야 함.
        """
        with self._lock:
            self._event.set()

    def reset(self) -> None:
        """취소 신호 초기화 및 신규 작업 시작(In-Flight) 등록.

        Note:
            이전 작업이 끝나지 않은(_in_flight=True) 상태에서 reset() 호출 시
            경고 로그를 기록. 작업 종료 후에는 반드시 finish() 호출 필요.
        """
        with self._lock:
            if self._in_flight:
                logger.warning("Resetting cancellation token while a previous operation was still flagged in flight.")
            self._event.clear()
            self._in_flight = True

    def finish(self) -> None:
        """진행 중인 작업 종료 처리.

        호출 이후 안전하게 다음 작업용 reset() 호출 가능.
        """
        with self._lock:
            self._in_flight = False

    @property
    def is_cancelled(self) -> bool:
        """작업 취소 신호 설정 여부 확인.

        Returns:
            bool: cancel() 호출로 취소 플래그 활성화 시 True.
        """
        with self._lock:
            return self._event.is_set()

