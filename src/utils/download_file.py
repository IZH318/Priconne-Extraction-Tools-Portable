"""외부 파일 다운로드 및 수신 완결성 교차검증 유틸리티 모듈.

모든 다운로드 경로(도구 아카이브, 데이터베이스 등)가 동일한 정책으로 검증되도록
단일 진입점(verified_download)을 제공한다. 검증 항목:
1. HTTP 응답 상태 코드 200 여부.
2. Content-Length 헤더와 실제 수신 바이트 수의 교차 검증(절단 다운로드 탐지).
3. 수신 크기의 max_bytes 상한 초과 여부.
4. 호출자가 주입한 형식 검증기(validator) 통과 여부 (예: ZIP 매직, SQLite 헤더/무결성).
검증을 모두 통과한 파일만 목적지 경로로 안전하게 치환(os.replace)되며,
실패 시 임시 파일은 남기지 않는다.
"""
from __future__ import annotations

import http.client
import logging
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Final

from src.constants import DOWNLOAD_CHUNK_SIZE, TEMP_PART_SUFFIX
from src.exceptions import DownloadError
from src.utils.temp_registry import register_temp_artifact, unregister_temp_artifact

logger = logging.getLogger(__name__)

# 다운로드 허용 최대 크기 기본값 (500MB) - 비정상 대용량 응답 방지
DEFAULT_MAX_DOWNLOAD_BYTES: Final[int] = 500 * 1024 * 1024

_USER_AGENT: Final[str] = "Priconne-Extraction-Tools"


def verified_download(
    url: str,
    dest_path: Path,
    *,
    timeout: float,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    validator: Callable[[Path], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> int:
    """URL에서 파일을 내려받아 완결성/형식 검증 후 안전하게 치환한다.

    검증 항목:
        1. HTTP 응답 상태 코드 200 여부.
        2. Content-Length 헤더가 존재하면 실제 수신 바이트 수와 일치 여부(절단 다운로드 탐지).
        3. 수신 크기가 max_bytes 상한을 초과하지 않는지 여부.
        4. validator 주입 시 임시 파일에 대한 형식/무결성 검증.

    임시 파일에 기록한 뒤 모든 검증을 통과해야 os.replace로 목적지에 반영하므로,
    실패 또는 크래시 시 목적지 경로에는 부분 파일이 남지 않는다.

    Args:
        url (str): 다운로드 대상 URL.
        dest_path (Path): 다운로드 결과를 저장할 로컬 파일 경로.
        timeout (float): 소켓 타임아웃(초).
        max_bytes (int): 허용 최대 다운로드 크기(바이트).
        validator (Callable[[Path], None] | None): 임시 파일 경로를 받아 형식/무결성을
            검증하는 콜백. 실패 시 예외를 발생시켜야 한다.
        progress_cb (Callable[[int, int], None] | None): (수신 바이트, 전체 바이트)
            형태로 진행 상황을 통지받는 콜백. 전체 크기를 알 수 없으면 0이 전달된다.

    Returns:
        int: 실제 수신한 바이트 수.

    Raises:
        DownloadError: HTTP 오류, 크기 초과, 또는 수신 바이트 수가 Content-Length와
            불일치하여 완결성이 확인되지 않은 경우.
        OSError: 네트워크/파일 I/O 오류 (urllib.error.URLError 포함).
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 동일 목적지에 대한 중복 다운로드(다중 인스턴스)가 서로의 임시 파일을 덮어쓰지 않도록 PID 포함
    temp_path = dest.with_name(f"{dest.name}.{os.getpid()}{TEMP_PART_SUFFIX}")
    register_temp_artifact(temp_path)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(temp_path, "wb") as out_file:
            status = getattr(response, "status", 200)
            if status != 200:
                raise DownloadError(f"HTTP Error: {status} {getattr(response, 'reason', '')}")
            headers = getattr(response, "headers", None)
            content_length_raw = headers.get("Content-Length") if headers is not None else None
            expected_length: int | None = None
            if content_length_raw:
                try:
                    expected_length = int(content_length_raw)
                except (TypeError, ValueError):
                    expected_length = None
            if expected_length is not None and expected_length > max_bytes:
                raise DownloadError(f"Download too large: {expected_length} bytes")
            while True:
                try:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                except http.client.IncompleteRead as exc:
                    # 서버가 Content-Length 보다 먼저 연결을 끊은 경우 → 호출자 계약(DownloadError)으로 정규화
                    raise DownloadError(f"Incomplete download: {exc} ({url})") from exc
                if not chunk:
                    break
                received += len(chunk)
                if received > max_bytes:
                    raise DownloadError(f"Download exceeds size limit: {received} bytes > {max_bytes} bytes")
                out_file.write(chunk)
                if progress_cb is not None:
                    progress_cb(received, expected_length or 0)

        # Content-Length ↔ 실수신 바이트 교차 검증
        if expected_length is not None and received != expected_length:
            raise DownloadError(
                f"Incomplete download: received {received} of {expected_length} bytes ({url})"
            )

        # 호출자 주입 형식/무결성 검증 (실패 시 임시 파일은 아래에서 제거됨)
        if validator is not None:
            validator(temp_path)

        # 검증 통과 후에만 목적지로 안전 치환(os.replace)
        os.replace(temp_path, dest)
        unregister_temp_artifact(temp_path)
        return received
    except BaseException:
        # 완결성이 확인되지 않은 부분 다운로드 파일 잔존 방지 (목적지 경로는 불변)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Failed to remove incomplete download %s: %s", temp_path, exc)
        unregister_temp_artifact(temp_path)
        raise
