"""애플리케이션 기준 루트 경로(Base Path) 해석 모듈.

PyInstaller 패키징된 단일 포터블 실행 파일 환경(sys.frozen=True)과
로컬 개발 소스코드 실행 환경을 자동으로 감지하여,
사용자 데이터(로그, DB, 변환 결과물) 저장용 기준 경로 반환.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 소스 트리 실행 시 프로젝트 최상위 루트 식별용 센티넬(Sentinel) 파일명 목록
_PROJECT_SENTINELS = ("pyproject.toml", "README.md")


def _find_project_root(start: Path) -> Path | None:
    """상위 디렉터리를 순회하며 프로젝트 센티넬 파일이 존재하는 디렉터리 탐색.

    Args:
        start (Path): 탐색 시작 디렉터리 (통상 현재 파일의 부모 디렉터리).

    Returns:
        Path | None: 센티넬 파일이 발견된 최상위 디렉터리, 미발견 시 None.
    """
    for directory in (start, *start.parents):
        if any((directory / sentinel).is_file() for sentinel in _PROJECT_SENTINELS):
            return directory
    return None


def get_application_base_path() -> Path:
    """애플리케이션 기준 루트 경로(Path) 반환.

    실행 환경별 분기 처리:
    1. PyInstaller Frozen 환경 (getattr(sys, 'frozen', False) == True):
       - 임시 압축 해제 폴더(sys._MEIPASS)가 아닌, 실제 실행 파일(.exe) 위치 부모 폴더 반환.
       - 임시 폴더는 프로세스 종료 시 자동 삭제되므로 사용자 데이터 및 로그 보관에 부적합.
    2. 일반 Python 스크립트 실행 환경:
       - 현재 파일 위치에서 상위 디렉터리로 순회하며 프로젝트 센티넬
         (pyproject.toml 또는 README.md)이 존재하는 디렉터리를 최상위 루트로 반환.
       - src/utils/ 3단계 중첩 구조에 의존하지 않으므로 파일 배치가 바뀌어도 안정적으로 동작.
       - 센티넬 미발견 시 기존 동작(parents[2] = 3단계 상위)으로 폴백하여 하위 호환 유지.

    Returns:
        Path: 애플리케이션의 기준 경로(Path) 객체.
    """
    if getattr(sys, 'frozen', False):
        # 패키징(PyInstaller) 번들 환경: 임시 폴더(_MEIPASS) 대신 실행 파일 실제 위치 기준 경로 적용
        return Path(sys.executable).parent
    else:
        # 소스 트리 탐색: 프로젝트 센티넬 파일 기준 상위 루트 탐색, 미발견 시 기존 3단계 상위로 폴백
        source_root = _find_project_root(Path(__file__).resolve().parent)
        if source_root is not None:
            return source_root
        return Path(__file__).resolve().parent.parent.parent

