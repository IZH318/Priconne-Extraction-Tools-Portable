"""UsmToolkit 실행용 .NET Runtime 준비 모듈."""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path
from queue import Queue
from typing import Any

from src.constants import (
    DOWNLOAD_SOCKET_TIMEOUT,
    DOTNET_EXE_NAME,
    DOTNET_RUNTIME_DIR_NAME,
    DOTNET_RUNTIME_PROBE_TIMEOUT,
    DOTNET_RUNTIME_SHA512,
    DOTNET_RUNTIME_URL,
    DOTNET_RUNTIME_ZIP_FILENAME,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import LogEvent
from src.utils.download_file import verified_download

from ..archive_validation import validate_zip_download
from .probe import (
    _is_executable_usable,
    collect_system_dotnet_runtimes,
    find_satisfying_dotnet_runtime,
    is_dotnet_force_local_runtime,
)


def _validate_dotnet_runtime_zip(temp_path: Path) -> None:
    """다운로드한 .NET Runtime ZIP의 아카이브 무결성과 SHA-512 체크섬을 함께 검증.

    verified_download의 validator 콜백으로 사용되어, 형식과 해시를 모두 통과한
    아카이브만 목적지 경로로 안전하게 치환되도록 보장한다.

    Args:
        temp_path (Path): 검증할 ZIP 임시 파일 경로.

    Raises:
        FileIntegrityError: ZIP 형식 오류 또는 SHA-512 체크섬 불일치 시.
    """
    validate_zip_download(temp_path)
    digest = hashlib.sha512()
    with open(temp_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != DOTNET_RUNTIME_SHA512.lower():
        raise FileIntegrityError(str(temp_path), ".NET Runtime ZIP SHA-512 checksum mismatch")


class DotnetRuntimeDownloader:
    """.NET Runtime 자동 다운로드 및 압축 해제 관리 클래스."""

    def __init__(
        self,
        log_queue: Queue[Any],
        usmtoolkit_dir: Path,
    ) -> None:
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_dir / DOTNET_RUNTIME_DIR_NAME
        self.dotnet_exe_path = self.download_dir / DOTNET_EXE_NAME

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target='video', key=log_key, kwargs=kwargs))

    def ensure_ready(self) -> bool:
        """UsmToolkit 실행용 .NET Runtime 준비 여부 확인 및 부재 시 다운로드와 압축 해제 수행."""
        # 1. 시스템 런타임 우선 확인 (요구 버전 이상이면 그대로 사용, 다운로드 생략)
        if not is_dotnet_force_local_runtime():
            satisfied = find_satisfying_dotnet_runtime(collect_system_dotnet_runtimes())
            if satisfied is not None:
                self._log_entry('dotnet_system_runtime_found', version=satisfied)
                return True

        # 2. 로컬 런타임 재사용 (이미 준비되어 있으면 사용)
        if _is_executable_usable(self.dotnet_exe_path, ["--list-runtimes"], DOTNET_RUNTIME_PROBE_TIMEOUT):
            self._log_entry('dotnet_already_exists', path=self.download_dir)
            return True

        # 3. 로컬 런타임 다운로드 및 압축 해제 (시스템에 없을 때)
        self._log_entry('dotnet_not_found', path=self.download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        local_zip_path = self.download_dir / DOTNET_RUNTIME_ZIP_FILENAME

        try:
            self._log_entry('dotnet_download_start', url=DOTNET_RUNTIME_URL)
            verified_download(DOTNET_RUNTIME_URL, local_zip_path, timeout=DOWNLOAD_SOCKET_TIMEOUT,
                              validator=_validate_dotnet_runtime_zip)

            self._log_entry('dotnet_download_complete')
            self._log_entry('dotnet_extract_start')

            # 런타임 ZIP은 최상위 폴더 없이 평면 구조이므로 각 엔트리를 안전하게 추출 (Zip-Slip 방지)
            from src.utils.zip_safe import safe_extract
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    if member.is_dir():
                        continue
                    safe_extract(zip_ref, member, self.download_dir)

            self._log_entry('dotnet_extract_complete', path=self.dotnet_exe_path)
            return self.dotnet_exe_path.is_file()
        except (OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError, RuntimeError, ValueError) as e:
            self._log_entry('dotnet_download_fail', error=e)
            return False
        finally:
            if local_zip_path.exists():
                try:
                    os.remove(local_zip_path)
                except OSError:
                    pass
