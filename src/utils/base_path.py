"""애플리케이션 기준 루트 경로(Base Path) 해석 모듈.

PyInstaller 패키징된 단일 포터블 실행 파일 환경(sys.frozen=True)과
로컬 개발 소스코드 실행 환경을 자동으로 감지하여,
사용자 데이터(로그, DB, 변환 결과물) 저장용 기준 경로 반환.
"""
from __future__ import annotations

import sys
from pathlib import Path


def get_application_base_path() -> Path:
    """애플리케이션 기준 루트 경로(Path) 반환.

    실행 환경별 분기 처리:
    1. PyInstaller Frozen 환경 (getattr(sys, 'frozen', False) == True):
       - 임시 압축 해제 폴더(sys._MEIPASS)가 아닌, 실제 실행 파일(.exe) 위치 부모 폴더 반환.
       - 임시 폴더는 프로세스 종료 시 자동 삭제되므로 사용자 데이터 및 로그 보관에 부적합.
    2. 일반 Python 스크립트 실행 환경:
       - 소스 트리 구조(src/utils/base_path.py 기준 3단계 상위) 탐색 기반 프로젝트 최상위 루트 디렉터리 반환.

    Returns:
        Path: 애플리케이션의 영속적 기준 경로 객체.
    """
    if getattr(sys, 'frozen', False):
        # 패키징(PyInstaller) 번들 환경: 임시 폴더(_MEIPASS) 대신 실행 파일 실제 위치 기준 경로 적용
        return Path(sys.executable).parent
    else:
        # 소스 트리 탐색: src/utils/base_path.py → src/utils → src → 프로젝트 루트
        return Path(__file__).resolve().parent.parent.parent

