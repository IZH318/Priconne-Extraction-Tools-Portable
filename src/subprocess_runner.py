from __future__ import annotations
import subprocess
import sys

class SubprocessRunner:
    """외부 프로세스 실행을 표준화하는 래퍼 클래스입니다."""
    
    @staticmethod
    def run(command: list[str], cwd: str | None = None, timeout: int | None = None, encoding: str | None = None) -> subprocess.CompletedProcess[str]:
        """
        Windows 시스템에서의 콘솔 숨김 플래그 및 공통 I/O 인코딩, 타임아웃 처리가 적용된
        표준 subprocess.run 메서드입니다.
        
        Args:
            command: 실행할 커맨드 리스트.
            cwd: 작업 디렉토리 절대 경로 (옵션).
            timeout: 실행 타임아웃 (초, 옵션).
            encoding: 입출력 인코딩 (기본값: 'utf-8').
            
        Returns:
            subprocess.CompletedProcess[str]: 프로세스 실행 결과.
            
        Raises:
            subprocess.TimeoutExpired: 타임아웃 초과 시.
            Exception: 알 수 없는 기타 예외 발생 시.
        """
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

        # capture_output=True, text=True 설정으로 출력을 문자열로 캡처
        # UTF-8 기본 인코딩과 errors='replace'를 통해 인코딩 깨짐 방지
        return subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding=encoding or 'utf-8',
            errors='replace',
            creationflags=creationflags,
            check=False # 에러 코드 발생 시 예외를 던지지 않고 returncode로 반환
        )
