from __future__ import annotations
# src/story_viewer/db_helper.py
"""
Story Viewer의 DB 접근 로직을 집중 관리하는 모듈.
이벤트 목록 조회, 이벤트 ID 검색 등 sqlite3 관련 작업을 캡슐화합니다.
"""
import os
import re
import sqlite3
from typing import Any

# SQL 식별자(테이블/컬럼명) 화이트리스트 패턴: 영숫자, 언더스코어만 허용
# 참고: priconne-database의 해시 기반 테이블/컬럼명은 'v1_' prefix가 있어
# 이 패턴을 통과합니다. 숫자로 시작하는 순수 hex 식별자가 사용될 경우 별도 처리가 필요합니다.
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_identifier(name: str) -> str:
    """SQL 식별자를 화이트리스트 검증하여 안전한 이름만 반환합니다.

    Args:
        name: 검증할 테이블명 또는 컬럼명.

    Returns:
        검증을 통과한 이름 문자열.

    Raises:
        ValueError: 허용되지 않는 문자가 포함된 경우.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier rejected: {name!r}")
    return name


def _get_db_path(db_info: dict[str, Any]) -> str:
    """DB 정보 딕셔너리에서 절대 경로를 반환합니다."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(script_dir, db_info['db_path'])


def fetch_event_names(db_info: dict[str, Any]) -> list[str]:
    """
    이벤트 이름 목록을 DB에서 조회하여 반환합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리 (db_path, event_list_table, event_name_col_list 포함).
        
    Returns:
        list[str]: 이벤트 이름 리스트. 오류 시 빈 리스트 반환.
        
    Raises:
        sqlite3.Error: DB 접근 중 오류 발생 시.
    """
    db_path = _get_db_path(db_info)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        col = _validate_identifier(db_info['event_name_col_list'])
        tbl = _validate_identifier(db_info['event_list_table'])
        query = f'SELECT DISTINCT "{col}" FROM "{tbl}"'
        cursor.execute(query)
        return [row[0].replace('\\n', ' ').strip() for row in cursor.fetchall() if row[0]]


def fetch_event_story_ids(db_info: dict[str, Any], event_name: str) -> set[str]:
    """
    특정 이벤트 이름에 속하는 스토리 ID 세트를 반환합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        event_name (str): 검색할 이벤트 이름.
        
    Returns:
        set[str]: 'storydata_{id}.json' 형태의 파일명 세트.
        
    Raises:
        sqlite3.Error: DB 접근 중 오류 발생 시.
    """
    db_path = _get_db_path(db_info)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        id_col = _validate_identifier(db_info['event_id_col_details'])
        tbl = _validate_identifier(db_info['event_details_table'])
        info_col = _validate_identifier(db_info['event_info_col_details'])
        query = f'SELECT "{id_col}" FROM "{tbl}" WHERE "{info_col}" LIKE ?'
        cursor.execute(query, (f"{event_name}%",))
        return {f"storydata_{row[0]}.json" for row in cursor.fetchall()}


def fetch_event_list_for_export(db_info: dict[str, Any]) -> tuple[list[str], list[tuple]]:
    """
    내보내기용 이벤트 목록 데이터를 반환합니다.
    
    이 함수는 의도적으로 테이블의 **모든 컬럼**을 조회합니다.
    PRAGMA table_info로 먼저 컬럼 목록을 확보한 뒤, 해당 컬럼들을 명시적으로
    SELECT 절에 나열하여 스키마 변경에 안전한 방식으로 전체 데이터를 반환합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리 (export_table, export_cols 포함).
        
    Returns:
        tuple[list[str], list[tuple]]: (컬럼 헤더 리스트, 데이터 행 리스트).
        
    Raises:
        sqlite3.Error: DB 접근 중 오류 발생 시.
    """
    db_path = _get_db_path(db_info)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        tbl = _validate_identifier(db_info['event_list_table'])
        
        # 테이블의 모든 컬럼 이름 가져오기
        cursor.execute(f'PRAGMA table_info("{tbl}")')
        columns = [col_info[1] for col_info in cursor.fetchall()]
        
        # 컬럼 목록을 명시적으로 나열하여 조회 (SELECT * 대신 안전한 방식)
        validated_cols = ', '.join(f'"{_validate_identifier(c)}"' for c in columns)
        cursor.execute(f'SELECT {validated_cols} FROM "{tbl}"')
        rows = cursor.fetchall()
        
        return columns, rows
