"""Story Viewer 마스터 DB 역난독화 결과 캐시.

`resolve_all_servers_parallel`은 매 기동마다 대상 DB와 베이스라인 DB의 구조를
비교해 난독화 테이블명을 역추적한다(실측 약 11초). 본 모듈은 그 **작업 단위 결과**를
`src/schema_cache.json`에 저장해, 입력이 동일하면 재계산 없이 재사용한다.

파일에는 사람이 확인할 수 있도록 다음 정보도 함께 기록한다(판정에는 사용하지 않음):
- `saved_at`: 마지막 저장 시각.
- `db_versions`: `version.json`의 서버별 DB 버전.
- 각 항목의 `target_db` / `baseline_db`: 비교에 사용한 DB 파일 경로(상대 경로).

무효화 조건(하나라도 다르면 재계산):
1. 대상 DB / 베이스라인 DB의 (수정시각, 크기) 서명 변경.
2. 베이스라인 테이블명(config 값) 변경.
3. 캐시된 결과 테이블명/컬럼명이 대상 DB에 존재하지 않음.
4. 항목 구조가 손상됨(필수 키 누락).

캐시 파일 구조가 바뀌어 형식이 맞지 않는 항목은 로드 시 자동으로 폐기되고
재계산된다. 역난독화 로직 수정으로 결과를 다시 계산해야 할 때는 파일을 삭제하면
된다(다음 실행에서 재생성).

무매칭(결과 없음)도 캐시한다 — 재계산해도 같은 결과가 나오는 탐색 비용을 제거하기 위함.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from src.story_viewer.db_helper import get_readonly_connection

logger = logging.getLogger(__name__)

# 저장 파일: src/schema_cache.json (런타임 생성, gitignore 대상)
_CACHE_FILENAME = "schema_cache.json"


def _is_valid_entry(entry: Any) -> bool:
    """캐시 항목 필수 키/타입 검증(손상된 항목은 재계산 대상으로 넘김)."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("baseline"), str)
        and isinstance(entry.get("resolved"), str)
        and isinstance(entry.get("target_sig"), list)
        and isinstance(entry.get("baseline_sig"), list)
    )


class CacheHit(NamedTuple):
    """캐시 적중 결과."""

    resolved: str  # 해석된 테이블명('' 이면 무매칭 확정)
    columns: dict[str, tuple[str, str]]  # {컬럼 키: (원본 값, 해석된 값)}


def _signature(path: str | Path) -> list[int] | None:
    """파일 (수정시각 ns, 크기) 서명. 실패 시 None."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return [stat.st_mtime_ns, stat.st_size]


class SchemaCacheManager:
    """작업 단위 역난독화 결과 캐시 조회/기록 관리자."""

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        """캐시 관리자 초기화.

        Args:
            path (Path): 캐시 파일 경로.
            data (dict[str, Any]): 캐시 딕셔너리(없으면 빈 구조).
        """
        self._path = path
        self._project_root = path.parent.parent
        self._data = data
        self._dirty = False
        self._table_names: dict[str, set[str] | None] = {}
        self._table_columns: dict[tuple[str, str], set[str] | None] = {}
        self._stale_servers: set[str] = set()

    @property
    def stale_servers(self) -> set[str]:
        """버전 불일치로 인해 캐시가 무효화되어 재분석이 필요한 서버 키 집합."""
        return self._stale_servers

    @classmethod
    def load(cls, cache_dir: str | Path) -> SchemaCacheManager:
        """캐시 파일을 로드한다(손상된 파일/항목은 재계산 대상으로 처리).

        Args:
            cache_dir (str | Path): 캐시 파일을 둘 디렉터리(앱의 src 폴더).

        Returns:
            SchemaCacheManager: 로드된 캐시 관리자.
        """
        path = Path(cache_dir) / _CACHE_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Schema cache unreadable (%s); rebuilding", exc)
            raw = {}

        if not isinstance(raw, dict):
            raw = {}
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        raw["entries"] = {
            key: entry
            for key, entry in entries.items()
            if isinstance(key, str) and _is_valid_entry(entry)
        }
        mgr = cls(path, raw)
        mgr.sync_with_version_json()
        return mgr

    def invalidate_server(self, server_key: str) -> None:
        """지정된 서버의 모든 캐시 항목을 삭제하고 재분석 대상으로 등록."""
        self._stale_servers.add(server_key)
        prefix = f"{server_key}|"
        entries = self._data.get("entries")
        if isinstance(entries, dict):
            to_delete = [k for k in list(entries.keys()) if k.startswith(prefix)]
            for k in to_delete:
                del entries[k]
        self._table_names.clear()
        self._table_columns.clear()
        self._dirty = True

    def is_server_signature_changed(self, server_key: str, target_db_path: str) -> bool:
        """대상 DB 파일의 (수정시각, 크기) 서명이 캐시와 다른지 검사."""
        sig = _signature(target_db_path)
        if sig is None:
            return False
        entries = self._data.get("entries")
        if not isinstance(entries, dict):
            return True
        prefix = f"{server_key}|"
        server_entries = [e for k, e in entries.items() if k.startswith(prefix) and isinstance(e, dict)]
        if not server_entries:
            return False
        for entry in server_entries:
            cached_sig = entry.get("target_sig")
            if cached_sig is not None:
                return bool(cached_sig != sig)
        return False

    def sync_with_version_json(self) -> set[str]:
        """`version.json`과 캐시의 `db_versions`를 비교하여 불일치 서버의 캐시를 무효화하고 즉시 갱신."""
        current_versions = self._read_db_versions()
        if not current_versions:
            return set()

        cached_versions = self._data.get("db_versions")
        if not isinstance(cached_versions, dict):
            cached_versions = {}
            self._data["db_versions"] = cached_versions

        entries = self._data.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            self._data["entries"] = entries

        for server, cur_ver in current_versions.items():
            cached_ver = cached_versions.get(server)
            if cached_ver != cur_ver:
                logger.info(
                    "Schema cache stale for server %s (cached: %s, current: %s); invalidating entries for full re-analysis",
                    server, cached_ver, cur_ver,
                )
                self.invalidate_server(server)

        return self._stale_servers

    def save(self) -> None:
        """변경이 있으면 캐시 파일을 기록한다.

        임시 파일에 먼저 기록한 뒤 `os.replace`로 안전하게 치환한다(기록 중 중단되어도
        기존 파일이 손상되지 않음). 사람이 직접 확인할 수 있도록 들여쓰기(2칸),
        키 정렬, 저장 시각, 서버별 DB 버전을 함께 기록한다.
        """
        if not self._dirty:
            return
        self._data["saved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        db_versions = self._read_db_versions()
        if db_versions:
            self._data["db_versions"] = db_versions

        temp_path = self._path.with_name(f"{self._path.name}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, self._path)
        except OSError as exc:
            logger.debug("Failed to write schema cache: %s", exc)
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_db_versions(self) -> dict[str, Any]:
        """`version.json`의 서버별 DB 버전 정보(사람용 참고 정보)."""
        try:
            raw = json.loads((self._project_root / "version.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.debug("Failed to read version.json for cache metadata: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        versions: dict[str, Any] = {}
        for server, info in raw.items():
            if isinstance(info, dict) and "version" in info:
                versions[server] = info["version"]
        return versions

    def _relative(self, path: str) -> str:
        """프로젝트 루트 기준 상대 경로(표시용, 실패 시 원본)."""
        try:
            return os.path.relpath(path, self._project_root)
        except (ValueError, OSError):
            return path

    def lookup(
        self,
        server: str,
        table_key: str,
        baseline_table: str,
        baseline_db: str,
        target_db: str,
    ) -> CacheHit | None:
        """캐시 조회.

        Args:
            server (str): 서버 키('JP', 'KR').
            table_key (str): 스키마 키(예: 'event_list_table').
            baseline_table (str): 비교 기준이 된 베이스라인 테이블명.
            baseline_db (str): 베이스라인 DB 경로.
            target_db (str): 대상(난독화) DB 경로.

        Returns:
            CacheHit | None: 적중 시 해석된 테이블명과 컬럼 매핑, 미적중 시 None.
        """
        entry = self._data["entries"].get(f"{server}|{table_key}")
        if not isinstance(entry, dict):
            return None
        if entry.get("baseline") != baseline_table:
            return None
        if entry.get("target_sig") != _signature(target_db):
            return None
        if entry.get("baseline_sig") != _signature(baseline_db):
            return None

        resolved = entry.get("resolved", "")
        if not isinstance(resolved, str):
            return None
        if not resolved:
            return CacheHit("", {})

        names = self._target_table_names(target_db)
        if names is not None and resolved not in names:
            logger.info("Schema cache stale (%s not in %s); recomputing", resolved, Path(target_db).name)
            return None

        columns: dict[str, tuple[str, str]] = {}
        raw_columns = entry.get("columns")
        if isinstance(raw_columns, dict):
            existing = self._target_table_columns(target_db, resolved)
            for col_key, pair in raw_columns.items():
                if not (isinstance(col_key, str) and isinstance(pair, (list, tuple)) and len(pair) == 2):
                    continue
                orig_value, new_value = pair
                if not (isinstance(orig_value, str) and isinstance(new_value, str)):
                    continue
                if existing is not None and new_value not in existing:
                    logger.info(
                        "Schema cache stale (%s.%s missing); recomputing", resolved, new_value
                    )
                    return None
                columns[col_key] = (orig_value, new_value)
        return CacheHit(resolved, columns)

    def record(
        self,
        server: str,
        table_key: str,
        baseline_table: str,
        baseline_db: str,
        target_db: str,
        resolved: str,
        columns: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        """계산 결과(테이블명 + 컬럼 매핑)를 캐시에 기록한다(무매칭은 빈 문자열)."""
        target_sig = _signature(target_db)
        baseline_sig = _signature(baseline_db)
        if target_sig is None or baseline_sig is None:
            return
        entry: dict[str, Any] = {
            "baseline": baseline_table,
            "resolved": resolved,
            "target_db": self._relative(target_db),
            "baseline_db": self._relative(baseline_db),
            "target_sig": target_sig,
            "baseline_sig": baseline_sig,
        }
        if columns:
            entry["columns"] = {key: [orig, new] for key, (orig, new) in columns.items()}
        self._data["entries"][f"{server}|{table_key}"] = entry
        self._dirty = True

    def _target_table_names(self, db_path: str) -> set[str] | None:
        """대상 DB의 테이블명 집합(검증용). 실패 시 None(검증 생략)."""
        cached = self._table_names.get(db_path)
        if cached is not None or db_path in self._table_names:
            return cached
        names: set[str] | None
        try:
            cursor = get_readonly_connection(db_path).cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            names = {row[0] for row in cursor.fetchall()}
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.debug("Failed to list tables of %s: %s", db_path, exc)
            names = None
        self._table_names[db_path] = names
        return names

    def _target_table_columns(self, db_path: str, table: str) -> set[str] | None:
        """대상 테이블의 컬럼명 집합(캐시된 컬럼 검증용). 실패 시 None(검증 생략)."""
        from .schema_resolver import escape_identifier

        key = (db_path, table)
        if key in self._table_columns:
            return self._table_columns[key]
        columns: set[str] | None
        try:
            cursor = get_readonly_connection(db_path).cursor()
            cursor.execute(f'PRAGMA table_info({escape_identifier(table)});')
            columns = {row[1] for row in cursor.fetchall()}
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.debug("Failed to inspect columns of %s.%s: %s", db_path, table, exc)
            columns = None
        self._table_columns[key] = columns
        return columns
