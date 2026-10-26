"""공통 에러 및 작업 결과 리포트 파일 생성 유틸리티 모듈.

각 서브도구(Renamer, Story Viewer, Resource Remover, AV Converter)에서
일괄 작업 실패, 건너뜀, 오류 발생 시 일관된 형식의 텍스트 로그 파일
(시스템 사양 헤더, 순번별 실패 사유) 작성 보일러플레이트 제공.
"""
from __future__ import annotations

import os
import platform
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants import SEPARATOR_LONG


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
        for line in extra_report:
            f.write(f"{line}\n")
    f.write(f"{SEPARATOR_LONG}\n\n")
    return now


def write_log_items(
    f: Any,
    items: Iterable[Any],
    item_label: str = "File",
    item_header: str = "[ITEM #{idx}]",
    timestamp: datetime | None = None,
    context: str | None = None,
    reason_fn: Callable[[Any], str] | None = None,
) -> None:
    """작업 실패 또는 스킵된 파일 항목 열거 기록.

    Args:
        f (Any): 쓰기 모드로 열린 파일 객체.
        items (Iterable[Any]): 기록할 항목 컬렉션 (단일 파일 경로 문자열 또는 (path, reason) 튜플).
        item_label (str): 항목 식별 라벨 (기본값: 'File').
        item_header (str): 항목 헤더 템플릿 ('{idx}' 치환자 지원, 기본값: '[ITEM #{idx}]').
        timestamp (datetime | None): 기록할 타임스탬프 (None인 경우 현재 시각 적용).
        context (str | None): 발생 맥락 설명 문자열.
        reason_fn (Callable[[Any], str] | None): 항목 객체에서 사유(reason) 문자열을 커스텀 추출하는 콜백.
    """
    ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    for idx, item in enumerate(items, 1):
        f.write(item_header.format(idx=idx) + "\n")
        f.write(f"Timestamp : {ts}\n")
        if context:
            f.write(f"Context   : {context}\n")
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            f.write(f"{item_label:8s}: {item[0]}\n")
            reason = reason_fn(item) if reason_fn else str(item[1])
            f.write(f"Reason    : {reason}\n")
        else:
            f.write(f"{item_label:8s}: {item}\n")
        f.write(f"{SEPARATOR_LONG}\n\n")

