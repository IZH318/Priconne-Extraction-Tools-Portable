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
        return [row[0].replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip() for row in cursor.fetchall() if row[0]]


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
    details_tbl = _validate_identifier(db_info['event_details_table'])
    details_id_col = _validate_identifier(db_info['event_id_col_details'])
    group_col_details = _validate_identifier(db_info.get('event_group_id_col_details', 'story_group_id'))
    list_tbl = _validate_identifier(db_info['event_list_table'])
    group_col_list = _validate_identifier(db_info.get('event_group_id_col_list', 'story_group_id'))
    name_col = _validate_identifier(db_info['event_name_col_list'])

    cleaned_name = event_name.replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
    query = (
        f'SELECT "{details_id_col}" FROM "{details_tbl}" '
        f'WHERE "{group_col_details}" IN ('
        f'SELECT "{group_col_list}" FROM "{list_tbl}" '
        f'WHERE trim(replace(replace(replace("{name_col}", char(13), \'\'), char(10), \' \'), \'\\n\', \' \')) = ? '
        f'OR "{name_col}" = ?)'
    )
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (cleaned_name, event_name))
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


def fetch_dear_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 dear_story_detail 테이블에서 title과 sub_title을 일괄 조회합니다.
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
                tbl = _validate_identifier(db_info['dear_story_detail_table'])
                col_id = _validate_identifier(db_info['dear_story_detail_id_col'])
                col_title = _validate_identifier(db_info['dear_story_detail_title_col'])
                col_sub = _validate_identifier(db_info['dear_story_detail_sub_title_col'])
                
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


def fetch_tower_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 tower_story_detail 테이블에서 title과 sub_title을 일괄 조회합니다.
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
                tbl = _validate_identifier(db_info['tower_story_detail_table'])
                col_id = _validate_identifier(db_info['tower_story_detail_id_col'])
                col_title = _validate_identifier(db_info['tower_story_detail_title_col'])
                col_sub = _validate_identifier(db_info['tower_story_detail_sub_title_col'])
                
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


def fetch_alchemy_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """
    adv_id 목록을 기반으로 alchemy_story_detail 테이블에서 title을 일괄 조회합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        
    Returns:
        dict[str, str]: adv_id를 키로, title을 값으로 갖는 딕셔너리.
    """
    tbl_name = db_info.get('alchemy_story_detail_table')
    if not tbl_name:
        return {}

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
                tbl = _validate_identifier(tbl_name)
                col_id = _validate_identifier(db_info['alchemy_story_detail_id_col'])
                col_title = _validate_identifier(db_info['alchemy_story_detail_title_col'])
                
                query = f'SELECT "{col_id}", "{col_title}" FROM "{tbl}" WHERE "{col_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                for row in cursor.fetchall():
                    story_id = str(row[0]) if row[0] is not None else ''
                    t = str(row[1]).replace('\\n', ' ').strip() if row[1] is not None else ''
                    if t:
                        result_map[story_id] = t
    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass
        
    return result_map


def _format_sekai_time_range(time_from_str: str, time_to_str: str) -> str:
    """DB의 타임스탬프 문자열('2024/04/01 9:00:00', '2024/04/01 11:59:59')을
    '09:00~12:00' 형태로 변환합니다.

    Args:
        time_from_str: 시작 일시 문자열.
        time_to_str: 종료 일시 문자열.

    Returns:
        str: 'HH:MM~HH:MM' 형태의 시간 구간 문자열.
    """
    try:
        from datetime import datetime, timedelta
        fmt = '%Y/%m/%d %H:%M:%S'
        d1 = datetime.strptime(time_from_str.strip(), fmt)
        d2 = datetime.strptime(time_to_str.strip(), fmt)
        if d2.second == 59:
            d2 += timedelta(seconds=1)
        return f"{d1.strftime('%H:%M')}~{d2.strftime('%H:%M')}"
    except Exception:
        t1 = time_from_str.split()[-1][:5] if ' ' in time_from_str else time_from_str
        t2 = time_to_str.split()[-1][:5] if ' ' in time_to_str else time_to_str
        return f"{t1}~{t2}"


def fetch_sekai_story_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록을 기반으로 sekai_top_data 및 sekai_top_story_data 테이블에서
    순수 DB 데이터(이벤트명, MODE, 시간대, HP 0)를 조회하여 타이틀을 일괄 생성합니다.

    - sekai_top_data: 보스전 연출 (4004101~4004104, 4004109)
      - MODE 1, MODE 2, MODE 3
      - 4004104: MODE 1 (18:00)
      - 4004109: HP 0
    - sekai_top_story_data: 시간대별 토크 컷신 (4004105~4004108)
      - 09:00~12:00, 12:00~15:00, 15:00~19:00, 19:00~22:00

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.

    Returns:
        dict[str, str]: adv_id를 키로, '이벤트명 - 부제'를 값으로 갖는 딕셔너리.
    """
    top_tbl_name = db_info.get('sekai_top_data_table')
    if not top_tbl_name:
        return {}

    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    result_map = {}
    default_event_name = ""

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()

            tbl_top = _validate_identifier(top_tbl_name)
            col_id = _validate_identifier(db_info.get('sekai_top_data_id_col', 'story_id'))
            col_name = _validate_identifier(db_info.get('sekai_top_data_name_col', 'name'))
            col_mode = _validate_identifier(db_info.get('sekai_top_data_boss_mode_col', 'boss_mode'))
            col_time_from = _validate_identifier(db_info.get('sekai_top_data_boss_time_from_col', 'boss_time_from'))
            col_hp_from = _validate_identifier(db_info.get('sekai_top_data_boss_hp_from_col', 'boss_hp_from'))

            # 1. sekai_top_data 일괄 조회
            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                query = (
                    f'SELECT "{col_id}", "{col_name}", "{col_mode}", "{col_time_from}", "{col_hp_from}" '
                    f'FROM "{tbl_top}" WHERE "{col_id}" IN ({placeholders})'
                )
                cursor.execute(query, chunk)
                for row in cursor.fetchall():
                    sid = str(row[0]) if row[0] is not None else ''
                    if not sid or sid in result_map:
                        continue
                    name = str(row[1]).strip() if row[1] is not None else ''
                    mode = str(row[2]).strip() if row[2] is not None else ''
                    t_from = str(row[3]).strip() if row[3] is not None else ''
                    hp_from = str(row[4]).strip() if row[4] is not None else ''

                    if name and not default_event_name:
                        default_event_name = name

                    if hp_from == '0':
                        sub = "HP 0"
                    elif sid == '4004104' or (mode == '1' and '18:00' in t_from):
                        sub = f"MODE {mode} (18:00)"
                    elif mode:
                        sub = f"MODE {mode}"
                    else:
                        sub = ""

                    result_map[sid] = f"{name} - {sub}" if sub else name

            # default_event_name이 아직 없다면 4004101에서 이벤트명 단독 조회
            if not default_event_name:
                cursor.execute(f'SELECT "{col_name}" FROM "{tbl_top}" WHERE "{col_id}" = 4004101 LIMIT 1')
                row = cursor.fetchone()
                if row and row[0]:
                    default_event_name = str(row[0]).strip()

            # 2. sekai_top_story_data 일괄 조회 (4004105~4004108 등 시간대 토크)
            story_tbl_name = db_info.get('sekai_top_story_data_table')
            remaining_ids = [aid for aid in adv_ids if aid not in result_map]
            if story_tbl_name and remaining_ids and default_event_name:
                tbl_story = _validate_identifier(story_tbl_name)
                col_s_id = _validate_identifier(db_info.get('sekai_top_story_data_id_col', 'story_id'))
                col_s_from = _validate_identifier(db_info.get('sekai_top_story_data_boss_time_from_col', 'boss_time_from'))
                col_s_to = _validate_identifier(db_info.get('sekai_top_story_data_boss_time_to_col', 'boss_time_to'))

                for i in range(0, len(remaining_ids), chunk_size):
                    chunk = remaining_ids[i:i + chunk_size]
                    placeholders = ', '.join(['?'] * len(chunk))
                    query = f'SELECT "{col_s_id}", "{col_s_from}", "{col_s_to}" FROM "{tbl_story}" WHERE "{col_s_id}" IN ({placeholders})'
                    cursor.execute(query, chunk)
                    for row in cursor.fetchall():
                        sid = str(row[0]) if row[0] is not None else ''
                        if not sid or sid in result_map:
                            continue
                        t_from = str(row[1]).strip() if row[1] is not None else ''
                        t_to = str(row[2]).strip() if row[2] is not None else ''
                        time_range = _format_sekai_time_range(t_from, t_to)
                        result_map[sid] = f"{default_event_name} - {time_range}" if time_range else default_event_name

    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map


def fetch_event_top_adv_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록을 기반으로 event_top_adv, unit_data, event_story_data를 조회하여
    '캐릭터명 [이벤트명]' 형식의 타이틀을 일괄 조회합니다.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.

    Returns:
        dict[str, str]: adv_id를 키로, '캐릭터명 [이벤트명]'을 값으로 갖는 딕셔너리.
    """
    tbl_name = db_info.get('event_top_adv_table')
    if not tbl_name:
        return {}

    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()

            tbl_top = _validate_identifier(tbl_name)
            col_top_id = _validate_identifier(db_info.get('event_top_adv_id_col', 'story_id'))
            col_top_chara = _validate_identifier(db_info.get('event_top_adv_character_id_col', 'character_id'))

            tbl_unit = _validate_identifier(db_info.get('unit_table', 'unit_data'))
            col_unit_id = _validate_identifier(db_info.get('unit_id_col', 'unit_id'))
            col_unit_name = _validate_identifier(db_info.get('unit_name_col', 'unit_name'))

            tbl_event = _validate_identifier(db_info.get('event_list_table', 'event_story_data'))
            col_event_group = _validate_identifier(db_info.get('event_group_id_col_list', 'story_group_id'))
            col_event_title = _validate_identifier(db_info.get('event_name_col_list', 'title'))

            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))

                # 1. event_top_adv에서 대상 story_id의 character_id 조회
                query = f'SELECT "{col_top_id}", "{col_top_chara}" FROM "{tbl_top}" WHERE "{col_top_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                rows = cursor.fetchall()
                if not rows:
                    continue

                # 2. 관련 character_id 및 story_group_id 수집
                chara_ids = list({r[1] for r in rows if r[1] is not None})
                group_ids = list({int(r[0]) // 1000 for r in rows if r[0] is not None and str(r[0]).isdigit()})

                # 캐릭터 유닛명 조회
                unit_map = {}
                if chara_ids:
                    u_holders = ', '.join(['?'] * len(chara_ids))
                    cursor.execute(f'SELECT "{col_unit_id}", "{col_unit_name}" FROM "{tbl_unit}" WHERE "{col_unit_id}" IN ({u_holders})', chara_ids)
                    for r in cursor.fetchall():
                        if r[0] is not None and r[1] is not None:
                            unit_map[r[0]] = str(r[1]).strip()

                    # 혹시 unit_map에 없는 02/03 특수 폼은 01 베이스 유닛 ID로 조회
                    missing_cids = [cid for cid in chara_ids if cid not in unit_map and cid % 10 != 1]
                    if missing_cids:
                        base_cids = list({(cid // 10) * 10 + 1 for cid in missing_cids})
                        b_holders = ', '.join(['?'] * len(base_cids))
                        cursor.execute(f'SELECT "{col_unit_id}", "{col_unit_name}" FROM "{tbl_unit}" WHERE "{col_unit_id}" IN ({b_holders})', base_cids)
                        base_map = {r[0]: str(r[1]).strip() for r in cursor.fetchall() if r[0] is not None and r[1] is not None}
                        for mcid in missing_cids:
                            b_id = (mcid // 10) * 10 + 1
                            if b_id in base_map:
                                unit_map[mcid] = base_map[b_id]

                # 이벤트명 조회
                event_map = {}
                if group_ids:
                    e_holders = ', '.join(['?'] * len(group_ids))
                    cursor.execute(f'SELECT "{col_event_group}", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_group}" IN ({e_holders})', group_ids)
                    for r in cursor.fetchall():
                        if r[0] is not None and r[1] is not None:
                            t_clean = str(r[1]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
                            event_map[r[0]] = t_clean

                # 3. 타이틀 조립: '캐릭터명 [이벤트명]'
                for r in rows:
                    sid_raw = r[0]
                    sid_str = str(sid_raw)
                    cid = r[1]

                    chara_name = unit_map.get(cid, "")
                    grp_id = int(sid_raw) // 1000 if str(sid_raw).isdigit() else 0
                    event_title = event_map.get(grp_id, "")

                    if chara_name and event_title:
                        result_map[sid_str] = f"{chara_name} [{event_title}]"
                    elif chara_name:
                        result_map[sid_str] = chara_name
                    elif event_title:
                        result_map[sid_str] = f"[{event_title}]"
    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map


def fetch_event_boss_battle_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록을 기반으로 hatsune_boss, hatsune_special_battle, event_story_data를 조회하여
    이벤트 보스전/배틀 타이틀을 일괄 조회합니다.
    대사 없는 단순 영상/오디오 재생 파일은 매핑하지 않고 원본명을 유지합니다.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.

    Returns:
        dict[str, str]: adv_id를 키로, '[이벤트명] - 보스 전투(난이도)' 등의 타이틀을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()

            # 이벤트 타이틀 캐시 로드
            tbl_event = _validate_identifier(db_info.get('event_list_table', 'event_story_data'))
            col_event_grp = _validate_identifier(db_info.get('event_group_id_col_list', 'story_group_id'))
            col_event_title = _validate_identifier(db_info.get('event_name_col_list', 'title'))

            grp_ids = list({int(aid) // 1000 for aid in adv_ids if aid.isdigit() and len(aid) == 7 and aid.startswith('5')})
            event_map = {}
            if grp_ids:
                for i in range(0, len(grp_ids), 500):
                    chunk = grp_ids[i:i + 500]
                    placeholders = ', '.join(['?'] * len(chunk))
                    cursor.execute(f'SELECT "{col_event_grp}", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_grp}" IN ({placeholders})', chunk)
                    for r in cursor.fetchall():
                        if r[0] is not None and r[1] is not None:
                            event_map[r[0]] = str(r[1]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()

            # 1. hatsune_boss 테이블 매핑
            tbl_hb = db_info.get('hatsune_boss_table')
            if tbl_hb:
                tbl_hb_v = _validate_identifier(tbl_hb)
                col_qname = _validate_identifier(db_info.get('hatsune_boss_quest_name_col', 'quest_name'))
                col_ws = _validate_identifier(db_info.get('hatsune_boss_wavestart_col', 'story_id_wavestart_1'))
                col_we = _validate_identifier(db_info.get('hatsune_boss_waveend_col', 'story_id_waveend_1'))

                cursor.execute(f'SELECT "{col_ws}", "{col_qname}" FROM "{tbl_hb_v}" WHERE "{col_ws}" != 0')
                for sid, qname in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        q_clean = str(qname).strip() if qname else "보스 전투"
                        result_map[sid_str] = f"[{ev_title}] - {q_clean}" if ev_title else q_clean

                cursor.execute(f'SELECT "{col_we}", "{col_qname}" FROM "{tbl_hb_v}" WHERE "{col_we}" != 0')
                for sid, qname in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        q_clean = str(qname).strip() if qname else "보스 전투"
                        result_map[sid_str] = f"[{ev_title}] - {q_clean} (승리)" if ev_title else f"{q_clean} (승리)"

            # 2. hatsune_special_battle 테이블 매핑
            tbl_hsb = db_info.get('hatsune_special_battle_table')
            if tbl_hsb:
                tbl_hsb_v = _validate_identifier(tbl_hsb)
                col_mode = _validate_identifier(db_info.get('hatsune_special_battle_mode_col', 'mode'))
                col_ms = _validate_identifier(db_info.get('hatsune_special_battle_mode_start_col', 'story_id_mode_start'))
                col_me = _validate_identifier(db_info.get('hatsune_special_battle_mode_end_col', 'story_id_mode_end'))

                cursor.execute(f'SELECT "{col_ms}", "{col_mode}" FROM "{tbl_hsb_v}" WHERE "{col_ms}" != 0')
                for sid, mode in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        m_str = f"SP 배틀 (MODE {mode})"
                        result_map[sid_str] = f"[{ev_title}] - {m_str}" if ev_title else m_str

                cursor.execute(f'SELECT "{col_me}", "{col_mode}" FROM "{tbl_hsb_v}" WHERE "{col_me}" != 0')
                for sid, mode in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        suffix = "클리어" if mode == 3 else "전환"
                        m_str = f"SP 배틀 (MODE {mode} {suffix})"
                        result_map[sid_str] = f"[{ev_title}] - {m_str}" if ev_title else m_str

            # 3. movie 테이블 또는 미디어 전용 컷신 제외 목록 구성
            media_sids = set()
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movie'")
                if cursor.fetchone():
                    cursor.execute("SELECT story_id FROM movie WHERE story_id IS NOT NULL")
                    media_sids = {str(r[0]) for r in cursor.fetchall()}
            except sqlite3.Error:
                pass

            # 4. 잔여 5xxxxxx 배틀 ADV 매핑 (단순 미디어 전용 파일 제외)
            for aid in adv_ids:
                if aid in result_map or aid in media_sids:
                    continue
                if aid.isdigit() and len(aid) == 7 and aid.startswith('5'):
                    sub_id = int(aid) % 1000
                    # 대사 없는 영상/음향 전용 서브ID 패턴 (007, 501, 602~669 등) 제외
                    if sub_id == 7 or sub_id == 501 or (602 <= sub_id <= 669):
                        continue
                    grp_id = int(aid) // 1000
                    ev_title = event_map.get(grp_id)
                    if ev_title:
                        result_map[aid] = f"[{ev_title}] - 배틀 연출 {sub_id}"

    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map






