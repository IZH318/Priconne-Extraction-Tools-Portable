"""스레드/프로세스 간 큐(Queue) 통신용 불변 이벤트 메시지 모듈.

백그라운드 워커 스레드 및 멀티프로세싱 워커에서 발생한 작업 진행률, 로그 메시지,
작업 완료 신호 및 UI 동기화 콜백을 메인 Tkinter GUI 스레드로 안전 전달하기 위한
불변(frozen=True) 데이터클래스 이벤트 객체 정의.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueueEvent:
    """모든 큐 통신 메시지 기본 추상 이벤트 클래스.

    불변(frozen=True) 선언 기반 다중 스레드 큐 전송 시
    객체 변경으로 인한 데이터 레이스 방지.
    """


@dataclass(frozen=True)
class LogEvent(QueueEvent):
    """단일 로그 메시지 이벤트.

    각 모듈(AV Converter, Renamer, Unity Converter 등)에서 백그라운드 작업 중
    GUI 로그 창 텍스트 출력을 위해 발행.

    Attributes:
        target (str): 대상 탭 또는 서브 뷰 식별자 (예: 'video', 'audio').
        key (str): 다국어 languages.json에 정의된 번역 메시지 키.
        level (str): 로그 심각도 레벨 ('info', 'success', 'warning', 'error' 등).
        kwargs (dict[str, Any]): 번역 템플릿에 치환될 키워드 인자 딕셔너리.
        un_timestamped (bool): True인 경우 타임스탬프 접두사를 생략하고 출력.
        is_spacing (bool): True인 경우 빈 줄(여백)을 삽입.
        timestamp (str | None): 명시적 타임스탬프 문자열. None이면 렌더러가 현재 시각 적용.
    """
    target: str = ""
    key: str = ""
    level: str = "info"
    kwargs: dict[str, Any] = field(default_factory=dict)
    un_timestamped: bool = False
    is_spacing: bool = False
    timestamp: str | None = None


@dataclass(frozen=True)
class LogBlockEvent(QueueEvent):
    """다수 로그 엔트리 일괄(Batch) 묶음 전달 이벤트.

    대량 파일 변환 시 GUI 큐 병목 및 UI 프리징 방지용.

    Attributes:
        target (str): 대상 탭 또는 로그 위젯 식별자.
        entries (list[tuple[Any, ...]]): 개별 로그 엔트리 튜플 리스트.
    """
    target: str = ""
    entries: list[tuple[Any, ...]] = field(default_factory=list)


@dataclass(frozen=True)
class ProgressEvent(QueueEvent):
    """작업 진행률 및 카운터 변경 이벤트.

    GUI ttk.Progressbar 및 처리 개수 라벨(현재/전체) 갱신용.

    Attributes:
        target (str): 대상 탭 식별자 (예: 'video', 'audio', 'renamer').
        is_start (bool): True인 경우 진행바를 0으로 리셋하고 시작 상태로 전환.
        value (int): 진행률 백분율(0~100) 또는 진행바 증분.
        current (int): 현재까지 완료된 파일 수.
        total (int): 전체 처리 대상 파일 수.
    """
    target: str = ""
    is_start: bool = False
    value: int = 0
    current: int = 0
    total: int = 0


@dataclass(frozen=True)
class CompletionEvent(QueueEvent):
    """비동기 배치 작업 완료 신호 이벤트.

    Attributes:
        target (str): 완료된 작업 식별 센티넬 (예: constants.SENTINEL_VIDEO_DONE).
        success (bool): 전체 작업 성공 여부 (에러 발생 시 False).
        result (Any): 작업 결과 데이터 또는 요약 통계 객체.
    """
    target: str = ""
    success: bool = True
    result: Any = None

