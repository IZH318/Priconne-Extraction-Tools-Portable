"""장애 진단 및 사후 분석용 동작 추적(Breadcrumbs) 모듈.

GUI 내 사용자 버튼 클릭, 경로 선택, 설정 변경 등 최근 이벤트를 메모리 버퍼에 누적 기록하고
예외 발생 시 동작 이력을 에러 로그에 첨부.
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
    """단일 동작 추적(Breadcrumb) 레코드.

    Attributes:
        timestamp (str): 밀리초를 포함하는 발생 시각 ('YYYY-MM-DD HH:MM:SS.mmm').
        category (str): 이벤트 카테고리 (예: 'ui', 'io', 'conv', 'db').
        message (str): 동작 요약 설명 (예: 'Clicked Convert Video').
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
    """스레드 세이프(Thread-safe) 브레드크럼 버퍼.

    Thread Safety:
        내부 threading.Lock을 통해 다중 스레드 동시 기록 및 안전 조회 보장.
    """

    def __init__(self) -> None:
        """브레드크럼 버퍼 초기화."""
        self._lock = threading.Lock()
        self._buffer: deque[Breadcrumb] = deque()

    def add(self, category: str, message: str, data: dict[str, Any] | None = None) -> None:
        """새로운 브레드크럼(동작 이력) 기록.

        Args:
            category (str): 이벤트 범주 (예: 'ui', 'system', 'worker').
            message (str): 동작 설명.
            data (dict[str, Any] | None): 추가 메타데이터.
        """
        payload: Any = copy.deepcopy(data) if data else {}
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
        """현재 버퍼에 저장된 모든 브레드크럼의 복사본 리스트 반환.

        Returns:
            list[Breadcrumb]: 오래된 순서대로 정렬된 브레드크럼 목록.
        """
        with self._lock:
            return list(self._buffer)

    def format(self) -> str:
        """최근 브레드크럼을 에러 로그 첨부용 다중 라인 문자열로 포맷팅.

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
    """기본 버퍼에 브레드크럼 기록.

    Args:
        category (str): 이벤트 카테고리.
        message (str): 동작 설명.
        data (dict[str, Any] | None): 부가 정보 딕셔너리.
    """
    _default_buffer.add(category, message, data)


def format_breadcrumbs() -> str:
    """기본 버퍼의 모든 브레드크럼을 에러 로그용 문자열로 포맷팅.

    Returns:
        str: 포맷팅된 브레드크럼 문자열.
    """
    return _default_buffer.format()


