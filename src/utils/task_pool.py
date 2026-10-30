"""앱 종료를 지연시키지 않는 백그라운드 작업 풀 유틸리티.

- `DaemonThreadPoolExecutor`: 워커 스레드를 데몬으로 생성한다. 표준
  `ThreadPoolExecutor`는 비데몬 워커를 사용하므로, 창을 닫아도 실행 중인
  작업이 끝날 때까지 `threading._shutdown()`이 대기해 프로세스가 남는다.
- 프로세스 풀 등록/종료: `ProcessPoolExecutor` 워커는 데몬화할 수 없어
  종료 시 명시적으로 `kill()` 해야 한다. 생성 시 등록해 두고
  `shutdown_registered_process_pools()`를 종료 경로에서 호출한다.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import threading
import weakref
from typing import Any

logger = logging.getLogger(__name__)

try:
    from concurrent.futures import thread as _cf_thread

    _STDLIB_WORKER = _cf_thread._worker
except (ImportError, AttributeError):  # pragma: no cover - 표준 라이브러리 구조 변경 대비
    _cf_thread = None  # type: ignore[assignment]
    _STDLIB_WORKER = None  # type: ignore[assignment]

_POOLS_LOCK = threading.Lock()
_PROCESS_POOLS: set[concurrent.futures.ProcessPoolExecutor] = set()
_POOLS_CLOSED: bool = False


class DaemonThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """워커 스레드를 데몬으로 생성하는 `ThreadPoolExecutor`.

    워커 생성 로직만 표준 구현과 동일하게 유지하면서 `daemon=True`로 바꾼다.
    따라서 진행 중인 작업이 있어도 인터프리터 종료가 대기하지 않는다.
    표준 라이브러리 내부 구조가 달라지면 기본(비데몬) 동작으로 자동 폴백한다.
    """

    def _adjust_thread_count(self) -> None:
        try:
            self._adjust_thread_count_daemon()
        except AttributeError:
            logger.warning(
                "Daemon worker pool unavailable (stdlib layout changed); falling back to default workers",
                exc_info=True,
            )
            super()._adjust_thread_count()

    def _adjust_thread_count_daemon(self) -> None:
        if _STDLIB_WORKER is None:
            raise AttributeError("concurrent.futures.thread._worker unavailable")

        # 표준 구현과 동일: 유휴 워커가 있으면 새로 만들지 않는다.
        if self._idle_semaphore.acquire(timeout=0):
            return

        def weakref_cb(_: Any, q: Any = self._work_queue) -> None:
            q.put(None)

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = "%s_%d" % (self._thread_name_prefix or self, num_threads)
            thread = threading.Thread(
                name=thread_name,
                target=_STDLIB_WORKER,
                args=(
                    weakref.ref(self, weakref_cb),
                    self._create_worker_context(),
                    self._work_queue,
                ),
                daemon=True,
            )
            thread.start()
            self._threads.add(thread)  # type: ignore[attr-defined]
            # 주의: 표준 라이브러리의 _threads_queues에 등록하지 않는다.
            # 등록하면 종료 시 concurrent.futures.thread._python_exit가
            # t.join()으로 진행 중 작업 완료까지 기다려 프로세스가 남는다.


def _terminate_pool(pool: concurrent.futures.ProcessPoolExecutor) -> None:
    """프로세스 풀의 워커 프로세스를 강제 종료하고 대기 작업을 취소."""
    processes = getattr(pool, "_processes", None)
    if processes:
        for proc in list(processes.values()):
            with contextlib.suppress(OSError, ValueError, AttributeError):
                proc.kill()
    else:
        logger.debug("Process pool exposes no worker registry; shutdown without kill")
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except (RuntimeError, ValueError, OSError) as exc:
        logger.debug("Process pool shutdown failed: %s", exc)


def register_process_pool(
    pool: concurrent.futures.ProcessPoolExecutor,
) -> concurrent.futures.ProcessPoolExecutor:
    """종료 시 정리할 프로세스 풀로 등록하고 그대로 반환.

    종료 절차가 이미 시작된 뒤 등록된 풀은 정리 목록에서 누락되므로 즉시 종료한다.
    """
    global _POOLS_CLOSED
    with _POOLS_LOCK:
        closing = _POOLS_CLOSED
        if not closing:
            _PROCESS_POOLS.add(pool)
    if closing:
        logger.warning("Process pool registered during shutdown; terminating immediately")
        _terminate_pool(pool)
    return pool


def unregister_process_pool(pool: concurrent.futures.ProcessPoolExecutor) -> None:
    """이미 정상 종료된 프로세스 풀을 등록부에서 제거."""
    with _POOLS_LOCK:
        _PROCESS_POOLS.discard(pool)


def shutdown_registered_process_pools() -> int:
    """등록된 모든 프로세스 풀의 대기 작업을 취소하고 워커 프로세스를 강제 종료.

    Returns:
        int: 정리한 풀 개수.
    """
    global _POOLS_CLOSED
    with _POOLS_LOCK:
        _POOLS_CLOSED = True
        pools = list(_PROCESS_POOLS)
        _PROCESS_POOLS.clear()

    for pool in pools:
        _terminate_pool(pool)
    if pools:
        logger.info("Shut down %d registered process pool(s) on exit", len(pools))
    return len(pools)
