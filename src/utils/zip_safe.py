"""ZIP 아카이브 안전 압축 해제 및 Zip-Slip 경로 순회 방지 모듈.

외부에서 다운로드하거나 사용자가 제공한 ZIP 파일을 해제할 때 발생할 수 있는
경로 순회(Path Traversal / Zip-Slip) 공격 및 심볼릭 링크를 통한 임의 파일 덮어쓰기
방지를 위해 경로 유효성 검증 및 스트리밍 추출 제공.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class UnsafeZipMemberError(ValueError):
    """ZIP 아카이브 멤버가 경로 순회 시도(..), 절대 경로 또는 심볼릭 링크를 포함할 때 발생하는 보안 예외."""


# Windows 예약 디바이스명 (확장자와 무관하게 예약되어 파일 생성이 불가/오동작)
_WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }
)

# Zip Bomb(비정상 고압축률 아카이브) 방지 기본 상한
DEFAULT_MAX_ARCHIVE_BYTES: int = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO: int = 10_000


def _is_safe_member_name(name: str) -> bool:
    """ZIP 멤버 이름의 경로 순회 및 위험 패턴 여부 검사 (무결성 검사).

    검증 항목:
    1. 빈 이름 및 전체 이름이 "." / ".." 인 경우 거부
    2. 슬래시(/)로 시작하는 절대 경로 거부
    3. 콜론(:) 위치 무관 거부 → NTFS 대체 데이터 스트림(ADS) 방지
    4. 상위 디렉터리 탐색 세그먼트(..) 포함 여부 거부
    5. 세그먼트별 후행 공백/점 제거 후 "." / ".." / 빈 세그먼트 거부
       (Windows가 ".. " / "..." 등을 ".." 로 정규화하는 동작 방지)

    Args:
        name (str): 검사할 ZIP 내부 멤버 파일 경로 문자열.

    Returns:
        bool: 안전한 상대 경로이면 True, 위험 요소 감지 시 False.
    """
    if not name or name in (".", ".."):
        return False
    # 백슬래시를 슬래시로 정규화 (Windows 혼용 대비)
    normalized = name.replace("\\", "/")
    # NTFS 대체 데이터 스트림(ADS) 생성 방지: 콜론(:) 포함 경로 거부
    if ":" in normalized:
        return False
    if normalized.startswith("/"):
        return False
    if os.path.isabs(normalized):
        return False
    for part in normalized.split("/"):
        if part == "..":
            return False
        # Windows는 세그먼트 후행 공백/점을 제거하므로 정규화 결과로 재검사
        stripped = part.rstrip(" .")
        if not stripped or stripped in (".", ".."):
            return False
        # Windows 예약 디바이스명(CON, NUL, COM1 등) 거부
        if stripped.split(".", 1)[0].upper() in _WINDOWS_RESERVED_DEVICE_NAMES:
            return False
    return True


def validate_zip_limits(
    zip_ref: Any,
    max_total_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
) -> None:
    """아카이브 전체 해제 크기 및 압축률 상한 검증 (Zip Bomb 방지).

    압축 해제 전에 호출하여 디스크 고갈로 이어지는 비정상 아카이브 압축 해제를 중단한다.

    Args:
        zip_ref (Any): 열려 있는 zipfile.ZipFile 인스턴스.
        max_total_bytes (int): 전체 해제 크기 상한(바이트).
        max_compression_ratio (int): 단일 멤버 허용 최대 압축률(해제 크기 / 압축 크기).

    Raises:
        UnsafeZipMemberError: 전체 해제 크기 또는 단일 멤버 압축률이 상한을 초과한 경우.
    """
    total_uncompressed = 0
    for member in zip_ref.infolist():
        size = getattr(member, "file_size", 0) or 0
        compressed = getattr(member, "compress_size", 0) or 0
        total_uncompressed += size
        if total_uncompressed > max_total_bytes:
            raise UnsafeZipMemberError(
                f"ZIP archive exceeds total size limit: {total_uncompressed} bytes > {max_total_bytes} bytes"
            )
        if compressed > 0 and size > compressed * max_compression_ratio:
            raise UnsafeZipMemberError(
                f"ZIP member compression ratio too high: {getattr(member, 'filename', member)!r}"
            )


def _is_symlink_member(member: Any) -> bool:
    """ZIP 멤버의 심볼릭 링크 여부 검사.

    Unix 파일 모드 S_IFLNK (0xA000) 비트 설정 탐지.

    Args:
        member (Any): zipfile.ZipInfo 객체.

    Returns:
        bool: 해당 엔트리가 심볼릭 링크이면 True, 일반 파일/디렉터리면 False.
    """
    external_attr = getattr(member, "external_attr", 0) or 0
    mode = (external_attr >> 16) & 0xFFFF
    # 유닉스 심볼릭 링크 판별 비트: S_IFLNK (0xA000)
    return (mode & 0xF000) == 0xA000


def safe_extract(zip_ref: Any, member: Any, dest_dir: str | Path) -> Path:
    """ZIP 멤버 단건 안전 추출.

    zipfile.ZipFile.extract() 경로 순회 취약점 방지를 위해,
    목적지 경로 상위 디렉터리 포함 여부(os.path.commonpath) 경로 검증 후
    shutil.copyfileobj 기반 안전 스트리밍 복사.

    Args:
        zip_ref (Any): 열려 있는 zipfile.ZipFile 인스턴스.
        member (Any): 추출 대상 멤버 (파일 경로 문자열 또는 ZipInfo 객체).
            문자열로 전달되면 내부에서 동일 이름의 ZipInfo로 승격하여 검사하므로,
            external_attr 기반 심볼릭 링크 탐지가 누락되지 않음.
        dest_dir (str | Path): 추출 대상 최상위 목적지 디렉터리 경로.

    Returns:
        Path: 안전하게 추출된 결과 파일의 절대 경로.

    Raises:
        UnsafeZipMemberError: 심볼릭 링크이거나, 경로 순회 시도(..), 절대 경로가 포함된 경우.
    """
    # 문자열 멤버는 ZipInfo로 승격하여 심볼릭 링크 비트(external_attr) 검사 누락 방지
    if isinstance(member, str):
        try:
            member = zip_ref.getinfo(member)
        except KeyError:
            # 아카이브에 없는 이름은 문자열 그대로 두고 아래 이름 검증에서 거부
            pass
    if _is_symlink_member(member):
        name = getattr(member, "filename", str(member))
        raise UnsafeZipMemberError(f"Symlink ZIP member rejected: {name!r}")
    name = member.filename if hasattr(member, "filename") else str(member)
    if not _is_safe_member_name(name):
        raise UnsafeZipMemberError(f"Unsafe ZIP member name rejected: {name!r}")

    dest = Path(dest_dir).resolve()
    target = (dest / name).resolve() if not os.path.isabs(name) else None
    if target is None:
        raise UnsafeZipMemberError(f"Unsafe ZIP member name rejected: {name!r}")

    # 최종 대상 경로가 지정된 dest 디렉터리 하위에 머무는지(Containment) 검증
    try:
        if os.path.commonpath([str(dest), str(target)]) != str(dest):
            raise UnsafeZipMemberError(f"ZIP member escapes destination: {name!r}")
    except ValueError:
        raise UnsafeZipMemberError(f"ZIP member escapes destination: {name!r}") from None

    dest.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # 안전한 스트리밍 복사 (중단/CRC 오류 시 부분 파일을 남기지 않음)
    try:
        import shutil

        with zip_ref.open(member, "r") as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
    except BaseException:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target
