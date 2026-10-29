"""AV Converter 다운로드 아카이브(ZIP) 무결성 검증 모듈."""
from __future__ import annotations

import zipfile
from pathlib import Path

from src.exceptions import FileIntegrityError


def validate_zip_download(temp_path: Path) -> None:
    """다운로드한 ZIP 임시 파일의 매직 바이트 및 엔트리 무결성을 검증.

    verified_download의 validator 콜백으로 사용되어, 형식 검증을 통과한
    아카이브만 목적지 경로로 안전하게 치환(원자적 이동)되도록 보장한다.

    Args:
        temp_path (Path): 검증할 ZIP 임시 파일 경로.

    Raises:
        FileIntegrityError: ZIP 매직 바이트('PK') 불일치 시.
        zipfile.BadZipFile: 아카이브 내 손상된 엔트리 발견 시.
    """
    with open(temp_path, 'rb') as f:
        magic = f.read(4)
    if magic[:2] != b'PK':
        raise FileIntegrityError(str(temp_path), "not a valid ZIP archive (magic bytes mismatch)")
    with zipfile.ZipFile(temp_path, 'r') as zip_test:
        # Zip Bomb(과도한 압축률) 검사를 먼저 수행해 불필요한 압축 해제 방지
        from src.utils.zip_safe import UnsafeZipMemberError, validate_zip_limits
        try:
            validate_zip_limits(zip_test)
        except UnsafeZipMemberError as exc:
            raise FileIntegrityError(str(temp_path), str(exc)) from exc
        bad_file = zip_test.testzip()
        if bad_file is not None:
            raise zipfile.BadZipFile(f"ZIP archive integrity check failed: corrupted entry '{bad_file}'.")
