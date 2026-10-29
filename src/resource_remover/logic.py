"""원본 게임 리소스 파일 탐색 및 안전 삭제 비즈니스 로직 모듈.

에셋 추출 완료 후 불필요해진 원본 클라이언트 캐시 파일(.unity3d, .acb, .awb, .usm 등)
디스크 검색 후 휴지통(send2trash) 이동 또는 영구 삭제.
개발 환경 소스코드 및 형상관리 폴더 보호용 _PROTECTED_DIRS 필터링(모든 깊이) 및
루트 디렉터리 탈출 방지(is_relative_to) 안전장치 내장.

추가 안전장치:
    - 파일 간 취소 토큰(CancellationToken) 점검을 통한 실행 중 중단 지원.
    - 기준 경로(base_path) resolve 정규화로 보호 디렉터리 필터 일관성 보장.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from send2trash import send2trash

from src.cancellation_token import CancellationToken
from src.constants import LOG_DIR_NAME, LOG_FILENAME_TS_FMT
from src.utils.base_path import get_application_base_path
from src.utils.file_scan import iter_files

logger = logging.getLogger(__name__)

# 삭제 진행률 콜백 호출 간격(파일 수)
_PROGRESS_INTERVAL: int = 10

# 삭제 대상에서 제외할 시스템/개발 보호 디렉터리 (소문자 비교, 모든 항목 소문자로 유지)
_PROTECTED_DIRS: frozenset[str] = frozenset({
    'src', 'tests', '.git', '.github', '.venv', 'venv',
    'node_modules', '__pycache__', '.mypy_cache',
    'packages', 'usmtoolkit', '_backup', '_source', 'docs', 'logs', 'scratch',
})


class ResourceRemoverLogic:
    """원본 리소스 파일 검색, 유효성 검증 및 삭제를 수행하는 도메인 로직 클래스."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        """ResourceRemoverLogic 초기화.

        Args:
            base_path (str | Path | None): 리소스 파일 검색 기준 루트 경로.
                None인 경우 실행 파일 기준 경로(get_application_base_path()) 자동 감지 적용.
                전달 경로는 즉시 resolve() 정규화되어(심볼릭 링크/정션 해석) 컨트롤러가
                할당하는 경로와 항상 동일한 기준 절대 경로를 공유.
        """
        self._base_path: Path = self._normalize_base_path(
            base_path if base_path is not None else get_application_base_path()
        )
        # 탐색/삭제 루프 파일 간 점검용 취소 토큰. cleanup()/Cancel 시 cancel되어 루프 중단.
        self._cancel_token: CancellationToken = CancellationToken()
        # 마지막 remove_resources() 실행이 취소로 종료되었는지 여부
        self.last_run_cancelled: bool = False

    @staticmethod
    def _normalize_base_path(value: str | Path) -> Path:
        """기준 경로를 심볼릭 링크/정션 해석이 완료된 절대 경로로 정규화.

        로직(resolve)과 컨트롤러 할당 경로 간 불일치로 인해 보호 디렉터리 필터가
        무력화되거나 정상 파일이 오탐 거부되는 문제를 방지하기 위해 단일 정규화 규칙 적용.

        Args:
            value (str | Path): 정규화할 경로.

        Returns:
            Path: resolve()된 절대 경로 (해석 실패 시 absolute() 폴백).
        """
        try:
            return Path(value).resolve()
        except OSError:
            return Path(value).absolute()

    @property
    def base_path(self) -> Path:
        """현재 검색 기준 루트 경로(정규화된 절대 경로) 반환.

        Returns:
            Path: resolve() 정규화된 기준 경로.
        """
        return self._base_path

    @base_path.setter
    def base_path(self, value: str | Path) -> None:
        """검색 기준 루트 경로 설정 시 즉시 resolve() 정규화 적용.

        Args:
            value (str | Path): 새 기준 경로 (컨트롤러 폴더 선택 등에서 할당).
        """
        self._base_path = self._normalize_base_path(value)

    def request_cancel(self) -> None:
        """진행 중인 탐색/삭제 루프에 취소 신호 전송 (스레드 안전)."""
        self._cancel_token.cancel()

    def reset_cancel(self) -> None:
        """이전 작업 상태를 마무리하고 취소 신호 초기화 (새 작업 시작 직전 호출)."""
        self._cancel_token.finish()
        self._cancel_token.reset()
        self.last_run_cancelled = False

    @property
    def is_cancelled(self) -> bool:
        """취소 신호가 설정되었는지 여부 반환.

        Returns:
            bool: 취소 요청이 들어왔으면 True.
        """
        return self._cancel_token.is_cancelled

    def count_resources(self, extensions_to_remove: Sequence[str]) -> list[Path]:
        """지정 확장자 파일 검색 및 삭제 대상 목록 반환.

        보호 디렉터리(_PROTECTED_DIRS)는 os.walk의 dirs 슬라이싱을 통해
        최상위뿐 아니라 모든 하위 레벨에서 순회 대상에서 즉시 배제.
        취소 토큰(_cancel_token)이 설정되면 순회를 즉시 중단.

        Args:
            extensions_to_remove (Sequence[str]): 검색할 대상 확장자 목록 (예: ['.unity3d', '.awb']).

        Returns:
            list[Path]: 발견된 일치 파일들의 절대 Path 객체 리스트.
        """
        target_exts = tuple(extensions_to_remove)

        # 모든 깊이에서 보호 디렉터리를 사전 배제 (Windows 대소문자 무시 대응: 소문자 비교)
        return [
            Path(path)
            for path in iter_files(
                self._base_path,
                predicate=lambda name: name.lower().endswith(target_exts),
                skip_dir_names=_PROTECTED_DIRS,
                cancel=lambda: self.is_cancelled,
            )
        ]

    def remove_resources(
        self,
        target_files: Sequence[Path | str],
        extensions_to_remove: Sequence[str],
        use_trash: bool = True,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> tuple[int, list[str], str]:
        """선택 리소스 파일 삭제(또는 휴지통 이동) 및 결과 리포트 반환.

        보안 검증 단계:
        1. 경로 유효성 검증: 대상 파일이 self.base_path 하위에 존재하는지 확인 (is_relative_to).
        2. 확장자 검증: 허용된 확장자 목록(extensions_to_remove)에 속하는지 재확인.
        3. 안전 삭제: use_trash=True인 경우 send2trash로 휴지통 이동을 시도하며(볼륨에 따라 영구 삭제될 수 있음), False면 영구 삭제.
        4. 삭제 로그 작성: 성공 및 실패 항목을 logs/DeletionLog_*.log에 **항목별 즉시** 기록.
        5. 취소 토큰(_cancel_token)을 파일 간 점검하여 설정 시 남은 대상 처리 없이 중단.

        Args:
            target_files (Sequence[Path | str]): 삭제 대상 파일 경로 시퀀스.
            extensions_to_remove (Sequence[str]): 허용된 삭제 대상 확장자 시퀀스.
            use_trash (bool): True이면 OS 휴지통 이동을 시도하며(볼륨에 따라 영구 삭제될 수 있음), False이면 즉시 영구 삭제.
            progress_cb (Callable[[int, int], None] | None): (처리 수, 전체 수) 진행 콜백.

        Returns:
            tuple[int, list[str], str]: (삭제 성공 파일 수, 에러 메시지 리스트, 생성된 로그 파일 경로 문자열).
        """
        deleted_files: list[str] = []
        # (대상 경로, 실패 사유) 튜플로 보관하여 로그의 Target/Message 항목으로 분리 기록
        error_items: list[tuple[str, str]] = []
        allowed_exts = tuple(extensions_to_remove)
        self.last_run_cancelled = False
        total_files = len(target_files)

        # 삭제 시작 전에 삭제 로그를 열어 항목별로 즉시 기록한다.
        # (중간 종료/크래시가 발생해도 이미 처리된 내역이 남도록 하기 위함)
        log_filename = self._open_deletion_log()
        log_handle = None
        log_timestamp = None
        if log_filename is not None:
            try:
                log_handle = open(log_filename, "a", encoding="utf-8")
                log_timestamp = self._write_deletion_header(log_handle, extensions_to_remove, use_trash)
            except OSError as exc:
                logger.warning("Failed to open deletion log %s: %s", log_filename, exc)
                log_handle = None
                log_filename = None

        try:
            for index, file_path in enumerate(target_files, 1):
                if self.is_cancelled:
                    self.last_run_cancelled = True
                    break
                try:
                    target = Path(file_path)
                    # 1. 경로 유효성 검증은 심볼릭 링크/정션을 해석한 결과를 기준으로 수행
                    if not target.resolve().is_relative_to(self.base_path):
                        self._record_deletion_error(log_handle, log_timestamp, index, str(target), "path outside base directory", error_items)
                        continue
                    # 2. 승인 목록과 동일한 이름으로 확장자 재검증
                    if not target.name.lower().endswith(allowed_exts):
                        self._record_deletion_error(log_handle, log_timestamp, index, str(target), "extension not allowed", error_items)
                        continue
                    # 2-1. 탐색 이후 디렉터리 등으로 교체된 항목 제외 (일반 파일만 대상)
                    if not target.is_file():
                        self._record_deletion_error(log_handle, log_timestamp, index, str(target), "not a regular file", error_items)
                        continue
                    # 3. 휴지통 이동 또는 영구 삭제 수행 (사용자가 승인한 경로 그대로 사용)
                    if use_trash:
                        send2trash(target)
                    else:
                        os.remove(target)
                    deleted_files.append(str(target))
                    self._write_deletion_item(log_handle, log_timestamp, index, str(target), "OK")
                except OSError as e:
                    self._record_deletion_error(log_handle, log_timestamp, index, str(file_path), str(e), error_items)

                if progress_cb is not None and (index % _PROGRESS_INTERVAL == 0 or index == total_files):
                    try:
                        progress_cb(index, total_files)
                    except Exception:  # noqa: BLE001
                        logger.debug("Deletion progress callback failed", exc_info=True)
        finally:
            if log_handle is not None:
                try:
                    log_handle.write(
                        f"[REPORT]  Cancelled:       {self.last_run_cancelled}\n"
                        f"[REPORT]  Total Deleted:   {len(deleted_files)}\n"
                        f"[REPORT]  Total Errors:    {len(error_items)}\n"
                    )
                except OSError as exc:
                    logger.debug("Failed to write deletion log footer: %s", exc)
                try:
                    log_handle.close()
                except OSError:
                    pass

        errors = [f"{target}: {message}" for target, message in error_items]
        return len(deleted_files), errors, str(log_filename) if log_filename else ""

    @staticmethod
    def _open_deletion_log() -> Path | None:
        """삭제 작업 로그 파일 경로 생성 (디렉터리 보장).

        Returns:
            Path | None: 생성할 로그 파일 경로. 준비 실패 시 None.
        """
        try:
            log_dir = get_application_base_path() / LOG_DIR_NAME
            log_dir.mkdir(parents=True, exist_ok=True)
            return log_dir / f"DeletionLog_{datetime.now().strftime(LOG_FILENAME_TS_FMT)}.log"
        except OSError as exc:
            logger.warning("Failed to prepare deletion log path: %s", exc)
            return None

    @staticmethod
    def _write_deletion_header(handle: Any, extensions_to_remove: Sequence[str], use_trash: bool) -> Any:
        """삭제 작업 로그 상단 헤더 기록 및 기준 타임스탬프 반환."""
        from src.constants import APP_DEVELOPER, APP_LAST_UPDATE, APP_VERSION
        from src.utils.error_log import write_log_header

        app_info = {'APP_VERSION': APP_VERSION, 'APP_LAST_UPDATE': APP_LAST_UPDATE, 'APP_DEVELOPER': APP_DEVELOPER}
        extra_report = [
            f"[REPORT]  Target Exts:     {', '.join(extensions_to_remove)}",
            f"[REPORT]  Trash Requested: {use_trash}",
        ]
        return write_log_header(handle, "Resource Deletion Log", get_application_base_path(), app_info, extra_report)

    @staticmethod
    def _write_deletion_item(handle: Any, timestamp: Any, index: int, target: str, message: str) -> None:
        """단일 삭제 결과 항목을 삭제 로그에 즉시 기록."""
        if handle is None or timestamp is None:
            return
        from src.utils.error_log import write_log_item
        try:
            write_log_item(
                handle,
                item_header="[OK ITEM #{idx}]",
                idx=index,
                timestamp=timestamp,
                context="Resource Deletion",
                target=target,
                message=message,
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Failed to write deletion log item: %s", exc)

    @staticmethod
    def _record_deletion_error(handle: Any, timestamp: Any, index: int, target: str, message: str, error_items: list[tuple[str, str]]) -> None:
        """삭제 실패 항목을 결과 목록과 삭제 로그에 동시 기록."""
        error_items.append((target, message))
        if handle is None or timestamp is None:
            return
        from src.utils.error_log import write_log_item
        try:
            write_log_item(
                handle,
                item_header="[ERROR ITEM #{idx}]",
                idx=index,
                timestamp=timestamp,
                context="Resource Deletion",
                target=target,
                message=message,
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Failed to write deletion log error item: %s", exc)


