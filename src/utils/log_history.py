"""로그 렌더링 공통 규칙(타임스탬프/들여쓰기/그룹/캐시 서명) 모듈.

각 서브도구의 로그 렌더러가 동일한 규칙을 개별 복제하던 부분을 단일화한다.
출력 포맷은 기존 동작과 100% 동일하게 유지한다.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

# 로그 타임스탬프 표기 형식 ('HH:MM:SS.mmm' — 밀리초 3자리)
LOG_TIME_FORMAT: str = "%H:%M:%S.%f"

# 동일 타임스탬프 그룹의 후속 항목 들여쓰기 (타임스탬프 접두사 폭과 동일)
LOG_INDENT: str = " " * 13


def new_log_timestamp() -> str:
    """현재 시각의 로그 타임스탬프 문자열('HH:MM:SS.mmm')을 반환."""
    return datetime.now().strftime(LOG_TIME_FORMAT)[:-3]


def timestamp_prefix(timestamp: str | None, same_group: bool) -> str:
    """로그 라인 접두사 반환: 동일 그룹이면 들여쓰기, 아니면 `[timestamp] `.

    Args:
        timestamp (str | None): 타임스탬프 문자열. None이면 접두사 없음.
        same_group (bool): 직전 항목과 동일 타임스탬프 그룹인지 여부.

    Returns:
        str: 라인 앞에 붙일 접두사.
    """
    if not timestamp:
        return ""
    return LOG_INDENT if same_group else f"[{timestamp}] "


def is_same_timestamp_group(entries: Sequence[tuple[Any, ...]], index: int) -> bool:
    """`entries[index]`가 직전 항목과 같은 타임스탬프 그룹인지 판정.

    Args:
        entries (Sequence[tuple]): (timestamp, key, ...) 형태의 로그 이력.
        index (int): 판정할 항목 인덱스.

    Returns:
        bool: 직전 항목과 타임스탬프가 같으면 True.
    """
    return index > 0 and entries[index - 1][0] == entries[index][0]
