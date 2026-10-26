"""장애 진단 및 사후 분석용 사용자 행동 궤적(Breadcrumbs) 추적 모듈.

GUI 내 사용자 버튼 클릭, 경로 선택, 설정 변경 등 최근 이벤트를 링 버퍼에 기록하고
예외 발생 시 최근 행동 이력을 에러 로그에 첨부.
"""
from __future__ import annotations

import copy
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class Breadcrumb:
    """단일 사용자 행동 궤적 레코드.

    Attributes:
        timestamp (str): 밀리초를 포함하는 발생 시각 ('YYYY-MM-DD HH:MM:SS.mmm').
        category (str): 이벤트 카테고리 (예: 'ui', 'io', 'conv', 'db').
        message (str): 행동 요약 설명 (예: 'Clicked Convert Video').
        data (Any): 이벤트 관련 추가 메타데이터 딕셔너리.
    """

    timestamp: str
    category: str
    message: str
    data: Any = field(default_factory=dict)

    def format(self) -> str:
        """에러 리포트용 포맷팅 단일 라인 문자열 반환.

        Returns:
            str: 시각, 4자리 카테고리, 메시지, 데이터를 포함하는 포맷 문자열.
        """
        data_str = f"  {self.data}" if self.data else ""
        return f"  [{self.timestamp}] [{self.category.upper()[:4]:4s}] {self.message}{data_str}"


class BreadcrumbBuffer:
    """스레드 안전한 행동 궤적 링 버퍼(Ring Buffer).

    지정된 최대 크기(max_size) 초과 시 가장 오래된 기록부터 순차 제거.
    메모리 누수 방지를 위해 2,000자 초과 데이터는 자동 절삭.

    Thread Safety:
        내부 threading.Lock을 통해 다중 스레드 동시 기록 및 안전 조회 보장.
    """

    def __init__(self, max_size: int = 50) -> None:
        """브레드크럼 버퍼 초기화.

        Args:
            max_size (int): 보관할 최대 궤적 개수. 기본값 50개.
        """
        self._max_size = max_size
        self._lock = threading.Lock()
        self._buffer: deque[Breadcrumb] = deque(maxlen=max_size)

    def add(self, category: str, message: str, data: dict[str, Any] | None = None) -> None:
        """새로운 행동 궤적 기록.

        Args:
            category (str): 행동 범주 (예: 'ui', 'system', 'worker').
            message (str): 행동 설명.
            data (dict[str, Any] | None): 추가 메타데이터. 2,000자 초과 시 절삭.
        """
        payload: Any = copy.deepcopy(data) if data else {}
        if len(str(payload)) > 2000:
            payload = {"_truncated": True}
        if isinstance(payload, dict):
            payload = MappingProxyType(payload)
        crumb = Breadcrumb(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            category=category,
            message=message,
            data=payload,
        )
        with self._lock:
            self._buffer.append(crumb)

    def get(self) -> list[Breadcrumb]:
        """현재 버퍼에 저장된 모든 궤적의 복사본 리스트 반환.

        Returns:
            list[Breadcrumb]: 오래된 순서대로 정렬된 브레드크럼 목록.
        """
        with self._lock:
            return list(self._buffer)

    def format(self) -> str:
        """최근 행동 궤적을 에러 로그 첨부용 다중 라인 문자열로 포맷팅.

        Returns:
            str: 헤더와 각 이벤트 라인으로 구성된 문자열. 빈 버퍼이면 빈 문자열.
        """
        crumbs = self.get()
        if not crumbs:
            return ""
        lines = [f"[BREADCRUMBS] Recent {len(crumbs)} actions before error:"]
        for crumb in crumbs:
            lines.append(crumb.format())
        return "\n".join(lines)


# 기본 전역 버퍼
_default_buffer = BreadcrumbBuffer()


def add_breadcrumb(category: str, message: str, data: dict[str, Any] | None = None) -> None:
    """기본 버퍼에 사용자 행동 궤적 기록.

    Args:
        category (str): 이벤트 카테고리.
        message (str): 행동 설명.
        data (dict[str, Any] | None): 부가 정보 딕셔너리.
    """
    _default_buffer.add(category, message, data)


def get_breadcrumbs() -> list[Breadcrumb]:
    """기본 버퍼에 저장된 모든 궤적 목록 반환.

    Returns:
        list[Breadcrumb]: 보관된 브레드크럼 리스트.
    """
    return _default_buffer.get()


def format_breadcrumbs() -> str:
    """기본 버퍼의 모든 궤적을 에러 로그용 문자열로 포맷팅.

    Returns:
        str: 포맷팅된 브레드크럼 문자열.
    """
    return _default_buffer.format()

