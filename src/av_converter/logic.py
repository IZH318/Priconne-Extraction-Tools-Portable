from __future__ import annotations
import os
import shutil
import subprocess
import urllib.request
import urllib.error
import zipfile
import hashlib
import concurrent.futures
import queue
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.cancellation_token import CancellationToken

from src.exceptions import DownloadError, FileIntegrityError

from src.constants import (
    SEPARATOR_SHORT, AV_TEMP_EXTENSIONS, FFMPEG_URL, 
    FFMPEG_ZIP_FILENAME, FFMPEG_EXE_NAME,
    FFMPEG_TARGET_VERSION, FFMPEG_EXPECTED_SHA256, FFMPEG_VERSION_FILENAME,
    SENTINEL_VIDEO_DONE, SENTINEL_AUDIO_DONE, TabType,
)
from src.subprocess_runner import SubprocessRunner
from src.queue_events import (
    LogEvent, LogBlockEvent, ProgressEvent, CompletionEvent
)

class ConversionLogic:
    # 시스템 CPU 코어 수의 절반을 최대 작업자 수로 설정 (과도한 부하 방지)
    cpu_threads: int = os.cpu_count() or 1
    MAX_WORKERS: int = max(1, cpu_threads // 2)

    def __init__(self, log_queue: queue.Queue, base_path: Path) -> None:
        """
        ConversionLogic 인스턴스 초기화.

        Args:
            log_queue (queue.Queue): GUI와 통신하기 위한 큐.
            base_path (Path): 프로그램 실행 기준 경로.
        """
        self.log_queue = log_queue
        self.base_path = base_path

    def _log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가합니다."""
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def get_relative_path(self, full_path: str | Path) -> str:
        """로그에 표시할 파일의 상대 경로를 계산합니다."""
        try:
            return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError):
            return str(full_path)

    def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """외부 프로세스를 실행하고 출력을 캡처하는 헬퍼 함수입니다."""
        return SubprocessRunner.run(command)

    @staticmethod
    def get_installed_dotnet_runtimes() -> list[str]:
        """시스템에 설치된 .NET Runtime (Microsoft.NETCore.App) 버전 목록을 반환합니다."""
        versions: list[str] = []
        try:
            res = SubprocessRunner.run(['dotnet', '--list-runtimes'], timeout=2)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0] == 'Microsoft.NETCore.App':
                        versions.append(f"{parts[0]} {parts[1]}")
        except Exception:
            pass
        if not versions:
            for base in [Path(r'C:\Program Files\dotnet\shared\Microsoft.NETCore.App'),
                         Path(r'C:\Program Files (x86)\dotnet\shared\Microsoft.NETCore.App')]:
                if base.is_dir():
                    try:
                        for p in sorted(base.iterdir()):
                            if p.is_dir():
                                versions.append(f"Microsoft.NETCore.App {p.name}")
                    except Exception:
                        pass
        seen = set()
        return [v for v in versions if not (v in seen or seen.add(v))]

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
                # UsmToolkit 프로세스 실행
                result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir))

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

                    # 변환 과정에서 생성된 임시 파일 삭제
                    temp_file_dir = usm_file.parent
                    for ext in AV_TEMP_EXTENSIONS:
                        temp_file = temp_file_dir / (usm_file.stem + ext)
                        if temp_file.exists():
                            try:
                                os.remove(temp_file)
                            except OSError:
                                pass
                else:
                    status = "error"
                    log_entries.append(('conv_log_error_fail', {'filename': usm_file.name}))
                    
                    # 실패 시 오류 로그 추가
                    error_output = (result.stderr or result.stdout or "No process output.").strip()
                    if error_output:
                        log_entries.append(('spacing', {}))
                        log_entries.append(('conv_log_details_error_header', {}))
                        log_entries.extend([('raw', {'text': f"    > {line}"}) for line in error_output.splitlines()])

            except Exception as e:
                status = "error"
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_exception', {'error': str(e)}))

        log_entries.append(('spacing', {}))
        return status, log_entries

    def run_video_conversion(self, input_paths: list[str], output_dir: str, usmtoolkit_path: Path | None, cancel_token: CancellationToken | None) -> None:
        """비디오 변환 작업을 총괄하고 스레드 풀에 작업을 분배합니다."""
        target_tab = 'video'
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
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_token and cancel_token.is_cancelled:
                    # 취소 요청된 상태면 pending 중인 future를 cancel 시도 (이미 실행 중인 것은 계속 끝남)
                    for f in future_to_path:
                        f.cancel()
                    self._log_entry(target_tab, 'status_cancelled')
                    break

                try:
                    status, log_entries = future.result()
                    self.log_queue.put(LogBlockEvent(target=target_tab, entries=log_entries))
                    if status == "success":
                        success_count += 1
                    elif status == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                        # We don't have the exact error message from the worker here easily if it didn't throw,
                        # but we can just say "Conversion failed" since detailed logs are in the GUI.
                        failed_files.append((future_to_path[future], "Conversion process failed"))
                except Exception as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                    error_count += 1
                    failed_files.append((path, str(e)))
                finally:
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))
        
        self._log_entry(target_tab, 'conv_summary_video', total=total_files, success=success_count, skipped=skipped_count, error=error_count)
        self.log_queue.put(CompletionEvent(target=SENTINEL_VIDEO_DONE, result=failed_files))

    def run_audio_conversion(self, input_paths: list[str], output_dir: str, vgmstream_path: Path | None, overwrite: bool, cancel_token: CancellationToken | None) -> None:
        """오디오 변환 작업을 총괄하고 스레드 풀에 작업을 분배합니다."""
        target_tab = 'audio'
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
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_token and cancel_token.is_cancelled:
                    for f in future_to_path:
                        f.cancel()
                    self._log_entry(target_tab, 'status_cancelled')
                    break

                try:
                    converted_count, log_entries = future.result()
                    self.log_queue.put(LogBlockEvent(target=target_tab, entries=log_entries))
                    total_converted_tracks += converted_count
                    if any(k in ('conv_audio_stream_fail', 'conv_audio_stream_error', 'conv_log_details_error_header') for k, _ in log_entries):
                        failed_files.append((future_to_path[future], "Audio conversion failed"))
                except Exception as e:
                    path = future_to_path[future]
                    self._log_entry(target_tab, 'conv_log_worker_exception', filename=Path(path).name, error=e)
                    failed_files.append((path, str(e)))
                finally:
                    completed_tasks += 1
                    self.log_queue.put(ProgressEvent(target=target_tab, current=completed_tasks, total=total_files))
                    
        self._log_entry(target_tab, 'conv_audio_summary_combined', tracks=total_converted_tracks)
        self.log_queue.put(CompletionEvent(target=SENTINEL_AUDIO_DONE, result=failed_files))

    def get_stream_count(self, file_path: Path | str, vgmstream_path: Path | str) -> int:
        """vgmstream을 이용해 AWB 파일 내의 오디오 스트림 개수를 확인합니다."""
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
        """vgmstream을 이용해 특정 스트림의 이름을 가져옵니다."""
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
        """vgmstream을 이용해 AWB 파일 내 모든 오디오 스트림의 번호와 이름을 일괄 수집합니다.

        백그라운드 스레드에서 실행되어 메인 UI 스레드의 블로킹을 방지합니다.
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

    def _convert_audio_container(self, item_path_str: str, output_dir: str, vgmstream_path: Path | str, overwrite: bool) -> tuple[int, list[tuple[str, dict]]]:
        """
        단일 오디오 컨테이너(.awb) 파일 내의 모든 스트림을 변환하는 작업자 태스크.

        Returns:
            tuple: (변환된 트랙 수, 로그 항목 리스트)
        """
        item_path = Path(item_path_str)
        log_entries = [('spacing', {}),
                       ('conv_log_source', {'path': self.get_relative_path(item_path)}),
                       ('spacing', {}),
                       ('conv_log_result_header', {})]
        total_converted = 0
        
        # AWB 파일 이름으로 하위 폴더 생성
        item_output_folder = Path(output_dir) / item_path.stem
        item_output_folder.mkdir(parents=True, exist_ok=True)

        streams = self.get_audio_streams_info(item_path, vgmstream_path)
        if not streams:
            log_entries.append(('conv_audio_stream_error', {}))
            return 0, log_entries

        # 각 스트림을 개별 .wav 파일로 변환
        for stream_idx, stream_name in streams:
            output_file = item_output_folder / f"{stream_name}.wav"

            if not overwrite and output_file.exists():
                log_entries.append(('conv_audio_stream_skipped', {'filename': output_file.name}))
                continue

            command = [str(vgmstream_path), "-s", str(stream_idx), "-o", str(output_file), str(item_path)]
            result = self._run_subprocess(command)

            if result.returncode == 0 and output_file.exists():
                log_entries.append(('conv_audio_stream_success', {'path': self.get_relative_path(output_file)}))
                total_converted += 1
            else:
                log_entries.append(('conv_audio_stream_fail', {'index': stream_idx, 'name': stream_name}))
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    log_entries.append(('conv_log_details_error_header', {}))
                    log_entries.extend([('raw', {'text': f"      > {line}"}) for line in error_output.splitlines()])

        log_entries.append(('spacing', {}))
        return total_converted, log_entries

    def preview_single_audio(self, file_path: str, stream_num: int, output_path: str, vgmstream_path: Path) -> bool:
        """단일 오디오 스트림을 지정된 임시 경로로 변환합니다 (미리보기용)."""
        command = [str(vgmstream_path), "-s", str(stream_num), "-o", str(output_path), str(file_path)]
        result = self._run_subprocess(command)
        return result.returncode == 0 and Path(output_path).exists()

    def preview_single_video(self, usm_file_str: str, output_dir: str, usmtoolkit_path: Path) -> Path | None:
        """단일 비디오를 지정된 임시 경로로 변환합니다 (미리보기용)."""
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        output_path = Path(output_dir)
        final_mp4_path = output_path / (usm_file.stem + ".mp4")

        command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(output_path.resolve())]
        try:
            SubprocessRunner.run(command, cwd=str(usmtoolkit_dir))
            # 변환 후 임시 중간 파일 정리
            for ext in AV_TEMP_EXTENSIONS:
                temp_file = usm_file.parent / (usm_file.stem + ext)
                if temp_file.exists():
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass
            return final_mp4_path if final_mp4_path.exists() else None
        except (OSError, subprocess.SubprocessError):
            return None


class FFmpegDownloader:
    def __init__(self, log_queue: queue.Queue, usmtoolkit_path_parent_dir: Path, get_lang_data_func: Callable[[], dict[str, str]]) -> None:
        """
        FFmpegDownloader 인스턴스 초기화.

        Args:
            log_queue (queue.Queue): GUI와 통신하기 위한 큐.
            usmtoolkit_path_parent_dir (Path): FFmpeg를 설치할 기준 디렉터리.
            get_lang_data_func (function): 현재 언어 데이터를 가져오는 함수.
        """
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_path_parent_dir
        self.ffmpeg_path = self.download_dir / FFMPEG_EXE_NAME
        self.version_marker_path = self.download_dir / FFMPEG_VERSION_FILENAME
        self.get_lang_data = get_lang_data_func
        os.makedirs(self.download_dir, exist_ok=True)

    def _log_entry(self, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가합니다."""
        self.log_queue.put(LogEvent(target='video', key=log_key, kwargs=kwargs))

    def _is_target_version_installed(self) -> tuple[bool, str]:
        """설치된 ffmpeg.exe가 목표 안정화 버전과 일치하는지 확인합니다."""
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
            res = SubprocessRunner.run([str(self.ffmpeg_path), "-version"])
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
        except Exception:
            return False, "unknown"

    def _verify_sha256(self, file_path: Path, expected_hash: str) -> bool:
        """파일의 SHA-256 해시를 계산하여 기대값과 일치하는지 검증합니다."""
        if not expected_hash:
            return True
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest().lower() == expected_hash.lower()

    def ensure_ffmpeg_ready(self) -> concurrent.futures.Future:
        """
        FFmpeg 준비 작업을 별도 스레드에서 시작하고 Future 객체를 반환합니다.

        Note:
            executor를 컨텍스트 매니저(with) 없이 사용합니다.
            with 문은 __exit__ 시 shutdown(wait=True)를 호출하여
            Future 반환 전에 블로킹되기 때문입니다.
            done_callback에서 try/finally로 shutdown을 보장하여
            콜백 예외 시에도 리소스 누수를 방지합니다.
        
        Returns:
            Future: 작업의 완료 여부와 결과를 확인할 수 있는 Future 객체.
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._actual_download_and_extract)

        def _shutdown_executor(_future: concurrent.futures.Future) -> None:
            try:
                _future.result()
            except Exception:
                pass
            finally:
                executor.shutdown(wait=False)

        future.add_done_callback(_shutdown_executor)
        return future

    def _actual_download_and_extract(self) -> bool:
        """실제 다운로드 및 압축 해제 로직을 수행합니다."""
        local_zip_path = self.download_dir / FFMPEG_ZIP_FILENAME
        temp_extract_dir = None

        # FFmpeg 버전 확인 및 존재 여부 검사
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
            with urllib.request.urlopen(req, timeout=10) as response, open(local_zip_path, 'wb') as out_file:
                if response.status != 200:
                    raise DownloadError(f"HTTP Error: {response.status} {response.reason}")
                shutil.copyfileobj(response, out_file)

            # 1-1. 다운로드된 파일 무결성 검증 (SHA-256 해시 검증)
            if FFMPEG_EXPECTED_SHA256 and not self._verify_sha256(local_zip_path, FFMPEG_EXPECTED_SHA256):
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
                # ZIP 파일 내에서 ffmpeg.exe 경로 탐색
                ffmpeg_internal_path = next((name for name in zip_ref.namelist() if name.endswith(f'/bin/{FFMPEG_EXE_NAME}')), None)
                if not ffmpeg_internal_path:
                    raise FileIntegrityError(str(local_zip_path), "expected folder structure not found in ZIP")
                # 필요한 파일만 추출 후 이동
                zip_ref.extract(ffmpeg_internal_path, temp_extract_dir)
                extracted_file = temp_extract_dir / ffmpeg_internal_path
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
