"""UsmToolkit, vgmstream, FFmpeg 준비 파이프라인 매니저 모듈."""
from __future__ import annotations

import concurrent.futures
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Any

from src.constants import TabType
from src.queue_events import LogEvent
from src.utils.task_pool import DaemonThreadPoolExecutor

from .ffmpeg import FFmpegDownloader
from .usmtoolkit import UsmToolkitDownloader
from .vgmstream import VgmstreamDownloader


class ToolPipelineManager:
    """UsmToolkit, vgmstream, FFmpeg의 순차적 준비를 통합 관리하는 파이프라인 매니저."""

    def __init__(
        self,
        log_queue: Queue[Any],
        base_path: Path,
        on_tools_updated_callback: Callable[[], None] | None = None,
    ) -> None:
        self.log_queue = log_queue
        self.base_path = base_path
        self.on_tools_updated = on_tools_updated_callback
        self._prep_lock = threading.Lock()
        self._prep_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._active_future: concurrent.futures.Future[Any] | None = None
        # 마지막 도구 준비 실패 키 (팝업 안내용)
        self.last_prepare_fail: str | None = None

        self.usmtoolkit_dir = self.base_path / "usmtoolkit"
        self.vgmstream_dir = self.usmtoolkit_dir / "vgmstream"

        self.usmtoolkit_downloader = UsmToolkitDownloader(
            log_queue=self.log_queue,
            usmtoolkit_dir=self.usmtoolkit_dir,
        )
        self.vgmstream_downloader = VgmstreamDownloader(
            log_queue=self.log_queue,
            vgmstream_dir=self.vgmstream_dir,
        )
        self.ffmpeg_downloader = FFmpegDownloader(
            log_queue=self.log_queue,
            usmtoolkit_path_parent_dir=self.usmtoolkit_dir,
        )

    def _log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def ensure_tools_ready(self, tab_type: TabType) -> concurrent.futures.Future[Any]:
        """탭 종류에 맞는 도구 준비 작업을 백그라운드 스레드에서 순차적으로 실행하고 Future 반환."""
        with self._prep_lock:
            if self._active_future is not None and not self._active_future.done():
                return self._active_future
            if self._prep_executor is None:
                self._prep_executor = DaemonThreadPoolExecutor(max_workers=1)
            future = self._prep_executor.submit(self._prepare_pipeline, tab_type)
            self._active_future = future
            return future

    def cleanup(self) -> None:
        with self._prep_lock:
            executor = self._prep_executor
            self._prep_executor = None
            self._active_future = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def _prepare_pipeline(self, tab_type: TabType) -> bool:
        """지정된 탭 타입에 필요한 도구들을 올바른 계층 순서로 준비."""
        self.last_prepare_fail = None
        if tab_type == 'video':
            # 1. UsmToolkit 준비 (usmtoolkit 폴더 생성 및 압축 해제, config/deps 필터링)
            self.usmtoolkit_downloader.target_tab = 'video'
            if not self.usmtoolkit_downloader.ensure_ready():
                self.last_prepare_fail = 'usmtoolkit_prepare_fail'
                self._log_entry('video', 'usmtoolkit_prepare_fail')
                return False

            # 2. vgmstream 준비 (usmtoolkit/vgmstream 폴더에 압축 해제 및 test.exe 복사)
            self.vgmstream_downloader.target_tab = 'video'
            if not self.vgmstream_downloader.ensure_ready():
                self.last_prepare_fail = 'vgmstream_prepare_fail'
                self._log_entry('video', 'vgmstream_prepare_fail')
                return False

            # 3. FFmpeg 준비 (usmtoolkit/ffmpeg.exe)
            if not self.ffmpeg_downloader._actual_download_and_extract():
                self.last_prepare_fail = 'ffmpeg_prepare_fail'
                self._log_entry('video', 'ffmpeg_prepare_fail')
                return False

            if self.on_tools_updated:
                self.on_tools_updated()
            return True

        elif tab_type == 'audio':
            # 1. vgmstream 준비 (usmtoolkit/vgmstream 폴더)
            self.vgmstream_downloader.target_tab = 'audio'
            if not self.vgmstream_downloader.ensure_ready():
                self.last_prepare_fail = 'vgmstream_prepare_fail'
                self._log_entry('audio', 'vgmstream_prepare_fail')
                return False

            if self.on_tools_updated:
                self.on_tools_updated()
            return True

        return False  # type: ignore[unreachable]
