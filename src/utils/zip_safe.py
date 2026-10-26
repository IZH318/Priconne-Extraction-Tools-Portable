"""ZIP 아카이브 안전 압축 해제 및 Zip-Slip 취약점 방어 모듈.

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


def _is_safe_member_name(name: str) -> bool:
    """ZIP 멤버 이름의 경로 순회 위험 여부 검사.

    검증 항목:
    1. 슬래시(/)로 시작하는 절대 경로 거부
    2. Windows 드라이브 레터(예: C:) 포함 여부 거부
    3. 상위 디렉터리 탐색 세그먼트(..) 포함 여부 거부

    Args:
        name (str): 검사할 ZIP 내부 멤버 파일 경로 문자열.

    Returns:
        bool: 안전한 상대 경로이면 True, 위험 요소 감지 시 False.
    """
    if not name:
        return True
    # 백슬래시를 슬래시로 정규화 (Windows 혼용 대비)
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    if os.path.isabs(normalized):
        return False
    # 드라이브 레터 (예: C:/...) 거부
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    parts = normalized.split("/")
    return not any(part == ".." for part in parts)


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

    zipfile.ZipFile.extract() 잠재 취약점 방어를 위해,
    목적지 경로 상위 디렉터리 포함 여부(os.path.commonpath) 엄격 검증 후
    shutil.copyfileobj 기반 안전 스트리밍 복사.

    Args:
        zip_ref (Any): 열려 있는 zipfile.ZipFile 인스턴스.
        member (Any): 추출 대상 멤버 (파일 경로 문자열 또는 ZipInfo 객체).
        dest_dir (str | Path): 추출 대상 최상위 목적지 디렉터리 경로.

    Returns:
        Path: 안전하게 추출된 결과 파일의 절대 경로.

    Raises:
        UnsafeZipMemberError: 심볼릭 링크이거나, 경로 순회 시도(..), 절대 경로가 포함된 경우.
    """
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
    # 안전한 스트리밍 복사
    with zip_ref.open(member, "r") as src, open(target, "wb") as out:
        import shutil
        shutil.copyfileobj(src, out)
    return target


def safe_extractall(zip_ref: Any, dest_dir: str | Path, skip_names: set[str] | None = None) -> list[Path]:
    """ZIP 아카이브 내 모든 파일 안전 일괄 추출.

    디렉터리 엔트리 및 심볼릭 링크 스킵, skip_names 지정 파일(대소문자 무시) 제외 처리.

    Args:
        zip_ref (Any): 열려 있는 zipfile.ZipFile 인스턴스.
        dest_dir (str | Path): 압축을 풀 루트 대상 디렉터리.
        skip_names (set[str] | None): 건너뛸 파일 기본 이름(basename) 집합 (소문자 비교).

    Returns:
        list[Path]: 추출 완료된 모든 파일들의 Path 객체 리스트.
    """
    skip = {s.lower() for s in (skip_names or set())}
    extracted: list[Path] = []
    for member in zip_ref.infolist():
        if member.is_dir():
            continue
        if _is_symlink_member(member):
            continue
        base_name = os.path.basename(member.filename).lower()
        if base_name in skip:
            continue
        extracted.append(safe_extract(zip_ref, member, dest_dir))
    return extracted

