"""비정상 종료로 남은 임시 파일 추적 및 자동 정리 모듈.

정상 경로에서는 각 작업이 자신이 만든 임시 파일·폴더를 직접 제거한 뒤
레지스트리에서 해제한다. 동일 폴더에서 앱을 중복 실행할 수 있으므로
각 항목에 소유 프로세스(PID)를 함께 기록하고, 소유자가 아직 살아 있는 항목은
실행 중인 다른 인스턴스의 임시 파일로 간주하여 건드리지 않는다.
강제 종료로 남은 항목은 다음 기동 시 `sweep_stale_temp_artifacts()`가
'임시 파일 패턴'에 해당하는 경우에만 삭제한다.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.constants import LOG_DIR_NAME, TEMP_AVTMP_PREFIX, TEMP_FFMPEG_DIR_NAME, TEMP_PART_SUFFIX, TEMP_PARTIAL_SUFFIX
from src.utils.process_check import is_pid_alive

logger = logging.getLogger(__name__)

_REGISTRY_NAME = ".pending_temp.json"
_LOCK = threading.Lock()


def _registry_path() -> Path:
    from src.utils.base_path import get_application_base_path

    return get_application_base_path() / LOG_DIR_NAME / _REGISTRY_NAME


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    """지정 경로의 사이드카 파일에 OS 수준 배타 락을 건다(다중 인스턴스 보호).

    Windows는 msvcrt.locking, 그 외는 fcntl.flock을 사용한다. 락 파일 열기/획득에
    실패하면 경고 로그만 남기고 락 없이 진행한다(인프로세스 락은 별도 유지).
    """
    fd: int | None = None
    locked = False
    try:
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        except OSError as exc:
            logger.debug("Failed to open lock file %s: %s", lock_path, exc)
            yield
            return
        try:
            if os.name == 'nt':
                import msvcrt
                try:
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"\0")
                except OSError:
                    pass
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)  # type: ignore[attr-defined]
            locked = True
        except OSError as exc:
            logger.debug("Failed to acquire lock %s: %s", lock_path, exc)
        yield
    finally:
        if fd is not None:
            try:
                if locked:
                    try:
                        if os.name == 'nt':
                            import msvcrt
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
                    except OSError:
                        pass
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass


@contextmanager
def _interprocess_lock() -> Iterator[None]:
    """temp 레지스트리 파일에 대한 프로세스 간 배타 락 컨텍스트."""
    reg_path = _registry_path()
    with _file_lock(reg_path.with_name(reg_path.name + ".lock")):
        yield


def _is_temp_artifact(path: Path) -> bool:
    """삭제 허용 대상(임시 파일 및 폴더) 패턴 판정."""
    name = path.name
    if name.endswith(TEMP_PART_SUFFIX) or name.endswith(TEMP_PARTIAL_SUFFIX):
        return True
    return name.startswith(TEMP_AVTMP_PREFIX) or name == TEMP_FFMPEG_DIR_NAME


def _read_registry() -> list[dict[str, Any]]:
    """레지스트리 항목({path, pid}) 목록 반환.

    구버전(경로 문자열 목록)과 현버전(딕셔너리 목록)을 모두 읽어들이며,
    구버전 항목은 소유자를 알 수 없으므로 pid=None 으로 표기한다.

    Returns:
        list[dict[str, Any]]: {'path': str, 'pid': int | None} 형태의 항목 목록.
    """
    path = _registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.debug("Failed to read temp artifact registry: %s", exc)
        return []
    if not isinstance(data, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, str):
            entries.append({"path": item, "pid": None})
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            pid = item.get("pid")
            entries.append({"path": item["path"], "pid": pid if isinstance(pid, int) else None})
    return entries


def _write_registry(entries: list[dict[str, Any]]) -> None:
    """레지스트리를 임시 파일 경유로 원자적으로 기록.

    강제 종료/디스크 부족으로 쓰기가 중단되어도 기존 레지스트리가 잘린 JSON 으로
    대체되지 않도록 임시 파일에 쓴 뒤 교체한다.
    """
    path = _registry_path()
    if not entries:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Failed to remove temp artifact registry: %s", exc)
        return

    temp_path = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, path)
    except OSError as exc:
        logger.debug("Failed to write temp artifact registry: %s", exc)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def register_temp_artifact(path: str | Path) -> None:
    """임시 파일/폴더 경로를 소유 프로세스(PID)와 함께 레지스트리에 기록한다.

    Args:
        path (str | Path): 임시 파일 또는 폴더 경로.
    """
    target = str(Path(path))
    pid = os.getpid()
    with _LOCK, _interprocess_lock():
        entries = _read_registry()
        if not any(entry["path"] == target for entry in entries):
            entries.append({"path": target, "pid": pid})
            _write_registry(entries)


def unregister_temp_artifact(path: str | Path) -> None:
    """정상 제거가 끝난 임시 파일/폴더를 레지스트리에서 해제한다.

    Args:
        path (str | Path): 임시 파일 또는 폴더 경로.
    """
    target = str(Path(path))
    with _LOCK, _interprocess_lock():
        entries = _read_registry()
        remaining = [entry for entry in entries if entry["path"] != target]
        if len(remaining) != len(entries):
            _write_registry(remaining)


def _remove_artifact(path: Path) -> bool:
    """임시 파일 패턴에 해당하는 항목만 삭제하고, 레지스트리에서 제거 가능한지 반환.

    Returns:
        bool: 패턴에 부합하고 실제로 제거되었으면 True (일부만 지워진 폴더는 False).
    """
    if not _is_temp_artifact(path):
        logger.warning("Ignoring unrecognized temp artifact entry: %s", path)
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Failed to remove stale temp artifact %s: %s", path, exc)
        return False
    # ignore_errors 로 일부 파일이 남은 폴더는 다음 기동에서 재시도하도록 유지
    return not path.exists()


def sweep_stale_temp_artifacts() -> int:
    """이전 실행에서 남은 임시 파일을 정리하고 삭제 개수를 반환한다.

    소유 프로세스가 아직 살아 있는 항목은 실행 중인 다른 인스턴스의 임시 파일일 수 있으므로
    건드리지 않고 레지스트리에 그대로 남긴다. 삭제에 실패한 항목도 다음 기동에서
    재시도할 수 있도록 유지하며, 소유자를 알 수 없는 구버전 항목은 안전을 위해 보존한다.

    Returns:
        int: 실제로 삭제한 항목 수.
    """
    with _LOCK, _interprocess_lock():
        entries = _read_registry()
        if not entries:
            return 0

        current_pid = os.getpid()
        remaining: list[dict[str, Any]] = []
        removed = 0
        for entry in entries:
            path = Path(entry["path"])
            pid = entry["pid"]
            if pid is None:
                logger.debug("Skipping temp artifact with unknown owner: %s", path)
                remaining.append(entry)
                continue
            if pid == current_pid or is_pid_alive(pid):
                # 실행 중인 인스턴스의 작업 파일 → 보존
                remaining.append(entry)
                continue
            if _remove_artifact(path):
                removed += 1
            else:
                remaining.append(entry)

        _write_registry(remaining)
        return removed
