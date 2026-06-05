from __future__ import annotations
import os
import sys
import subprocess


def open_with_default_app(file_path: str) -> None:
    """OS 기본 프로그램으로 파일을 엽니다.

    플랫폼별 차이를 추상화하여 Windows, macOS, Linux에서 동일하게 동작합니다.

    Args:
        file_path: 열 파일의 절대 경로.

    Raises:
        OSError: 파일이 존재하지 않거나 열 수 없는 경우.
    """
    if sys.platform == 'win32':
        os.startfile(file_path)
    elif sys.platform == 'darwin':
        subprocess.call(['open', file_path])
    else:
        subprocess.call(['xdg-open', file_path])
