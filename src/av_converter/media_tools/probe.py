"""외부 실행 파일 기동 프로브 및 vgmstream 호환 헬퍼 모듈."""
from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from src.subprocess_runner import SubprocessRunner

_test_exe_lock = threading.Lock()


def ensure_vgmstream_test_exe(vgm_exe_path: Path | None) -> None:
    """vgmstream-cli.exe를 UsmToolkit 호환용 test.exe로 복사 (스레드 락 보호).

    UsmToolkit은 내부적으로 vgmstream을 호출할 때 test.exe라는 고정 이름을 기대하므로,
    동일 디렉터리에 사본이 존재하지 않을 경우 안전하게 복제.

    Args:
        vgm_exe_path (Path | None): vgmstream-cli.exe의 파일 경로.
    """
    if vgm_exe_path is None:
        return
    vgm_path = Path(vgm_exe_path)
    if not vgm_path.is_file():
        return
    test_exe = vgm_path.parent / "test.exe"
    with _test_exe_lock:
        if test_exe.exists():
            return
        try:
            shutil.copy2(vgm_path, test_exe)
        except OSError:
            pass


def _is_executable_usable(exe_path: Path, probe_args: list[str], timeout: int) -> bool:
    """실행 파일이 실제로 기동 가능한지 프로브하여 손상/잘림 여부를 판별.

    파일 존재 여부만으로 '설치됨'을 판정하면 0바이트/중단된 복사본을 영구히 신뢰하게 되므로,
    짧은 인자로 기동을 시도해 손상 바이너리만 재설치 대상으로 분류한다.

    Args:
        exe_path (Path): 검사할 실행 파일 경로.
        probe_args (list[str]): 기동 확인용 인자 목록.
        timeout (int): 프로브 최대 대기 시간(초).

    Returns:
        bool: 파일이 존재하고 프로세스 기동이 가능하면 True.
    """
    if not exe_path.is_file():
        return False
    try:
        SubprocessRunner.run([str(exe_path), *probe_args], timeout=timeout)
    except OSError:
        # 손상/잘린 바이너리, 실행 권한 문제 → 재설치 대상
        return False
    except (subprocess.SubprocessError, ValueError, RuntimeError):
        # 기동은 되었으나 인자/런타임 문제일 뿐 파일 자체는 유효
        return True
    return True
