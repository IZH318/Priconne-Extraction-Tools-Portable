"""외부 서브프로세스 실행 표준화 및 프로세스 트리 관리 모듈.

FFmpeg, vgmstream, UsmToolkit 등 외부 CLI 도구 실행 시 GUI 콘솔 창 깜빡임(CREATE_NO_WINDOW)
방지 및 타임아웃 발생 시 프로세스 그룹 전체 종료(taskkill /T 또는 killpg).
실행 중인 프로세스는 클래스 수준 레지스트리로 추적되어, 애플리케이션 종료 시
terminate_all()로 잔류 프로세스 트리를 일괄 정리할 수 있다.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.constants import SUBPROCESS_REAP_TIMEOUT

logger = logging.getLogger(__name__)


class ProcessCancelledError(subprocess.SubprocessError):
    """취소 토큰에 의해 실행 중이던 서브프로세스가 종료되었음을 알리는 예외."""


# Windows taskkill.exe 절대 경로 캐시 (PATH/SystemRoot 조회는 최초 1회만 수행)
_TASKKILL_PATH: str | None = None
_TASKKILL_RESOLVED: bool = False


def _resolve_taskkill() -> str | None:
    """Windows taskkill 실행 파일의 절대 경로를 반환.

    PATH 조회(shutil.which)를 우선 시도하고, 실패 시 %SystemRoot%\\System32\\taskkill.exe로
    폴백한다. 어느 쪽도 찾지 못하면 None을 반환하여 호출부가 proc.kill()로 대체하도록 한다.
    """
    global _TASKKILL_PATH, _TASKKILL_RESOLVED
    if _TASKKILL_RESOLVED:
        return _TASKKILL_PATH
    candidate = shutil.which("taskkill")
    if candidate is None:
        system_root = os.environ.get("SystemRoot")
        if system_root:
            fallback = Path(system_root) / "System32" / "taskkill.exe"
            if fallback.exists():
                candidate = str(fallback)
    _TASKKILL_PATH = candidate
    _TASKKILL_RESOLVED = True
    return candidate


class SubprocessRunner:
    """외부 CLI 바이너리 실행 안전 캡슐화 래퍼 클래스."""

    # 실행 중인 자식 프로세스 레지스트리 (앱 종료 시 일괄 정리용)
    _registry_lock: threading.Lock = threading.Lock()
    _active_processes: set[subprocess.Popen[str]] = set()

    @classmethod
    def _register_process(cls, proc: subprocess.Popen[str]) -> None:
        """실행 중 프로세스를 레지스트리에 등록."""
        with cls._registry_lock:
            cls._active_processes.add(proc)

    @classmethod
    def _unregister_process(cls, proc: subprocess.Popen[str]) -> None:
        """종료된 프로세스를 레지스트리에서 제거."""
        with cls._registry_lock:
            cls._active_processes.discard(proc)

    @classmethod
    def terminate_all(cls) -> int:
        """현재 실행 중인 모든 자식 프로세스 트리를 종료 (앱 종료 경로 전용).

        Returns:
            int: 종료를 시도한(실행 중이던) 프로세스 수.
        """
        with cls._registry_lock:
            processes = [proc for proc in cls._active_processes if proc.poll() is None]
        for proc in processes:
            logger.info("Terminating active child process tree (pid=%s)", proc.pid)
            cls._kill_process_tree(proc)
        return len(processes)

    @staticmethod
    def run(
        command: list[str],
        cwd: str | Path | None = None,
        timeout: int | None = None,
        cancel_token: Any | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """표준화된 환경에서 외부 명령어 실행 및 결과 반환.

        주요 기능:
        1. GUI 창 숨김: Windows 환경에서 검은색 콘솔 창 깜빡임 방지용 CREATE_NO_WINDOW 적용.
        2. 프로세스 그룹 분리: Windows CREATE_NEW_PROCESS_GROUP, POSIX start_new_session=True 활성화.
        3. 자식 프로세스 잔류 방지: TimeoutExpired 발생 시 taskkill /F /T 또는 killpg(SIGKILL) 호출로
           파생 프로세스 트리 전체 종료.
        4. 인코딩 안전성: 문자열 디코딩 실패 시 프로세스 비정상 종료 방지를 위해 replace 오류 처리 정책 적용.

        Args:
            command (list[str]): 실행할 실행 파일 및 인자 리스트.
            cwd (str | Path | None): 작업 디렉터리 경로. 유효하지 않은 경로인 경우 FileNotFoundError 발생.
            timeout (int | None): 최대 대기 시간(초). 초과 시 subprocess.TimeoutExpired 발생.
            env (Mapping[str, str] | None): 자식 프로세스에 전달할 환경 변수. None이면 부모 환경을 상속.

        Returns:
            subprocess.CompletedProcess: 실행 완료된 프로세스의 반환 코드, stdout, stderr를 담은 객체.

        Raises:
            FileNotFoundError: 지정된 작업 디렉터리(cwd)가 존재하지 않는 경우.
            subprocess.TimeoutExpired: 제한된 시간 내에 프로세스가 종료되지 않는 경우.
        """
        is_windows = sys.platform == 'win32'

        # 윈도우 GUI 콘솔 창 노출 방지 및 프로세스 그룹 분리 플래그
        creationflags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if is_windows else 0

        if cwd is not None:
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                raise FileNotFoundError(f"cwd does not exist: {cwd_path}")
            cwd = str(cwd_path)

        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags,
            start_new_session=not is_windows,
            env=env,
        )
        SubprocessRunner._register_process(proc)
        try:
            if cancel_token is None:
                out, err = proc.communicate(timeout=timeout)
            else:
                out, err = SubprocessRunner._communicate_with_cancel(proc, command, timeout, cancel_token)
            return subprocess.CompletedProcess(
                args=command,
                returncode=proc.returncode,
                stdout=out,
                stderr=err,
            )
        except subprocess.TimeoutExpired:
            # 타임아웃 발생 시 잔류 프로세스 방지를 위해 프로세스 트리 전체 종료
            SubprocessRunner._kill_process_tree(proc)
            partial_out: str | bytes | None = None
            partial_err: str | bytes | None = None
            try:
                partial_out, partial_err = proc.communicate(timeout=SUBPROCESS_REAP_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.warning("Process %s did not terminate within %ss after kill", proc.pid, SUBPROCESS_REAP_TIMEOUT)
            except OSError as comm_exc:
                logger.warning("Failed to collect output of process %s: %s", proc.pid, comm_exc)
            raise subprocess.TimeoutExpired(
                command,
                float(timeout) if timeout is not None else 0.0,
                output=partial_out,
                stderr=partial_err,
            )
        except ProcessCancelledError:
            # 취소에 의한 종료는 이미 프로세스 트리를 정리했으므로 그대로 전파
            raise
        except BaseException:
            # communicate()가 비정상 중단된 경우(OSError/KeyboardInterrupt 등)에도
            # 자식 트리를 남기지 않도록 정리한 뒤 예외를 그대로 전파한다.
            SubprocessRunner._kill_process_tree(proc)
            raise
        finally:
            SubprocessRunner._unregister_process(proc)

    @staticmethod
    def _communicate_with_cancel(
        proc: subprocess.Popen[str],
        command: list[str],
        timeout: int | None,
        cancel_token: Any,
    ) -> tuple[Any, Any]:
        """취소 토큰을 주기적으로 확인하며 프로세스 출력을 수집.

        취소 시 프로세스 트리를 종료하고 ProcessCancelledError를 발생시킨다.
        전체 timeout이 경과하면 subprocess.TimeoutExpired를 발생시킨다.
        """
        poll_interval = 0.2
        deadline = (time.monotonic() + timeout) if timeout is not None else None
        while True:
            if cancel_token.is_cancelled:
                SubprocessRunner._kill_process_tree(proc)
                try:
                    proc.communicate(timeout=SUBPROCESS_REAP_TIMEOUT)
                except (subprocess.TimeoutExpired, OSError):
                    pass
                raise ProcessCancelledError(f"Process cancelled by token: {command!r}")
            wait = poll_interval
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, float(timeout) if timeout is not None else 0.0)
                wait = min(poll_interval, remaining)
            try:
                return proc.communicate(timeout=wait)
            except subprocess.TimeoutExpired:
                continue

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
        """타임아웃된 프로세스와 파생된 자식 프로세스 트리 전체를 종료.

        Windows: taskkill /F /T 로 트리 전체를 종료한다. taskkill을 찾지 못하면 proc.kill()로 폴백.
        POSIX: 자식 프로세스가 start_new_session=True로 세션/그룹 리더이므로 실제 PGID를 조회하여
        프로세스 그룹 전체에 SIGKILL을 전송한다. 이미 종료된 경우(ProcessLookupError)는 무시한다.
        """
        if sys.platform == 'win32':
            taskkill = _resolve_taskkill()
            if taskkill is not None:
                try:
                    subprocess.run(
                        [taskkill, '/F', '/T', '/PID', str(proc.pid)],
                        check=False,
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                except (OSError, subprocess.SubprocessError) as kill_exc:
                    logger.warning("Failed to kill process tree %s via taskkill: %s", proc.pid, kill_exc)
            else:
                logger.warning("taskkill not found; falling back to proc.kill() for pid %s", proc.pid)
            try:
                proc.kill()
            except OSError:
                pass
            return

        try:  # type: ignore[unreachable]
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            # 이미 종료된 프로세스
            return
        except OSError as pgid_exc:
            logger.warning("Failed to resolve process group of %s: %s", proc.pid, pgid_exc)
            try:
                proc.kill()
            except OSError:
                pass
            return

        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            # 이미 종료된 프로세스 그룹
            pass
        except OSError as kill_exc:
            logger.warning("Failed to kill process group %s: %s", pgid, kill_exc)
            try:
                proc.kill()
            except OSError:
                pass

