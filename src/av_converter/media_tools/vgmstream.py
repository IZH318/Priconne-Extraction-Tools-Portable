"""vgmstream 자동 다운로드/설치 모듈."""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from queue import Queue
from typing import Any

from src.constants import (
    DOWNLOAD_SOCKET_TIMEOUT,
    USMTOOLKIT_VERSION_PROBE_TIMEOUT,
    VGMSTREAM_EXE_NAME,
    VGMSTREAM_URL,
    VGMSTREAM_ZIP_FILENAME,
    TabType,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import LogEvent
from src.utils.download_file import verified_download

from ..archive_validation import validate_zip_download
from .probe import _is_executable_usable, ensure_vgmstream_test_exe


class VgmstreamDownloader:
    """vgmstream 자동 다운로드 및 압축 해제 관리 클래스."""

    def __init__(
        self,
        log_queue: Queue[Any],
        vgmstream_dir: Path,
    ) -> None:
        self.log_queue = log_queue
        self.download_dir = vgmstream_dir
        self.vgm_exe_path = self.download_dir / VGMSTREAM_EXE_NAME
        self.target_tab: TabType = 'audio'

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target=self.target_tab, key=log_key, kwargs=kwargs))

    def ensure_ready(self) -> bool:
        """vgmstream-cli.exe 준비 여부 확인 및 부재 시 다운로드와 설치 수행."""
        if _is_executable_usable(self.vgm_exe_path, ["-h"], USMTOOLKIT_VERSION_PROBE_TIMEOUT):
            ensure_vgmstream_test_exe(self.vgm_exe_path)
            self._log_entry('vgmstream_already_exists', path=self.download_dir)
            return True

        self._log_entry('vgmstream_not_found', path=self.download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        local_zip_path = self.download_dir / VGMSTREAM_ZIP_FILENAME

        try:
            self._log_entry('vgmstream_download_start', url=VGMSTREAM_URL)
            verified_download(VGMSTREAM_URL, local_zip_path, timeout=DOWNLOAD_SOCKET_TIMEOUT,
                              validator=validate_zip_download)

            self._log_entry('vgmstream_download_complete')
            self._log_entry('vgmstream_extract_start')

            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                from src.utils.zip_safe import safe_extract
                for member in zip_ref.infolist():
                    if member.is_dir():
                        continue
                    safe_extract(zip_ref, member, self.download_dir)

            # 툴체인(UsmToolkit) 호환성을 위해 vgmstream-cli.exe를 test.exe로 복사
            test_exe = self.download_dir / "test.exe"
            if self.vgm_exe_path.exists() and not test_exe.exists():
                try:
                    shutil.copy2(self.vgm_exe_path, test_exe)
                except OSError:
                    pass

            self._log_entry('vgmstream_extract_complete', path=self.vgm_exe_path)
            return self.vgm_exe_path.is_file()
        except (OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError, RuntimeError, ValueError) as e:
            self._log_entry('vgmstream_download_fail', error=e)
            return False
        finally:
            if local_zip_path.exists():
                try:
                    os.remove(local_zip_path)
                except OSError:
                    pass
