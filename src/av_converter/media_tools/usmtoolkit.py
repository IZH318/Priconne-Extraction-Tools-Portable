"""UsmToolkit 자동 다운로드/설치 모듈."""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from queue import Queue
from typing import Any

from src.constants import (
    DOWNLOAD_SOCKET_TIMEOUT,
    USMTOOLKIT_EXE_NAME,
    USMTOOLKIT_URL,
    USMTOOLKIT_VERSION_PROBE_TIMEOUT,
    USMTOOLKIT_ZIP_FILENAME,
    TabType,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import LogEvent
from src.utils.download_file import verified_download

from ..archive_validation import validate_zip_download
from .probe import _is_executable_usable


class UsmToolkitDownloader:
    """UsmToolkit 자동 다운로드 및 압축 해제 관리 클래스."""

    def __init__(
        self,
        log_queue: Queue[Any],
        usmtoolkit_dir: Path,
    ) -> None:
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_dir
        self.usm_exe_path = self.download_dir / USMTOOLKIT_EXE_NAME
        self.target_tab: TabType = 'video'

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target=self.target_tab, key=log_key, kwargs=kwargs))

    def ensure_ready(self) -> bool:
        """UsmToolkit.exe 준비 여부 확인 및 부재 시 다운로드와 설치 수행."""
        if _is_executable_usable(self.usm_exe_path, ["--version"], USMTOOLKIT_VERSION_PROBE_TIMEOUT):
            self._log_entry('usmtoolkit_already_exists', path=self.download_dir)
            return True

        self._log_entry('usmtoolkit_not_found', path=self.download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        local_zip_path = self.download_dir / USMTOOLKIT_ZIP_FILENAME

        try:
            self._log_entry('usmtoolkit_download_start', url=USMTOOLKIT_URL)
            verified_download(USMTOOLKIT_URL, local_zip_path, timeout=DOWNLOAD_SOCKET_TIMEOUT,
                              validator=validate_zip_download)

            self._log_entry('usmtoolkit_download_complete')
            self._log_entry('usmtoolkit_extract_start')

            # 설정 파일(config.json, deps.json)을 제외하고 압축 해제 (Zip-Slip 방지)
            from src.utils.zip_safe import safe_extract
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    base_name = os.path.basename(member.filename).lower()
                    if base_name in {"config.json", "deps.json"}:
                        continue
                    if member.is_dir():
                        continue
                    safe_extract(zip_ref, member, self.download_dir)

            # 압축 해제 후 기본 최적화 config.json이 없으면 생성
            config_file = self.download_dir / "config.json"
            if not config_file.exists():
                default_config = {
                    "VideoParameter": "-c:v libx264 -crf 14 -bf 2 -preset medium -pix_fmt yuv420p -tune animation -deblock 1:1",
                    "AudioParameter": "-c:a aac -b:a 320k -ac 2",
                    "OutputFormat": "mp4"
                }
                config_file.write_text(json.dumps(default_config, indent=4), encoding="utf-8")

            # 혹시 deps.json이 존재한다면 삭제하여 오해 방지
            deps_file = self.download_dir / "deps.json"
            if deps_file.exists():
                try:
                    os.remove(deps_file)
                except OSError:
                    pass

            self._log_entry('usmtoolkit_extract_complete', path=self.usm_exe_path)
            return self.usm_exe_path.is_file()
        except (OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError, RuntimeError, ValueError) as e:
            self._log_entry('usmtoolkit_download_fail', error=e)
            return False
        finally:
            if local_zip_path.exists():
                try:
                    os.remove(local_zip_path)
                except OSError:
                    pass
