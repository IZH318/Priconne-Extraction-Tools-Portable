from __future__ import annotations
import sys
from pathlib import Path


def get_application_base_path() -> Path:
    """애플리케이션의 기준 경로를 반환합니다.

    PyInstaller frozen 빌드 환경과 일반 스크립트 실행 환경을 자동으로
    감지하여 적절한 기준 경로를 반환합니다.

    - frozen 빌드: 실행 파일이 위치한 디렉터리
    - 일반 실행: 프로젝트 루트 디렉터리 (src의 상위)

    Returns:
        애플리케이션 기준 경로의 Path 객체.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        # src/utils/base_path.py → src/utils → src → 프로젝트 루트
        return Path(__file__).resolve().parent.parent.parent
