"""Resource Remover 서비스 모듈.

컨트롤러와 ResourceRemoverLogic 간 데이터 전달 및
공유 상태(SharedState)의 다국어 번역 연동 담당.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .logic import ResourceRemoverLogic


class ResourceRemovalService:
    """리소스 탐색 및 삭제 비즈니스 로직을 컨트롤러에 제공하는 서비스 계층 클래스."""

    def __init__(
        self,
        shared_state: Any = None,
        logic: Any = None,
    ) -> None:
        """ResourceRemovalService 초기화.

        Args:
            shared_state (Any): 공통 상태 및 다국어 콜백을 제공하는 SharedState 객체.
            logic (ResourceRemoverLogic | None): 도메인 로직 인스턴스 (None이면 신규 생성).
        """
        if logic is None:
            logic = ResourceRemoverLogic()
        self._logic: ResourceRemoverLogic = logic
        self._shared_state = shared_state
        if shared_state is not None and callable(getattr(shared_state, "get_lang_dict", None)):
            self._get_lang_dict = shared_state.get_lang_dict
        else:
            self._get_lang_dict = dict

    @property
    def logic(self) -> ResourceRemoverLogic:
        """하위 도메인 로직 인스턴스 반환."""
        return self._logic

    def get_lang_dict(self) -> dict[str, str]:
        """현재 활성화된 다국어 UI 번역 딕셔너리 반환."""
        try:
            return self._get_lang_dict() or {}
        except (TypeError, ValueError, AttributeError, RuntimeError):
            return {}

    def count_resources(self, extensions_to_remove: Sequence[str]) -> list[Any]:
        """지정된 확장자를 가진 파일들을 검색하여 파일 목록 반환.

        Args:
            extensions_to_remove (Sequence[str]): 검색할 대상 확장자 시퀀스.

        Returns:
            list[Path]: 검색된 파일들의 Path 목록.
        """
        return self._logic.count_resources(extensions_to_remove)

    def remove_resources(
        self,
        target_files: Sequence[Any],
        extensions_to_remove: Sequence[str],
        use_trash: bool = True,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> tuple[int, list[str], str]:
        """대상 파일들을 안전하게 삭제하거나 휴지통으로 이동.

        Args:
            target_files (Sequence[Any]): 삭제 대상 파일 경로 시퀀스.
            extensions_to_remove (Sequence[str]): 삭제 허용 확장자 시퀀스.
            use_trash (bool): True이면 휴지통 이동, False이면 영구 삭제.
            progress_cb (Callable[[int, int], None] | None): 진행 콜백.

        Returns:
            tuple[int, list[str], str]: (삭제 성공 수, 실패 사유 목록, 로그 파일 경로).
        """
        return self._logic.remove_resources(
            target_files=target_files,
            extensions_to_remove=extensions_to_remove,
            use_trash=use_trash,
            progress_cb=progress_cb,
        )

