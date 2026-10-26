"""외부 서브프로세스 실행 표준화 및 프로세스 트리 관리 모듈.

FFmpeg, vgmstream, UsmToolkit 등 외부 CLI 도구 실행 시 GUI 콘솔 창 깜빡임(CREATE_NO_WINDOW)
차단 및 타임아웃 발생 시 프로세스 그룹 전체 강제 종료(taskkill /T 또는 killpg).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SubprocessRunner:
    """외부 CLI 바이너리 실행 안전 캡슐화 래퍼 클래스."""

    @staticmethod
    def run(
        command: list[str],
        cwd: str | Path | None = None,
        timeout: int | None = None,
        encoding: str | None = None,
        input: str | bytes | None = None,
        env: dict[str, str] | None = None,
        text: bool = True,
        errors: str = "replace",
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """표준화된 환경에서 외부 명령어 실행 및 결과 반환.

        주요 기능:
        1. GUI 창 숨김: Windows 환경에서 검은색 콘솔 창 깜빡임 방지용 CREATE_NO_WINDOW 적용.
        2. 프로세스 그룹 격리: Windows CREATE_NEW_PROCESS_GROUP 활성화.
        3. 자식 프로세스 잔류 방지: TimeoutExpired 발생 시 taskkill /F /T 호출로 파생 프로세스 트리 전체 강제 종료.
        4. 인코딩 안전성: 문자열 디코딩 실패 시 프로세스 비정상 종료 방어용 replace 오류 처리 정책 적용.

        Args:
            command (list[str]): 실행할 실행 파일 및 인자 리스트.
            cwd (str | Path | None): 작업 디렉터리 경로. 유효하지 않은 경로인 경우 FileNotFoundError 발생.
            timeout (int | None): 최대 대기 시간(초). 초과 시 subprocess.TimeoutExpired 발생.
            encoding (str | None): 텍스트 I/O 인코딩. None인 경우 기본 'utf-8'.
            input (str | bytes | None): 표준 입력(stdin)으로 전달할 데이터.
            env (dict[str, str] | None): 서브프로세스에 주입할 환경 변수 딕셔너리.
            text (bool): True이면 stdout/stderr를 문자열로 디코딩, False이면 바이트로 반환.
            errors (str): 디코딩 에러 처리 정책 (기본값: 'replace').
            capture_output (bool): True이면 stdout과 stderr를 캡처하여 반환.

        Returns:
            subprocess.CompletedProcess: 실행 완료된 프로세스의 반환 코드, stdout, stderr를 담은 객체.

        Raises:
            FileNotFoundError: 지정된 작업 디렉터리(cwd)가 존재하지 않는 경우.
            subprocess.TimeoutExpired: 제한된 시간 내에 프로세스가 종료되지 않은 경우.
        """
        # 윈도우 GUI 콘솔 창 노출 방지 및 프로세스 그룹 분리 플래그
        creationflags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == 'win32' else 0

        if cwd is not None:
            cwd_path = Path(cwd)
            if not cwd_path.exists():
                raise FileNotFoundError(f"cwd does not exist: {cwd_path}")
            cwd = str(cwd_path)

        enc = encoding or 'utf-8'

        def _execute(err_mode: str) -> subprocess.CompletedProcess:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                env=env,
                text=text,
                encoding=enc if text else None,
                errors=err_mode if text else None,
                creationflags=creationflags,
            )
            try:
                out, err = proc.communicate(input=input, timeout=timeout)
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=proc.returncode,
                    stdout=out,
                    stderr=err,
                )
            except subprocess.TimeoutExpired:
                # 타임아웃 발생 시 잔류 프로세스 방지를 위해 프로세스 트리 전체 강제 종료
                pid = proc.pid
                try:
                    if sys.platform == 'win32':
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], check=False, capture_output=True)
                    else:
                        os.killpg(pid, 9)
                except (OSError, subprocess.SubprocessError) as kill_exc:
                    logger.warning("Failed to kill process group %s: %s", pid, kill_exc)
                try:
                    proc.kill()
                except OSError:
                    pass
                out, err = proc.communicate()
                raise subprocess.TimeoutExpired(command, float(timeout) if timeout is not None else 0.0, output=out, stderr=err)

        return _execute(errors)

