# src/story_viewer/db_helper.py
"""
Story Viewer의 DB 접근 로직을 집중 관리하는 모듈.
이벤트 목록 조회, 이벤트 ID 검색 등 sqlite3 관련 작업을 캡슐화합니다.
"""
from __future__ import annotations
import os
import sqlite3
from typing import Any


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
        query = f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\""
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
        query = f"SELECT \"{db_info['event_id_col_details']}\" FROM \"{db_info['event_details_table']}\" WHERE \"{db_info['event_info_col_details']}\" LIKE ?"
        cursor.execute(query, (f"{event_name}%",))
        return {f"storydata_{row[0]}.json" for row in cursor.fetchall()}


def fetch_event_list_for_export(db_info: dict[str, Any]) -> tuple[list[str], list[tuple]]:
    """
    내보내기용 이벤트 목록 데이터를 반환합니다.
    
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
        
        # 테이블의 모든 컬럼 이름 가져오기
        cursor.execute(f"PRAGMA table_info(\"{db_info['event_list_table']}\")")
        columns = [col_info[1] for col_info in cursor.fetchall()]
        
        # 모든 데이터 가져오기
        cursor.execute(f"SELECT * FROM \"{db_info['event_list_table']}\"")
        rows = cursor.fetchall()
        
        return columns, rows
