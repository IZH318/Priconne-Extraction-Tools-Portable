from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModuleController(Protocol):
    """모든 모듈 Controller가 구현해야 하는 공통 인터페이스입니다.

    main.py의 on_closing()에서 덕 타이핑 대신 타입 안전한 호출을 보장합니다.
    """

    def cleanup(self) -> None:
        """앱 종료 시 리소스를 해제합니다."""
        ...

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        ...

    def get_lang_dict(self) -> dict[str, str]:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        ...
