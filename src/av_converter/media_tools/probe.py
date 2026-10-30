"""외부 실행 파일 기동 프로브, .NET Runtime 조회 및 vgmstream 호환 헬퍼 모듈."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Mapping
from pathlib import Path

from src.constants import DOTNET_EXE_NAME, DOTNET_RUNTIME_DIR_NAME, DOTNET_RUNTIME_MIN_VERSION, DOTNET_RUNTIME_PROBE_TIMEOUT
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


def local_dotnet_exe_path(base_path: Path) -> Path:
    """로컬(usmtoolkit/dotnet) .NET Runtime 실행 파일 경로 반환."""
    return Path(base_path) / "usmtoolkit" / DOTNET_RUNTIME_DIR_NAME / DOTNET_EXE_NAME


def query_dotnet_runtimes(dotnet_exe: Path, timeout: int = DOTNET_RUNTIME_PROBE_TIMEOUT,
                          env: Mapping[str, str] | None = None) -> list[str]:
    """지정한 dotnet 실행 파일의 `--list-runtimes` 결과에서 Microsoft.NETCore.App 버전 문자열 목록 반환.

    Args:
        dotnet_exe (Path): 조회에 사용할 dotnet(.exe) 실행 파일 경로.
        timeout (int): 조회 서브프로세스 최대 대기 시간(초).
        env (Mapping[str, str] | None): 조회 프로세스에 주입할 환경변수 (미지정 시 부모 환경 상속).

    Returns:
        list[str]: "Microsoft.NETCore.App <version>" 형식 문자열 목록 (조회 실패 시 빈 목록).
    """
    versions: list[str] = []
    try:
        res = SubprocessRunner.run([str(dotnet_exe), '--list-runtimes'], timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError, ValueError):
        return versions
    if res.returncode != 0:
        return versions
    for line in (res.stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == 'Microsoft.NETCore.App':
            versions.append(f"{parts[0]} {parts[1]}")
    return versions


def _dedupe_ordered(items: list[str]) -> list[str]:
    """순서를 유지하며 중복을 제거한 목록 반환."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def collect_system_dotnet_runtimes(timeout: int = DOTNET_RUNTIME_PROBE_TIMEOUT) -> list[str]:
    """시스템 PATH의 dotnet 실행 파일에서 .NET Runtime (Microsoft.NETCore.App) 목록 반환.

    Args:
        timeout (int): 조회 서브프로세스 최대 대기 시간(초).

    Returns:
        list[str]: "Microsoft.NETCore.App <version>" 형식 문자열 목록 (시스템 미설치 시 빈 목록).
    """
    system_exe = shutil.which('dotnet')
    if not system_exe:
        return []
    return _dedupe_ordered(query_dotnet_runtimes(Path(system_exe), timeout))


def collect_local_dotnet_runtimes(base_path: Path | None, timeout: int = DOTNET_RUNTIME_PROBE_TIMEOUT) -> list[str]:
    """로컬(usmtoolkit/dotnet) .NET Runtime (Microsoft.NETCore.App) 목록 반환.

    Args:
        base_path (Path | None): 프로그램 기준 경로. None 이거나 로컬 런타임이 없으면 빈 목록.
        timeout (int): 조회 서브프로세스 최대 대기 시간(초).

    Returns:
        list[str]: "Microsoft.NETCore.App <version>" 형식 문자열 목록.
    """
    if base_path is None:
        return []
    exe = local_dotnet_exe_path(base_path)
    if not exe.is_file():
        return []
    # 멀티레벨 조회를 끄고 로컬 런타임만 조회 (시스템 런타임 혼입 방지)
    env = dict(os.environ)
    env["DOTNET_MULTILEVEL_LOOKUP"] = "0"
    return _dedupe_ordered(query_dotnet_runtimes(exe, timeout, env=env))


def find_satisfying_dotnet_runtime(versions: list[str], minimum: tuple[int, int] = DOTNET_RUNTIME_MIN_VERSION) -> str | None:
    """버전 문자열 목록에서 major.minor가 minimum 이상인 첫 항목 반환 (없으면 None).

    Args:
        versions (list[str]): "Microsoft.NETCore.App <version>" 형식 문자열 목록.
        minimum (tuple[int, int]): 최소 요구 major.minor 버전.

    Returns:
        str | None: 요구 버전을 만족하는 첫 버전 문자열 또는 None.
    """
    for entry in versions:
        parts = entry.split()
        if len(parts) < 2:
            continue
        try:
            major_minor = tuple(int(part) for part in parts[1].split('.')[:2])
        except ValueError:
            continue
        if len(major_minor) == 2 and major_minor >= minimum:
            return entry
    return None


def is_dotnet_force_local_runtime() -> bool:
    """환경변수 PRICONNE_DOTNET_FORCE_LOCAL_RUNTIME 설정 여부 반환.

    시스템 .NET을 무시하고 로컬 런타임만 사용하도록 강제하는 테스트/디버그 스위치.

    Returns:
        bool: 강제 로컬 모드가 활성화되면 True.
    """
    return (os.environ.get('PRICONNE_DOTNET_FORCE_LOCAL_RUNTIME') or '').strip().lower() in ('1', 'true', 'yes', 'on')
