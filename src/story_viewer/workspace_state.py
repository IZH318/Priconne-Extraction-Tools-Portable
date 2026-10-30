"""Story Viewer 작업 공간(Workspace) 상태 컨테이너 모듈.

스토리 뷰어의 컨트롤러와 서비스 계층이 공유하는 가변 상태(로드된 파일 목록,
파생 메타데이터, 백그라운드 작업 진행 상태)를 단일 데이터클래스로 묶어
서비스 생성자의 Long Parameter List 및 접근자(getter/setter) 보일러플레이트를 제거.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StoryWorkspaceState:
    """Story Viewer 컨트롤러와 서비스가 공유하는 가변 작업 공간 상태.

    Attributes:
        all_files (dict[str, Any]): 파일명 -> 실제 파일 경로 매핑.
        search_data (dict[str, Any]): 검색 창 콤보박스용 메타데이터(화자/BGM/배경/보이스).
        file_titles (dict[str, str]): 파일명 -> 표시 제목 매핑.
        raw_file_titles (dict[str, str]): 파일명 -> 원본(스토리 데이터 유래) 제목.
        file_situations (dict[str, Any]): 파일명 -> 상황(Situation) 텍스트.
        file_outlines (dict[str, Any]): 파일명 -> 줄거리(Outline) 텍스트.
        file_voice_adv_ids (dict[str, Any]): 파일명 -> 음성 ADV ID.
        file_speakers (dict[str, Any]): 파일명 -> 대표 화자 이름.
        display_name_to_filename (dict[str, str]): 리스트박스 표시명 -> 파일명 매핑.
        current_filenames_in_list (list[str]): 현재 리스트박스에 표시 중인 파일명 목록.
        loaded_filenames (list[str]): 로드된 전체 파일명 목록.
        current_file_path (Path | str | None): 현재 본문 표시 중인 파일 경로.
        story_data_cache (OrderedDict[Any, Any]): 파싱 결과 LRU 캐시.
        is_loading (bool): 파일 로딩 진행 여부.
        base_search_files (list[str]): 고급 검색 결과 기준 파일명 목록.
        populate_generation (int): 리스트박스 비동기 채우기 무효화용 세대 카운터.
        db_analyzed (bool): DB 스키마 분석 완료 여부.
        server_titles_cache (dict[str, dict[str, str]]): 서버별 해석된 제목 캐시.
        pending_json_results (dict[str, Any] | None): DB 준비 대기 중인 로딩 결과.
        pending_invalid_files (list[tuple[str, str]]): DB 준비 대기 중인 무효 파일 목록.
        db_ready (bool): DB 사용 준비 완료 여부.
        kr_notice_shown (bool): KR 서버 안내 팝업 표시 여부.
    """

    all_files: dict[str, Any] = field(default_factory=dict)
    search_data: dict[str, Any] = field(default_factory=dict)
    file_titles: dict[str, str] = field(default_factory=dict)
    raw_file_titles: dict[str, str] = field(default_factory=dict)
    file_situations: dict[str, Any] = field(default_factory=dict)
    file_outlines: dict[str, Any] = field(default_factory=dict)
    file_voice_adv_ids: dict[str, Any] = field(default_factory=dict)
    file_speakers: dict[str, Any] = field(default_factory=dict)
    display_name_to_filename: dict[str, str] = field(default_factory=dict)
    current_filenames_in_list: list[str] = field(default_factory=list)
    loaded_filenames: list[str] = field(default_factory=list)
    current_file_path: Path | str | None = None
    story_data_cache: OrderedDict[Any, Any] = field(default_factory=OrderedDict)
    is_loading: bool = False
    base_search_files: list[str] = field(default_factory=list)
    populate_generation: int = 0
    db_analyzed: bool = False
    server_titles_cache: dict[str, dict[str, str]] = field(default_factory=lambda: {'JP': {}, 'KR': {}})
    pending_json_results: dict[str, Any] | None = None
    pending_invalid_files: list[tuple[str, str]] = field(default_factory=list)
    db_ready: bool = False
    kr_notice_shown: bool = False
