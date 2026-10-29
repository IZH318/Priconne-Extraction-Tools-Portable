"""AV Converter 비즈니스 로직 및 툴체인 다운로드/검증 엔진 모듈.

CRI Sofdec (.usm) 비디오 디먹싱 및 H.264/AAC MP4 인코딩,
CRI Atom (.awb) 멀티트랙 오디오 디코딩 및 WAV 변환 로직과 함께,
외부 툴체인(FFmpeg, UsmToolkit, vgmstream)의 자동 다운로드, ZIP 완결성 검증(매직
바이트 및 아카이브 무결성 테스트), Zip-Slip 경로 순회 방지 압축 해제 및 .NET Core 런타임
환경 감지 기능 제공.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from src.cancellation_token import CancellationToken

logger = logging.getLogger(__name__)

from src.constants import (
    AV_TEMP_EXTENSIONS,
    DOTNET_RUNTIME_PROBE_TIMEOUT,
    DOWNLOAD_SOCKET_TIMEOUT,
    FFMPEG_ACCEPTED_MAJOR,
    FFMPEG_EXE_NAME,
    FFMPEG_MIN_SUPPORTED,
    FFMPEG_TARGET_VERSION,
    FFMPEG_URL,
    FFMPEG_VERSION_MARKER_PATH,
    FFMPEG_VERSION_PROBE_TIMEOUT,
    FFMPEG_ZIP_FILENAME,
    SENTINEL_AUDIO_DONE,
    SENTINEL_VIDEO_DONE,
    SUBPROCESS_AUDIO_CONVERT_TIMEOUT,
    SUBPROCESS_PREVIEW_TIMEOUT,
    SUBPROCESS_VIDEO_CONVERT_TIMEOUT,
    USMTOOLKIT_EXE_NAME,
    USMTOOLKIT_URL,
    USMTOOLKIT_VERSION_PROBE_TIMEOUT,
    USMTOOLKIT_ZIP_FILENAME,
    VGMSTREAM_EXE_NAME,
    VGMSTREAM_URL,
    VGMSTREAM_ZIP_FILENAME,
    TabType,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import CompletionEvent, LogBlockEvent, LogEvent, ProgressEvent
from src.subprocess_runner import SubprocessRunner
from src.utils.download_file import verified_download
from src.utils.task_pool import DaemonThreadPoolExecutor
from src.utils.temp_registry import register_temp_artifact, unregister_temp_artifact

FULLWIDTH_CHAR_MAP: Final[dict[str, str]] = {
    '\\': '＼',  # U+FF3C
    '/':  '／',  # U+FF0F
    ':':  '：',  # U+FF1A
    '*':  '＊',  # U+FF0A
    '?':  '？',  # U+FF1F
    '"':  '＂',  # U+FF02
    '<':  '＜',  # U+FF1C
    '>':  '＞',  # U+FF1E
    '|':  '｜',  # U+FF5C
}

_test_exe_lock = threading.Lock()


def ensure_vgmstream_test_exe(vgm_exe_path: Path | None) -> None:
    """vgmstream-cli.exe를 UsmToolkit 호환용 test.exe로 복사 (스레드 락 보호).

    UsmToolkit은 내부적으로 vgmstream을 호출할 때 test.exe라는 고정 이름을 기대하므로,
    동일 디렉터리에 사본이 존재하지 않을 경우 안전하게 복제.

    Args:
        vgm_exe_path (Path | None): vgmstream-cli.exe의 파일 경로.
    """
    if vgm_exe_path is None:
        return
    vgm_path = Path(vgm_exe_path)
    if not vgm_path.is_file():
        return
    test_exe = vgm_path.parent / "test.exe"
    with _test_exe_lock:
        if test_exe.exists():
            return
        try:
            shutil.copy2(vgm_path, test_exe)
        except OSError:
            pass


def sanitize_stream_filename(name: str) -> str:
    """Windows 파일시스템 금지 문자를 전각 유니코드 문자로 치환 및 유효한 파일명으로 정제.

    Args:
        name (str): 원본 오디오 스트림 또는 큐 시트 이름.

    Returns:
        str: Windows 예약 특수문자 및 제어문자가 제거/치환된 안전한 파일명.
    """
    table = str.maketrans(FULLWIDTH_CHAR_MAP)
    sanitized = name.translate(table)
    sanitized = re.sub(r'[\x00-\x1f]', '', sanitized)
    return sanitized.strip('. ')


def expected_output_extension(usmtoolkit_dir: Path) -> str:
    """usmtoolkit/config.json 의 OutputFormat 을 읽어 실제 출력 파일 확장자를 결정.

    UsmToolkit 은 동일 폴더의 config.json 값을 사용해 인코딩/먹싱을 수행하므로,
    이 값과 기대 확장자가 어긋나면 성공한 변환을 실패로 오판하게 된다.

    Args:
        usmtoolkit_dir (Path): UsmToolkit.exe 가 위치한 폴더 경로.

    Returns:
        str: 점(.) 없는 소문자 확장자. 파일 미존재/파싱 실패 시 기본값 'mp4'.
    """
    try:
        config = json.loads((usmtoolkit_dir / "config.json").read_text(encoding="utf-8"))
        fmt = str(config.get("OutputFormat", "mp4")).strip().lstrip(".").lower()
    except (OSError, ValueError, AttributeError):
        return "mp4"
    return fmt if fmt.isalnum() else "mp4"


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


def validate_zip_download(temp_path: Path) -> None:
    """다운로드한 ZIP 임시 파일의 매직 바이트 및 엔트리 무결성을 검증.

    verified_download의 validator 콜백으로 사용되어, 형식 검증을 통과한
    아카이브만 목적지 경로로 안전하게 치환(원자적 이동)되도록 보장한다.

    Args:
        temp_path (Path): 검증할 ZIP 임시 파일 경로.

    Raises:
        FileIntegrityError: ZIP 매직 바이트('PK') 불일치 시.
        zipfile.BadZipFile: 아카이브 내 손상된 엔트리 발견 시.
    """
    with open(temp_path, 'rb') as f:
        magic = f.read(4)
    if magic[:2] != b'PK':
        raise FileIntegrityError(str(temp_path), "not a valid ZIP archive (magic bytes mismatch)")
    with zipfile.ZipFile(temp_path, 'r') as zip_test:
        # Zip Bomb(과도한 압축률) 검사를 먼저 수행해 불필요한 압축 해제 방지
        from src.utils.zip_safe import UnsafeZipMemberError, validate_zip_limits
        try:
            validate_zip_limits(zip_test)
        except UnsafeZipMemberError as exc:
            raise FileIntegrityError(str(temp_path), str(exc)) from exc
        bad_file = zip_test.testzip()
        if bad_file is not None:
            raise zipfile.BadZipFile(f"ZIP archive integrity check failed: corrupted entry '{bad_file}'.")


class ConversionLogic:
    """오디오/비디오 일괄 변환 및 메타데이터 추출 엔진 클래스.

    시스템 CPU 코어 기반 워커 스레드 풀을 관리하며, 서브프로세스를 통해 외부 바이너리를 실행하고
    진행 상태 및 로그 이벤트를 통신 큐로 전송.
    """

    # 시스템 CPU 코어 수의 절반을 최대 워커 스레드 수로 설정 (과도한 부하 방지)
    cpu_threads: int = (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or os.cpu_count() or 1
    MAX_WORKERS: int = max(1, cpu_threads // 2)


    @staticmethod
    def _snapshot_directory(directory: Path) -> set[str]:
        """서브프로세스 실행 직전 디렉터리 내 파일명 스냅샷 생성 (중간 파일 정리 보호용).

        변환/디먹싱 작업 완료 후에는 이 스냅샷에 없던 파일만 중간 임시 파일로 간주하여
        삭제하므로, 작업 이전부터 존재하던 사용자 파일은 삭제 대상에서 제외됨.

        Args:
            directory (Path): 스냅샷 대상 디렉터리 경로.

        Returns:
            set[str]: 소문자 파일명 집합. 디렉터리 부재 또는 스캔 실패 시 빈 집합.
        """
        if not directory.exists() or not directory.is_dir():
            return set()
        try:
            return {item.name.lower() for item in directory.iterdir() if item.is_file()}
        except OSError as exc:
            logger.debug("Failed to snapshot dir %s: %s", directory, exc)
            return set()

    @staticmethod
    def _cleanup_intermediate_files(
        directory: Path,
        stem: str,
        pre_existing: set[str],
        protected_stems: set[str] | None = None,
    ) -> None:
        """USM 디먹싱 및 변환 시 생성된 중간 임시 파일(.adx, .wav, .m2v, .bin 등) 안전 삭제.

        단일 스트림 파일(예: movie.wav)뿐만 아니라 다중 오디오 스트림 인덱스가 붙은
        파생 파일(예: movie_0.adx, movie_1.wav)까지 정확히 탐지하여 제거하되,
        작업 시작 전 스냅샷(pre_existing)에 이미 존재하던 파일은 사용자 원본일 수 있으므로 삭제 제외.
        같은 배치에서 함께 변환 중인 다른 입력의 stem(protected_stems)은 그 작업이 직접
        정리하도록 남겨두어, 동시 실행 중인 작업의 중간 파일을 삭제하지 않는다.

        Args:
            directory (Path): 정리 대상 디렉터리 경로.
            stem (str): 중간 임시 파일 접두어로 사용할 원본 파일 stem.
            pre_existing (set[str]): 작업 시작 전 스냅샷된 파일명(소문자) 집합.
            protected_stems (set[str] | None): 보호할 다른 입력 파일의 stem 집합(대소문자 무시).
        """
        if not directory.exists() or not directory.is_dir():
            return
        prefix = f"{stem}_"
        protected = {value.lower() for value in protected_stems} if protected_stems else set()
        try:
            for item in directory.iterdir():
                if not item.is_file():
                    continue
                if item.suffix.lower() not in AV_TEMP_EXTENSIONS:
                    continue
                # 작업 이전부터 존재하던 파일(사용자 원본 등)은 삭제 대상에서 제외
                if item.name.lower() in pre_existing:
                    continue
                # 1. 확장자만 다른 동일 파일명 (단일 스트림: movie.m2v, movie.wav 등)
                if item.name == f"{stem}{item.suffix}":
                    removable = True
                # 2. 접두사 + 숫자 (다중 오디오 스트림: movie_0.adx 등)
                #    다른 입력의 stem 과 겹치면 그 작업의 중간 파일이므로 남겨둔다.
                elif item.stem.startswith(prefix) and item.stem[len(prefix):].isdigit():
                    removable = item.stem.lower() not in protected
                else:
                    removable = False
                if removable:
                    try:
                        os.remove(item)
                    except OSError as exc:
                        logger.debug("Failed to remove temp file %s: %s", item, exc)
        except OSError as exc:
            logger.debug("Failed to scan temp dir: %s", exc)

    @staticmethod
    def _is_valid_output_file(path: Path) -> bool:
        """변환 출력 파일의 유효성(존재 + 비어 있지 않음) 검사.

        Args:
            path (Path): 검사할 출력 파일 경로.

        Returns:
            bool: 0바이트보다 큰 일반 파일이면 True.
        """
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    @staticmethod
    def _quarantine_output(path: Path) -> None:
        """변환 실패 시 0바이트 파일은 삭제하고 부분 출력 파일은 '.partial'로 보존.

        완성됐을 수도 있는 파일을 실수로 삭제하지 않으면서, 다음 실행이 손상/부분
        미완성 파일을 '이미 변환됨'으로 오인하지 않도록 별도 이름으로 옮긴다.

        Args:
            path (Path): 실패한 변환의 출력 파일 경로.
        """
        try:
            if not path.is_file():
                return
            if path.stat().st_size > 0:
                os.replace(path, path.with_name(path.name + ".partial"))
            else:
                os.remove(path)
        except OSError as exc:
            logger.debug("Failed to quarantine incomplete output %s: %s", path, exc)

    @staticmethod
    def _discard_quarantined_output(path: Path) -> None:
        """변환 성공 시 기존 '.partial' 임시 파일이 남아 있으면 제거.

        Args:
            path (Path): 성공한 변환의 출력 파일 경로.
        """
        try:
            partial = path.with_name(path.name + ".partial")
            if partial.is_file():
                os.remove(partial)
        except OSError as exc:
            logger.debug("Failed to remove quarantined output %s: %s", partial, exc)

    def __init__(self, log_queue: queue.Queue, base_path: Path) -> None:
        """ConversionLogic 인스턴스 초기화.

        Args:
            log_queue (queue.Queue): GUI 통신용 큐.
            base_path (Path): 프로그램 실행 기준 경로.
        """
        self.log_queue = log_queue
        self.base_path = base_path

    def _log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def get_relative_path(self, full_path: str | Path) -> str:
        """로그에 표시할 파일의 상대 경로 계산."""
        try:
            return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError):
            return str(full_path)

    def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """외부 프로세스를 실행하고 출력을 캡처하는 헬퍼 함수."""
        return SubprocessRunner.run(command, timeout=SUBPROCESS_AUDIO_CONVERT_TIMEOUT)

    @staticmethod
    def get_installed_dotnet_runtimes() -> list[str]:
        """`dotnet --list-runtimes`로 조회한 .NET Runtime (Microsoft.NETCore.App) 버전 목록 반환."""
        versions: list[str] = []
        dotnet_exe = shutil.which('dotnet')
        if dotnet_exe and Path(dotnet_exe).is_file():
            try:
                res = SubprocessRunner.run([dotnet_exe, '--list-runtimes'], timeout=DOTNET_RUNTIME_PROBE_TIMEOUT)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == 'Microsoft.NETCore.App':
                            versions.append(f"{parts[0]} {parts[1]}")
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                logger.debug("Failed to list dotnet runtimes: %s", exc)
        seen = set()
        result = []
        for v in versions:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result

    def _convert_single_video_task(
        self,
        usm_file_str: str,
        output_dir: str,
        usmtoolkit_path: Path,
        target_stem: str | None = None,
        protected_stems: set[str] | None = None,
    ) -> tuple[str, list[tuple[str, dict]]]:
        """
        단일 비디오(.usm) 파일을 변환하는 작업 태스크.

        Args:
            usm_file_str (str): 변환할 USM 파일 경로.
            output_dir (str): 출력 디렉터리 경로.
            usmtoolkit_path (Path): UsmToolkit.exe 파일 경로.
            target_stem (str | None): 출력 파일 stem. 동일 stem 입력 충돌 시 호출자가
                입력 경로 기반 접미사를 붙여 전달하며, None이면 원본 stem을 사용.
            protected_stems (set[str] | None): 같은 배치의 다른 입력 stem 집합.
                해당 stem 의 중간 파일은 그 작업이 직접 정리하도록 남겨둔다.

        Returns:
            tuple: (변환 상태 문자열, 로그 항목 리스트)
        """
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        output_path = Path(output_dir)
        out_stem = target_stem or usm_file.stem
        output_ext = expected_output_extension(usmtoolkit_dir)
        final_mp4_path = output_path / f"{out_stem}.{output_ext}"
        # 동일 stem 충돌 시: UsmToolkit은 입력 stem 이름으로 출력 파일을 만들므로
        # 작업별 임시 폴더에서 변환한 뒤 최종 경로로 이동한다.
        is_duplicate_stem = out_stem != usm_file.stem
        run_dir = output_path / f".avtmp_{out_stem}" if is_duplicate_stem else output_path

        log_entries = [('spacing', {}),
                       ('conv_log_source', {'path': self.get_relative_path(usm_file)})]
        status = "unknown"

        log_entries.append(('spacing', {}))

        # 이미 변환된 파일은 건너뛰기 (0바이트/손상 파일은 재변환 대상)
        if self._is_valid_output_file(final_mp4_path):
            log_entries.append(('conv_log_result_header', {}))
            log_entries.append(('conv_log_skipped', {}))
            status = "skipped"
        else:
            if is_duplicate_stem:
                try:
                    run_dir.mkdir(parents=True, exist_ok=True)
                    register_temp_artifact(run_dir)
                except OSError as dir_exc:
                    logger.debug("Failed to create duplicate-stem temp dir %s: %s", run_dir, dir_exc)
            command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(run_dir.resolve())]
            # 디먹싱 시작 전 소스 폴더 스냅샷 (기존 사용자 파일을 중간 파일로 오인 삭제하지 않도록)
            pre_existing_files = self._snapshot_directory(usm_file.parent)
            try:
                # 외부 UsmToolkit 프로세스 실행
                result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_VIDEO_CONVERT_TIMEOUT)

                log_entries.append(('conv_log_result_header', {}))

                # 중복 stem 대응: 임시 폴더에 생성된 출력 파일을 최종 경로로 안전하게 이동
                if is_duplicate_stem:
                    produced_path = run_dir / f"{usm_file.stem}.{output_ext}"
                    try:
                        if produced_path.is_file():
                            os.replace(produced_path, final_mp4_path)
                    except OSError as move_exc:
                        logger.debug("Failed to move duplicate-stem output %s: %s", produced_path, move_exc)

                # 종료 코드와 출력 파일 유효성(존재 + 비어 있지 않음)을 함께 검증
                if result.returncode == 0 and self._is_valid_output_file(final_mp4_path):
                    status = "success"
                    log_entries.append(('conv_log_success', {'path': self.get_relative_path(final_mp4_path)}))

                    # 성공 시, 스택 트레이스를 제외한 유용한 로그만 파싱 및 추가
                    raw_output = (result.stdout or "").strip()
                    if raw_output:
                        filtered_log_lines = []
                        for line in raw_output.splitlines():
                            # 스택 트레이스 시작 패턴이나 FATAL ERROR를 만나면 로그 기록 중단
                            if line.strip().startswith('at ') or 'FATAL ERROR:' in line:
                                break
                            filtered_log_lines.append(line)

                        if filtered_log_lines:
                            log_entries.append(('raw', {'text': ''}))
                            log_entries.append(('conv_log_details_header', {}))
                            log_entries.extend([('raw', {'text': f"    > {line}"}) for line in filtered_log_lines])

                    raw_stderr = (result.stderr or "").strip()
                    if raw_stderr:
                        filtered_stderr = [line for line in raw_stderr.splitlines() if line.strip()]
                        if filtered_stderr:
                            log_entries.append(('raw', {'text': ''}))
                            log_entries.extend([('raw', {'text': f"    > {line}"}) for line in filtered_stderr])

                    # 이전 실패로 남은 미완성 파일(.partial) 제거 (중간 파일은 finally 에서 정리)
                    self._discard_quarantined_output(final_mp4_path)
                else:
                    status = "error"
                    log_entries.append(('conv_log_error_fail', {'filename': usm_file.name}))

                    # 실패 시 프로세스 오류 로그 추가
                    error_output = (result.stderr or result.stdout or "No process output.").strip()
                    if error_output:
                        log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])

                    # 미완성 출력 파일 처리 (내용 있는 파일은 .partial 보존, 0바이트만 삭제)
                    self._quarantine_output(final_mp4_path)

            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, AttributeError, KeyError, TypeError) as e:
                status = "error"
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_exception', {'error': str(e)}))
                self._quarantine_output(final_mp4_path)
            finally:
                # 성공/실패/타임아웃 어느 경로에서도 디먹싱 중간 파일을 정리한다.
                # (UsmToolkit 은 정상 완료 시 스스로 정리하므로, 이 정리는 중단/실패 대비 안전망이다)
                self._cleanup_intermediate_files(
                    usm_file.parent, usm_file.stem, pre_existing_files, protected_stems
                )
                if is_duplicate_stem:
                    shutil.rmtree(run_dir, ignore_errors=True)
                    unregister_temp_artifact(run_dir)

        log_entries.append(('spacing', {}))
        return status, log_entries

    def run_video_conversion(
        self,
        input_paths: list[str],
        output_dir: str,
        usmtoolkit_path: Path | None,
        cancel_token: CancellationToken | None,
    ) -> None:
        """비디오(.usm) 변환 작업 총괄 및 스레드 풀 작업 분배 실행.

        각 USM 파일을 비동기로 UsmToolkit에 전달하여 MP4로 디먹싱/인코딩하며,
        중간에 취소 요청이 발생하면 즉시 미시작 태스크를 취소하고 대기.
        완료 시 통계 요약 및 실패 파일 목록을 CompletionEvent로 전송.

        Args:
            input_paths (list[str]): 변환할 대상 USM 파일 경로 목록.
            output_dir (str): MP4 결과물을 저장할 출력 폴더 경로.
            usmtoolkit_path (Path | None): UsmToolkit.exe 실행 바이너리 경로.
            cancel_token (CancellationToken | None): 작업 취소 감시용 토큰.
        """
        target_tab: TabType = 'video'
        self._log_entry(target_tab, 'conv_start_video')
        self._log_entry(target_tab, 'conv_video_skip_notice')

        if not usmtoolkit_path:
            self._log_entry(target_tab, 'conv_error_usmtoolkit_not_found')
            self.log_queue.put(CompletionEvent(target=SENTINEL_VIDEO_DONE))
            return

        total_files = len(input_paths)
        success_count, skipped_count, error_count, completed_tasks = 0, 0, 0, 0
        failed_files: list[tuple[str, str]] = []  # List of (file_path, error_reason)
        self.log_queue.put(ProgressEvent(target=target_tab, is_start=True, total=total_files))

        with DaemonThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # 동일 stem 입력이 여러 개면 같은 출력 파일을 노려 파일이 서로 덮어써지거나
            # 한 작업의 실패가 다른 작업의 정상 출력 파일을 건드릴 수 있으므로,
            # 입력 경로 기반 해시 접미사로 출력명을 고유화한다(단일 파일이면 기존 이름 유지).
            stem_counts: dict[str, int] = {}
            for path in input_paths:
                source_stem = Path(path).stem
                stem_counts[source_stem] = stem_counts.get(source_stem, 0) + 1
            unique_stems: dict[str, str] = {}
            for path in input_paths:
                source_stem = Path(path).stem
                if stem_counts[source_stem] > 1:
                    digest = hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:8]
                    unique_stems[path] = f"{source_stem}_{digest}"
                else:
                    unique_stems[path] = source_stem

            protected_stems = set(stem_counts)
            future_to_path = {
                executor.submit(
                    self._convert_single_video_task,
                    path,
                    output_dir,
                    usmtoolkit_path,
                    unique_stems[path],
                    protected_stems,
                ): path
                for path in input_paths
            }
            cancelled = False
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_token and cancel_token.is_cancelled and not cancelled:
                    cancelled = True
                    for f in future_to_path:
                        f.cancel()
                    self._log_entry(target_tab, 'status_cancelled')

                if cancelled:
                    try:
                        future.result()
                    except concurrent.futures.CancelledError:
                        pass
                    except (OSError, RuntimeError, ValueError, TypeError) as exc:
                        logger.debug("Future result failed during cancellation: %s", exc)
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))
                    continue

                try:
                    status, log_entries = future.result()
                    self.log_queue.put(LogBlockEvent(target=target_tab, entries=log_entries))
                    if status == "success":
                        success_count += 1
                    elif status == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                        failed_files.append((future_to_path[future], "Conversion failed"))
                except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, AttributeError, KeyError, TypeError) as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                    error_count += 1
                    failed_files.append((path, str(e)))
                finally:
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))

        self._log_entry(target_tab, 'conv_summary_video', total=total_files, success=success_count, skipped=skipped_count, error=error_count)
        self.log_queue.put(CompletionEvent(target=SENTINEL_VIDEO_DONE, result=failed_files))

    def run_audio_conversion(
        self,
        input_paths: list[str],
        output_dir: str,
        vgmstream_path: Path | None,
        overwrite: bool,
        cancel_token: CancellationToken | None,
    ) -> None:
        """오디오(.awb) 변환 작업 총괄 및 스레드 풀 작업 분배 실행.

        각 컨테이너 파일 내의 모든 오디오 스트림을 탐색하여 개별 WAV 파일로 디코딩 및 추출.
        진행률과 로그 블록을 실시간 큐 이벤트로 GUI에 브로드캐스트.

        Args:
            input_paths (list[str]): 변환할 대상 오디오 파일 경로 목록.
            output_dir (str): WAV 결과물을 저장할 루트 폴더 경로.
            vgmstream_path (Path | None): vgmstream-cli.exe 실행 바이너리 경로.
            overwrite (bool): 기존 파일이 있을 때 덮어쓸지 여부 (False 시 건너뜀).
            cancel_token (CancellationToken | None): 작업 취소 감시용 토큰.
        """
        target_tab: TabType = 'audio'
        self._log_entry(target_tab, 'conv_start_audio')
        self._log_entry(target_tab, 'conv_audio_overwrite_notice' if overwrite else 'conv_audio_skip_notice')

        if not vgmstream_path:
            self._log_entry(target_tab, 'conv_error_vgmstream_not_found')
            self.log_queue.put(CompletionEvent(target=SENTINEL_AUDIO_DONE))
            return

        total_files = len(input_paths)
        total_converted_tracks = 0
        completed_tasks = 0
        failed_files: list[tuple[str, str]] = []
        self.log_queue.put(ProgressEvent(target=target_tab, is_start=True, total=total_files))

        with DaemonThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # 동일 stem 입력이 여러 개면 같은 출력 하위 폴더를 공유해 서로 덮어쓰므로
            # 입력 경로 기반 해시 접미사로 출력 폴더명을 고유화한다(단일 파일이면 기존 이름 유지).
            stem_counts: dict[str, int] = {}
            for path in input_paths:
                source_stem = Path(path).stem
                stem_counts[source_stem] = stem_counts.get(source_stem, 0) + 1
            unique_stems: dict[str, str] = {}
            for path in input_paths:
                source_stem = Path(path).stem
                if stem_counts[source_stem] > 1:
                    digest = hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:8]
                    unique_stems[path] = f"{source_stem}_{digest}"
                else:
                    unique_stems[path] = source_stem

            future_to_path = {
                executor.submit(
                    self._convert_audio_container, path, output_dir, vgmstream_path, overwrite, unique_stems[path]
                ): path
                for path in input_paths
            }
            cancelled = False
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_token and cancel_token.is_cancelled and not cancelled:
                    cancelled = True
                    for f in future_to_path:
                        f.cancel()
                    self._log_entry(target_tab, 'status_cancelled')

                if cancelled:
                    try:
                        future.result()
                    except concurrent.futures.CancelledError:
                        pass
                    except (OSError, RuntimeError, ValueError, TypeError) as exc:
                        logger.debug("Future result failed during cancellation: %s", exc)
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))
                    continue

                try:
                    converted_count, log_entries, error_details = future.result()
                    self.log_queue.put(LogBlockEvent(target=target_tab, entries=log_entries))
                    total_converted_tracks += converted_count
                    if any(k in ('conv_audio_stream_fail', 'conv_audio_stream_error', 'conv_log_details_error_header') for k, _ in log_entries):
                        failed_files.append((future_to_path[future], error_details or "Audio conversion failed"))
                except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, AttributeError, KeyError, TypeError) as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                    failed_files.append((path, str(e)))
                finally:
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))

        self._log_entry(target_tab, 'conv_audio_summary_combined', tracks=total_converted_tracks)
        self.log_queue.put(CompletionEvent(target=SENTINEL_AUDIO_DONE, result=failed_files))

    def get_stream_count(self, file_path: Path | str, vgmstream_path: Path | str) -> int:
        """vgmstream을 이용한 AWB 파일 내 오디오 스트림 개수 확인."""
        try:
            result = self._run_subprocess([str(vgmstream_path), "-m", str(file_path)])
        except (OSError, subprocess.SubprocessError):
            return 0
        if result.returncode != 0:
            return 0
        for line in result.stdout.splitlines():
            if line.startswith("stream count:"):
                try:
                    return int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    return 1
        return 1

    def get_stream_name(self, file_path: Path | str, stream_num: int, vgmstream_path: Path | str) -> str:
        """vgmstream을 이용한 특정 스트림 이름 조회."""
        try:
            result = self._run_subprocess([str(vgmstream_path), "-m", "-s", str(stream_num), str(file_path)])
        except (OSError, subprocess.SubprocessError):
            return f"{Path(file_path).stem}_{stream_num:04d}"
        if result.returncode != 0:
            return f"{Path(file_path).stem}_{stream_num:04d}"
        for line in result.stdout.splitlines():
            if line.startswith("stream name:"):
                name = line.split(":", 1)[1].strip().split(';')[0].strip()
                if name:
                    return name
        return f"{Path(file_path).stem}_{stream_num:04d}"

    def get_audio_streams_info(self, file_path: Path | str, vgmstream_path: Path | str) -> list[tuple[int, str]]:
        """vgmstream을 이용한 AWB 파일 내 모든 오디오 스트림 번호 및 이름 일괄 수집.

        백그라운드 스레드에서 실행하여 메인 UI 스레드 블로킹 방지.
        """
        stream_count = self.get_stream_count(file_path, vgmstream_path)
        if stream_count <= 0:
            return []

        # 1. 일괄 메타데이터 파싱 시도 (-s 1 -S 0)
        streams: list[tuple[int, str]] = []
        try:
            result = self._run_subprocess([str(vgmstream_path), "-m", "-s", "1", "-S", "0", str(file_path)])
            if result.returncode == 0:
                current_subsong = 0
                for line in result.stdout.splitlines():
                    if line.startswith("subsong "):
                        try:
                            token = line.split()[1]
                            current_subsong = int(token.split("/")[0].split(":")[0])
                        except (IndexError, ValueError):
                            current_subsong += 1
                    elif line.startswith("stream name:") and current_subsong > 0:
                        name = line.split(":", 1)[1].strip().split(';')[0].strip()
                        if name:
                            streams.append((current_subsong, name))
        except (OSError, subprocess.SubprocessError):
            pass

        if len(streams) == stream_count:
            return streams

        # 2. 폴백: 개별 쿼리
        streams = []
        for i in range(1, stream_count + 1):
            name = self.get_stream_name(file_path, i, vgmstream_path)
            streams.append((i, name))
        return streams

    def _convert_audio_container(
        self,
        item_path_str: str,
        output_dir: str,
        vgmstream_path: Path | str,
        overwrite: bool,
        target_stem: str | None = None,
    ) -> tuple[int, list[tuple[str, dict]], str]:
        """
        단일 오디오 컨테이너(.awb) 파일 내의 모든 스트림을 변환하는 작업 태스크.

        Args:
            item_path_str (str): 대상 오디오 컨테이너 경로.
            output_dir (str): 결과 WAV 를 저장할 루트 폴더.
            vgmstream_path (Path | str): vgmstream 실행 파일 경로.
            overwrite (bool): 기존 WAV 덮어쓰기 여부.
            target_stem (str | None): 출력 하위 폴더명. 동일 stem 입력 충돌 시 호출자가
                입력 경로 기반 접미사를 붙여 전달하며, None 이면 원본 stem 을 사용.

        Returns:
            tuple: (변환된 트랙 수, 로그 항목 리스트, 에러 상세)
        """
        item_path = Path(item_path_str)
        log_entries = [('spacing', {}),
                       ('conv_log_source', {'path': self.get_relative_path(item_path)}),
                       ('spacing', {}),
                       ('conv_log_result_header', {})]
        total_converted = 0
        error_details_list: list[str] = []

        streams = self.get_audio_streams_info(item_path, vgmstream_path)
        if not streams:
            log_entries.append(('conv_audio_stream_error', {}))
            return 0, log_entries, "Could not read stream info from the file"

        # 스트림 정보를 확인한 뒤 하위 폴더 생성 (읽기 실패 시 빈 폴더를 남기지 않음)
        item_output_folder = Path(output_dir) / (target_stem or item_path.stem)
        item_output_folder.mkdir(parents=True, exist_ok=True)

        # 각 스트림을 개별 .wav 파일로 변환
        used_filenames: set[str] = set()
        for stream_idx, stream_name in streams:
            clean_name = sanitize_stream_filename(stream_name)
            if not clean_name:
                clean_name = f"{item_path.stem}_{stream_idx:04d}"

            target_name = clean_name
            collision_idx = 1
            while target_name.lower() in used_filenames:
                target_name = f"{clean_name}_{collision_idx}"
                collision_idx += 1
            used_filenames.add(target_name.lower())

            output_file = item_output_folder / f"{target_name}.wav"

            if not overwrite and self._is_valid_output_file(output_file):
                log_entries.append(('conv_audio_stream_skipped', {'filename': output_file.name}))
                continue

            command = [str(vgmstream_path), "-s", str(stream_idx), "-o", str(output_file), str(item_path)]
            result = self._run_subprocess(command)

            if result.returncode == 0 and self._is_valid_output_file(output_file):
                log_entries.append(('conv_audio_stream_success', {'path': self.get_relative_path(output_file)}))
                total_converted += 1
            else:
                log_entries.append(('conv_audio_stream_fail', {'index': str(stream_idx), 'name': stream_name}))
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    error_details_list.append(f"Stream #{stream_idx} ({stream_name}):\n{error_output}")
                    log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])
                self._quarantine_output(output_file)

        log_entries.append(('spacing', {}))
        return total_converted, log_entries, "\n\n".join(error_details_list)

    def preview_single_audio(self, file_path: str, stream_num: int, output_path: str, vgmstream_path: Path) -> tuple[bool, str | None]:
        """단일 오디오 스트림을 지정된 임시 WAV 파일로 디코딩 (미리보기 재생용).

        Args:
            file_path (str): 원본 오디오 파일 경로 (.awb).
            stream_num (int): 디코딩할 1-기반 서브송(스트림) 번호.
            output_path (str): 출력 임시 WAV 파일 경로.
            vgmstream_path (Path): vgmstream 실행 파일 경로.

        Returns:
            tuple[bool, str | None]: (성공 여부, 오류 메시지 또는 None).
        """
        item_path = Path(file_path)
        command = [str(vgmstream_path), "-s", str(stream_num), "-o", str(output_path), str(file_path)]
        try:
            result = self._run_subprocess(command)
            success = result.returncode == 0 and self._is_valid_output_file(Path(output_path))
            if not success:
                self._log_entry('audio', 'conv_preview_fail', filename=item_path.name)
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    for line in error_output.splitlines():
                        self.log_queue.put(LogEvent(target='audio', key='raw', kwargs={'text': f"    > {line}"}))
                self._log_entry('audio', 'spacing')
                return False, error_output
            return True, None
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            self._log_entry('audio', 'conv_preview_fail', filename=item_path.name)
            self._log_entry('audio', 'conv_log_error_exception', error=str(e))
            self._log_entry('audio', 'spacing')
            return False, str(e)

    def preview_single_video(self, usm_file_str: str, output_dir: str, usmtoolkit_path: Path) -> tuple[Path | None, str | None]:
        """단일 비디오(.usm)를 지정된 임시 경로로 변환 (미리보기 재생용).

        변환 성공 시 생성된 MP4 경로를 반환하며, 작업 직후 디먹싱 중간 임시 파일들을 자동 정리.

        Args:
            usm_file_str (str): 원본 USM 파일 경로.
            output_dir (str): 변환 임시 디렉터리 경로.
            usmtoolkit_path (Path): UsmToolkit.exe 실행 바이너리 경로.

        Returns:
            tuple[Path | None, str | None]: (생성된 MP4 경로 또는 None, 오류 메시지 또는 None).
        """
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        output_path = Path(output_dir)
        output_ext = expected_output_extension(usmtoolkit_dir)
        final_mp4_path = output_path / f"{usm_file.stem}.{output_ext}"

        command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(output_path.resolve())]
        # 미리보기 변환 시작 전 소스 폴더 스냅샷 (기존 사용자 파일을 중간 파일로 오인 삭제하지 않도록)
        pre_existing_files = self._snapshot_directory(usm_file.parent)
        try:
            result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_PREVIEW_TIMEOUT)
            if self._is_valid_output_file(final_mp4_path):
                return final_mp4_path, None
            else:
                self._log_entry('video', 'conv_preview_fail', filename=usm_file.name)
                error_output = (result.stderr or result.stdout or "No process output.").strip()
                if error_output:
                    for line in error_output.splitlines():
                        self.log_queue.put(LogEvent(target='video', key='raw', kwargs={'text': f"    > {line}"}))
                self._log_entry('video', 'spacing')
                return None, error_output
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            self._log_entry('video', 'conv_preview_fail', filename=usm_file.name)
            self._log_entry('video', 'conv_log_error_exception', error=str(e))
            self._log_entry('video', 'spacing')
            return None, str(e)
        finally:
            # 성공/실패/타임아웃 어느 경로에서도 디먹싱 중간 파일을 정리
            self._cleanup_intermediate_files(usm_file.parent, usm_file.stem, pre_existing_files)


def _is_executable_usable(exe_path: Path, probe_args: list[str], timeout: int) -> bool:
    """실행 파일이 실제로 기동 가능한지 프로브하여 손상/잘림 여부를 판별.

    파일 존재 여부만으로 '설치됨'을 판정하면 0바이트/중단된 복사본을 영구히 신뢰하게 되므로,
    짧은 인자로 기동을 시도해 손상 바이너리만 재설치 대상으로 분류한다.

    Args:
        exe_path (Path): 검사할 실행 파일 경로.
        probe_args (list[str]): 기동 확인용 인자 목록.
        timeout (int): 프로브 최대 대기 시간(초).

    Returns:
        bool: 파일이 존재하고 프로세스 기동이 가능하면 True.
    """
    if not exe_path.is_file():
        return False
    try:
        SubprocessRunner.run([str(exe_path), *probe_args], timeout=timeout)
    except OSError:
        # 손상/잘린 바이너리, 실행 권한 문제 → 재설치 대상
        return False
    except (subprocess.SubprocessError, ValueError, RuntimeError):
        # 기동은 되었으나 인자/런타임 문제일 뿐 파일 자체는 유효
        return True
    return True


class FFmpegDownloader:
    """FFmpeg 바이너리 자동 다운로드, 버전 정책 확인 및 완결성 검증 클래스.

    지정된 안정화 버전(FFMPEG_TARGET_VERSION)의 빌드를 공식 미러에서 다운로드하며,
    ZIP 매직 바이트/아카이브 무결성 검증 및 Zip-Slip 방지 안전 압축 해제를 통한 설치 수행.
    """

    def __init__(
        self,
        log_queue: queue.Queue,
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
        """설치된 ffmpeg.exe 버전을 실행 확인하고 정책 분류 결과를 반환.

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
            temp_extract_dir = self.download_dir / "ffmpeg_extracted_temp"
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


class UsmToolkitDownloader:
    """UsmToolkit 자동 다운로드 및 압축 해제 관리 클래스."""

    def __init__(
        self,
        log_queue: queue.Queue,
        usmtoolkit_dir: Path,
    ) -> None:
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_dir
        self.usm_exe_path = self.download_dir / USMTOOLKIT_EXE_NAME
        self.target_tab: TabType = 'video'
        self._target_tab_lock = threading.Lock()

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


class VgmstreamDownloader:
    """vgmstream 자동 다운로드 및 압축 해제 관리 클래스."""

    def __init__(
        self,
        log_queue: queue.Queue,
        vgmstream_dir: Path,
    ) -> None:
        self.log_queue = log_queue
        self.download_dir = vgmstream_dir
        self.vgm_exe_path = self.download_dir / VGMSTREAM_EXE_NAME
        self.target_tab: TabType = 'audio'
        self._target_tab_lock = threading.Lock()

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


class ToolPipelineManager:
    """UsmToolkit, vgmstream, FFmpeg의 순차적 준비를 통합 관리하는 파이프라인 매니저."""

    def __init__(
        self,
        log_queue: queue.Queue,
        base_path: Path,
        on_tools_updated_callback: Callable[[], None] | None = None,
    ) -> None:
        self.log_queue = log_queue
        self.base_path = base_path
        self.on_tools_updated = on_tools_updated_callback
        self._prep_lock = threading.Lock()
        self._prep_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._active_future: concurrent.futures.Future | None = None
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

    def ensure_tools_ready(self, tab_type: TabType) -> concurrent.futures.Future:
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

        return False
