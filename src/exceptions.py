"""애플리케이션 전용 커스텀 예외 계층 모듈.

프로젝트 전반 도메인별 에러(DB, 변환, 다운로드, 무결성) 세분화 정의.
모든 커스텀 예외는 AppBaseError를 상속하므로 최상위 핸들러 포괄적 에러 트랩 지원.

사용 예:
    from src.exceptions import UnsafeIdentifierError, AssetProcessingError

    raise UnsafeIdentifierError("v1_table; DROP TABLE --")
    raise AssetProcessingError("storydata_1001", "corrupted")
"""
from __future__ import annotations


class AppBaseError(Exception):
    """프로젝트 전체 커스텀 예외 최상위 기본 클래스.

    모든 도메인별 커스텀 예외의 상위 타입.
    except AppBaseError: 구문으로 라이브러리/시스템 예외와 분리된 선별 처리 지원.
    """


# ---- Database 도메인 예외 ----

class DatabaseError(AppBaseError):
    """데이터베이스 접근 및 쿼리 처리 관련 기본 예외."""


class UnsafeIdentifierError(DatabaseError):
    """SQL 식별자(테이블/컬럼명) 화이트리스트 검증 실패 예외.

    SQL 인젝션 방어 목적의 동적 쿼리 생성 전 식별자 검증 시 사용.

    Attributes:
        identifier (str): 허용되지 않아 거부된 식별자 문자열.
    """
    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Unsafe SQL identifier rejected: {identifier!r}")


class DatabaseIntegrityError(DatabaseError):
    """SQLite DB 파일 헤더 또는 구조적 무결성 검증 실패 예외.

    Attributes:
        filename (str): 검증에 실패한 대상 DB 파일명.
        reason (str): 검증 실패 사유 (예: 'header mismatch', 'corrupted schema').
    """
    def __init__(self, filename: str, reason: str = "header mismatch") -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"Database integrity check failed for '{filename}': {reason}")


# ---- Conversion 도메인 예외 ----

class ConversionError(AppBaseError):
    """파일 변환(AV, Unity3D 에셋 등) 처리 중 발생하는 기본 예외."""


class AssetProcessingError(ConversionError):
    """Unity 애셋 번들 언패킹 또는 바이너리 역직렬화 실패 예외.

    Attributes:
        asset_name (str): 처리에 실패한 애셋 이름 또는 파일명.
        reason (str): 실패 세부 원인.
    """
    def __init__(self, asset_name: str, reason: str = "") -> None:
        self.asset_name = asset_name
        self.reason = reason
        msg = f"Asset processing failed: {asset_name}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


# ---- Download 도메인 예외 ----

class DownloadError(AppBaseError):
    """외부 종속 도구 다운로드 및 네트워크 통신 중 발생하는 기본 예외."""


class FileIntegrityError(DownloadError):
    """다운로드 파일 해시(SHA-256) 또는 매직 바이트 무결성 검증 실패 예외.

    Attributes:
        filename (str): 검증에 실패한 다운로드 파일명.
        reason (str): 실패 상세 사유 (예: 'hash mismatch', 'magic bytes mismatch').
    """
    def __init__(self, filename: str, reason: str = "magic bytes mismatch") -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"File integrity check failed for '{filename}': {reason}")

