from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class QueueEvent:
    """모든 큐 통신 메시지의 기본이 되는 추상 이벤트 클래스입니다."""

@dataclass
class LogEvent(QueueEvent):
    """일반적인 로그 메시지 이벤트 (AV Converter, Renamer, Unity Converter 호환)"""
    target: str = ""  # 탭 이름이나 프로그레스 대상 (e.g. 'audio', 'video')
    key: str = ""     # 언어 파일의 로그 키
    level: str = "info" # 로그 레벨
    kwargs: dict[str, Any] = field(default_factory=dict)
    un_timestamped: bool = False
    is_spacing: bool = False
    timestamp: str | None = None

@dataclass
class LogBlockEvent(QueueEvent):
    """여러 로그 항목을 한 번에 처리하는 블록 이벤트 (AV Converter)"""
    target: str = ""
    entries: list[tuple] = field(default_factory=list)

@dataclass
class ProgressEvent(QueueEvent):
    """진행 상태 변경 이벤트"""
    target: str = ""
    is_start: bool = False
    value: int = 0
    current: int = 0
    total: int = 0

@dataclass
class CompletionEvent(QueueEvent):
    """작업 완료 이벤트"""
    target: str = "" # e.g., SENTINEL_VIDEO_DONE, SENTINEL_AUDIO_DONE (constants.py)
    success: bool = True
    result: Any = None

# ---- Resource Remover 용 커스텀 이벤트 ----
@dataclass
class SearchDoneEvent(QueueEvent):
    target_files: list[Any]
    lang_dict: dict[str, str]

@dataclass
class DeleteDoneEvent(QueueEvent):
    deleted_count: int
    errors: list[str]
    log_path: str
    lang_dict: dict[str, str]

# ---- Story Viewer 용 람다 래퍼 이벤트 ----
@dataclass
class ActionEvent(QueueEvent):
    """동기화를 위해 메인 스레드에서 즉시 실행되어야 할 콜백을 담는 이벤트"""
    action: Callable[[], None]
