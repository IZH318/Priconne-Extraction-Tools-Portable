from __future__ import annotations
# src/story_viewer/db_helper.py
"""
Story Viewer의 DB 접근 로직을 집중 관리하는 모듈.
이벤트 목록 조회, 이벤트 ID 검색 등 sqlite3 관련 작업을 캡슐화합니다.

SQL 조립은 _build_query() / _build_select_all_query()로 집중 관리됩니다.
식별자 검증은 _validate_identifier()를 통해 화이트리스트 방식으로 처리합니다.
"""
import os
import re
import sqlite3
from typing import Any

from src.exceptions import UnsafeIdentifierError

# SQL 식별자(테이블/컬럼명) 화이트리스트 패턴: 영숫자, 언더스코어만 허용
# 참고: priconne-database의 해시 기반 테이블/컬럼명은 'v1_' prefix가 있어
# 이 패턴을 통과합니다. 숫자로 시작하는 순수 hex 식별자가 사용될 경우 별도 처리가 필요합니다.
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_]+$')


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
        raise UnsafeIdentifierError(name)
    return name


def _build_query(
    table: str,
    columns: list[str],
    *,
    distinct: bool = False,
    where_col: str | None = None,
    where_op: str = "=",
) -> str:
    """검증된 식별자로 SELECT 쿼리를 조립합니다.

    모든 SQL 문자열 조립은 이 함수를 통해서만 수행되며,
    식별자 검증 → 쿼리 조립을 한 곳에서 관리합니다.

    Args:
        table: 조회 대상 테이블명 (검증됨).
        columns: 조회할 컬럼명 리스트 (각각 검증됨).
        distinct: DISTINCT 키워드 적용 여부.
        where_col: WHERE 절에 사용할 컬럼명 (None이면 WHERE 없음).
        where_op: WHERE 절의 비교 연산자 (기본값: "=").

    Returns:
        조립된 SQL 쿼리 문자열 (파라미터 자리는 ? 로 표시).
    """
    tbl = _validate_identifier(table)
    cols = ", ".join(f'"{_validate_identifier(c)}"' for c in columns)
    distinct_kw = "DISTINCT " if distinct else ""
    query = f'SELECT {distinct_kw}{cols} FROM "{tbl}"'

    if where_col is not None:
        w_col = _validate_identifier(where_col)
        query += f' WHERE "{w_col}" {where_op} ?'

    return query


def _build_select_all_query(table: str) -> tuple[str, str]:
    """테이블의 전체 컬럼을 동적으로 조회하기 위한 PRAGMA + SELECT 쿼리 쌍을 반환합니다.

    Args:
        table: 조회 대상 테이블명 (검증됨).

    Returns:
        (PRAGMA 쿼리, SELECT 쿼리 템플릿 접두사) 튜플.
        SELECT 쿼리는 PRAGMA 결과로 컬럼 목록을 채워야 합니다.
    """
    tbl = _validate_identifier(table)
    pragma_query = f'PRAGMA table_info("{tbl}")'
    select_prefix = f'FROM "{tbl}"'
    return pragma_query, select_prefix


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
    db_path = _get_db_path(db_info).replace('\\', '/')
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cursor = conn.cursor()
        query = _build_query(
            table=db_info['event_list_table'],
            columns=[db_info['event_name_col_list']],
            distinct=True,
        )
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
    db_path = _get_db_path(db_info).replace('\\', '/')
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cursor = conn.cursor()
        query = _build_query(
            table=db_info['event_details_table'],
            columns=[db_info['event_id_col_details']],
            where_col=db_info['event_info_col_details'],
            where_op="LIKE",
        )
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
    db_path = _get_db_path(db_info).replace('\\', '/')
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cursor = conn.cursor()
        pragma_query, select_suffix = _build_select_all_query(db_info['event_list_table'])
        
        # 테이블의 모든 컬럼 이름 가져오기
        cursor.execute(pragma_query)
        columns = [col_info[1] for col_info in cursor.fetchall()]
        
        # 컬럼 목록을 명시적으로 나열하여 조회 (SELECT * 대신 안전한 방식)
        validated_cols = ', '.join(f'"{_validate_identifier(c)}"' for c in columns)
        cursor.execute(f'SELECT {validated_cols} {select_suffix}')
        rows = cursor.fetchall()
        
        return columns, rows


def fetch_birthday_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 birthday_login_bonus_data 테이블에서 이름들을 일괄 조회합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        
    Returns:
        dict[str, str]: adv_id를 키로, 조회된 이름을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}
        
    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            
            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                # _validate_identifier must be called on each column/table to prevent injection since we are manually constructing the SQL here
                tbl = _validate_identifier(db_info['birthday_table'])
                col_id = _validate_identifier(db_info['birthday_adv_id_col'])
                col_name = _validate_identifier(db_info['birthday_name_col'])
                
                query = f'SELECT "{col_id}", "{col_name}" FROM "{tbl}" WHERE "{col_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                for row in cursor.fetchall():
                    if row[0] and row[1]:
                        result_map[str(row[0])] = str(row[1]).replace('\\n', ' ').strip()
    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass
        
    return result_map


def fetch_quest_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 quest_data 테이블에서 quest_name들을 일괄 조회합니다.
    story_id_wavestart_3에서 일치 시 '{quest_name}_start',
    story_id_waveend_3에서 일치 시 '{quest_name}_end'로 매핑합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        
    Returns:
        dict[str, str]: adv_id를 키로, '{quest_name}_start' 또는 '{quest_name}_end'를 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}
        
    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            
            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                tbl = _validate_identifier(db_info['quest_table'])
                col_start = _validate_identifier(db_info['quest_wavestart_col'])
                col_end = _validate_identifier(db_info['quest_waveend_col'])
                col_name = _validate_identifier(db_info['quest_name_col'])
                
                query = f'SELECT "{col_start}", "{col_end}", "{col_name}" FROM "{tbl}" WHERE "{col_start}" IN ({placeholders}) OR "{col_end}" IN ({placeholders})'
                cursor.execute(query, chunk + chunk)
                chunk_set = set(chunk)
                for row in cursor.fetchall():
                    start_id = str(row[0]) if row[0] is not None else ''
                    end_id = str(row[1]) if row[1] is not None else ''
                    name = str(row[2]).replace('\\n', ' ').strip() if row[2] is not None else ''
                    if not name:
                        continue
                    if start_id in chunk_set and start_id != '0':
                        result_map[start_id] = f"{name}_start"
                    if end_id in chunk_set and end_id != '0':
                        result_map[end_id] = f"{name}_end"
    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass
        
    return result_map


def fetch_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 story_detail 테이블에서 title과 sub_title을 일괄 조회합니다.
    조회된 값은 'title - sub_title' 형식으로 매핑됩니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        
    Returns:
        dict[str, str]: adv_id를 키로, 'title - sub_title'을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}
        
    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            
            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                tbl = _validate_identifier(db_info['story_detail_table'])
                col_id = _validate_identifier(db_info['story_detail_id_col'])
                col_title = _validate_identifier(db_info['story_detail_title_col'])
                col_sub = _validate_identifier(db_info['story_detail_sub_title_col'])
                
                query = f'SELECT "{col_id}", "{col_title}", "{col_sub}" FROM "{tbl}" WHERE "{col_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                for row in cursor.fetchall():
                    story_id = str(row[0]) if row[0] is not None else ''
                    t = str(row[1]).replace('\\n', ' ').strip() if row[1] is not None else ''
                    sub = str(row[2]).replace('\\n', ' ').strip() if row[2] is not None else ''
                    
                    if t and sub:
                        formatted = f"{t} - {sub}"
                    elif t:
                        formatted = t
                    elif sub:
                        formatted = sub
                    else:
                        continue
                    result_map[story_id] = formatted
    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass
        
    return result_map


