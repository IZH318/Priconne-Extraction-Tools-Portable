"""운영체제 기본 프로그램 연동 유틸리티 모듈.

변환 완료된 오디오/비디오 파일 재생, 추출된 텍스처/메시 폴더 탐색기 열기 등
운영체제 기본 프로그램(xdg-open / open, Windows ShellExecute)을 통한
파일 및 폴더 열기 지원.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def open_with_default_app(file_path: str) -> None:
    """운영체제 기본 프로그램 또는 탐색기로 파일 및 폴더 열기.

    Windows에서는 os.startfile(file_path)을 호출하여 ShellExecute 실행.
    그 외 플랫폼에서는 셸 해석(shell=True, cmd /c) 없이 인자 목록(list-arg) 기반으로
    외부 오프너(xdg-open / open)를 직접 실행하여 path 재해석 및 명령 인젝션 위험 방지.

    Args:
        file_path (str): 열고자 하는 파일 또는 폴더의 절대 경로.

    Raises:
        FileNotFoundError: 지정된 경로가 디스크 상에 존재하지 않는 경우.
        OSError: 기본 프로그램 실행에 실패한 경우.
    """
    if not os.path.exists(file_path):
        logger.warning("File does not exist: %s", file_path)
        raise FileNotFoundError(file_path)

    logger.info("Opening %s with default app", file_path)
    if sys.platform == 'win32':
        os.startfile(file_path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', file_path])
    else:
        subprocess.Popen(['xdg-open', file_path])

