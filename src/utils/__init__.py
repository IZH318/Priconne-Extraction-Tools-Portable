"""공통 유틸리티 패키지.

보안(Zip-Slip 방어), 파일 시스템 경로 해석, 에러 로그 포맷팅,
Tkinter 위젯 생명주기 안전 조작, 마우스 툴팁, 파일 목록 믹스인,
OS 기본 프로그램 연동 및 어바웃 대화상자 모듈 통합 제공.
"""
from __future__ import annotations

__all__ = [
    "about_dialog",
    "base_path",
    "error_log",
    "file_list_mixin",
    "platform_open",
    "tk_safe",
    "tooltip",
    "zip_safe",
]

