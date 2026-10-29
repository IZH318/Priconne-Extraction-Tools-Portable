"""파일명 안전 처리 공통 모듈.

Windows 파일 시스템에서 확장자와 무관하게 예약되어 정상 파일 생성이 불가/오동작하는
예약 디바이스명 집합을 단일 정의로 제공한다. 여러 서브도구가 각자 복제하던 집합을
이 모듈로 통일하여 집합 불일치(예: CONIN$/CONOUT$ 누락)로 인한 방어 누락을 방지한다.
"""
from __future__ import annotations

# Windows 예약 디바이스명 (확장자와 무관하게 파일 생성이 불가/오동작)
# CONIN$/CONOUT$ 를 포함한 상위집합으로 통일.
WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }
)
