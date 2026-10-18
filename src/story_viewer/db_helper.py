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


def _get_baseline_db_path(db_info: dict[str, Any], baseline_version: str = 'default') -> str | None:
    """지정된 baseline DB(기본 10052900, 10067600 등)의 실제 파일 경로를 반환합니다."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src_dir = os.path.join(script_dir, 'src')

    baseline_dbs = db_info.get('baseline_dbs')
    if isinstance(baseline_dbs, dict) and baseline_version in baseline_dbs:
        fname = baseline_dbs[baseline_version].get('db_path', '')
        if fname:
            p = os.path.join(src_dir, fname)
            if os.path.exists(p):
                return p

    if baseline_version == 'default':
        fname = db_info.get('baseline_db_path', '')
        if fname:
            p = os.path.join(src_dir, fname)
            if os.path.exists(p):
                return p

    candidates = [
        os.path.join(src_dir, f"master_jp_{baseline_version}.db"),
        os.path.join(os.path.dirname(__file__), '..', f"master_jp_{baseline_version}.db"),
        os.path.join(os.path.dirname(__file__), f"master_jp_{baseline_version}.db"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


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


_JP_SITUATION_TO_CANONICAL_ID: dict[str, str] | None = None


def _get_jp_situation_to_canonical_id() -> dict[str, str]:
    """JP baseline DB의 dear_story_detail 테이블에서 situation(일어) -> canonical story_id 매핑을 반환합니다."""
    global _JP_SITUATION_TO_CANONICAL_ID
    if _JP_SITUATION_TO_CANONICAL_ID is not None:
        return _JP_SITUATION_TO_CANONICAL_ID

    _JP_SITUATION_TO_CANONICAL_ID = {}
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', 'master_jp_10052900.db'),
        os.path.join(os.path.dirname(__file__), 'master_jp_10052900.db'),
    ]
    for p in candidates:
        norm_p = os.path.abspath(p).replace('\\', '/')
        if os.path.exists(norm_p):
            try:
                with sqlite3.connect(f"file:{norm_p}?mode=ro", uri=True) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT story_id, sub_title FROM dear_story_detail')
                    for r in cursor.fetchall():
                        if r[0] and r[1]:
                            clean = re.sub(r'\s+', '', str(r[1]).replace('\\n', ''))
                            _JP_SITUATION_TO_CANONICAL_ID[clean] = str(r[0])
                break
            except Exception:
                pass
    return _JP_SITUATION_TO_CANONICAL_ID


def fetch_dear_story_detail_fallback_titles_batch(
    db_info: dict[str, Any], 
    meta_dict: dict[str, tuple[str | None, str | None]]
) -> dict[str, str]:
    """
    복각 및 신규 이벤트에서 재활용된 6xxxxxx 신뢰도 에피소드에 대해
    voice_adv_id(내부 음성 번호) 또는 situation(상황 대사)을 기반으로
    dear_story_detail 테이블과 교차 매핑하여 공식 타이틀을 반환합니다.
    
    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        meta_dict (dict): adv_id를 키로 하고, (voice_adv_id, situation) 튜플을 값으로 갖는 딕셔너리.
        
    Returns:
        dict[str, str]: adv_id를 키로, 'title - sub_title'을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not meta_dict:
        return {}

    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            tbl = _validate_identifier(db_info['dear_story_detail_table'])
            col_id = _validate_identifier(db_info['dear_story_detail_id_col'])
            col_title = _validate_identifier(db_info['dear_story_detail_title_col'])
            col_sub = _validate_identifier(db_info['dear_story_detail_sub_title_col'])

            cursor.execute(f'SELECT "{col_id}", "{col_title}", "{col_sub}" FROM "{tbl}"')
            
            id_to_title = {}
            sub_to_title = {}
            for row in cursor.fetchall():
                sid = str(row[0]) if row[0] is not None else ''
                t = str(row[1]).replace('\\n', ' ').strip() if row[1] is not None else ''
                sub = str(row[2]).replace('\\n', ' ').strip() if row[2] is not None else ''
                if t and sub:
                    fmt = f"{t} - {sub}"
                elif t:
                    fmt = t
                elif sub:
                    fmt = sub
                else:
                    continue
                
                if sid:
                    id_to_title[sid] = fmt
                clean_sub = re.sub(r'\s+', '', sub)
                if clean_sub:
                    sub_to_title[clean_sub] = fmt

            jp_sit_map = _get_jp_situation_to_canonical_id()
            for aid, (vo_id, situation) in meta_dict.items():
                if vo_id and vo_id in id_to_title:
                    result_map[aid] = id_to_title[vo_id]
                elif situation:
                    clean_sit = re.sub(r'\s+', '', situation)
                    if clean_sit in sub_to_title:
                        result_map[aid] = sub_to_title[clean_sit]
                    elif clean_sit in jp_sit_map:
                        canonical_id = jp_sit_map[clean_sit]
                        if canonical_id in id_to_title:
                            result_map[aid] = id_to_title[canonical_id]
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


def fetch_event_top_adv_titles_batch(
    db_info: dict[str, Any],
    adv_ids: list[str],
    meta_dict: dict[str, tuple[str | None, str | None]] | None = None,
) -> dict[str, str]:
    """adv_id 목록을 기반으로 event_top_adv, unit_data, event_story_data를 조회하고,
    JSON의 situation(부제목)과 결합하여 '[이벤트명] 캐릭터명 - 부제목' 형식의 타이틀을 일괄 조회합니다.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        meta_dict (dict, optional): adv_id를 키로 (voice_adv_id, situation) 튜플을 값으로 갖는 딕셔너리.

    Returns:
        dict[str, str]: adv_id를 키로, '[이벤트명] 캐릭터명 - 부제목' 등을 값으로 갖는 딕셔너리.
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
            col_top_event = _validate_identifier(db_info.get('event_top_adv_event_id_col', 'event_id'))

            tbl_unit = _validate_identifier(db_info.get('unit_table', 'unit_data'))
            col_unit_id = _validate_identifier(db_info.get('unit_id_col', 'unit_id'))
            col_unit_name = _validate_identifier(db_info.get('unit_name_col', 'unit_name'))

            tbl_event = _validate_identifier(db_info.get('event_list_table', 'event_story_data'))
            col_event_group = _validate_identifier(db_info.get('event_group_id_col_list', 'story_group_id'))
            col_event_title = _validate_identifier(db_info.get('event_name_col_list', 'title'))

            # voice_adv_id 별칭 매핑 구성 (5152403 -> 5094403 등 재사용된 ID 지원)
            reverse_voice_map: dict[str, list[str]] = {}
            if meta_dict:
                for aid, meta in meta_dict.items():
                    if meta and meta[0] and meta[0] != aid:
                        v_id = str(meta[0])
                        reverse_voice_map.setdefault(v_id, []).append(aid)

            search_id_set = set(adv_ids)
            search_id_set.update(reverse_voice_map.keys())
            query_ids = list(search_id_set)

            chunk_size = 500
            for i in range(0, len(query_ids), chunk_size):
                chunk = query_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))

                # 1. event_top_adv에서 대상 story_id의 character_id 및 event_id 조회
                query = f'SELECT "{col_top_id}", "{col_top_chara}", "{col_top_event}" FROM "{tbl_top}" WHERE "{col_top_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                rows = cursor.fetchall()
                if not rows:
                    continue

                # 2. 관련 character_id, event_id 및 story_group_id 수집
                chara_ids = list({r[1] for r in rows if r[1] is not None})
                event_ids = list({r[2] for r in rows if r[2] is not None})
                group_ids = list({int(r[0]) // 1000 for r in rows if r[0] is not None and str(r[0]).isdigit()})

                # 캐릭터 유닛명 조회
                unit_map = {}
                if chara_ids:
                    u_holders = ', '.join(['?'] * len(chara_ids))
                    cursor.execute(f'SELECT "{col_unit_id}", "{col_unit_name}" FROM "{tbl_unit}" WHERE "{col_unit_id}" IN ({u_holders})', chara_ids)
                    for r in cursor.fetchall():
                        if r[0] is not None and r[1] is not None:
                            unit_map[r[0]] = str(r[1]).strip()

                    # base 유닛 ID(01) 보정 (ex: 104001 -> 104001 또는 104002 -> 104001)
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

                # 이벤트명 조회 (story_group_id 및 value(event_id) 기준 양방향 캐시)
                event_map_by_grp = {}
                event_map_by_val = {}
                
                # event_story_data의 컬럼 확인
                has_value_col = False
                try:
                    cursor.execute(f'PRAGMA table_info("{tbl_event}")')
                    cols = [c[1] for c in cursor.fetchall()]
                    has_value_col = 'value' in cols
                except sqlite3.Error:
                    pass

                target_grps = list(set(group_ids))
                if target_grps:
                    e_holders = ', '.join(['?'] * len(target_grps))
                    if has_value_col:
                        cursor.execute(f'SELECT "{col_event_group}", "value", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_group}" IN ({e_holders})', target_grps)
                        for r in cursor.fetchall():
                            if r[0] is not None and r[2] is not None:
                                t_clean = str(r[2]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
                                event_map_by_grp[r[0]] = t_clean
                                if r[1] is not None:
                                    event_map_by_val[r[1]] = t_clean
                    else:
                        cursor.execute(f'SELECT "{col_event_group}", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_group}" IN ({e_holders})', target_grps)
                        for r in cursor.fetchall():
                            if r[0] is not None and r[1] is not None:
                                t_clean = str(r[1]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
                                event_map_by_grp[r[0]] = t_clean

                # event_id로 추가 조회
                target_ev_ids = [eid for eid in event_ids if eid not in event_map_by_val]
                if has_value_col and target_ev_ids:
                    ev_holders = ', '.join(['?'] * len(target_ev_ids))
                    cursor.execute(f'SELECT "{col_event_group}", "value", "{col_event_title}" FROM "{tbl_event}" WHERE "value" IN ({ev_holders})', target_ev_ids)
                    for r in cursor.fetchall():
                        if r[2] is not None:
                            t_clean = str(r[2]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
                            if r[0] is not None:
                                event_map_by_grp[r[0]] = t_clean
                            if r[1] is not None:
                                event_map_by_val[r[1]] = t_clean

                # 3. 타이틀 조립: '[이벤트명] 캐릭터명 - 부제목' (인위적 라벨 0%)
                for r in rows:
                    sid_raw = r[0]
                    sid_str = str(sid_raw)
                    cid = r[1]
                    ev_id = r[2]

                    chara_name = unit_map.get(cid, "")
                    grp_id = int(sid_raw) // 1000 if str(sid_raw).isdigit() else 0
                    event_title = event_map_by_val.get(ev_id) or event_map_by_grp.get(grp_id) or ""

                    # 이 쿼리 결과에 매핑되는 대상 adv_id 리스트 (직접 일치 + voice_adv_id 별칭)
                    matched_aids = []
                    if sid_str in adv_ids:
                        matched_aids.append(sid_str)
                    if sid_str in reverse_voice_map:
                        matched_aids.extend(reverse_voice_map[sid_str])

                    for target_aid in matched_aids:
                        situation = ""
                        if meta_dict and target_aid in meta_dict and meta_dict[target_aid]:
                            situation = str(meta_dict[target_aid][1] or "").strip()

                        if event_title and chara_name and situation:
                            result_map[target_aid] = f"[{event_title}] {chara_name} - {situation}"
                        elif event_title and chara_name:
                            result_map[target_aid] = f"[{event_title}] {chara_name}"
                        elif chara_name and situation:
                            result_map[target_aid] = f"{chara_name} - {situation}"
                        elif event_title and situation:
                            result_map[target_aid] = f"[{event_title}] - {situation}"
                        elif situation:
                            result_map[target_aid] = situation
                        elif event_title:
                            result_map[target_aid] = f"[{event_title}]"
                        elif chara_name:
                            result_map[target_aid] = chara_name
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
                        q_clean = str(qname).strip() if qname else ""
                        if q_clean:
                            result_map[sid_str] = f"[{ev_title}] {q_clean} (wavestart)" if ev_title else f"{q_clean} (wavestart)"

                cursor.execute(f'SELECT "{col_we}", "{col_qname}" FROM "{tbl_hb_v}" WHERE "{col_we}" != 0')
                for sid, qname in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        q_clean = str(qname).strip() if qname else ""
                        if q_clean:
                            result_map[sid_str] = f"[{ev_title}] {q_clean} (waveend)" if ev_title else f"{q_clean} (waveend)"

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
                        m_str = f"SPECIAL MODE {mode} (mode_start)"
                        result_map[sid_str] = f"[{ev_title}] {m_str}" if ev_title else m_str

                cursor.execute(f'SELECT "{col_me}", "{col_mode}" FROM "{tbl_hsb_v}" WHERE "{col_me}" != 0')
                for sid, mode in cursor.fetchall():
                    sid_str = str(sid)
                    if sid_str in adv_ids and sid_str not in result_map:
                        ev_title = event_map.get(int(sid) // 1000, "")
                        m_str = f"SPECIAL MODE {mode} (mode_end)"
                        result_map[sid_str] = f"[{ev_title}] {m_str}" if ev_title else m_str

    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map


def fetch_event_minigame_and_sub_scenes_batch(
    db_info: dict[str, Any], 
    adv_ids: list[str],
    speaker_map: dict[str, str] | None = None,
    raw_titles_map: dict[str, str] | None = None
) -> dict[str, str]:
    """adv_id 목록을 기반으로 이벤트 미니게임 스토리, 신규 보스/SP/EX 배틀 연출,
    요리 리액션 및 이벤트 가이드 타이틀을 일괄 조회합니다.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        speaker_map (dict, optional): adv_id->화자명 매핑 딕셔너리.
        raw_titles_map (dict, optional): adv_id->JSON Frame 0 원본 타이틀 매핑 딕셔너리.

    Returns:
        dict[str, str]: adv_id를 키로, 공식 이벤트명과 결합된 타이틀을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    adv_set = set(adv_ids)
    result_map = {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()

            # 1. 이벤트 타이틀 캐시 로드
            event_map = {}
            try:
                tbl_event = _validate_identifier(db_info.get('event_list_table', 'event_story_data'))
                col_event_grp = _validate_identifier(db_info.get('event_group_id_col_list', 'story_group_id'))
                col_event_title = _validate_identifier(db_info.get('event_name_col_list', 'title'))

                grp_ids = list({int(aid) // 1000 for aid in adv_ids if aid.isdigit() and len(aid) == 7 and aid.startswith('5')})
                if grp_ids:
                    for i in range(0, len(grp_ids), 500):
                        chunk = grp_ids[i:i + 500]
                        placeholders = ', '.join(['?'] * len(chunk))
                        cursor.execute(f'SELECT "{col_event_grp}", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_grp}" IN ({placeholders})', chunk)
                        for r in cursor.fetchall():
                            if r[0] is not None and r[1] is not None:
                                event_map[r[0]] = str(r[1]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
            except (sqlite3.Error, UnsafeIdentifierError):
                pass

            # baseline default(10052900) 보강
            p_base = _get_baseline_db_path(db_info, 'default')
            if p_base and os.path.exists(p_base):
                norm_base = p_base.replace('\\', '/')
                try:
                    with sqlite3.connect(f"file:{norm_base}?mode=ro", uri=True) as conn_b:
                        cur_b = conn_b.cursor()
                        cur_b.execute('SELECT story_group_id, title FROM event_story_data')
                        for r in cur_b.fetchall():
                            if r[0] is not None and r[1] is not None and r[0] not in event_map:
                                event_map[r[0]] = str(r[1]).replace('\r\n', ' ').replace('\n', ' ').replace('\\n', ' ').strip()
                except Exception:
                    pass

            # baseline 10067600 보강 (최신 이벤트 및 요리 미니게임 리액션)
            cooking_pairs = {}
            v2_titles = {}
            mypage_names = {}
            story_to_mypage = {}

            p_676 = _get_baseline_db_path(db_info, '10067600')
            v2_table = db_info.get('event_story_v2_table', 'v1_5dc6443a480cd7e8a680f6904c9125ceba8a8b571beaf0f7c6c8b2788f4dc2eb')
            if p_676 and os.path.exists(p_676):
                norm_676 = p_676.replace('\\', '/')
                try:
                    with sqlite3.connect(f"file:{norm_676}?mode=ro", uri=True) as conn_676:
                        cur_676 = conn_676.cursor()
                        cur_676.execute(f'SELECT [bc69627001b433fade0a20e641d68ecd7f8b1e8b66370f29099c48ecc3c65afc], [c6064be3e0ab536646b7ce09315a0bda7958e82c6da3194472c2431345a34c35] FROM "{v2_table}"')
                        for ev_id, full_t in cur_676.fetchall():
                            grp = ev_id % 10000 if ev_id > 10000 else ev_id
                            if grp not in event_map:
                                clean_t = str(full_t).split(' ')[0].split('\u3000')[0].replace('\\n', ' ').strip()
                                event_map[grp] = clean_t
                                event_map[ev_id] = clean_t

                        cur_676.execute('''
                            SELECT f.[dc74953d7740483e43b6386653875c77e21540cc26cd8a3f0e802b57e7268baa], s.[f12d807789adeed6bccdb807e76bac3d299582a4a1ebed1caa5fdb045499a84d]
                            FROM (SELECT * FROM v1_9f485b9b32e33f9d26dc0b0d907ef5dc93bb41f5f0dcd20fd8fa0ed703cac974 WHERE [dd05c32b741bbc005e7e29fdf97d4617786274bdec22143e69dae4c1c38c848d] = 3) f
                            JOIN (SELECT * FROM v1_9f485b9b32e33f9d26dc0b0d907ef5dc93bb41f5f0dcd20fd8fa0ed703cac974 WHERE [dd05c32b741bbc005e7e29fdf97d4617786274bdec22143e69dae4c1c38c848d] = 2) s
                            ON f.[f12d807789adeed6bccdb807e76bac3d299582a4a1ebed1caa5fdb045499a84d] = s.[dc74953d7740483e43b6386653875c77e21540cc26cd8a3f0e802b57e7268baa]
                        ''')
                        for r in cur_676.fetchall():
                            cooking_pairs[str(r[0])] = str(r[1])

                        cur_676.execute(f'SELECT [5b802c21ec8ff3e0285a4aae847211dc5d0c1251fb2a070436b7bc86e1699985], [c6064be3e0ab536646b7ce09315a0bda7958e82c6da3194472c2431345a34c35] FROM "{v2_table}"')
                        for sid, sub in cur_676.fetchall():
                            v2_titles[str(sid)] = str(sub).replace('\\n', ' ').strip() if sub else ''

                        mypage_table = 'v1_e249e1c41d6767271e5bc0df243fe5f0de2eff1e70cb2e5c501318ef33f59f64'
                        cur_676.execute(f'SELECT [c7b81a6de35976d0586d541b42f0a6249219165076d2d550b908f3a0b2a5f689], [8f2a28a54d18237e54de33e65d39bb4f5328a1b2a505c770aebc27fb157dd474] FROM "{mypage_table}" WHERE [8f2a28a54d18237e54de33e65d39bb4f5328a1b2a505c770aebc27fb157dd474] LIKE "%ビストロ%"')
                        for mp_id, mp_name in cur_676.fetchall():
                            mypage_names[mp_id] = mp_name.replace('福弾ける出張ビストロ', '').strip()

                        cur_676.execute(f'SELECT * FROM "{v2_table}"')
                        for r in cur_676.fetchall():
                            if r[13] is not None:
                                story_to_mypage[str(r[13])] = r[19]
                except Exception:
                    pass

            def get_ev_prefix(aid_int: int) -> str:
                ev = event_map.get(aid_int // 1000, "")
                return f"[{ev}] " if ev else ""

            # 2. 최신 이벤트 스토리 v2 (10201+)
            tbl_ev2 = db_info.get('event_story_v2_table')
            if tbl_ev2:
                try:
                    tbl_ev2_v = _validate_identifier(tbl_ev2)
                    col_id = _validate_identifier(db_info.get('event_story_v2_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_story_v2_title_col', 'title'))
                    col_sub = _validate_identifier(db_info.get('event_story_v2_sub_title_col', 'sub_title'))

                    cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_sub}" FROM "{tbl_ev2_v}"')
                    for sid, t, sub in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = str(t).replace('\\n', ' ').strip() if t else ''
                            sub_clean = str(sub).replace('\\n', ' ').strip() if sub else ''
                            if sub_clean and t_clean:
                                result_map[sid_str] = f"{sub_clean} - {t_clean}"
                            else:
                                val = sub_clean or t_clean
                                if val:
                                    result_map[sid_str] = val
                except (sqlite3.Error, UnsafeIdentifierError):
                    pass

            # 3. 이벤트 상세 / 엔딩 / 특별 드라마 (event_details_table)
            tbl_ev_det = db_info.get('event_details_table')
            if tbl_ev_det:
                try:
                    tbl_ev_det_v = _validate_identifier(tbl_ev_det)
                    col_id = _validate_identifier(db_info.get('event_id_col_details', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_info_col_details', 'sub_title'))
                    col_title_det = db_info.get('event_title_col_details')

                    if col_title_det:
                        col_title_det_v = _validate_identifier(col_title_det)
                        cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_title_det_v}" FROM "{tbl_ev_det_v}"')
                        for sid, sub, t in cursor.fetchall():
                            sid_str = str(sid)
                            if sid_str in adv_ids and sid_str not in result_map:
                                t_clean = str(t).replace('\\n', ' ').strip() if t else ''
                                sub_clean = str(sub).replace('\\n', ' ').strip() if sub else ''
                                if sub_clean and t_clean:
                                    result_map[sid_str] = f"{sub_clean} - {t_clean}"
                                else:
                                    ev_p = get_ev_prefix(int(sid))
                                    val = sub_clean or t_clean
                                    if val:
                                        result_map[sid_str] = f"{ev_p}{val}"
                    else:
                        cursor.execute(f'SELECT "{col_id}", "{col_t}" FROM "{tbl_ev_det_v}"')
                        for sid, sub in cursor.fetchall():
                            sid_str = str(sid)
                            if sid_str in adv_ids and sid_str not in result_map:
                                sub_clean = str(sub).replace('\\n', ' ').strip() if sub else ''
                                if sub_clean:
                                    ev_p = get_ev_prefix(int(sid))
                                    result_map[sid_str] = f"{ev_p}{sub_clean}"
                except (sqlite3.Error, UnsafeIdentifierError):
                    pass

            # 4. 시나리오 보스 배틀 (hatsune_boss_v2 / hatsune_scenario_boss)
            boss_tbls = [
                (db_info.get('hatsune_boss_v2_table'), db_info.get('hatsune_boss_v2_quest_name_col', 'quest_name'), db_info.get('hatsune_boss_v2_wavestart_col', 'story_id_wavestart_1'), db_info.get('hatsune_boss_v2_waveend_col', 'story_id_waveend_1')),
                (db_info.get('hatsune_scenario_boss_table'), db_info.get('hatsune_scenario_boss_quest_name_col', 'quest_name'), db_info.get('hatsune_scenario_boss_wavestart_col', 'story_id_wavestart_1'), db_info.get('hatsune_scenario_boss_waveend_col', 'story_id_waveend_1')),
                # 10061600 하위 호환 후보
                ('v1_62da2e9924c716b713b50ba5b98fdf6fb4b00edd33a726d77f26e5645f2ac56c', 'd2de788a5b97de69e7cd89e44538c449e4964655c6f544794a5428c600448449', 'a8e5845f1910754597eb16a2920266762b4396b2759de187a4619fd639d8265a', '000c4a2a54553549639505fcd615042770ad16d1f902339806c2adafee420cc6'),
            ]
            for b_tbl, b_qn, b_ws, b_we in boss_tbls:
                if not b_tbl:
                    continue
                try:
                    tbl_sb_v = _validate_identifier(b_tbl)
                    col_qn = _validate_identifier(b_qn)
                    col_ws = _validate_identifier(b_ws)
                    col_we = _validate_identifier(b_we)

                    cursor.execute(f'SELECT "{col_ws}", "{col_qn}" FROM "{tbl_sb_v}" WHERE "{col_ws}" != 0')
                    for sid, qn in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            q_clean = str(qn).strip() if qn else ""
                            if q_clean:
                                result_map[sid_str] = f"{ev_p}{q_clean} (wavestart)"

                    cursor.execute(f'SELECT "{col_we}", "{col_qn}" FROM "{tbl_sb_v}" WHERE "{col_we}" != 0')
                    for sid, qn in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            q_clean = str(qn).strip() if qn else ""
                            if q_clean:
                                result_map[sid_str] = f"{ev_p}{q_clean} (waveend)"
                except (sqlite3.Error, UnsafeIdentifierError):
                    continue

            # 5. SP 배틀 v2 (hatsune_sp_battle_v2)
            sp_tbls = [
                (db_info.get('hatsune_sp_battle_v2_table'), db_info.get('hatsune_sp_battle_v2_mode_col', 'mode'), db_info.get('hatsune_sp_battle_v2_mode_start_col', 'story_id_mode_start'), db_info.get('hatsune_sp_battle_v2_mode_end_col', 'story_id_mode_end')),
                # 10061600 하위 호환 후보
                ('v1_925518ad624d33c97b5c6b1217cff2f77c6bea2ce835af0f6522aff44fa60fef', '07f267b1b2032da295e9140aeb449775139f05a590c42ba30175ea611dcdddcd', 'f711a059c2dc8230d4764c8ed9bb54e47dadc862b25ca2aa2fad4ef22af27b20', '64bbdc98663043a40cc8762161250e89fc91cd4d43f374ad42282ba3de644c85'),
            ]
            for s_tbl, s_mode, s_ms, s_me in sp_tbls:
                if not s_tbl:
                    continue
                try:
                    tbl_sp_v = _validate_identifier(s_tbl)
                    col_mode = _validate_identifier(s_mode)
                    col_ms = _validate_identifier(s_ms)
                    col_me = _validate_identifier(s_me)

                    cursor.execute(f'SELECT "{col_ms}", "{col_mode}" FROM "{tbl_sp_v}" WHERE "{col_ms}" != 0')
                    for sid, mode in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            result_map[sid_str] = f"{ev_p}SPECIAL MODE {mode} (mode_start)"

                    cursor.execute(f'SELECT "{col_me}", "{col_mode}" FROM "{tbl_sp_v}" WHERE "{col_me}" != 0')
                    for sid, mode in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            result_map[sid_str] = f"{ev_p}SPECIAL MODE {mode} (mode_end)"
                except (sqlite3.Error, UnsafeIdentifierError):
                    continue

            # 6. 전시 배틀 EX (hatsune_ex_battle)
            tbl_ex = db_info.get('hatsune_ex_battle_table')
            if tbl_ex:
                try:
                    tbl_ex_v = _validate_identifier(tbl_ex)
                    col_id = _validate_identifier(db_info.get('hatsune_ex_battle_id_col', 'story_id'))

                    cursor.execute(f'SELECT "{col_id}" FROM "{tbl_ex_v}" WHERE "{col_id}" != 0')
                    for sid, in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            result_map[sid_str] = f"{ev_p}EX (ex_battle)"
                except (sqlite3.Error, UnsafeIdentifierError):
                    pass

            # 7. 요리 교실 미니게임 (event_cooking_minigame)
            tbl_cook = db_info.get('event_cooking_minigame_table')
            if tbl_cook:
                try:
                    tbl_cook_v = _validate_identifier(tbl_cook)
                    col_id = _validate_identifier(db_info.get('event_cooking_minigame_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_cooking_minigame_title_col', 'title'))

                    cursor.execute(f'SELECT "{col_id}", "{col_t}" FROM "{tbl_cook_v}" WHERE "{col_id}" != 0')
                    for sid, t in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = str(t).strip() if t else ""
                            if t_clean:
                                ev_p = get_ev_prefix(int(sid))
                                result_map[sid_str] = f"{ev_p}{t_clean}"
                except (sqlite3.Error, UnsafeIdentifierError):
                    pass

            # 8. 몬스터 박물관 미니게임 (event_museum_minigame)
            tbl_mus = db_info.get('event_museum_minigame_table')
            if tbl_mus:
                try:
                    tbl_mus_v = _validate_identifier(tbl_mus)
                    col_id = _validate_identifier(db_info.get('event_museum_minigame_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_museum_minigame_title_col', 'title'))
                    col_sub = _validate_identifier(db_info.get('event_museum_minigame_sub_title_col', 'sub_title'))

                    cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_sub}" FROM "{tbl_mus_v}" WHERE "{col_id}" != 0')
                    for sid, t, sub in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = str(t).strip() if t else ""
                            sub_clean = str(sub).strip() if sub else ""
                            full_t = f"{t_clean} ({sub_clean})" if (t_clean and sub_clean) else (t_clean or sub_clean)
                            if full_t:
                                ev_p = get_ev_prefix(int(sid))
                                result_map[sid_str] = f"{ev_p}{full_t}"
                except (sqlite3.Error, UnsafeIdentifierError):
                    pass

            # 9. 수수께끼/추리 미니게임 (event_riddle_minigame / hatsune_quiz)
            riddle_configs = [
                (
                    db_info.get('event_riddle_minigame_table'),
                    db_info.get('event_riddle_minigame_point_name_col', 'cafc37baad89226305f2d059e1211997acc6ac0e3331ece2ff97997e2b16ce2d'),
                    db_info.get('event_riddle_minigame_title_col', '2ba0dc5bcba3572c90ba7256063d19e2da38135d66aeb1205e967acc5f694617'),
                    db_info.get('event_riddle_minigame_start_id_col', '740818df0deafcfe5af0d25482c4b5a977bc7d4824f0a546c9b26c5d7587948f'),
                    db_info.get('event_riddle_minigame_end_id_col', 'c93191ec229a06aaf5cd07f0007a82bd7ab92df206831cec87dba9f616b67090'),
                ),
                (
                    db_info.get('hatsune_quiz_table'),
                    db_info.get('hatsune_quiz_point_name_col', 'quiz_point_name'),
                    db_info.get('hatsune_quiz_title_col', 'question_title'),
                    db_info.get('hatsune_quiz_start_id_col', 'adv_id_quiz_start'),
                    db_info.get('hatsune_quiz_end_id_col', 'adv_id_quiz_end'),
                ),
            ]
            for r_tbl, r_pt, r_ti, r_s1, r_s2 in riddle_configs:
                if not r_tbl:
                    continue
                try:
                    r_tbl_v = _validate_identifier(r_tbl)
                    col_pt = _validate_identifier(r_pt)
                    col_ti = _validate_identifier(r_ti)
                    col_s1 = _validate_identifier(r_s1)
                    col_s2 = _validate_identifier(r_s2)
                    cursor.execute(f'SELECT "{col_s1}", "{col_s2}", "{col_pt}", "{col_ti}" FROM "{r_tbl_v}"')
                    for s1, s2, pt, ti in cursor.fetchall():
                        pt_clean = str(pt).strip() if pt else ""
                        ti_clean = str(ti).strip() if ti else ""
                        full_name = f"{pt_clean} {ti_clean}".strip()
                        s1_str = str(s1)
                        s2_str = str(s2)
                        if s1_str in adv_ids and s1_str not in result_map:
                            ev_p = get_ev_prefix(int(s1))
                            result_map[s1_str] = f"{ev_p}{full_name} (quiz_start)"
                        if s2_str in adv_ids and s2_str not in result_map:
                            ev_p = get_ev_prefix(int(s2))
                            result_map[s2_str] = f"{ev_p}{full_name} (quiz_end)"
                except (sqlite3.Error, UnsafeIdentifierError):
                    continue

            # 10. 이벤트 미니게임 및 추가 서브씬 (17개 테이블 일괄 조회)
            def _clean_sub(s: Any) -> str:
                if not s:
                    return ""
                clean = str(s).replace('\\n', ' ').strip()
                if len(clean) > 30 or clean.isdigit() or re.match(r'^\d{4}/\d{2}/\d{2}', clean):
                    return ""
                return clean

            generic_minigame_tables = [
                'event_secret_minigame', 'event_collab_minigame', 'event_vampire_minigame',
                'event_crybaby_minigame', 'event_summer_minigame', 'event_liberate_minigame',
                'event_hatsune_dream_minigame', 'event_christmas_minigame', 'event_coaster_minigame',
                'event_nebia_minigame', 'event_taiso_minigame', 'event_alces_minigame',
                'event_trip_minigame', 'event_house_minigame', 'event_diary_minigame',
                'event_opening_adv', 'event_boss_battle_v3',
                'event_remember_story', 'hatsune_present', 'hatsune_quest'
            ]

            for t_prefix in generic_minigame_tables:
                tbl_name = db_info.get(f'{t_prefix}_table')
                if not tbl_name:
                    continue
                try:
                    tbl_name_v = _validate_identifier(tbl_name)
                    id_col = _validate_identifier(db_info.get(f'{t_prefix}_id_col', 'story_id'))
                    title_col = _validate_identifier(db_info.get(f'{t_prefix}_title_col', 'title'))
                    sub_col_raw = db_info.get(f'{t_prefix}_sub_title_col')

                    if sub_col_raw:
                        sub_col_v = _validate_identifier(sub_col_raw)
                        cursor.execute(f'SELECT "{id_col}", "{title_col}", "{sub_col_v}" FROM "{tbl_name_v}" WHERE "{id_col}" != 0')
                        for sid, t, sub in cursor.fetchall():
                            sid_str = str(sid)
                            if sid_str in adv_set and sid_str not in result_map:
                                t_c = str(t).replace('\\n', ' ').strip() if t else ""
                                s_c = _clean_sub(sub)
                                full_t = f"{t_c} - {s_c}" if (t_c and s_c) else (t_c or s_c)
                                if full_t:
                                    try:
                                        ev_p = get_ev_prefix(int(sid))
                                    except (ValueError, TypeError):
                                        ev_p = ""
                                    if ev_p and ev_p.strip('[] ') in full_t:
                                        result_map[sid_str] = full_t
                                    else:
                                        result_map[sid_str] = f"{ev_p}{full_t}"
                    else:
                        cursor.execute(f'SELECT "{id_col}", "{title_col}" FROM "{tbl_name_v}" WHERE "{id_col}" != 0')
                        for sid, t in cursor.fetchall():
                            sid_str = str(sid)
                            if sid_str in adv_set and sid_str not in result_map:
                                t_c = str(t).replace('\\n', ' ').strip() if t else ""
                                if t_c:
                                    try:
                                        ev_p = get_ev_prefix(int(sid))
                                    except (ValueError, TypeError):
                                        ev_p = ""
                                    if ev_p and ev_p.strip('[] ') in t_c:
                                        result_map[sid_str] = t_c
                                    else:
                                        result_map[sid_str] = f"{ev_p}{t_c}"
                except (sqlite3.Error, UnsafeIdentifierError):
                    continue

            # 11. 요리 미니게임 리액션, JSON 원본 타이틀 및 이벤트 가이드 매핑
            for aid in adv_ids:
                if aid in result_map:
                    continue

                # A. 요리 미니게임 실패 리액션 (21개)
                if aid in cooking_pairs:
                    succ_id = cooking_pairs[aid]
                    dish_title = v2_titles.get(succ_id, '')
                    mp_id = story_to_mypage.get(succ_id)
                    char_name = mypage_names.get(mp_id) or (speaker_map.get(aid, '') if speaker_map else '')
                    if dish_title and char_name:
                        result_map[aid] = f"{dish_title} - {char_name}"
                    elif dish_title:
                        result_map[aid] = dish_title
                    continue

                # B. JSON 원본 Frame 0 / 메타데이터 타이틀 보존 (128개 등)
                if raw_titles_map and aid in raw_titles_map:
                    raw_t = raw_titles_map[aid].strip()
                    if raw_t and not raw_t.startswith("storydata_") and not raw_t.isdigit():
                        result_map[aid] = raw_t
                        continue

    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map


def fetch_legion_and_byway_battle_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록을 기반으로 legion_special_battle, byway_battle_quest_data, byway_quest_data를 조회하여
    왕도종말결전 및 우회로 특수전투 타이틀을 일괄 조회합니다.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.

    Returns:
        dict[str, str]: adv_id를 키로 생성된 타이틀을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    adv_set = set(adv_ids)
    result_map = {}

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()

            # 1. 왕도종말결전 (legion_special_battle)
            tbl_legion = db_info.get('legion_special_battle_table')
            if tbl_legion:
                tbl_legion_v = _validate_identifier(tbl_legion)
                col_mode = _validate_identifier(db_info.get('legion_special_battle_mode_col', 'mode'))
                col_ms = _validate_identifier(db_info.get('legion_special_battle_mode_start_col', 'story_id_mode_start'))
                col_me = _validate_identifier(db_info.get('legion_special_battle_mode_end_col', 'story_id_mode_end'))

                cursor.execute(f'SELECT "{col_mode}", "{col_ms}", "{col_me}" FROM "{tbl_legion_v}"')
                for mode, ms, me in cursor.fetchall():
                    ms_str = str(ms)
                    me_str = str(me)
                    if ms_str != '0' and ms_str in adv_set:
                        result_map[ms_str] = f"[王都終末決戦] SPECIAL MODE {mode} (wavestart)"
                    if me_str != '0' and me_str in adv_set:
                        result_map[me_str] = f"[王都終末決戦] SPECIAL MODE {mode} (waveend)"

            # 2. 우회로 특수전투 (byway_battle_quest_data + byway_quest_data)
            tbl_bb = db_info.get('byway_battle_quest_data_table')
            tbl_bq = db_info.get('byway_quest_data_table')
            if tbl_bb and tbl_bq:
                tbl_bb_v = _validate_identifier(tbl_bb)
                tbl_bq_v = _validate_identifier(tbl_bq)
                col_bb_qid = _validate_identifier(db_info.get('byway_battle_quest_data_quest_id_col', 'quest_id'))
                col_bb_ws = _validate_identifier(db_info.get('byway_battle_quest_data_wavestart_col', 'story_id_wavestart_1'))
                col_bb_we = _validate_identifier(db_info.get('byway_battle_quest_data_waveend_col', 'story_id_waveend_1'))
                col_bq_qid = _validate_identifier(db_info.get('byway_quest_data_quest_id_col', 'quest_id'))
                col_bq_name = _validate_identifier(db_info.get('byway_quest_data_quest_name_col', 'quest_name'))

                cursor.execute(f'''
                    SELECT 
                        b."{col_bb_ws}", 
                        b."{col_bb_we}", 
                        q."{col_bq_name}"
                    FROM "{tbl_bb_v}" b
                    JOIN "{tbl_bq_v}" q ON b."{col_bb_qid}" = q."{col_bq_qid}"
                    WHERE b."{col_bb_ws}" != 0 OR b."{col_bb_we}" != 0
                ''')
                for ws, we, qname in cursor.fetchall():
                    q_clean = str(qname).strip() if qname else ""
                    ws_str = str(ws)
                    we_str = str(we)
                    if ws_str != '0' and ws_str in adv_set:
                        result_map[ws_str] = f"{q_clean} (wavestart)"
                    if we_str != '0' and we_str in adv_set:
                        result_map[we_str] = f"{q_clean} (waveend)"

    except (sqlite3.Error, KeyError, UnsafeIdentifierError):
        pass

    return result_map
