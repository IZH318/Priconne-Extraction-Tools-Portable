"""FFmpeg 버전 정책 헬퍼 및 자동 다운로드/설치 모듈."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from queue import Queue
from typing import Any

from src.constants import (
    DOWNLOAD_SOCKET_TIMEOUT,
    FFMPEG_ACCEPTED_MAJOR,
    FFMPEG_EXE_NAME,
    FFMPEG_MIN_SUPPORTED,
    FFMPEG_TARGET_VERSION,
    FFMPEG_URL,
    FFMPEG_VERSION_MARKER_PATH,
    FFMPEG_VERSION_PROBE_TIMEOUT,
    FFMPEG_ZIP_FILENAME,
    TEMP_FFMPEG_DIR_NAME,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import LogEvent
from src.subprocess_runner import SubprocessRunner
from src.utils.download_file import verified_download
from src.utils.temp_registry import register_temp_artifact, unregister_temp_artifact

from ..archive_validation import validate_zip_download

logger = logging.getLogger(__name__)

_FFMPEG_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

_FFMPEG_MIN_DISPLAY = f"{FFMPEG_MIN_SUPPORTED[0]}.{FFMPEG_MIN_SUPPORTED[1]}"


def parse_ffmpeg_version(version_line: str) -> tuple[int, int, int] | None:
    """ffmpeg `-version` 첫 줄에서 (major, minor, patch) 버전 튜플을 추출.

    예: 'ffmpeg version 7.1.1-essentials_build-www.gyan.dev ...' → (7, 1, 1).
    버전 숫자 패턴이 없으면(N-빌드 등) None 반환.

    Args:
        version_line (str): ffmpeg -version 출력의 첫 줄.

    Returns:
        tuple[int, int, int] | None: 파싱된 버전 튜플. 실패 시 None.
    """
    match = _FFMPEG_VERSION_RE.search(version_line or "")
    if not match:
        return None
    patch = int(match.group(3)) if match.group(3) is not None else 0
    return int(match.group(1)), int(match.group(2)), patch


def classify_ffmpeg_version(parsed: tuple[int, int, int] | None) -> str:
    """파싱된 FFmpeg 버전을 정책에 따라 분류.

    Args:
        parsed (tuple[int, int, int] | None): parse_ffmpeg_version 결과.

    Returns:
        str: not_found(확인 불가) / too_old(최소 지원 미만) / recommend(권장 미만) /
            ok(사용) / newer(신 메이저, 경고) 중 하나.
    """
    if parsed is None:
        return "not_found"
    target = tuple(int(part) for part in FFMPEG_TARGET_VERSION.split("."))
    target = (target + (0, 0, 0))[:3]
    if parsed < FFMPEG_MIN_SUPPORTED:
        return "too_old"
    if parsed >= target:
        return "newer" if parsed[0] > FFMPEG_ACCEPTED_MAJOR else "ok"
    return "recommend"


class FFmpegDownloader:
    """FFmpeg 바이너리 자동 다운로드, 버전 정책 확인 및 완결성 검증 클래스.

    지정된 안정화 버전(FFMPEG_TARGET_VERSION)의 빌드를 공식 미러에서 다운로드하며,
    ZIP 매직 바이트/아카이브 무결성 검증 및 Zip-Slip 방지 안전 압축 해제를 통한 설치 수행.
    """

    def __init__(
        self,
        log_queue: Queue[Any],
        usmtoolkit_path_parent_dir: Path,
        version_marker_path: Path | None = None,
    ) -> None:
        """FFmpegDownloader 인스턴스 초기화.

        Args:
            log_queue (queue.Queue): GUI 통신용 로그 큐.
            usmtoolkit_path_parent_dir (Path): FFmpeg를 설치할 대상 디렉터리 (UsmToolkit 폴더).
            version_marker_path (Path | None): 설치된 버전을 캐싱하는 마커 파일 경로.
        """
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_path_parent_dir
        self.ffmpeg_path = self.download_dir / FFMPEG_EXE_NAME
        self.version_marker_path = version_marker_path or FFMPEG_VERSION_MARKER_PATH
        # False면 사용자가 배치한 버전을 그대로 사용 (기본: 권장 버전으로 맞춤)
        self.prefer_target: bool = True
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.version_marker_path.parent, exist_ok=True)

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target='video', key=log_key, kwargs=kwargs))

    def _read_version_marker(self) -> str | None:
        """버전 마커 파일(.ffmpeg_version) 내용 조회 (부재 또는 읽기 실패 시 None)."""
        if not self.version_marker_path.exists():
            return None
        try:
            return self.version_marker_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _write_version_marker(self, version: str) -> None:
        """버전 마커 파일에 검증된 버전 기록 (실패는 무시)."""
        try:
            self.version_marker_path.write_text(version, encoding="utf-8")
        except OSError:
            pass

    def check_version(self) -> tuple[str, str]:
        """설치된 ffmpeg.exe 버전을 실행 확인하고 정책 분류 결과 반환.

        마커 파일만 신뢰하지 않고 실제 바이너리에 `-version`을 실행한다.

        Returns:
            tuple[str, str]: (classify_ffmpeg_version 결과, 감지된 버전 문자열).
        """
        if not self.ffmpeg_path.exists():
            return "not_found", "not_found"

        # 실제 바이너리 버전을 실행 확인 (마커 단독 신뢰 금지)
        try:
            res = SubprocessRunner.run([str(self.ffmpeg_path), "-version"], timeout=FFMPEG_VERSION_PROBE_TIMEOUT)
            first_line = (res.stdout or "").splitlines()[0] if res.stdout else ""
        except (OSError, subprocess.SubprocessError, ValueError, IndexError, UnicodeDecodeError):  # 실행 실패/타임아웃/파싱 실패 시 unknown
            return "not_found", "unknown"

        parsed = parse_ffmpeg_version(first_line)
        if parsed is None:
            return "not_found", "unknown"

        detected = f"{parsed[0]}.{parsed[1]}.{parsed[2]}"

        # 마커 갱신 (이전 값과 다르면 경고)
        marker_version = self._read_version_marker()
        if marker_version is not None and marker_version != detected:
            logger.warning(
                "ffmpeg version marker mismatch (marker=%r, binary=%r); refreshing marker.",
                marker_version, detected,
            )
        self._write_version_marker(detected)

        return classify_ffmpeg_version(parsed), detected

    def _actual_download_and_extract(self) -> bool:
        """실제 다운로드 및 압축 해제 로직 수행."""
        local_zip_path = self.download_dir / FFMPEG_ZIP_FILENAME
        temp_extract_dir = None

        # 버전 정책 판정
        decision, current_ver = self.check_version()
        if decision in ("ok", "newer"):
            self._log_entry('ffmpeg_already_exists', path=self.download_dir)
            return True
        if decision == "recommend" and not self.prefer_target:
            # 사용자 버전 유지 → 권장 안내만
            self._log_entry('ffmpeg_version_recommended', current=current_ver,
                            target=FFMPEG_TARGET_VERSION, min_supported=_FFMPEG_MIN_DISPLAY)
            return True

        if decision == "not_found":
            self._log_entry('ffmpeg_not_found', path=self.download_dir)
        else:
            self._log_entry('ffmpeg_version_mismatch', current=current_ver,
                            target=FFMPEG_TARGET_VERSION, min_supported=_FFMPEG_MIN_DISPLAY)

        try:
            # 1. 다운로드 (전송 완결성 및 ZIP 형식 검증 후 안전하게 반영)
            self._log_entry('ffmpeg_download_start', url=FFMPEG_URL)
            verified_download(FFMPEG_URL, local_zip_path, timeout=DOWNLOAD_SOCKET_TIMEOUT,
                              validator=validate_zip_download)

            self._log_entry('ffmpeg_download_complete')

            # 2. 압축 해제 및 설치
            self._log_entry('ffmpeg_extract_start')
            temp_extract_dir = self.download_dir / TEMP_FFMPEG_DIR_NAME
            os.makedirs(temp_extract_dir, exist_ok=True)
            register_temp_artifact(temp_extract_dir)
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                # 아카이브(ZIP) 파일 내에서 ffmpeg.exe 경로 탐색
                ffmpeg_internal_path = next((name for name in zip_ref.namelist() if name.endswith(f'/bin/{FFMPEG_EXE_NAME}')), None)
                if not ffmpeg_internal_path:
                    raise FileIntegrityError(str(local_zip_path), "expected folder structure not found in ZIP")
                # 필요한 파일만 안전하게 추출 후 이동 (Zip-Slip 방지)
                from src.utils.zip_safe import safe_extract
                # 문자열 전달 시 심볼릭 링크 검사가 누락될 수 있으므로 ZipInfo로 승격하여 전달
                extracted_path = safe_extract(zip_ref, zip_ref.getinfo(ffmpeg_internal_path), temp_extract_dir)
                extracted_file = extracted_path
                if self.ffmpeg_path.exists():
                    try:
                        os.remove(self.ffmpeg_path)
                    except OSError:
                        pass
                shutil.move(str(extracted_file), str(self.ffmpeg_path))

            # 버전 마커 파일 기록
            self._write_version_marker(FFMPEG_TARGET_VERSION)

            self._log_entry('ffmpeg_extract_complete', path=self.ffmpeg_path)
            return True
        except (OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError, RuntimeError, ValueError) as e:
            self._log_entry('ffmpeg_download_fail', error=e)
            # 실패 시 사용 가능한 기존 버전으로 폴백
            fallback_decision, fallback_ver = self.check_version()
            if fallback_decision in ("ok", "newer"):
                self._log_entry('ffmpeg_already_exists', path=self.download_dir)
                return True
            if fallback_decision == "recommend":
                self._log_entry('ffmpeg_version_recommended', current=fallback_ver,
                                target=FFMPEG_TARGET_VERSION, min_supported=_FFMPEG_MIN_DISPLAY)
                return True
            return False
        finally:
            # 3. 임시 파일 정리
            if local_zip_path.exists():
                try:
                    os.remove(local_zip_path)
                except OSError:
                    pass
            if temp_extract_dir and temp_extract_dir.exists():
                try:
                    shutil.rmtree(temp_extract_dir)
                except OSError:
                    pass
            if temp_extract_dir:
                unregister_temp_artifact(temp_extract_dir)
