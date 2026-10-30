"""매니페스트 기반 파일 이름 복원(Renamer) 서브툴 패키지.

프린세스 커넥트 Re:Dive 리소스 덤프 시 생성되는 40자 SHA1 해시 파일명을
매니페스트 데이터베이스 정보를 대조하여 원본 에셋 경로 및 파일명으로 복원.
"""
from __future__ import annotations

from .gui import FileRenamerGUI

__all__ = ["FileRenamerGUI"]
