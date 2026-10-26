"""Story Viewer 실시간 파일 목록 필터링 서비스 모듈.

입력된 검색어(파일명, 스토리 ID, 에피소드 제목)를 기준으로
파일 목록을 실시간 필터링하고 UI 리스트 갱신.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable
from typing import Any


class StoryFilterService:
    """스토리 파일 목록 실시간 검색 및 필터링 서비스.

    검색창 입력에 맞춰 파일명, 숫자 ID, 에피소드 제목(Title)에서
    대소문자 구분 없이 부분 일치 검색.

    Attributes:
        _view (Any): UI 조작용 상위 뷰 객체.
        _get_lang_dict (Callable[[], dict[str, str]]): 다국어 사전 조회 콜백.
        _get_base_search_files (Callable[[], list[str]]): 윈도우 상세 검색 결과 파일 목록 조회 콜백.
        _set_base_search_files (Callable[[list[str]], None]): 윈도우 상세 검색 결과 파일 목록 저장 콜백.
        _get_loaded_filenames (Callable[[], list[str]]): 로드된 전체 파일 이름 목록 조회 콜백.
        _get_file_titles (Callable[[], dict[str, str]]): 파일명-스토리제목 매핑 조회 콜백.
        _update_file_list (Callable[..., None]): 필터링된 파일 목록 UI 갱신 콜백.
        _filter_var (Any): 검색 입력창 바인딩 문자열 변수.
    """

    def __init__(
        self,
        view: Any,
        get_lang_dict: Callable[[], dict[str, str]],
        get_base_search_files: Callable[[], list[str]],
        set_base_search_files: Callable[[list[str]], None],
        get_loaded_filenames: Callable[[], list[str]],
        get_file_titles: Callable[[], dict[str, str]],
        update_file_list: Callable[..., None],
        filter_var: Any,
        shared_state: Any = None,
    ) -> None:
        """StoryFilterService 인스턴스 초기화.

        Args:
            view (Any): 상위 뷰 인스턴스.
            get_lang_dict (Callable[[], dict[str, str]]): 다국어 맵 반환 함수.
            get_base_search_files (Callable[[], list[str]]): 검색 필터 기준 파일 목록 반환 함수.
            set_base_search_files (Callable[[list[str]], None]): 검색 필터 기준 파일 목록 설정 함수.
            get_loaded_filenames (Callable[[], list[str]]): 로드된 전체 파일 목록 반환 함수.
            get_file_titles (Callable[[], dict[str, str]]): 파일별 제목 매핑 반환 함수.
            update_file_list (Callable[..., None]): 리스트박스 갱신 콜백.
            filter_var (Any): 필터 텍스트 변수.
            shared_state (Any): 상위 상태 컨테이너.
        """
        self._view = view
        self._get_lang_dict = get_lang_dict
        self._get_base_search_files = get_base_search_files
        self._set_base_search_files = set_base_search_files
        self._get_loaded_filenames = get_loaded_filenames
        self._get_file_titles = get_file_titles
        self._update_file_list = update_file_list
        self._filter_var = filter_var


    def set_search_results(self, filenames: list[str]) -> None:
        """검색 결과 파일 목록 설정 후 필터 갱신."""
        self._set_base_search_files(list(filenames))
        self.apply_filter()

    def clear_filter(self) -> None:
        """검색창 초기화 및 플레이스홀더 복원."""
        self._filter_var.set("")
        with contextlib.suppress(tk.TclError, RuntimeError, AttributeError):
            self._view.show_filter_placeholder()

    def apply_filter(self) -> None:
        """현재 검색어 기준 파일 목록 필터링 및 리스트 갱신."""
        query = self._filter_var.get().strip().lower()
        placeholder = self._get_lang_dict().get('filter_placeholder', 'ID, title, filename...').strip().lower()
        source_files = self._get_base_search_files() if self._get_base_search_files() else list(self._get_loaded_filenames())

        if not query or query == placeholder:
            self._update_file_list(source_files)
            return

        matched = []
        for fname in source_files:
            if query in fname.lower():
                matched.append(fname)
                continue
            import re
            match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', fname)
            if match and query in match.group(1):
                matched.append(fname)
                continue
            title = self._get_file_titles().get(fname, "")
            if query in title.lower():
                matched.append(fname)
                continue

        self._update_file_list(matched)
