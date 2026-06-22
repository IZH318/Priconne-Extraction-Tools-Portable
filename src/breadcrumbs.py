from __future__ import annotations
"""
에러 발생 직전의 행동 궤적(Breadcrumbs)을 기록하는 인메모리 버퍼 모듈.

주요 작업 시점마다 add_breadcrumb()를 호출하여 궤적을 남기면,
예외 발생 시 write_error_log()에서 자동으로 최근 궤적을 함께 기록합니다.

사용 예:
    from src.breadcrumbs import add_breadcrumb, get_breadcrumbs

    add_breadcrumb("ui", "폴더 열기 버튼 클릭")
    add_breadcrumb("io", "파일 로드 시작", {"path": "/some/file.json"})
    add_breadcrumb("db", "이벤트 목록 조회", {"server": "JP"})
"""
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Breadcrumb:
    """단일 행동 궤적 레코드.

    Attributes:
        timestamp: 궤적이 기록된 시각 (ISO 포맷).
        category: 궤적의 분류 (예: 'ui', 'io', 'db', 'net', 'conv').
        message: 행동 설명 메시지.
        data: 추가 컨텍스트 데이터 (선택).
    """
    timestamp: str
    category: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        """로그 파일 출력용 포맷 문자열을 반환합니다."""
        data_str = f"  {self.data}" if self.data else ""
        return f"  [{self.timestamp}] [{self.category.upper():4s}] {self.message}{data_str}"


# ---- 모듈 수준 싱글톤 버퍼 ----

_MAX_BREADCRUMBS = 50
_lock = threading.Lock()
_buffer: deque[Breadcrumb] = deque(maxlen=_MAX_BREADCRUMBS)


def add_breadcrumb(category: str, message: str, data: dict[str, Any] | None = None) -> None:
    """행동 궤적을 버퍼에 추가합니다.

    스레드 안전하게 동작하며, 버퍼가 가득 차면 가장 오래된 항목이 자동 제거됩니다.

    Args:
        category: 궤적 분류 (예: 'ui', 'io', 'db', 'net', 'conv').
        message: 행동 설명 메시지.
        data: 추가 컨텍스트 데이터 딕셔너리 (선택).
    """
    crumb = Breadcrumb(
        timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
        category=category,
        message=message,
        data=data or {},
    )
    with _lock:
        _buffer.append(crumb)


def get_breadcrumbs() -> list[Breadcrumb]:
    """현재 버퍼의 모든 궤적을 시간순 리스트로 반환합니다.

    Returns:
        Breadcrumb 객체 리스트 (가장 오래된 것이 먼저).
    """
    with _lock:
        return list(_buffer)


def format_breadcrumbs() -> str:
    """현재 버퍼의 궤적을 로그 파일에 기록할 수 있는 포맷 문자열로 반환합니다.

    Returns:
        포맷된 궤적 문자열. 비어 있으면 빈 문자열 반환.
    """
    crumbs = get_breadcrumbs()
    if not crumbs:
        return ""
    lines = [f"[BREADCRUMBS] Recent {len(crumbs)} actions before error:"]
    for crumb in crumbs:
        lines.append(crumb.format())
    return "\n".join(lines)


def clear_breadcrumbs() -> None:
    """버퍼를 초기화합니다. 테스트 또는 세션 리셋 시 사용합니다."""
    with _lock:
        _buffer.clear()
