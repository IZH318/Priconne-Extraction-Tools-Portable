"""Story Viewer SQLite 데이터베이스 쿼리 및 데이터 추출 헬퍼 모듈.

이벤트 목록, 메인/캐릭터/길드 스토리, 미니게임 대화, 특수 보스전 ADV 등의
쿼리 조립 및 실행 담당. SQL Injection 방지를 위한 _validate_identifier
화이트리스트 검증 및 _build_query 중앙 쿼리 빌더 강제 적용.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import sqlite3
import threading
import weakref
from collections.abc import Iterator
from typing import Any


from src.exceptions import UnsafeIdentifierError

logger = logging.getLogger(__name__)

# 읽기 전용 SQLite 연결 재사용 캐시.
# 실측(52MB DB): 신규 연결의 첫 쿼리 약 17~20ms vs 재사용 연결 약 0.06ms.
# 스레드별로 연결을 보관하며, DB 파일 교체/삭제 전에는 반드시
# close_cached_connections()로 해제해야 한다(Windows 파일 잠금 방지).
_CONNECTION_LOCAL = threading.local()
_CONNECTION_CACHES: weakref.WeakSet[_ConnectionCache] = weakref.WeakSet()
_CONNECTION_LOCK = threading.Lock()


class _ConnectionCache:
    """스레드별 읽기 전용 연결 보관소 (스레드 종료 시 WeakSet에서 자동 제거)."""

    __slots__ = ("connections", "__weakref__")

    def __init__(self) -> None:
        self.connections: dict[str, sqlite3.Connection] = {}


def _thread_connection_cache() -> _ConnectionCache:
    """현재 스레드의 연결 캐시를 반환(없으면 생성 후 등록)."""
    cache: _ConnectionCache | None = getattr(_CONNECTION_LOCAL, "cache", None)
    if cache is None:
        cache = _ConnectionCache()
        _CONNECTION_LOCAL.cache = cache
        with _CONNECTION_LOCK:
            _CONNECTION_CACHES.add(cache)
    return cache


def get_readonly_connection(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    """스레드별로 재사용되는 읽기 전용 SQLite 연결을 반환.

    Args:
        db_path (str | os.PathLike[str]): 열려는 SQLite 파일 경로.

    Returns:
        sqlite3.Connection: 해당 스레드가 보유한 읽기 전용 연결.
    """
    raw_path = os.fspath(db_path)
    key = os.path.normcase(os.path.abspath(raw_path))
    cache = _thread_connection_cache()
    conn = cache.connections.get(key)
    if conn is None:
        # check_same_thread=False: 연결 사용은 소유 스레드로 한정하되,
        # DB 교체 전 다른 스레드가 정리(close)할 수 있도록 허용.
        conn = sqlite3.connect(f"file:{raw_path}?mode=ro", uri=True, check_same_thread=False)
        cache.connections[key] = conn
    return conn


@contextlib.contextmanager
def _readonly_connection(db_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    """캐시된 읽기 전용 연결을 닫지 않고 사용하는 컨텍스트 매니저."""
    yield get_readonly_connection(db_path)


def close_cached_connections(db_path: str | os.PathLike[str] | None = None) -> int:
    """캐시된 읽기 전용 연결을 해제한다(DB 파일 교체/삭제 전 필수 호출).

    Args:
        db_path (str | os.PathLike[str] | None): 특정 파일만 해제할 경로.
            None이면 모든 캐시 연결을 해제.

    Returns:
        int: 닫은 연결 개수.
    """
    key = os.path.normcase(os.path.abspath(os.fspath(db_path))) if db_path is not None else None
    closed = 0
    with _CONNECTION_LOCK:
        caches = list(_CONNECTION_CACHES)
    for cache in caches:
        for cache_key, conn in list(cache.connections.items()):
            if key is not None and cache_key != key:
                continue
            try:
                conn.close()
            except sqlite3.Error:
                pass
            cache.connections.pop(cache_key, None)
            closed += 1
    return closed

# 데이터베이스 SQL 식별자(테이블/컬럼명) 화이트리스트 패턴: 영숫자, 언더스코어만 허용.
# 참고: priconne-database의 해시 기반 테이블/컬럼명은 'v1_' prefix가 있어
# 해당 패턴 통과 처리. 숫자로 시작하는 순수 hex 식별자가 사용될 경우 별도 처리 필요.
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z0-9_]+\Z')


def _validate_identifier(name: str) -> str:
    """SQL Injection 방지용 식별자 검증.

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
    """검증된 식별자 기반 SELECT 쿼리 조립.

    모든 SQL 문자열 조립은 본 함수를 거치도록 일원화하여
    식별자 검증 및 안전한 쿼리 생성 보장.

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
        allowed_ops = {"=", "!=", "<>", "<", ">", "<=", ">=", "LIKE", "IN", "IS", "IS NOT"}
        if where_op.upper() not in allowed_ops:
            raise ValueError(f"Unsupported where_op: {where_op}")
        query += f' WHERE "{w_col}" {where_op.upper()} ?'

    return query


def _get_db_path(db_info: dict[str, Any]) -> str:
    """DB 정보 딕셔너리 기반 절대 경로 반환."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = db_info.get('db_path') if isinstance(db_info, dict) else None
    if not db_path:
        raise ValueError("db_info missing 'db_path'")
    # 경로 순회(Path Traversal) 방지 검증 (db_path가 project_root 하위에 머무는지 검증)
    resolved = os.path.normpath(os.path.join(script_dir, db_path))
    try:
        if os.path.commonpath([script_dir, resolved]) != script_dir:
            raise ValueError(f"db_path escapes project root: {db_path!r}")
    except ValueError:
        raise ValueError(f"db_path escapes project root: {db_path!r}") from None
    return resolved


def _clean_title_text(val: Any) -> str:
    """타이틀 문자열 개행 치환 및 전각 공백 보존, 연속 반각 공백 단일 공백 정규화."""
    if val is None:
        return ""
    clean = re.sub(r'[ \t]*(\r\n|\n|\\n)[ \t]*', ' ', str(val))
    clean = clean.replace('\u3000 ', '\u3000').replace(' \u3000', '\u3000')
    return re.sub(r'[ \t]+', ' ', clean).strip()


def _get_baseline_db_path(db_info: dict[str, Any], baseline_version: str = 'default') -> str | None:
    """지정 baseline DB(기본 10052900, 10067600 등) 실제 파일 경로 반환."""
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src_dir = os.path.join(script_dir, 'src')

    baseline_dbs = db_info.get('baseline_dbs')
    if isinstance(baseline_dbs, dict) and baseline_version in baseline_dbs:
        fname = baseline_dbs[baseline_version].get('db_path', '')
        if fname:
            p = os.path.normpath(os.path.join(src_dir, fname))
            try:
                if os.path.commonpath([src_dir, p]) != src_dir:
                    raise ValueError("baseline db_path escapes src dir")
            except ValueError:
                raise ValueError("baseline db_path escapes src dir") from None
            if os.path.exists(p):
                return p

    if baseline_version == 'default':
        fname = db_info.get('baseline_db_path', '')
        if fname:
            p = os.path.normpath(os.path.join(src_dir, fname))
            try:
                if os.path.commonpath([src_dir, p]) != src_dir:
                    raise ValueError("baseline db_path escapes src dir")
            except ValueError:
                raise ValueError("baseline db_path escapes src dir") from None
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


_EVENT_NAMES_CACHE: dict[tuple[str, str, str, float | None], list[str]] = {}


def fetch_event_names(db_info: dict[str, Any]) -> list[str]:
    """이벤트 이름 목록 DB 조회 및 리스트 반환.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리 (db_path, event_list_table, event_name_col_list 포함).

    Returns:
        list[str]: 이벤트 이름 리스트 (오류 시 빈 리스트 반환).

    Raises:
        sqlite3.Error: DB 접근 중 오류 발생 시.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    table = db_info['event_list_table']
    col = db_info['event_name_col_list']
    try:
        mtime = os.path.getmtime(db_path)
    except OSError:
        mtime = None
    cache_key = (db_path, table, col, mtime)
    if mtime is not None:
        cached = _EVENT_NAMES_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)
    with _readonly_connection(db_path) as conn:
        cursor = conn.cursor()
        query = _build_query(
            table=table,
            columns=[col],
            distinct=True,
        )
        cursor.execute(query)
        result = [_clean_title_text(row[0]) for row in cursor.fetchall() if row[0]]
    if mtime is not None:
        _EVENT_NAMES_CACHE[cache_key] = result
    return list(result)


def fetch_event_story_ids(db_info: dict[str, Any], event_name: str) -> set[str]:
    """특정 이벤트 이름 소속 스토리 ID 세트 반환.

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

    cleaned_name = _clean_title_text(event_name)
    query = (
        f'SELECT DISTINCT "{details_id_col}" FROM "{details_tbl}" d '
        f'JOIN "{list_tbl}" l ON d."{group_col_details}" = l."{group_col_list}" '
        f'WHERE trim(replace(replace(replace(l."{name_col}", char(13), \'\'), char(10), \' \'), \'\\n\', \' \')) = ? '
        f'OR l."{name_col}" = ?'
    )
    with _readonly_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (cleaned_name, event_name))
        return {f"storydata_{row[0]}.json" for row in cursor.fetchall()}


def fetch_birthday_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 birthday_login_bonus_data 테이블 이름 일괄 조회.

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
        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()

            chunk_size = 500
            for i in range(0, len(adv_ids), chunk_size):
                chunk = adv_ids[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                # 식별자 검증(SQL Injection 방지)
                tbl = _validate_identifier(db_info['birthday_table'])
                col_id = _validate_identifier(db_info['birthday_adv_id_col'])
                col_name = _validate_identifier(db_info['birthday_name_col'])

                query = f'SELECT "{col_id}", "{col_name}" FROM "{tbl}" WHERE "{col_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                for row in cursor.fetchall():
                    if row[0] and row[1]:
                        result_map[str(row[0])] = _clean_title_text(row[1])
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_birthday_titles_batch failed: %s", exc)

    return result_map


def fetch_quest_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 quest_data 테이블 대상 quest_name 일괄 조회.

    story_id_wavestart_3 일치 시 '{quest_name} (start)',
    story_id_waveend_3 일치 시 '{quest_name} (end)'로 매핑.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.

    Returns:
        dict[str, str]: adv_id를 키로, '{quest_name} (start)' 또는 '{quest_name} (end)'를 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    result_map = {}
    try:
        with _readonly_connection(db_path) as conn:
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
                    name = _clean_title_text(row[2])
                    if not name:
                        continue
                    if start_id in chunk_set and start_id != '0':
                        result_map[start_id] = f"{name} (start)"
                    if end_id in chunk_set and end_id != '0':
                        result_map[end_id] = f"{name} (end)"
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_quest_titles_batch failed: %s", exc)

    return result_map


def fetch_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 story_detail 테이블 대상 title 및 sub_title 일괄 조회.

    조회 결과는 'title - sub_title' 형식으로 매핑.

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
        with _readonly_connection(db_path) as conn:
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
                    t = _clean_title_text(row[1])
                    sub = _clean_title_text(row[2])

                    if t and sub:
                        formatted = f"{t} - {sub}"
                    elif t:
                        formatted = t
                    elif sub:
                        formatted = sub
                    else:
                        continue
                    result_map[story_id] = formatted
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_story_detail_titles_batch failed: %s", exc)

    rem_ids = [aid for aid in adv_ids if aid not in result_map]
    if rem_ids:
        p_base = _get_baseline_db_path(db_info, 'default')
        if p_base and os.path.exists(p_base):
            norm_base = p_base.replace('\\', '/')
            try:
                with _readonly_connection(norm_base) as conn_b:
                    cursor_b = conn_b.cursor()
                    for i in range(0, len(rem_ids), 500):
                        chunk = rem_ids[i:i + 500]
                        placeholders = ', '.join(['?'] * len(chunk))
                        cursor_b.execute(
                            f'SELECT story_id, title, sub_title FROM story_detail WHERE story_id IN ({placeholders})',
                            chunk
                        )
                        for row in cursor_b.fetchall():
                            story_id = str(row[0]) if row[0] is not None else ''
                            t = _clean_title_text(row[1])
                            sub = _clean_title_text(row[2])
                            if t and sub:
                                formatted = f"{t} - {sub}"
                            elif t:
                                formatted = t
                            elif sub:
                                formatted = sub
                            else:
                                continue
                            result_map[story_id] = formatted
            except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                logger.debug("Failed to build dear story title map: %s", exc)

    return result_map


def fetch_dear_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 dear_story_detail 테이블 대상 title 및 sub_title 일괄 조회.

    조회 결과는 'title - sub_title' 형식으로 매핑.

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
        with _readonly_connection(db_path) as conn:
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
                    t = _clean_title_text(row[1])
                    sub = _clean_title_text(row[2])

                    if t and sub:
                        formatted = f"{t} - {sub}"
                    elif t:
                        formatted = t
                    elif sub:
                        formatted = sub
                    else:
                        continue
                    result_map[story_id] = formatted
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_dear_story_detail_titles_batch failed: %s", exc)

    return result_map


_JP_SITUATION_TO_CANONICAL_ID: dict[str, str] | None = None


def _get_jp_situation_to_canonical_id() -> dict[str, str]:
    """JP baseline DB dear_story_detail 테이블 기반 situation(일어) -> canonical story_id 매핑 반환."""
    global _JP_SITUATION_TO_CANONICAL_ID
    if _JP_SITUATION_TO_CANONICAL_ID is not None and _JP_SITUATION_TO_CANONICAL_ID:
        return _JP_SITUATION_TO_CANONICAL_ID

    # 역난독화 컬럼 매핑 로드
    _JP_SITUATION_TO_CANONICAL_ID = {}
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', 'master_jp_10052900.db'),
        os.path.join(os.path.dirname(__file__), 'master_jp_10052900.db'),
    ]
    for p in candidates:
        norm_p = os.path.abspath(p).replace('\\', '/')
        if os.path.exists(norm_p):
            try:
                with _readonly_connection(norm_p) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT story_id, sub_title FROM dear_story_detail')
                    for r in cursor.fetchall():
                        if r[0] and r[1]:
                            clean = re.sub(r'\s+', '', str(r[1]).replace('\\n', ''))
                            _JP_SITUATION_TO_CANONICAL_ID[clean] = str(r[0])
                if _JP_SITUATION_TO_CANONICAL_ID:
                    break
                else:
                    logger.warning("JP situation mapping cache empty for %s", norm_p)
            except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                logger.warning("Failed to load JP situation mapping from %s: %s", norm_p, exc)
    if not _JP_SITUATION_TO_CANONICAL_ID:
        logger.warning("JP situation mapping cache could not be populated")
    return _JP_SITUATION_TO_CANONICAL_ID


def fetch_dear_story_detail_fallback_titles_batch(
    db_info: dict[str, Any],
    meta_dict: dict[str, tuple[str | None, str | None]]
) -> dict[str, str]:
    """복각/신규 이벤트 재활용 6xxxxxx 신뢰도 에피소드 대상 교차 매핑 및 공식 타이틀 반환.

    voice_adv_id(내부 음성 번호) 또는 situation(상황 대사) 기반으로
    dear_story_detail 테이블과 교차 매핑하여 공식 타이틀 반환.

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
        tbl = _validate_identifier(db_info['dear_story_detail_table'])
        col_id = _validate_identifier(db_info['dear_story_detail_id_col'])
        col_title = _validate_identifier(db_info['dear_story_detail_title_col'])
        col_sub = _validate_identifier(db_info['dear_story_detail_sub_title_col'])

        jp_sit_map = _get_jp_situation_to_canonical_id()

        voice_ids = []
        sit_norms = []
        canonical_ids = []
        for aid, (vo_id, situation) in meta_dict.items():
            if vo_id:
                voice_ids.append(str(vo_id))
            if situation:
                clean_sit = re.sub(r'\s+', '', situation)
                sit_norms.append(clean_sit)
                if clean_sit in jp_sit_map:
                    canonical_ids.append(str(jp_sit_map[clean_sit]))

        candidate_ids = list(dict.fromkeys(voice_ids + canonical_ids))
        sit_norms_unique = list(dict.fromkeys([s for s in sit_norms if s]))

        norm_col = f'"{col_sub}"'
        norm_expr = (
            f"replace(replace(replace(replace(replace(replace({norm_col}, '\\n', ' '), char(9), ''), char(10), ''), char(11), ''), char(12), ''), char(13), ''), ' ', '')"
        )

        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()
            id_to_title = {}
            sub_to_title = {}

            for i in range(0, len(candidate_ids), 500):
                chunk = candidate_ids[i:i + 500]
                if not chunk:
                    continue
                placeholders = ', '.join(['?'] * len(chunk))
                cursor.execute(
                    f'SELECT "{col_id}", "{col_title}", "{col_sub}" FROM "{tbl}" WHERE "{col_id}" IN ({placeholders})',
                    chunk,
                )
                for row in cursor.fetchall():
                    sid = str(row[0]) if row[0] is not None else ''
                    t = _clean_title_text(row[1])
                    sub = _clean_title_text(row[2])
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

            for i in range(0, len(sit_norms_unique), 500):
                chunk = sit_norms_unique[i:i + 500]
                if not chunk:
                    continue
                placeholders = ', '.join(['?'] * len(chunk))
                cursor.execute(
                    f'SELECT "{col_id}", "{col_title}", "{col_sub}" FROM "{tbl}" WHERE {norm_expr} IN ({placeholders})',
                    chunk,
                )
                for row in cursor.fetchall():
                    sid = str(row[0]) if row[0] is not None else ''
                    t = _clean_title_text(row[1])
                    sub = _clean_title_text(row[2])
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

            for aid, (vo_id, situation) in meta_dict.items():
                if vo_id and str(vo_id) in id_to_title:
                    result_map[aid] = id_to_title[str(vo_id)]
                elif situation:
                    clean_sit = re.sub(r'\s+', '', situation)
                    if clean_sit in sub_to_title:
                        result_map[aid] = sub_to_title[clean_sit]
                    elif clean_sit in jp_sit_map:
                        canonical_id = jp_sit_map[clean_sit]
                        if str(canonical_id) in id_to_title:
                            result_map[aid] = id_to_title[str(canonical_id)]
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_dear_story_detail_fallback_titles_batch failed: %s", exc)

    return result_map



def fetch_tower_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 tower_story_detail 테이블 대상 title 및 sub_title 일괄 조회.

    조회 결과는 'title - sub_title' 형식으로 매핑.

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
        with _readonly_connection(db_path) as conn:
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
                    t = _clean_title_text(row[1])
                    sub = _clean_title_text(row[2])

                    if t and sub:
                        formatted = f"{t} - {sub}"
                    elif t:
                        formatted = t
                    elif sub:
                        formatted = sub
                    else:
                        continue
                    result_map[story_id] = formatted
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_tower_story_detail_titles_batch failed: %s", exc)

    return result_map


def fetch_alchemy_story_detail_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 alchemy_story_detail 테이블 대상 title 일괄 조회.

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
        with _readonly_connection(db_path) as conn:
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
                    t = _clean_title_text(row[1])
                    if t:
                        result_map[story_id] = t
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_alchemy_story_detail_titles_batch failed: %s", exc)

    return result_map


def _format_sekai_time_range(time_from_str: str, time_to_str: str) -> str:
    """DB 타임스탬프 문자열 대상 '09:00~12:00' 포맷 변환.

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
    except (ValueError, TypeError, IndexError):
        t1 = time_from_str.split()[-1][:5] if ' ' in time_from_str else time_from_str
        t2 = time_to_str.split()[-1][:5] if ' ' in time_to_str else time_to_str
        return f"{t1}~{t2}"


def fetch_sekai_story_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 sekai_top_data 및 sekai_top_story_data 테이블 대상 순수 DB 데이터(이벤트명, MODE, 시간대, HP 0) 조회 및 타이틀 일괄 생성.

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
        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()

            tbl_top = _validate_identifier(top_tbl_name)
            col_id = _validate_identifier(db_info.get('sekai_top_data_id_col', 'story_id'))
            col_name = _validate_identifier(db_info.get('sekai_top_data_name_col', 'name'))
            col_mode = _validate_identifier(db_info.get('sekai_top_data_boss_mode_col', 'boss_mode'))
            col_time_from = _validate_identifier(db_info.get('sekai_top_data_boss_time_from_col', 'boss_time_from'))
            col_hp_from = _validate_identifier(db_info.get('sekai_top_data_boss_hp_from_col', 'boss_hp_from'))

            # 1. sekai_top_data 테이블 조회
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

            # 기본 이벤트명 누락 시 default_event_name 보충 채우기
            if not default_event_name:
                cursor.execute(f'SELECT "{col_name}" FROM "{tbl_top}" WHERE "{col_id}" = 4004101 LIMIT 1')
                row = cursor.fetchone()
                if row and row[0]:
                    default_event_name = str(row[0]).strip()

            # 2. sekai_top_story_data 테이블 조회 (4004105~4004108 등 시나리오 보스 전용)
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

    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_sekai_story_titles_batch failed: %s", exc)

    return result_map


def fetch_event_top_adv_titles_batch(
    db_info: dict[str, Any],
    adv_ids: list[str],
    meta_dict: dict[str, tuple[str | None, str | None]] | None = None,
) -> dict[str, str]:
    """adv_id 목록 기반 event_top_adv, unit_data, event_story_data 조회 및 '[이벤트명] 캐릭터명 - 부제목' 타이틀 일괄 생성.

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
        with _readonly_connection(db_path) as conn:
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

            # 보이스 ID(voice_adv_id) 기반 파일명 매핑 (5152403 -> 5094403 등 타 ID 매핑)
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

                # 1. event_top_adv에서 대상 스토리 매핑
                query = f'SELECT "{col_top_id}", "{col_top_chara}", "{col_top_event}" FROM "{tbl_top}" WHERE "{col_top_id}" IN ({placeholders})'
                cursor.execute(query, chunk)
                rows = cursor.fetchall()
                if not rows:
                    continue

                # 2. 캐릭터 ID, 이벤트 ID 기반 매핑
                chara_ids = list({r[1] for r in rows if r[1] is not None})
                event_ids = list({r[2] for r in rows if r[2] is not None})
                group_ids = list({
                    int(r[0]) // 1000
                    for r in rows
                    if r[0] is not None and str(r[0]).isascii() and str(r[0]).isdigit()
                })

                # 캐릭터 기본 정보 조회
                unit_map = {}
                if chara_ids:
                    u_holders = ', '.join(['?'] * len(chara_ids))
                    cursor.execute(f'SELECT "{col_unit_id}", "{col_unit_name}" FROM "{tbl_unit}" WHERE "{col_unit_id}" IN ({u_holders})', chara_ids)
                    for r in cursor.fetchall():
                        if r[0] is not None and r[1] is not None:
                            unit_map[r[0]] = str(r[1]).strip()

                    # 베이스(base) 캐릭터 ID(01) 이름 매핑 (ex: 104001 -> 페코린느)
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

                # 이벤트 스토리 조회 (story_group_id 기반)
                event_map_by_grp = {}
                event_map_by_val = {}

                # 이벤트 스토리(event_story_data) 컬럼 정보 조회
                has_value_col = False
                try:
                    cursor.execute(f'PRAGMA table_info("{tbl_event}")')
                    cols = [c[1] for c in cursor.fetchall()]
                    has_value_col = 'value' in cols
                except sqlite3.Error as exc:
                    logger.debug("fetch_event_top_adv_titles_batch failed: %s", exc)

                target_grps = list(set(group_ids))
                if target_grps:
                    e_holders = ', '.join(['?'] * len(target_grps))
                    if has_value_col:
                        cursor.execute(f'SELECT "{col_event_group}", "value", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_group}" IN ({e_holders})', target_grps)
                        for r in cursor.fetchall():
                            if r[0] is not None and r[2] is not None:
                                t_clean = _clean_title_text(r[2])
                                event_map_by_grp[r[0]] = t_clean
                                if r[1] is not None:
                                    event_map_by_val[r[1]] = t_clean
                    else:
                        cursor.execute(f'SELECT "{col_event_group}", "{col_event_title}" FROM "{tbl_event}" WHERE "{col_event_group}" IN ({e_holders})', target_grps)
                        for r in cursor.fetchall():
                            if r[0] is not None and r[1] is not None:
                                t_clean = _clean_title_text(r[1])
                                event_map_by_grp[r[0]] = t_clean

                # 이벤트 ID(event_id) 기반 이벤트 타이틀 조회
                target_ev_ids = [eid for eid in event_ids if eid not in event_map_by_val]
                if has_value_col and target_ev_ids:
                    ev_holders = ', '.join(['?'] * len(target_ev_ids))
                    cursor.execute(f'SELECT "{col_event_group}", "value", "{col_event_title}" FROM "{tbl_event}" WHERE "value" IN ({ev_holders})', target_ev_ids)
                    for r in cursor.fetchall():
                        if r[2] is not None:
                            t_clean = _clean_title_text(r[2])
                            if r[0] is not None:
                                event_map_by_grp[r[0]] = t_clean
                            if r[1] is not None:
                                event_map_by_val[r[1]] = t_clean

                # 3. 기타 데이터 조회
                for r in rows:
                    sid_raw = r[0]
                    sid_str = str(sid_raw)
                    cid = r[1]
                    ev_id = r[2]

                    chara_name = unit_map.get(cid, "")
                    grp_id = int(sid_raw) // 1000 if sid_str.isascii() and sid_str.isdigit() else 0
                    event_title = event_map_by_val.get(ev_id) or event_map_by_grp.get(grp_id) or ""

                    # 이벤트 스토리 상세 조회
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
    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_event_top_adv_titles_batch failed: %s", exc)

    return result_map


def fetch_event_boss_battle_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 hatsune_boss, hatsune_special_battle, event_story_data 대상 이벤트 보스전/배틀 타이틀 일괄 조회.

    대사 없는 단순 영상/오디오 재생 파일은 매핑하지 않고 원본명 유지.

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
        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()

            # 이벤트 보스 배틀 스토리 조회
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
                            event_map[r[0]] = _clean_title_text(r[1])

            # 1. hatsune_boss 테이블 조회
            tbl_hb = db_info.get('hatsune_boss_table')
            if tbl_hb:
                tbl_hb_v = _validate_identifier(tbl_hb)
                col_qname = _validate_identifier(db_info.get('hatsune_boss_quest_name_col', 'quest_name'))
                col_ws = _validate_identifier(db_info.get('hatsune_boss_wavestart_col', 'story_id_wavestart_1'))
                col_we = _validate_identifier(db_info.get('hatsune_boss_waveend_col', 'story_id_waveend_1'))

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'SELECT "{col_ws}", "{col_qname}" FROM "{tbl_hb_v}" WHERE "{col_ws}" IN ({_ph})', _chunk)
                    for sid, qname in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_title = event_map.get(int(sid) // 1000, "")
                            q_clean = str(qname).strip() if qname else ""
                            if q_clean:
                                result_map[sid_str] = f"[{ev_title}] {q_clean} (wavestart)" if ev_title else f"{q_clean} (wavestart)"

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'SELECT "{col_we}", "{col_qname}" FROM "{tbl_hb_v}" WHERE "{col_we}" IN ({_ph})', _chunk)
                    for sid, qname in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_title = event_map.get(int(sid) // 1000, "")
                            q_clean = str(qname).strip() if qname else ""
                            if q_clean:
                                result_map[sid_str] = f"[{ev_title}] {q_clean} (waveend)" if ev_title else f"{q_clean} (waveend)"

            # 2. hatsune_special_battle 테이블 조회
            tbl_hsb = db_info.get('hatsune_special_battle_table')
            if tbl_hsb:
                tbl_hsb_v = _validate_identifier(tbl_hsb)
                col_mode = _validate_identifier(db_info.get('hatsune_special_battle_mode_col', 'mode'))
                col_ms = _validate_identifier(db_info.get('hatsune_special_battle_mode_start_col', 'story_id_mode_start'))
                col_me = _validate_identifier(db_info.get('hatsune_special_battle_mode_end_col', 'story_id_mode_end'))

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'SELECT "{col_ms}", "{col_mode}" FROM "{tbl_hsb_v}" WHERE "{col_ms}" IN ({_ph})', _chunk)
                    for sid, mode in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_title = event_map.get(int(sid) // 1000, "")
                            m_str = f"SPECIAL MODE {mode} (mode_start)"
                            result_map[sid_str] = f"[{ev_title}] {m_str}" if ev_title else m_str

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'SELECT "{col_me}", "{col_mode}" FROM "{tbl_hsb_v}" WHERE "{col_me}" IN ({_ph})', _chunk)
                    for sid, mode in cursor.fetchall():
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_title = event_map.get(int(sid) // 1000, "")
                            m_str = f"SPECIAL MODE {mode} (mode_end)"
                            result_map[sid_str] = f"[{ev_title}] {m_str}" if ev_title else m_str

    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_event_boss_battle_titles_batch failed: %s", exc)

    return result_map


def fetch_event_minigame_and_sub_scenes_batch(
    db_info: dict[str, Any],
    adv_ids: list[str],
    speaker_map: dict[str, str | None] | None = None,
    raw_titles_map: dict[str, str] | None = None,
    situation_map: dict[str, str | None] | None = None
) -> dict[str, str]:
    """adv_id 목록 기반 이벤트/아케이드 미니게임, 신규 보스/SP/EX 배틀 연출, 요리 리액션 및 이벤트 가이드 타이틀 일괄 조회.

    Args:
        db_info (dict): 서버별 DB 정보 딕셔너리.
        adv_ids (list[str]): 검색할 adv_id 문자열 리스트.
        speaker_map (dict, optional): adv_id->화자명 매핑 딕셔너리.
        raw_titles_map (dict, optional): adv_id->JSON Frame 0 원본 타이틀 매핑 딕셔너리.
        situation_map (dict, optional): adv_id->situation 매핑 딕셔너리.

    Returns:
        dict[str, str]: adv_id를 키로, 공식 이벤트명과 결합된 타이틀을 값으로 갖는 딕셔너리.
    """
    db_path = _get_db_path(db_info).replace('\\', '/')
    if not os.path.exists(db_path) or not adv_ids:
        return {}

    adv_set = set(adv_ids)
    result_map = {}
    try:
        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()

            # 1. 이벤트 서브스토리 조회
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
                                event_map[r[0]] = _clean_title_text(r[1])
            except (sqlite3.Error, UnsafeIdentifierError) as exc:
                logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

            # 베이스라인 default(10052900) 이벤트 매핑
            p_base = _get_baseline_db_path(db_info, 'default')
            if p_base and os.path.exists(p_base):
                norm_base = p_base.replace('\\', '/')
                with (
                    contextlib.suppress(sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError),
                    _readonly_connection(norm_base) as conn_b,
                ):
                    cur_b = conn_b.cursor()
                    _rows_b = []
                    for _c in range(0, len(grp_ids), 500):
                        _grp_chunk = grp_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _grp_chunk)
                        cur_b.execute(f'SELECT story_group_id, title FROM event_story_data WHERE story_group_id IN ({_ph})', _grp_chunk)
                        _rows_b.extend(cur_b.fetchall())
                    for r in _rows_b:
                        if r[0] is not None and r[1] is not None and r[0] not in event_map:
                            event_map[r[0]] = _clean_title_text(r[1])

            # 베이스라인 10067600 이벤트 매핑 (비스트로 이벤트)
            cooking_pairs = {}
            v2_titles = {}
            mypage_names = {}
            story_to_mypage = {}

            p_676 = _get_baseline_db_path(db_info, '10067600')
            v2_table = 'v1_5dc6443a480cd7e8a680f6904c9125ceba8a8b571beaf0f7c6c8b2788f4dc2eb'
            _validate_identifier(v2_table)
            if p_676 and os.path.exists(p_676):
                norm_676 = p_676.replace('\\', '/')
                try:
                    with _readonly_connection(norm_676) as conn_676:
                        cur_676 = conn_676.cursor()
                        cur_676.execute(f'SELECT [bc69627001b433fade0a20e641d68ecd7f8b1e8b66370f29099c48ecc3c65afc], [c6064be3e0ab536646b7ce09315a0bda7958e82c6da3194472c2431345a34c35] FROM "{v2_table}"')
                        for ev_id, full_t in cur_676.fetchall():
                            grp = ev_id % 10000 if ev_id > 10000 else ev_id
                            if grp not in event_map:
                                t_str = str(full_t).replace(' オープニング', '').replace('オープニング', '')
                                clean_t = _clean_title_text(t_str)
                                event_map[grp] = clean_t
                                event_map[ev_id] = clean_t
                                if grp < 1000:
                                    event_map[5000 + grp] = clean_t

                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cur_676.execute(f'''
                                SELECT f.[dc74953d7740483e43b6386653875c77e21540cc26cd8a3f0e802b57e7268baa], s.[f12d807789adeed6bccdb807e76bac3d299582a4a1ebed1caa5fdb045499a84d]
                                FROM (SELECT * FROM v1_9f485b9b32e33f9d26dc0b0d907ef5dc93bb41f5f0dcd20fd8fa0ed703cac974 WHERE [dd05c32b741bbc005e7e29fdf97d4617786274bdec22143e69dae4c1c38c848d] = 3 AND [dc74953d7740483e43b6386653875c77e21540cc26cd8a3f0e802b57e7268baa] IN ({_ph})) f
                                JOIN (SELECT * FROM v1_9f485b9b32e33f9d26dc0b0d907ef5dc93bb41f5f0dcd20fd8fa0ed703cac974 WHERE [dd05c32b741bbc005e7e29fdf97d4617786274bdec22143e69dae4c1c38c848d] = 2) s
                                ON f.[f12d807789adeed6bccdb807e76bac3d299582a4a1ebed1caa5fdb045499a84d] = s.[dc74953d7740483e43b6386653875c77e21540cc26cd8a3f0e802b57e7268baa]
                            ''', _chunk)
                            for r in cur_676.fetchall():
                                cooking_pairs[str(r[0])] = str(r[1])

                        succ_ids = list({str(v) for v in cooking_pairs.values() if v})
                        for i in range(0, len(succ_ids), 500):
                            _chunk = succ_ids[i:i + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cur_676.execute(f'SELECT [5b802c21ec8ff3e0285a4aae847211dc5d0c1251fb2a070436b7bc86e1699985], [c6064be3e0ab536646b7ce09315a0bda7958e82c6da3194472c2431345a34c35] FROM "{v2_table}" WHERE [5b802c21ec8ff3e0285a4aae847211dc5d0c1251fb2a070436b7bc86e1699985] IN ({_ph})', _chunk)
                            for sid, sub in cur_676.fetchall():
                                v2_titles[str(sid)] = _clean_title_text(sub)

                        # 마이페이지 매핑 (story_to_mypage: map story_id -> mypage id)
                        if succ_ids:
                            cols = [c[1] for c in cur_676.execute(f'PRAGMA table_info("{v2_table}")').fetchall()]
                            if len(cols) > 19:
                                try:
                                    col_story = _validate_identifier(cols[13])
                                    col_mp = _validate_identifier(cols[19])
                                    for i in range(0, len(succ_ids), 500):
                                        _chunk = succ_ids[i:i + 500]
                                        _ph = ', '.join('?' for _ in _chunk)
                                        cur_676.execute(f'SELECT "{col_story}", "{col_mp}" FROM "{v2_table}" WHERE "{col_story}" IN ({_ph})', _chunk)
                                        for r in cur_676.fetchall():
                                            if r[0] is not None and r[1] is not None:
                                                story_to_mypage[str(r[0])] = r[1]
                                except (UnsafeIdentifierError, sqlite3.Error) as exc:
                                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

                        mypage_table = 'v1_e249e1c41d6767271e5bc0df243fe5f0de2eff1e70cb2e5c501318ef33f59f64'
                        _validate_identifier(mypage_table)
                        # 필요 마이페이지 ID 필터링 (mypage_names: filter by needed mp_ids)
                        mp_ids = list({str(v) for v in story_to_mypage.values() if v is not None})
                        if mp_ids:
                            for i in range(0, len(mp_ids), 500):
                                _chunk = mp_ids[i:i + 500]
                                _ph = ', '.join('?' for _ in _chunk)
                                cur_676.execute(f'SELECT [c7b81a6de35976d0586d541b42f0a6249219165076d2d550b908f3a0b2a5f689], [8f2a28a54d18237e54de33e65d39bb4f5328a1b2a505c770aebc27fb157dd474] FROM "{mypage_table}" WHERE [c7b81a6de35976d0586d541b42f0a6249219165076d2d550b908f3a0b2a5f689] IN ({_ph})', _chunk)
                                for mp_id, mp_name in cur_676.fetchall():
                                    mypage_names[mp_id] = _clean_title_text(mp_name)
                except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    logger.debug("Failed to load mypage story mapping: %s", exc)

            def get_ev_prefix(aid_int: int) -> str:
                ev = event_map.get(aid_int // 1000, "")
                return f"[{ev}] " if ev else ""

            # 1-1. 미니게임 아케이드 스토리 매핑 (arcade_story_list & arcade_list, baseline default)
            p_base_arc = _get_baseline_db_path(db_info, 'default')
            if p_base_arc and os.path.exists(p_base_arc):
                norm_base_arc = p_base_arc.replace('\\', '/')
                try:
                    with _readonly_connection(norm_base_arc) as conn_arc:
                        cur_arc = conn_arc.cursor()
                        arc_map = {}
                        cur_arc.execute('PRAGMA table_info("arcade_list")')
                        cols_arc = [c[1] for c in cur_arc.fetchall()]
                        t_col = "title" if "title" in cols_arc else ("clan_chat_title" if "clan_chat_title" in cols_arc else "")
                        cur_arc.execute(f'SELECT arcade_id, "{t_col}" FROM arcade_list')
                        for aid_arc, raw_t in cur_arc.fetchall():
                            clean_t = _clean_title_text(raw_t)
                            if clean_t:
                                arc_map[aid_arc] = clean_t

                        _rows_arc = []
                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cur_arc.execute(f'SELECT story_id, arcade_id, sub_title FROM arcade_story_list WHERE story_id IN ({_ph})', _chunk)
                            _rows_arc.extend(cur_arc.fetchall())
                        for sid, aid_arc, sub_t in _rows_arc:
                            sid_str = str(sid)
                            if sid_str in adv_set and sid_str not in result_map:
                                sub_clean = _clean_title_text(sub_t)
                                arc_name = arc_map.get(aid_arc, "")
                                if sid_str.startswith('5') and len(sid_str) == 7:
                                    ev_p = get_ev_prefix(int(sid))
                                    prefix = ev_p if ev_p else (f"[{arc_name}] " if arc_name else "")
                                    result_map[sid_str] = f"{prefix}{sub_clean}" if sub_clean else prefix.strip()
                                else:
                                    prefix = f"[{arc_name}] " if arc_name else ""
                                    result_map[sid_str] = f"{prefix}{sub_clean}" if sub_clean else prefix.strip()
                except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    logger.debug("Failed to resolve event story title: %s", exc)

            # 2. 최신 이벤트 스토리 v2 (10201+)
            tbl_ev2 = db_info.get('event_story_v2_table')
            if tbl_ev2:
                try:
                    tbl_ev2_v = _validate_identifier(tbl_ev2)
                    col_id = _validate_identifier(db_info.get('event_story_v2_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_story_v2_title_col', 'title'))
                    col_sub = _validate_identifier(db_info.get('event_story_v2_sub_title_col', 'sub_title'))

                    _rows_ev2 = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_sub}" FROM "{tbl_ev2_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                        _rows_ev2.extend(cursor.fetchall())
                    for sid, t, sub in _rows_ev2:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = _clean_title_text(t)
                            sub_clean = _clean_title_text(sub)
                            if sub_clean and t_clean:
                                result_map[sid_str] = f"{sub_clean} - {t_clean}"
                            else:
                                val = sub_clean or t_clean
                                if val:
                                    result_map[sid_str] = val
                except (sqlite3.Error, UnsafeIdentifierError) as exc:
                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

            # 3. 이벤트 상세 / 서브스토리 조회 (event_details_table)
            tbl_ev_det = db_info.get('event_details_table')
            if tbl_ev_det:
                try:
                    tbl_ev_det_v = _validate_identifier(tbl_ev_det)
                    col_id = _validate_identifier(db_info.get('event_id_col_details', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_info_col_details', 'sub_title'))
                    col_title_det = db_info.get('event_title_col_details')

                    if col_title_det:
                        col_title_det_v = _validate_identifier(col_title_det)
                        _rows_det = []
                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_title_det_v}" FROM "{tbl_ev_det_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                            _rows_det.extend(cursor.fetchall())
                        for sid, sub, t in _rows_det:
                            sid_str = str(sid)
                            if sid_str in adv_ids and sid_str not in result_map:
                                t_clean = _clean_title_text(t)
                                sub_clean = _clean_title_text(sub)
                                if sub_clean and t_clean:
                                    result_map[sid_str] = f"{sub_clean} - {t_clean}"
                                else:
                                    ev_p = get_ev_prefix(int(sid))
                                    val = sub_clean or t_clean
                                    if val:
                                        result_map[sid_str] = f"{ev_p}{val}"
                    else:
                        _rows_det2 = []
                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cursor.execute(f'SELECT "{col_id}", "{col_t}" FROM "{tbl_ev_det_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                            _rows_det2.extend(cursor.fetchall())
                        for sid, sub in _rows_det2:
                            sid_str = str(sid)
                            if sid_str in adv_ids and sid_str not in result_map:
                                sub_clean = _clean_title_text(sub)
                                if sub_clean:
                                    ev_p = get_ev_prefix(int(sid))
                                    result_map[sid_str] = f"{ev_p}{sub_clean}"
                except (sqlite3.Error, UnsafeIdentifierError) as exc:
                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

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

                    _rows_sb_ws = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_ws}", "{col_qn}" FROM "{tbl_sb_v}" WHERE "{col_ws}" IN ({_ph})', _chunk)
                        _rows_sb_ws.extend(cursor.fetchall())
                    for sid, qn in _rows_sb_ws:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            q_clean = str(qn).strip() if qn else ""
                            if q_clean:
                                result_map[sid_str] = f"{ev_p}{q_clean} (wavestart)"

                    _rows_sb_we = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_we}", "{col_qn}" FROM "{tbl_sb_v}" WHERE "{col_we}" IN ({_ph})', _chunk)
                        _rows_sb_we.extend(cursor.fetchall())
                    for sid, qn in _rows_sb_we:
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

                    _rows_sp_ms = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_ms}", "{col_mode}" FROM "{tbl_sp_v}" WHERE "{col_ms}" IN ({_ph})', _chunk)
                        _rows_sp_ms.extend(cursor.fetchall())
                    for sid, mode in _rows_sp_ms:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            result_map[sid_str] = f"{ev_p}SPECIAL MODE {mode} (mode_start)"

                    _rows_sp_me = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_me}", "{col_mode}" FROM "{tbl_sp_v}" WHERE "{col_me}" IN ({_ph})', _chunk)
                        _rows_sp_me.extend(cursor.fetchall())
                    for sid, mode in _rows_sp_me:
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

                    _rows_ex = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_id}" FROM "{tbl_ex_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                        _rows_ex.extend(cursor.fetchall())
                    for sid, in _rows_ex:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            ev_p = get_ev_prefix(int(sid))
                            result_map[sid_str] = f"{ev_p}EX (ex_battle)"
                except (sqlite3.Error, UnsafeIdentifierError) as exc:
                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

            # 7. 요리 교실 미니게임 (event_cooking_minigame)
            tbl_cook = db_info.get('event_cooking_minigame_table')
            if tbl_cook:
                try:
                    tbl_cook_v = _validate_identifier(tbl_cook)
                    col_id = _validate_identifier(db_info.get('event_cooking_minigame_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_cooking_minigame_title_col', 'title'))

                    _rows_cook = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_id}", "{col_t}" FROM "{tbl_cook_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                        _rows_cook.extend(cursor.fetchall())
                    for sid, t in _rows_cook:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = _clean_title_text(t)
                            if t_clean:
                                ev_p = get_ev_prefix(int(sid))
                                result_map[sid_str] = f"{ev_p}{t_clean}"
                except (sqlite3.Error, UnsafeIdentifierError) as exc:
                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

            # 8. 몬스터 박물관 미니게임 (event_museum_minigame)
            tbl_mus = db_info.get('event_museum_minigame_table')
            if tbl_mus:
                try:
                    tbl_mus_v = _validate_identifier(tbl_mus)
                    col_id = _validate_identifier(db_info.get('event_museum_minigame_id_col', 'story_id'))
                    col_t = _validate_identifier(db_info.get('event_museum_minigame_title_col', 'title'))
                    col_sub = _validate_identifier(db_info.get('event_museum_minigame_sub_title_col', 'sub_title'))

                    _rows_mus = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_id}", "{col_t}", "{col_sub}" FROM "{tbl_mus_v}" WHERE "{col_id}" IN ({_ph})', _chunk)
                        _rows_mus.extend(cursor.fetchall())
                    for sid, t, sub in _rows_mus:
                        sid_str = str(sid)
                        if sid_str in adv_ids and sid_str not in result_map:
                            t_clean = _clean_title_text(t)
                            sub_clean = _clean_title_text(sub)
                            full_t = f"{t_clean} ({sub_clean})" if (t_clean and sub_clean) else (t_clean or sub_clean)
                            if full_t:
                                ev_p = get_ev_prefix(int(sid))
                                result_map[sid_str] = f"{ev_p}{full_t}"
                except (sqlite3.Error, UnsafeIdentifierError) as exc:
                    logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

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
                    _rows_rid = []
                    for _c in range(0, len(adv_ids), 500):
                        _chunk = adv_ids[_c:_c + 500]
                        _ph = ', '.join('?' for _ in _chunk)
                        cursor.execute(f'SELECT "{col_s1}", "{col_s2}", "{col_pt}", "{col_ti}" FROM "{r_tbl_v}" WHERE "{col_s1}" IN ({_ph}) OR "{col_s2}" IN ({_ph})', _chunk + _chunk)
                        _rows_rid.extend(cursor.fetchall())
                    for s1, s2, pt, ti in _rows_rid:
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
                clean = _clean_title_text(s)
                if len(clean) > 60 or clean.isdigit() or re.match(r'^\d{4}/\d{2}/\d{2}', clean):
                    return ""
                return clean

            generic_minigame_tables = [
                'event_secret_minigame', 'event_collab_minigame', 'event_vampire_minigame',
                'event_crybaby_minigame', 'event_summer_minigame', 'event_liberate_minigame',
                'event_hatsune_dream_minigame', 'event_christmas_minigame', 'event_coaster_minigame',
                'event_nebia_minigame', 'event_taiso_minigame', 'event_alces_minigame',
                'event_trip_minigame', 'event_house_minigame', 'event_diary_minigame',
                'event_opening_adv', 'event_boss_battle_v3',
                'event_remember_story', 'hatsune_present', 'hatsune_quest',
                'arcade_story'
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
                        _rows_gen_sub = []
                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cursor.execute(f'SELECT "{id_col}", "{title_col}", "{sub_col_v}" FROM "{tbl_name_v}" WHERE "{id_col}" IN ({_ph})', _chunk)
                            _rows_gen_sub.extend(cursor.fetchall())
                        for sid, t, sub in _rows_gen_sub:
                            sid_str = str(sid)
                            if sid_str in adv_set and sid_str not in result_map:
                                t_c = _clean_title_text(t)
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
                        _rows_gen_nosub = []
                        for _c in range(0, len(adv_ids), 500):
                            _chunk = adv_ids[_c:_c + 500]
                            _ph = ', '.join('?' for _ in _chunk)
                            cursor.execute(f'SELECT "{id_col}", "{title_col}" FROM "{tbl_name_v}" WHERE "{id_col}" IN ({_ph})', _chunk)
                            _rows_gen_nosub.extend(cursor.fetchall())
                        for sid, t in _rows_gen_nosub:
                            sid_str = str(sid)
                            if sid_str in adv_set and sid_str not in result_map:
                                t_c = _clean_title_text(t)
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

            # 11. 미니게임 리액션, JSON 원본 타이틀 및 이벤트 가이드 매핑
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

                # B. 이벤트 스토리 / 미니게임 원본 타이틀 복원 (프레임 0 또는 raw_t 기반 매핑)
                ev_name = ""
                if aid.isdigit() and len(aid) == 7 and aid.startswith('5'):
                    ev_name = event_map.get(int(aid) // 1000, "")
                    if ev_name:
                        ev_name = re.sub(r'\s+', ' ', str(ev_name)).strip()

                sit = (situation_map.get(aid, "") if situation_map else "") or ""
                spk = (speaker_map.get(aid, "") if speaker_map else "") or ""
                raw_t = (raw_titles_map.get(aid, "") if raw_titles_map else "") or ""

                if sit:
                    sit = _clean_title_text(sit)
                if spk:
                    spk = _clean_title_text(spk)
                if raw_t:
                    raw_t = _clean_title_text(raw_t)

                if ev_name:
                    # 5xxxxxx 이벤트 스토리 프리뷰/예고편 판정: raw_t -> sit -> spk -> [ev_name]
                    if raw_t and not raw_t.startswith("storydata_") and not raw_t.isdigit():
                        preview_suffixes = ('次回予告', '다음 화 예고', '다음 회 예고', '다음화 예고', '다음회 예고')
                        matched_suffix = next((s for s in preview_suffixes if raw_t.endswith(s)), None)
                        if matched_suffix:
                            result_map[aid] = f"[{ev_name}] {matched_suffix}"
                        elif ev_name in raw_t:
                            rest = raw_t.replace(ev_name, '').strip()
                            result_map[aid] = f"[{ev_name}] {rest}" if rest else f"[{ev_name}]"
                        else:
                            result_map[aid] = f"[{ev_name}] {raw_t}"
                    elif sit:
                        result_map[aid] = f"[{ev_name}] {sit}"
                    elif spk:
                        result_map[aid] = f"[{ev_name}] {spk}"
                    else:
                        result_map[aid] = f"[{ev_name}]"
                else:
                    # 일반 이벤트 스토리: raw_t -> sit -> 타이틀 fallback (프레임 0 기반)
                    if raw_t and not raw_t.startswith("storydata_") and not raw_t.isdigit():
                        result_map[aid] = raw_t
                    elif sit:
                        result_map[aid] = sit

    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("fetch_event_minigame_and_sub_scenes_batch failed: %s", exc)

    return result_map


def fetch_legion_and_byway_battle_titles_batch(db_info: dict[str, Any], adv_ids: list[str]) -> dict[str, str]:
    """adv_id 목록 기반 legion_special_battle, byway_battle_quest_data, byway_quest_data 대상 왕도종말결전 및 우회로 특수전투 타이틀 일괄 조회.

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
        with _readonly_connection(db_path) as conn:
            cursor = conn.cursor()

            # 1. 왕도종말결전 (legion_special_battle)
            tbl_legion = db_info.get('legion_special_battle_table')
            if tbl_legion:
                tbl_legion_v = _validate_identifier(tbl_legion)
                col_mode = _validate_identifier(db_info.get('legion_special_battle_mode_col', 'mode'))
                col_ms = _validate_identifier(db_info.get('legion_special_battle_mode_start_col', 'story_id_mode_start'))
                col_me = _validate_identifier(db_info.get('legion_special_battle_mode_end_col', 'story_id_mode_end'))

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'SELECT "{col_mode}", "{col_ms}", "{col_me}" FROM "{tbl_legion_v}" WHERE "{col_ms}" IN ({_ph}) OR "{col_me}" IN ({_ph})', _chunk + _chunk)
                    for mode, ms, me in cursor.fetchall():
                        ms_str = str(ms)
                        me_str = str(me)
                        if ms_str != '0' and ms_str in adv_set:
                            result_map[ms_str] = f"[王都終末決戦] SPECIAL MODE {mode} (wavestart)"
                        if me_str != '0' and me_str in adv_set:
                            result_map[me_str] = f"[王都終末決戦] SPECIAL MODE {mode} (waveend)"

            # 2. 메인 퀘스트 연동 우회로 (byway_battle_quest_data + byway_quest_data)
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

                for _c in range(0, len(adv_ids), 500):
                    _chunk = adv_ids[_c:_c + 500]
                    _ph = ', '.join('?' for _ in _chunk)
                    cursor.execute(f'''
                        SELECT
                            b."{col_bb_ws}",
                            b."{col_bb_we}",
                            q."{col_bq_name}"
                        FROM "{tbl_bb_v}" b
                        JOIN "{tbl_bq_v}" q ON b."{col_bb_qid}" = q."{col_bq_qid}"
                        WHERE (b."{col_bb_ws}" != 0 OR b."{col_bb_we}" != 0)
                          AND (b."{col_bb_ws}" IN ({_ph}) OR b."{col_bb_we}" IN ({_ph}))
                    ''', _chunk + _chunk)
                    for ws, we, qname in cursor.fetchall():
                        q_clean = str(qname).strip() if qname else ""
                        ws_str = str(ws)
                        we_str = str(we)
                        if ws_str != '0' and ws_str in adv_set:
                            result_map[ws_str] = f"{q_clean} (wavestart)"
                        if we_str != '0' and we_str in adv_set:
                            result_map[we_str] = f"{q_clean} (waveend)"

            # 3. 왕도종말결전 보스 (sre_boss_data) 및 우회로 상세 타이틀 (byway_story_detail) - baseline fallback
            rem_ids = [aid for aid in adv_ids if aid not in result_map]
            if rem_ids:
                p_base = _get_baseline_db_path(db_info, 'default')
                if p_base and os.path.exists(p_base):
                    norm_base = p_base.replace('\\', '/')
                    try:
                        with _readonly_connection(norm_base) as conn_b:
                            cur_b = conn_b.cursor()
                            # 우회로 상세 타이틀 조회 (byway_story_detail)
                            for i in range(0, len(rem_ids), 500):
                                chunk = rem_ids[i:i + 500]
                                placeholders = ', '.join(['?'] * len(chunk))
                                cur_b.execute(f'SELECT story_id, title, sub_title FROM byway_story_detail WHERE story_id IN ({placeholders})', chunk)
                                for sid, t, sub in cur_b.fetchall():
                                    sid_str = str(sid)
                                    t_c = _clean_title_text(t)
                                    s_c = _clean_title_text(sub)
                                    if t_c and s_c:
                                        result_map[sid_str] = f"{t_c} - {s_c}"
                                    elif t_c:
                                        result_map[sid_str] = t_c
                                    elif s_c:
                                        result_map[sid_str] = s_c

                            # 왕도종말결전 보스 조회 (sre_boss_data)
                            for _col in ('battle_start_story_id', 'battle_finish_story_id', 'disappearance_story_id'):
                                for i in range(0, len(rem_ids), 500):
                                    chunk = rem_ids[i:i + 500]
                                    placeholders = ', '.join('?' for _ in chunk)
                                    cur_b.execute(f'SELECT battle_start_story_id, battle_finish_story_id, disappearance_story_id, name FROM sre_boss_data WHERE {_col} IN ({placeholders})', chunk)
                                    for r in cur_b.fetchall():
                                        nm = str(r[3]).strip() if r[3] else ""
                                        if not nm:
                                            continue
                                        for sid in [r[0], r[1], r[2]]:
                                            sid_str = str(sid) if sid else ""
                                            if sid_str and sid_str in adv_set and sid_str not in result_map:
                                                result_map[sid_str] = nm
                    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                        logger.debug("Failed to map adv story names: %s", exc)

    except (sqlite3.Error, KeyError, UnsafeIdentifierError) as exc:
        logger.debug("DB helper operation failed: %s", exc)

    return result_map
