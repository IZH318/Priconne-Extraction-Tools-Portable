"""공통 에러 및 작업 결과 리포트 파일 생성 유틸리티 모듈.

각 서브도구(Renamer, Story Viewer, Resource Remover, AV Converter)에서
일괄 작업 실패, 건너뜀, 오류 발생 시 일관된 형식의 텍스트 로그 파일
(시스템 사양 헤더, 순번별 실패 사유) 작성 보일러플레이트 제공.
"""
from __future__ import annotations

import logging
import os
import platform
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants import SEPARATOR_LONG

logger = logging.getLogger(__name__)


def open_task_log(
    prefix: str,
    title: str,
    base_dir: str | Path | None = None,
    extra_report: Iterable[str] | None = None,
) -> tuple[Path, Any, datetime] | None:
    """표준 규격 작업 로그 파일을 생성하고 헤더를 기록한다.

    각 서브도구가 반복 구현하던 'logs 디렉터리 생성 → 파일명 조립 → app_info 헤더'
    보일러플레이트를 단일화한다. 실패 시 예외 대신 None을 반환한다.

    Args:
        prefix (str): 로그 파일명 접두사 (예: 'RenamerLog' → RenamerLog_YYYY-MM-DD_HHMMSS.log).
        title (str): 로그 제목 (헤더에 기록).
        base_dir (str | Path | None): 로그 기준 경로. None이면 앱 기준 경로 사용.
        extra_report (Iterable[str] | None): 헤더에 추가할 [REPORT] 라인 목록.

    Returns:
        tuple[Path, Any, datetime] | None: (로그 경로, 파일 객체, 기준 타임스탬프).
        파일 생성 또는 헤더 기록에 실패하면 None.
    """
    from src.constants import APP_DEVELOPER, APP_LAST_UPDATE, APP_VERSION
    from src.utils.base_path import get_application_base_path

    base = Path(base_dir) if base_dir is not None else get_application_base_path()
    try:
        log_dir = base / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_filename = log_dir / f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
        handle = open(log_filename, "a", encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to create task log %s: %s", prefix, exc)
        return None

    app_info = {
        "APP_VERSION": APP_VERSION,
        "APP_LAST_UPDATE": APP_LAST_UPDATE,
        "APP_DEVELOPER": APP_DEVELOPER,
    }
    try:
        timestamp = write_log_header(handle, title, base, app_info, extra_report)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Failed to write task log header %s: %s", log_filename, exc)
        try:
            handle.close()
        except OSError:
            pass
        return None
    return log_filename, handle, timestamp


def write_log_header(
    f: Any,
    context_name: str,
    base_path: str | Path,
    app_info: dict[str, Any],
    extra_report: Iterable[str] | None = None,
) -> datetime:
    """로그 파일 상단 표준 세션 정보 및 시스템 사양 헤더 작성.

    Args:
        f (Any): 쓰기 모드로 열린 파일 객체.
        context_name (str): 세션 작업 이름 (예: 'Manifest File Renamer', 'Audio Converter').
        base_path (str | Path): 애플리케이션 실행 기준 경로.
        app_info (dict[str, Any]): 앱 버전, 빌드일, 개발자 정보를 담은 딕셔너리.
        extra_report (Iterable[str] | None): 통계 요약 등 추가로 출력할 라인 이터러블.

    Returns:
        datetime: 헤더 생성 기준 시각 객체 (후속 항목 타임스탬프 동기화에 사용).
    """
    now = datetime.now()
    python_ver = platform.python_version()
    os_ver = platform.platform()
    cpu_cores = (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or os.cpu_count() or 1

    f.write(f"{SEPARATOR_LONG}\n")
    f.write(f"[SESSION] {context_name} Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
    f.write(f"{SEPARATOR_LONG}\n")
    f.write(f"[TOOL]    App Version:     {app_info.get('APP_VERSION', 'Unknown')} ({app_info.get('APP_LAST_UPDATE', 'Unknown')})\n")
    f.write(f"[TOOL]    Developer:       {app_info.get('APP_DEVELOPER', 'Unknown')}\n")
    f.write(f"[ENGINE]  Python Version:  {python_ver}\n")
    f.write(f"[SYSTEM]  OS Version:      {os_ver}\n")
    f.write(f"[SYSTEM]  Processor Count: {cpu_cores} Cores\n")
    f.write(f"[PATH]    Exec Path:       {base_path}\n")
    if extra_report:
        # 환경 정보 묶음과 [REPORT] 요약을 빈 줄로 구분
        f.write("\n")
        for line in extra_report:
            f.write(f"{line}\n")
    f.write(f"{SEPARATOR_LONG}\n")
    return now


def write_log_item(
    f: Any,
    item_header: str,
    idx: int,
    timestamp: datetime,
    context: str,
    target: Any,
    message: Any,
    detail: str | None = None,
) -> None:
    """단일 로그 항목을 공통 필드 규격(Target/Message)으로 기록.

    Args:
        f (Any): 쓰기 모드로 열린 파일 객체.
        item_header (str): 항목 헤더 템플릿 ('{idx}' 치환자 지원).
        idx (int): 항목 번호.
        timestamp (datetime): 기록할 타임스탬프.
        context (str): 발생 맥락 설명 문자열.
        target (Any): 대상(파일 경로/로거명/예외 타입 등).
        message (Any): 사유/메시지/예외 내용.
        detail (str | None): 추가 상세(스택 트레이스 등). 없으면 생략.
    """
    ts = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    indent = " " * 12  # "라벨(9) : " = 12칸, 여러 줄 값의 이어지는 줄 정렬용

    def field(label: str, value: Any) -> str:
        text = str(value).replace("\n", "\n" + indent)
        return f"{label:<9} : {text}\n"

    f.write(item_header.format(idx=idx) + "\n")
    f.write(field("Timestamp", ts))
    f.write(field("Context", context))
    f.write(field("Target", target))
    f.write(field("Message", message))
    if detail:
        # 여러 줄 상세(스택 트레이스 등)는 짧은 필드 묶음과 빈 줄로 구분
        f.write("\n")
        f.write(field("Detail", detail))
    f.write(f"{SEPARATOR_LONG}\n")


def write_log_items(
    f: Any,
    items: Iterable[Any],
    item_header: str = "[ITEM #{idx}]",
    timestamp: datetime | None = None,
    context: str = "",
    target_fn: Callable[[Any], Any] | None = None,
    message_fn: Callable[[Any], Any] | None = None,
    default_message: Any = "",
) -> None:
    """작업 실패/스킵/성공 항목 목록을 공통 필드 규격(Target/Message)으로 기록.

    Args:
        f (Any): 쓰기 모드로 열린 파일 객체.
        items (Iterable[Any]): 항목 컬렉션 (경로 문자열 또는 (대상, 사유) 튜플).
        item_header (str): 항목 헤더 템플릿 ('{idx}' 치환자 지원, 기본값: '[ITEM #{idx}]').
        timestamp (datetime | None): 기록할 타임스탬프 (None이면 현재 시각 적용).
        context (str): 발생 맥락 설명 문자열.
        target_fn (Callable[[Any], Any] | None): 항목에서 대상 값을 커스텀 추출하는 콜백.
        message_fn (Callable[[Any], Any] | None): 항목에서 메시지 값을 커스텀 추출하는 콜백.
        default_message (Any): 단일 문자열 항목일 때 사용할 기본 메시지.
    """
    ts = timestamp or datetime.now()
    for idx, item in enumerate(items, 1):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            target: Any = item[0]
            message: Any = item[1]
        else:
            target = item
            message = default_message
        if target_fn:
            target = target_fn(item)
        if message_fn:
            message = message_fn(item)
        write_log_item(f, item_header, idx, ts, context, target, message)

