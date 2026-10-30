"""AV Converter 변환 엔진 (`ConversionLogic`) 모듈.

CRI Sofdec (.usm) 비디오 디먹싱 및 H.264/AAC MP4 인코딩, CRI Atom (.awb) 멀티트랙
오디오 디코딩 및 WAV 변환 로직을 담당한다. 외부 도구 다운로드/검증은 `media_tools`
하위 모듈로 분리되어 있다.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import os
import queue
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.constants import (
    AV_STEM_HASH_LEN,
    AV_TEMP_EXTENSIONS,
    DOTNET_EXE_NAME,
    DOTNET_RUNTIME_DIR_NAME,
    SENTINEL_AUDIO_DONE,
    SENTINEL_VIDEO_DONE,
    SUBPROCESS_AUDIO_CONVERT_RETRIES,
    SUBPROCESS_AUDIO_CONVERT_TIMEOUT,
    SUBPROCESS_PREVIEW_TIMEOUT,
    SUBPROCESS_VIDEO_CONVERT_TIMEOUT,
    TEMP_AVTMP_PREFIX,
    TEMP_PARTIAL_SUFFIX,
    TabType,
)
from src.queue_events import CompletionEvent, LogBlockEvent, LogEvent, ProgressEvent
from src.subprocess_runner import ProcessCancelledError, SubprocessRunner
from src.utils.task_pool import DaemonThreadPoolExecutor
from src.utils.temp_registry import register_temp_artifact, unregister_temp_artifact

from .media_tools.probe import (
    collect_local_dotnet_runtimes,
    collect_system_dotnet_runtimes,
    find_satisfying_dotnet_runtime,
    is_dotnet_force_local_runtime,
)
from .naming import expected_output_extension, sanitize_stream_filename

if TYPE_CHECKING:
    from src.cancellation_token import CancellationToken

logger = logging.getLogger(__name__)


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
                #    다른 입력의 stem과 겹치면 그 작업의 중간 파일이므로 남겨둔다.
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
                os.replace(path, path.with_name(path.name + TEMP_PARTIAL_SUFFIX))
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
            partial = path.with_name(path.name + TEMP_PARTIAL_SUFFIX)
            if partial.is_file():
                os.remove(partial)
        except OSError as exc:
            logger.debug("Failed to remove quarantined output %s: %s", partial, exc)

    def __init__(self, log_queue: queue.Queue[Any], base_path: Path) -> None:
        """ConversionLogic 인스턴스 초기화.

        Args:
            log_queue (queue.Queue): GUI 통신용 큐.
            base_path (Path): 프로그램 실행 기준 경로.
        """
        self.log_queue = log_queue
        self.base_path = base_path
        # 시스템 .NET 요구 버전 충족 여부 캐시 (세션 중 1회 계산)
        self._system_dotnet_ok: bool | None = None

    def _log_entry(self, target_tab: TabType, log_key: str, **kwargs: Any) -> None:
        """로그 메시지를 통신 큐에 추가."""
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def get_relative_path(self, full_path: str | Path) -> str:
        """로그에 표시할 파일의 상대 경로 계산."""
        try:
            return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError):
            return str(full_path)

    def _run_subprocess(self, command: list[str], cancel_token: Any | None = None) -> subprocess.CompletedProcess[str]:
        """외부 프로세스를 실행하고 출력을 캡처하는 헬퍼 함수."""
        return SubprocessRunner.run(command, timeout=SUBPROCESS_AUDIO_CONVERT_TIMEOUT, cancel_token=cancel_token)

    def get_dotnet_runtimes_by_source(self) -> dict[str, list[str]]:
        """.NET Runtime (Microsoft.NETCore.App) 목록을 시스템/로컬로 구분해 반환."""
        return {
            "system": collect_system_dotnet_runtimes(),
            "local": collect_local_dotnet_runtimes(self.base_path),
        }

    def _system_dotnet_satisfies(self) -> bool:
        """시스템 .NET Runtime이 UsmToolkit 요구 버전(3.1 이상)을 만족하는지 여부 반환 (1회 캐시)."""
        if self._system_dotnet_ok is None:
            self._system_dotnet_ok = find_satisfying_dotnet_runtime(collect_system_dotnet_runtimes()) is not None
        return self._system_dotnet_ok

    def dotnet_runtime_env(self, usmtoolkit_dir: Path) -> dict[str, str]:
        """UsmToolkit 실행 시 주입할 자식 프로세스 환경 반환.

        Args:
            usmtoolkit_dir (Path): UsmToolkit.exe가 위치한 폴더 경로.

        Returns:
            dict[str, str]: 주입할 환경 맵.
        """
        env = dict(os.environ)
        # UsmToolkit(netcoreapp3.1)이 시스템의 상위 메이저 런타임으로 롤포워드되도록 강제
        env["DOTNET_ROLL_FORWARD"] = "Major"
        if not is_dotnet_force_local_runtime() and self._system_dotnet_satisfies():
            return env
        dotnet_dir = usmtoolkit_dir / DOTNET_RUNTIME_DIR_NAME
        if not (dotnet_dir / DOTNET_EXE_NAME).is_file():
            return env
        env["DOTNET_ROOT"] = str(dotnet_dir)
        # 머신 전역 .NET 조회를 비활성화하여 지정한 로컬 런타임만 사용하도록 강제
        env["DOTNET_MULTILEVEL_LOOKUP"] = "0"
        return env

    def _convert_single_video_task(
        self,
        usm_file_str: str,
        output_dir: str,
        usmtoolkit_path: Path,
        target_stem: str | None = None,
        protected_stems: set[str] | None = None,
        cancel_token: Any | None = None,
    ) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        """
        단일 비디오(.usm) 파일을 변환하는 작업 태스크.

        Args:
            usm_file_str (str): 변환할 USM 파일 경로.
            output_dir (str): 출력 디렉터리 경로.
            usmtoolkit_path (Path): UsmToolkit.exe 파일 경로.
            target_stem (str | None): 출력 파일 stem. 동일 stem 입력 충돌 시 호출자가
                입력 경로 기반 접미사를 붙여 전달하며, None이면 원본 stem을 사용.
            protected_stems (set[str] | None): 같은 배치의 다른 입력 stem 집합.
                해당 stem의 중간 파일은 그 작업이 직접 정리하도록 남겨둔다.

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
        run_dir = output_path / f"{TEMP_AVTMP_PREFIX}{out_stem}" if is_duplicate_stem else output_path

        log_entries = [('spacing', {}),
                       ('conv_log_source', {'path': self.get_relative_path(usm_file)})]
        status = "unknown"

        if cancel_token is not None and cancel_token.is_cancelled:
            return "cancelled", log_entries

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
                # 외부 UsmToolkit 프로세스 실행 (로컬 런타임 사용 시 자식 프로세스에만 주입)
                result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_VIDEO_CONVERT_TIMEOUT,
                                              cancel_token=cancel_token, env=self.dotnet_runtime_env(usmtoolkit_dir))

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

                    # 이전 실패로 남은 미완성 파일(.partial) 제거 (중간 파일은 finally에서 정리)
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

            except ProcessCancelledError:
                # 취소에 의한 중단: 부분 산출물은 finally에서 정리되고, 실패로 집계하지 않는다.
                status = "cancelled"
                log_entries.append(('conv_log_result_header', {}))
            except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, AttributeError, KeyError, TypeError) as e:
                status = "error"
                log_entries.append(('conv_log_result_header', {}))
                log_entries.append(('conv_log_error_exception', {'error': str(e)}))
                self._quarantine_output(final_mp4_path)
            finally:
                # 성공/실패/타임아웃 어느 경로에서도 디먹싱 중간 파일을 정리한다.
                # (UsmToolkit은 정상 완료 시 스스로 정리하므로, 이 정리는 중단/실패 대비 안전망이다)
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
                    digest = hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:AV_STEM_HASH_LEN]
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
                    cancel_token,
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
                    digest = hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:AV_STEM_HASH_LEN]
                    unique_stems[path] = f"{source_stem}_{digest}"
                else:
                    unique_stems[path] = source_stem

            future_to_path = {
                executor.submit(
                    self._convert_audio_container, path, output_dir, vgmstream_path, overwrite, unique_stems[path], cancel_token
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
        cancel_token: Any | None = None,
    ) -> tuple[int, list[tuple[str, dict[str, Any]]], str]:
        """
        단일 오디오 컨테이너(.awb) 파일 내의 모든 스트림을 변환하는 작업 태스크.

        Args:
            item_path_str (str): 대상 오디오 컨테이너 경로.
            output_dir (str): 결과 WAV를 저장할 루트 폴더.
            vgmstream_path (Path | str): vgmstream 실행 파일 경로.
            overwrite (bool): 기존 WAV 덮어쓰기 여부.
            target_stem (str | None): 출력 하위 폴더명. 동일 stem 입력 충돌 시 호출자가
                입력 경로 기반 접미사를 붙여 전달하며, None이면 원본 stem을 사용.

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

        if cancel_token is not None and cancel_token.is_cancelled:
            return 0, log_entries, "cancelled"

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
            if cancel_token is not None and cancel_token.is_cancelled:
                break
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
            result: subprocess.CompletedProcess[str] | None = None
            stream_cancelled = False
            max_attempts = SUBPROCESS_AUDIO_CONVERT_RETRIES + 1
            for attempt in range(max_attempts):
                try:
                    result = self._run_subprocess(command, cancel_token)
                    break
                except ProcessCancelledError:
                    stream_cancelled = True
                    break
                except subprocess.TimeoutExpired:
                    if attempt + 1 >= max_attempts:
                        raise
                    logger.warning(
                        "Audio stream decode timed out (attempt %d/%d); retrying: %s",
                        attempt + 1, max_attempts, output_file.name,
                    )
                    # 재시도 전 부분 출력을 제거해 깨끗한 상태에서 다시 디코딩.
                    try:
                        if output_file.is_file():
                            os.remove(output_file)
                    except OSError as exc:
                        logger.debug("Failed to remove partial output %s before retry: %s", output_file, exc)
                    continue

            if stream_cancelled:
                break
            if result is None:
                continue

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
            result = SubprocessRunner.run(command, cwd=str(usmtoolkit_dir), timeout=SUBPROCESS_PREVIEW_TIMEOUT,
                                          env=self.dotnet_runtime_env(usmtoolkit_dir))
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
