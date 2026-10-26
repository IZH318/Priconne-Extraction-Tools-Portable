"""AV Converter 비즈니스 로직 및 툴체인 다운로드/검증 엔진 모듈.

CRI Sofdec (.usm) 비디오 디먹싱 및 H.264/AAC MP4 인코딩,
CRI Atom (.awb, .acb, .hca) 멀티트랙 오디오 디코딩 및 WAV 변환 로직과 함께,
외부 툴체인(FFmpeg, UsmToolkit, vgmstream)의 자동 다운로드, SHA-256 무결성 검증,
Zip-Slip 방어 압축 해제 및 .NET Core 런타임 환경 감지 기능 제공.
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
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from src.cancellation_token import CancellationToken

logger = logging.getLogger(__name__)

from src.constants import (
    AV_TEMP_EXTENSIONS,
    DOWNLOAD_SOCKET_TIMEOUT,
    FFMPEG_EXE_NAME,
    FFMPEG_EXPECTED_SHA256,
    FFMPEG_TARGET_VERSION,
    FFMPEG_URL,
    FFMPEG_VERSION_MARKER_PATH,
    FFMPEG_ZIP_FILENAME,
    SENTINEL_AUDIO_DONE,
    SENTINEL_VIDEO_DONE,
    SUBPROCESS_AUDIO_CONVERT_TIMEOUT,
    SUBPROCESS_PREVIEW_TIMEOUT,
    SUBPROCESS_VIDEO_CONVERT_TIMEOUT,
    USMTOOLKIT_EXE_NAME,
    USMTOOLKIT_URL,
    USMTOOLKIT_ZIP_FILENAME,
    VGMSTREAM_EXE_NAME,
    VGMSTREAM_URL,
    VGMSTREAM_ZIP_FILENAME,
    TabType,
)
from src.exceptions import DownloadError, FileIntegrityError
from src.queue_events import CompletionEvent, LogBlockEvent, LogEvent, ProgressEvent
from src.subprocess_runner import SubprocessRunner

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


class ConversionLogic:
    """오디오/비디오 일괄 변환 및 메타데이터 추출 엔진 클래스.

    시스템 CPU 코어 기반 작업자 스레드 풀을 관리하며, 서브프로세스를 통해 외부 바이너리를 실행하고
    진행 상태 및 로그 이벤트를 통신 큐로 전송.
    """

    # 시스템 CPU 코어 수의 절반을 최대 작업자 수로 설정 (과도한 부하 방지)
    cpu_threads: int = (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or os.cpu_count() or 1
    MAX_WORKERS: int = max(1, cpu_threads // 2)


    @staticmethod
    def _cleanup_intermediate_files(directory: Path, stem: str) -> None:
        """USM 디먹싱 및 변환 시 생성된 중간 임시 파일(.adx, .wav, .m2v, .bin 등) 안전 삭제.

        단일 스트림 파일(예: movie.wav)뿐만 아니라 다중 오디오 스트림 인덱스가 붙은
        파생 파일(예: movie_0.adx, movie_1.wav)까지 정확히 탐지하여 제거.
        """
        if not directory.exists() or not directory.is_dir():
            return
        prefix = f"{stem}_"
        try:
            for item in directory.iterdir():
                if not item.is_file():
                    continue
                if item.suffix.lower() not in AV_TEMP_EXTENSIONS:
                    continue
                # 1. stem.ext 일치 (단일 스트림)
                if item.name == f"{stem}{item.suffix}" or item.stem.startswith(prefix) and item.stem[len(prefix):].isdigit():
                    try:
                        os.remove(item)
                    except OSError as exc:
                        logger.debug("Failed to remove temp file %s: %s", item, exc)
        except OSError as exc:
            logger.debug("Failed to scan temp dir: %s", exc)

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
        """시스템에 설치된 .NET Runtime (Microsoft.NETCore.App) 버전 목록 반환."""
        versions: list[str] = []
        dotnet_exe = shutil.which('dotnet')
        if dotnet_exe and Path(dotnet_exe).is_file():
            try:
                res = SubprocessRunner.run([dotnet_exe, '--list-runtimes'], timeout=2)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == 'Microsoft.NETCore.App':
                            versions.append(f"{parts[0]} {parts[1]}")
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                logger.debug("Failed to list dotnet runtimes: %s", exc)
        if not versions:
            for base in [Path(r'C:\Program Files\dotnet\shared\Microsoft.NETCore.App'),
                         Path(r'C:\Program Files (x86)\dotnet\shared\Microsoft.NETCore.App')]:
                if base.is_dir():
                    try:
                        for p in sorted(base.iterdir()):
                            if p.is_dir():
                                versions.append(f"Microsoft.NETCore.App {p.name}")
                    except (OSError, ValueError) as exc:
                        logger.debug("Failed to scan dotnet runtime dir %s: %s", base, exc)
        seen = set()
        result = []
        for v in versions:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result

    def _convert_single_video_task(self, usm_file_str: str, output_dir: str, usmtoolkit_path: Path) -> tuple[str, list[tuple[str, dict]]]:
        """
        단일 비디오(.usm) 파일을 변환하는 작업자(worker) 태스크.

        Args:
            usm_file_str (str): 변환할 USM 파일 경로.
            output_dir (str): 출력 디렉터리 경로.
            usmtoolkit_path (Path): UsmToolkit.exe 파일 경로.

        Returns:
            tuple: (변환 상태 문자열, 로그 항목 리스트)
        """
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        output_path = Path(output_dir)
        final_mp4_path = output_path / (usm_file.stem + ".mp4")

        log_entries = [('spacing', {}),
                       ('conv_log_source', {'path': self.get_relative_path(usm_file)})]
        status = "unknown"

        log_entries.append(('spacing', {}))

        # 이미 변환된 파일은 건너뛰기
        if final_mp4_path.exists():
            log_entries.append(('conv_log_result_header', {}))
            log_entries.append(('conv_log_skipped', {}))
            status = "skipped"
        else:
            command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(output_path.resolve())]
            try:
                # 외부 UsmToolkit 프로세스 실행
                result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_VIDEO_CONVERT_TIMEOUT)

                log_entries.append(('conv_log_result_header', {}))

                # 결과 파일 존재 여부로 성공/실패 판단
                if final_mp4_path.exists():
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

                    # 변환 과정에서 생성된 임시 파일 삭제 (단일 및 다중 스트림 파생 파일 포함)
                    self._cleanup_intermediate_files(usm_file.parent, usm_file.stem)
                else:
                    status = "error"
                    log_entries.append(('conv_log_error_fail', {'filename': usm_file.name}))

                    # 실패 시 프로세스 오류 로그 추가
                    error_output = (result.stderr or result.stdout or "No process output.").strip()
                    if error_output:
                        log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])

            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, AttributeError, KeyError, TypeError) as e:
                status = "error"
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_exception', {'error': str(e)}))

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

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_single_video_task, path, output_dir, usmtoolkit_path): path for path in input_paths}
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
        """오디오(.awb, .acb, .hca) 변환 작업 총괄 및 스레드 풀 작업 분배 실행.

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

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_audio_container, path, output_dir, vgmstream_path, overwrite): path for path in input_paths}
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

    def _convert_audio_container(self, item_path_str: str, output_dir: str, vgmstream_path: Path | str, overwrite: bool) -> tuple[int, list[tuple[str, dict]], str]:
        """
        단일 오디오 컨테이너(.awb) 파일 내의 모든 스트림을 변환하는 작업자 태스크.

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

        # 오디오(AWB) 파일 이름으로 하위 폴더 생성
        item_output_folder = Path(output_dir) / item_path.stem
        item_output_folder.mkdir(parents=True, exist_ok=True)

        streams = self.get_audio_streams_info(item_path, vgmstream_path)
        if not streams:
            log_entries.append(('conv_audio_stream_error', {}))
            return 0, log_entries, "Could not read stream info from the file"

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

            if not overwrite and output_file.exists():
                log_entries.append(('conv_audio_stream_skipped', {'filename': output_file.name}))
                continue

            command = [str(vgmstream_path), "-s", str(stream_idx), "-o", str(output_file), str(item_path)]
            result = self._run_subprocess(command)

            if result.returncode == 0 and output_file.exists():
                log_entries.append(('conv_audio_stream_success', {'path': self.get_relative_path(output_file)}))
                total_converted += 1
            else:
                log_entries.append(('conv_audio_stream_fail', {'index': str(stream_idx), 'name': stream_name}))
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    error_details_list.append(f"Stream #{stream_idx} ({stream_name}):\n{error_output}")
                    log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])

        log_entries.append(('spacing', {}))
        return total_converted, log_entries, "\n\n".join(error_details_list)

    def preview_single_audio(self, file_path: str, stream_num: int, output_path: str, vgmstream_path: Path) -> tuple[bool, str | None]:
        """단일 오디오 스트림을 지정된 임시 WAV 파일로 디코딩 (미리보기 재생용).

        Args:
            file_path (str): 원본 오디오 파일 경로 (.awb, .acb, .hca 등).
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
            success = result.returncode == 0 and Path(output_path).exists()
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
        final_mp4_path = output_path / (usm_file.stem + ".mp4")

        command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(output_path.resolve())]
        try:
            result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_PREVIEW_TIMEOUT)
            # 변환 후 임시 중간 파일 정리 (단일 및 다중 스트림 파생 파일 포함)
            self._cleanup_intermediate_files(usm_file.parent, usm_file.stem)
            if final_mp4_path.exists():
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


def verify_sha256(file_path: Path, expected_hash: str) -> bool:
    """파일의 SHA-256 해시를 청크 단위로 스트리밍 계산하여 기대값과 일치 여부 검증.

    보안을 위해 expected_hash가 빈 문자열이거나 None이면 Fail-Closed 원칙에 따라 False 반환.

    Args:
        file_path (Path): 검증할 로컬 파일 경로.
        expected_hash (str): 대소문자 무관 기대 SHA-256 16진수 문자열.

    Returns:
        bool: 파일의 해시가 기대값과 일치하면 True.
    """
    if not expected_hash:
        return False
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest().lower() == expected_hash.lower()


class FFmpegDownloader:
    """FFmpeg 바이너리 자동 다운로드, 버전 일치성 확인 및 무결성 검증 클래스.

    지정된 안정화 버전(FFMPEG_TARGET_VERSION)의 빌드를 공식 미러에서 다운로드하며,
    SHA-256 체크섬 및 Zip-Slip 방어 안전 압축 해제를 통한 설치 수행.
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
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.version_marker_path.parent, exist_ok=True)

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target='video', key=log_key, kwargs=kwargs))

    def _is_target_version_installed(self) -> tuple[bool, str]:
        """설치된 ffmpeg.exe의 목표 안정화 버전 일치 여부 확인."""
        if not self.ffmpeg_path.exists():
            return False, "not_found"

        # 1. 빠른 경로: 버전 마커 파일 확인
        if self.version_marker_path.exists():
            try:
                installed_ver = self.version_marker_path.read_text(encoding="utf-8").strip()
                if installed_ver == FFMPEG_TARGET_VERSION:
                    return True, installed_ver
            except OSError:
                pass

        # 2. 실행 파일 바이너리 버전 직접 확인
        try:
            res = SubprocessRunner.run([str(self.ffmpeg_path), "-version"], timeout=5)
            first_line = (res.stdout or "").splitlines()[0] if res.stdout else ""
            if f"version {FFMPEG_TARGET_VERSION}" in first_line:
                try:
                    self.version_marker_path.write_text(FFMPEG_TARGET_VERSION, encoding="utf-8")
                except OSError:
                    pass
                return True, FFMPEG_TARGET_VERSION

            parts = first_line.split()
            current_ver = parts[2] if len(parts) > 2 else "unknown"
            return False, current_ver
        except (OSError, ValueError, IndexError, UnicodeDecodeError):  # 폴백: 버전 파일 파싱 실패 시 unknown 반환
            return False, "unknown"

    def _verify_sha256(self, file_path: Path, expected_hash: str) -> bool:
        """파일의 SHA-256 해시를 계산하여 기대값과 일치 여부 검증."""
        return verify_sha256(file_path, expected_hash)

    def _actual_download_and_extract(self) -> bool:
        """실제 다운로드 및 압축 해제 로직 수행."""
        local_zip_path = self.download_dir / FFMPEG_ZIP_FILENAME
        temp_extract_dir = None

        # 대상 FFmpeg 버전 확인 및 존재 여부 검사
        is_ready, current_ver = self._is_target_version_installed()
        if is_ready:
            self._log_entry('ffmpeg_already_exists', path=self.download_dir)
            return True

        if current_ver != "not_found":
            self._log_entry('ffmpeg_version_mismatch', current=current_ver, target=FFMPEG_TARGET_VERSION)
        else:
            self._log_entry('ffmpeg_not_found', path=self.download_dir)

        try:
            # 1. 다운로드
            self._log_entry('ffmpeg_download_start', url=FFMPEG_URL)
            req = urllib.request.Request(FFMPEG_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_SOCKET_TIMEOUT) as response, open(local_zip_path, 'wb') as out_file:
                if response.status != 200:
                    raise DownloadError(f"HTTP Error: {response.status} {response.reason}")
                content_length = response.headers.get('Content-Length')
                if content_length:
                    try:
                        if int(content_length) > 500 * 1024 * 1024:
                            raise DownloadError(f"Download too large: {content_length} bytes")
                    except ValueError:
                        pass
                shutil.copyfileobj(response, out_file)

            # 1-1. 다운로드된 파일 무결성 검증 (SHA-256 해시 검증)
            if not self._verify_sha256(local_zip_path, FFMPEG_EXPECTED_SHA256):
                self._log_entry('ffmpeg_hash_mismatch')
                raise FileIntegrityError(str(local_zip_path), "SHA-256 checksum mismatch")

            # 1-2. ZIP magic bytes + 아카이브 테스트
            with open(local_zip_path, 'rb') as f:
                magic = f.read(4)
            if magic[:2] != b'PK':
                raise FileIntegrityError(str(local_zip_path), "not a valid ZIP archive (magic bytes mismatch)")
            with zipfile.ZipFile(local_zip_path, 'r') as zip_test:
                bad_file = zip_test.testzip()
                if bad_file is not None:
                    raise zipfile.BadZipFile(f"ZIP archive integrity check failed: corrupted entry '{bad_file}'.")

            self._log_entry('ffmpeg_download_complete')

            # 2. 압축 해제 및 설치
            self._log_entry('ffmpeg_extract_start')
            temp_extract_dir = self.download_dir / "ffmpeg_extracted_temp"
            os.makedirs(temp_extract_dir, exist_ok=True)
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                # 아카이브(ZIP) 파일 내에서 ffmpeg.exe 경로 탐색
                ffmpeg_internal_path = next((name for name in zip_ref.namelist() if name.endswith(f'/bin/{FFMPEG_EXE_NAME}')), None)
                if not ffmpeg_internal_path:
                    raise FileIntegrityError(str(local_zip_path), "expected folder structure not found in ZIP")
                # 필요한 파일만 안전하게 추출 후 이동 (zip-slip 방어)
                from src.utils.zip_safe import safe_extract
                extracted_path = safe_extract(zip_ref, ffmpeg_internal_path, temp_extract_dir)
                extracted_file = extracted_path
                if self.ffmpeg_path.exists():
                    try:
                        os.remove(self.ffmpeg_path)
                    except OSError:
                        pass
                shutil.move(str(extracted_file), str(self.ffmpeg_path))

            # 버전 마커 파일 기록
            try:
                self.version_marker_path.write_text(FFMPEG_TARGET_VERSION, encoding="utf-8")
            except OSError:
                pass

            self._log_entry('ffmpeg_extract_complete', path=self.ffmpeg_path)
            return True
        except (urllib.error.URLError, OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError) as e:
            self._log_entry('ffmpeg_download_fail', error=e)
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
        if self.usm_exe_path.exists():
            self._log_entry('usmtoolkit_already_exists', path=self.download_dir)
            return True

        self._log_entry('usmtoolkit_not_found', path=self.download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        local_zip_path = self.download_dir / USMTOOLKIT_ZIP_FILENAME

        try:
            self._log_entry('usmtoolkit_download_start', url=USMTOOLKIT_URL)
            req = urllib.request.Request(USMTOOLKIT_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response, open(local_zip_path, 'wb') as out_file:
                if response.status != 200:
                    raise DownloadError(f"HTTP Error: {response.status} {response.reason}")
                shutil.copyfileobj(response, out_file)

            with open(local_zip_path, 'rb') as f:
                magic = f.read(4)
            if magic[:2] != b'PK':
                raise FileIntegrityError(str(local_zip_path), "not a valid ZIP archive (magic bytes mismatch)")

            with zipfile.ZipFile(local_zip_path, 'r') as zip_test:
                bad_file = zip_test.testzip()
                if bad_file is not None:
                    raise zipfile.BadZipFile(f"ZIP archive integrity check failed: corrupted entry '{bad_file}'.")
            from src.constants import USMTOOLKIT_EXPECTED_SHA256
            if USMTOOLKIT_EXPECTED_SHA256 and not verify_sha256(local_zip_path, USMTOOLKIT_EXPECTED_SHA256):
                raise FileIntegrityError(str(local_zip_path), "SHA-256 checksum mismatch")

            self._log_entry('usmtoolkit_download_complete')
            self._log_entry('usmtoolkit_extract_start')

            # 설정 파일(config.json, deps.json)을 제외하고 압축 해제 (zip-slip 방어)
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
            return True
        except (urllib.error.URLError, OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError) as e:
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
        if self.vgm_exe_path.exists():
            ensure_vgmstream_test_exe(self.vgm_exe_path)
            self._log_entry('vgmstream_already_exists', path=self.download_dir)
            return True

        self._log_entry('vgmstream_not_found', path=self.download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        local_zip_path = self.download_dir / VGMSTREAM_ZIP_FILENAME

        try:
            self._log_entry('vgmstream_download_start', url=VGMSTREAM_URL)
            req = urllib.request.Request(VGMSTREAM_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response, open(local_zip_path, 'wb') as out_file:
                if response.status != 200:
                    raise DownloadError(f"HTTP Error: {response.status} {response.reason}")
                shutil.copyfileobj(response, out_file)

            with open(local_zip_path, 'rb') as f:
                magic = f.read(4)
            if magic[:2] != b'PK':
                raise FileIntegrityError(str(local_zip_path), "not a valid ZIP archive (magic bytes mismatch)")

            with zipfile.ZipFile(local_zip_path, 'r') as zip_test:
                bad_file = zip_test.testzip()
                if bad_file is not None:
                    raise zipfile.BadZipFile(f"ZIP archive integrity check failed: corrupted entry '{bad_file}'.")
            from src.constants import VGMSTREAM_EXPECTED_SHA256
            if VGMSTREAM_EXPECTED_SHA256 and not verify_sha256(local_zip_path, VGMSTREAM_EXPECTED_SHA256):
                raise FileIntegrityError(str(local_zip_path), "SHA-256 checksum mismatch")

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
            return True
        except (urllib.error.URLError, OSError, zipfile.BadZipFile, DownloadError, FileIntegrityError) as e:
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
                self._prep_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
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
        if tab_type == 'video':
            # 1. UsmToolkit 준비 (usmtoolkit 폴더 생성 및 압축 해제, config/deps 필터링)
            self.usmtoolkit_downloader.target_tab = 'video'
            if not self.usmtoolkit_downloader.ensure_ready():
                self._log_entry('video', 'usmtoolkit_prepare_fail')
                return False

            # 2. vgmstream 준비 (usmtoolkit/vgmstream 폴더에 압축 해제 및 test.exe 복사)
            self.vgmstream_downloader.target_tab = 'video'
            if not self.vgmstream_downloader.ensure_ready():
                self._log_entry('video', 'vgmstream_prepare_fail')
                return False

            # 3. FFmpeg 준비 (usmtoolkit/ffmpeg.exe)
            if not self.ffmpeg_downloader._actual_download_and_extract():
                self._log_entry('video', 'ffmpeg_prepare_fail')
                return False

            if self.on_tools_updated:
                self.on_tools_updated()
            return True

        elif tab_type == 'audio':
            # 1. vgmstream 준비 (usmtoolkit/vgmstream 폴더)
            self.vgmstream_downloader.target_tab = 'audio'
            if not self.vgmstream_downloader.ensure_ready():
                self._log_entry('audio', 'vgmstream_prepare_fail')
                return False

            if self.on_tools_updated:
                self.on_tools_updated()
            return True

        return False
