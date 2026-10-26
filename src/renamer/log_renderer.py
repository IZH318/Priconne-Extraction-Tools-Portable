"""Renamer 로그 렌더링 및 이력 버퍼 관리 모듈.

구조화된 로그 이벤트의 인메모리 링 버퍼를 유지하며 언어 변경 시 동적 다국어
재렌더링 지원. UI 뷰로부터 프레젠테이션 포맷팅, 트리 가지 접두사, 타임스탬프 그룹화를 분리.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any


class RenamerLogRenderer:
    """Renamer 탭의 로그 이벤트 이력 보관 및 다국어 텍스트 렌더링 관리 클래스.

    다국어 사전 키와 매개변수 딕셔너리를 포함하는 최대 10,000건의 로그 엔트리를 유지하여,
    언어 전환 시 타임스탬프나 내용 손실 없이 전체 UI 로그 재렌더링 지원.

    Attributes:
        get_string: 키 기반 다국어 번역 문자열 반환 콜백.
        get_lang_dict: 현재 언어 매핑 딕셔너리 반환 콜백.
        log_data: (timestamp, key, kwargs) 튜플의 시간순 리스트.
    """

    def __init__(
        self,
        get_string: Callable[..., str],
        get_lang_dict: Callable[[], dict[str, str]],
        get_lang_code: Callable[[], str],
        target_folders_provider: Callable[[], Sequence[str]],
        view: Any,
    ) -> None:
        """RenamerLogRenderer 초기화.

        Args:
            get_string: 다국어 번역 문자열 검색 콜백 함수.
            get_lang_dict: 현재 언어 딕셔너리 반환 콜백 함수.
            get_lang_code: 현재 언어 코드 문자열 반환 콜백 함수.
            target_folders_provider: 설정된 폴더명 시퀀스 반환 콜백 함수.
            view: write_log(text) 메서드를 보유한 프레젠테이션 뷰 인스턴스.
        """
        self.get_string = get_string
        self.get_lang_dict = get_lang_dict
        self._get_lang_code = get_lang_code
        self._target_folders_provider = target_folders_provider
        self._view = view

        self.log_data: list[tuple[Any, Any, Any]] = []
        self._render_cache: dict[Any, Any] = {}

    @property
    def _cache(self) -> dict[Any, Any]:
        """렌더 캐시용 하위 호환성 프로퍼티 별칭."""
        return self._render_cache

    def _target_folders(self) -> Sequence[str]:
        """설정된 대상 폴더명 시퀀스 안전 조회."""
        try:
            return self._target_folders_provider()
        except (TypeError, ValueError, AttributeError, RuntimeError):
            return []

    def _format_log_entry(
        self,
        timestamp: str | None,
        key: str,
        kwargs: dict[str, Any] | None,
        is_same_group: bool,
    ) -> tuple[str, str]:
        """단일 로그 이력 항목을 표시용 텍스트와 원본 메시지로 포맷팅.

        Args:
            timestamp: 포맷팅된 타임스탬프 문자열('HH:MM:SS.mmm') 또는 일반 텍스트용 None.
            key: 번역 사전 키 또는 일반 텍스트 문자열.
            kwargs: get_string에 전달할 동적 템플릿 변수 딕셔너리.
            is_same_group: 이전 항목과 동일 타임스탬프 여부 (동일 시 타임스탬프 반복 대신 들여쓰기 적용).

        Returns:
            (포맷팅_표시_텍스트, 다국어_메시지) 튜플.
        """
        if timestamp is None:
            return (key + "\n", key)

        render_kwargs = dict(kwargs) if kwargs is not None else None
        if key == 'initial_info_db' and render_kwargs is not None:
            folder_lines = []
            folders = self._target_folders()
            for idx, folder in enumerate(folders):
                prefix_key = 'folder_item_last' if idx == len(folders) - 1 else 'folder_item_branch'
                folder_lines.append(self.get_string(prefix_key, folder_name=folder))
            render_kwargs['folder_structure'] = "\n".join(folder_lines)

        message = self.get_string(key, **render_kwargs) if render_kwargs is not None else self.get_string(key)
        if not message:
            return ("", "")

        line_prefix = f"[{timestamp}] " if not is_same_group else ' ' * 13

        if key == 'backend_job_summary':
            return (f"\n[{timestamp}] {message}", message)
        return (f"{line_prefix}{message}", message)

    def redraw_all_logs(self) -> None:
        """활성 언어를 적용하여 전체 로그 이력을 UI 텍스트 위젯에 재렌더링.

        연속 호출 시 중복 연산을 방지하기 위해 (language_code, log_count, content_signature) 기반 캐싱 적용.
        """
        lang_code = self._get_lang_code()
        try:
            content_sig = hash(tuple((str(ts), str(key)) for ts, key, _ in self.log_data))
        except (TypeError, ValueError):
            content_sig = id(self.log_data)
        cache_key = (lang_code, len(self.log_data), content_sig)
        cache = self._render_cache
        if cache_key in cache:
            return

        output_buffer = []

        for i, (timestamp, key, kwargs) in enumerate(self.log_data):
            is_same_group = i > 0 and self.log_data[i - 1][0] == timestamp
            display_text, _ = self._format_log_entry(timestamp, key, kwargs, is_same_group)
            if display_text:
                output_buffer.append(display_text)

        final_text = "".join(output_buffer)
        self._view.write_log(final_text)
        cache[cache_key] = final_text
        if len(cache) > 4:
            oldest = next(iter(cache))
            del cache[oldest]

    def _add_raw_text(self, text: str) -> None:
        """포맷팅 없는 원시 문자열을 최대 10,000건 제한 버퍼에 추가."""
        self.log_data.append((None, text, None))
        if len(self.log_data) > 10000:
            del self.log_data[:len(self.log_data) - 10000]

    def _add_log_event(self, key: str, kwargs: dict[str, Any] | None = None) -> None:
        """타임스탬프가 포함된 구조화 로그 이벤트를 최대 10,000건 제한 버퍼에 추가."""
        if kwargs is None:
            kwargs = {}
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_data.append((timestamp, key, kwargs))
        if len(self.log_data) > 10000:
            del self.log_data[:len(self.log_data) - 10000]

    def show_initial_message(self) -> None:
        """프로그램 시작 안내 메시지 및 대상 디렉터리 트리 구성 출력."""
        self._add_log_event('program_started')
        self._add_raw_text("")

        folder_lines = []
        folders = self._target_folders()
        for i, folder in enumerate(folders):
            prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
            folder_lines.append(self.get_string(prefix_key, folder_name=folder))

        self._add_log_event('initial_info_db', {'folder_structure': "\n".join(folder_lines)})
        self._add_log_event('initial_info_start')
        self._add_raw_text("")

    def clear(self) -> None:
        """모든 로그 이력 항목 및 렌더 캐시 초기화."""
        self.log_data.clear()
        self._render_cache.clear()


# 하위 호환성을 위한 명명 규칙 별칭
RenamerLogManager = RenamerLogRenderer
RenamerLogService = RenamerLogRenderer


class RenamerLogManagerClass(RenamerLogRenderer):
    """RenamerLogRenderer의 하위 호환성 서브클래스 별칭."""
    pass
    pass
