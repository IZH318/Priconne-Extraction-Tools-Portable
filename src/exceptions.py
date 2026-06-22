from __future__ import annotations
"""
애플리케이션 전용 예외 클래스 계층 모듈.

프로젝트 전반에서 발생할 수 있는 도메인별 에러를 세분화하여 정의합니다.
모든 커스텀 예외는 AppBaseError를 상속하므로, 최상위에서 한 번에 잡을 수 있습니다.

사용 예:
    from src.exceptions import UnsafeIdentifierError, ToolNotFoundError

    raise UnsafeIdentifierError("v1_table; DROP TABLE --")
    raise ToolNotFoundError("ffmpeg.exe")
"""


class AppBaseError(Exception):
    """프로젝트 전체 커스텀 예외의 기본 클래스입니다.

    모든 도메인별 예외가 이 클래스를 상속합니다.
    `except AppBaseError`로 프로젝트 내 모든 커스텀 예외를 포괄적으로 처리할 수 있습니다.
    """


# ---- Database 도메인 ----

class DatabaseError(AppBaseError):
    """데이터베이스 접근 및 처리 관련 기본 예외입니다."""


class UnsafeIdentifierError(DatabaseError):
    """SQL 식별자(테이블/컬럼명)가 화이트리스트 검증을 통과하지 못한 경우 발생합니다.

    Args:
        identifier: 거부된 식별자 문자열.
    """
    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Unsafe SQL identifier rejected: {identifier!r}")


class DatabaseIntegrityError(DatabaseError):
    """다운로드 또는 로드된 DB 파일의 무결성 검증이 실패한 경우 발생합니다.

    Args:
        filename: 검증에 실패한 파일명.
        reason: 실패 사유.
    """
    def __init__(self, filename: str, reason: str = "header mismatch") -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"Database integrity check failed for '{filename}': {reason}")


# ---- Conversion 도메인 ----

class ConversionError(AppBaseError):
    """파일 변환(AV, Unity 등) 처리 중 발생하는 기본 예외입니다."""


class ToolNotFoundError(ConversionError):
    """외부 변환 도구(FFmpeg, UsmToolkit 등)를 찾을 수 없는 경우 발생합니다.

    Args:
        tool_name: 찾을 수 없는 도구의 이름.
    """
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Required tool not found: {tool_name}")


class AssetProcessingError(ConversionError):
    """Unity 애셋 처리 또는 역직렬화 중 오류가 발생한 경우입니다.

    Args:
        asset_name: 처리에 실패한 애셋 이름.
        reason: 실패 사유.
    """
    def __init__(self, asset_name: str, reason: str = "") -> None:
        self.asset_name = asset_name
        self.reason = reason
        msg = f"Asset processing failed: {asset_name}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


# ---- Download 도메인 ----

class DownloadError(AppBaseError):
    """파일 다운로드 중 발생하는 기본 예외입니다."""


class FileIntegrityError(DownloadError):
    """다운로드된 파일의 무결성 검증(매직 바이트, ZIP 구조 등)이 실패한 경우입니다.

    Args:
        filename: 검증에 실패한 파일명.
        reason: 실패 사유.
    """
    def __init__(self, filename: str, reason: str = "magic bytes mismatch") -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"File integrity check failed for '{filename}': {reason}")


# ---- Operation 도메인 ----

class OperationCancelledError(AppBaseError):
    """사용자가 진행 중인 작업을 취소한 경우 발생합니다."""
    def __init__(self, message: str = "Operation was cancelled by the user.") -> None:
        super().__init__(message)
