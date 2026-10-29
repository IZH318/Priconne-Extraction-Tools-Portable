"""프로세스 생존 판정 공통 유틸리티 모듈.

다중 인스턴스로 실행될 수 있는 환경에서 다른 인스턴스(또는 이미 종료된 인스턴스)가
사용한 세션 폴더 및 임시 파일을 구분하기 위해 PID 생존 여부를 보수적으로 판정한다.
"""
from __future__ import annotations

import os
import sys

# GetExitCodeProcess가 반환하는 STILL_ACTIVE 값
_STILL_ACTIVE: int = 259

# 프로세스 부재를 확정하는 OpenProcess 오류 코드 (ERROR_INVALID_PARAMETER, ERROR_FILE_NOT_FOUND, ERROR_NOT_FOUND)
_PROCESS_GONE_ERRORS: tuple[int, ...] = (87, 2, 1168)


def is_pid_alive(pid: int) -> bool:
    """지정 PID 프로세스의 활성 실행 여부 검사 (보수적 판정).

    OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) 및
    GetExitCodeProcess의 STILL_ACTIVE (259) 반환 여부 확인.
    종료가 확정된 경우에만 False, 권한 부족 등 판정 불가 시에는 True를 반환한다.

    Args:
        pid (int): 검사 대상 운영체제 프로세스 ID.

    Returns:
        bool: 프로세스가 활성이거나 생존 여부를 확정할 수 없으면 True,
            확실히 종료되었으면 False.
    """
    if pid <= 0:
        return False
    if sys.platform == 'win32':
        import ctypes

        # use_last_error=True 로 설정해야 다른 ctypes 호출에 오류값이 덮이지 않음
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            # 프로세스 부재 확정 외에는 판정 불가로 보고 생존 처리
            return ctypes.get_last_error() not in _PROCESS_GONE_ERRORS
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == _STILL_ACTIVE
            # 종료 코드 조회 실패 → 판정 불가 → 생존 처리
            return True
        finally:
            kernel32.CloseHandle(handle)

    try:  # type: ignore[unreachable]
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False  # 프로세스 부재
    except PermissionError:
        return True  # 권한 없음 → 생존 처리
    except OSError:
        return True  # 판정 불가 → 생존 처리
