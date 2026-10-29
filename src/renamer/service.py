"""Manifest File Renamer 서비스 모듈.

매니페스트 검증, 백그라운드 스레드 수명주기, 결과 집계 및
실패/미처리 파일 에러 리포트 생성 로직을 UI 컨트롤러로부터 분리.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from typing import Any

from src.renamer.logic import RenameHashedFile
from src.utils.base_path import get_application_base_path
from src.utils.error_log import open_task_log, write_log_items

logger = logging.getLogger(__name__)


class RenameService:
    """매니페스트 파일 이름 복원 작업 서비스 클래스.

    백엔드 스레드 관리 및 에러 로깅을 캡슐화하여 컨트롤러가 가벼운 프레젠테이션
    파사드 역할에 집중하도록 지원.

    Attributes:
        get_string: 다국어 UI 번역 콜백 함수.
        log_queue: UI 폴링용 로그 이벤트를 수신하는 스레드 안전 큐.
        progress_queue: UI 폴링용 진행률 이벤트를 수신하는 스레드 안전 큐.
        processor: 캐싱된 백엔드 RenameHashedFile 인스턴스.
    """

    def __init__(
        self,
        get_string: Callable[..., str],
        log_queue: Queue[Any],
        progress_queue: Queue[Any],
        base_path_provider: Callable[[], Path | None],
    ) -> None:
        """RenameService 초기화.

        Args:
            get_string: 다국어 번역 문자열 검색 콜백 함수.
            log_queue: 로그 이벤트 메시지를 수신하는 큐.
            progress_queue: 프로그레스바 갱신 이벤트를 수신하는 큐.
            base_path_provider: 대상 루트 디렉터리 경로(Path) 또는 None을 반환하는 콜백.
        """
        self.get_string = get_string
        self.log_queue = log_queue
        self.progress_queue = progress_queue
        self._base_path_provider = base_path_provider
        self.processor: RenameHashedFile | None = None

    def _base_path(self) -> Path | None:
        """현재 설정된 작업 대상 디렉터리 경로 반환."""
        return self._base_path_provider()

    def ensure_processor(self) -> RenameHashedFile:
        """RenameHashedFile 엔진 인스턴스 지연 생성 및 반환.

        프로세서의 작업 대상 경로가 사용자의 최신 선택을 반영하도록 보장.

        Returns:
            설정 완료된 RenameHashedFile 인스턴스.
        """
        if self.processor is None:
            bp = self._base_path()
            self.processor = RenameHashedFile(
                self.log_queue, self.progress_queue, self.get_string, base_path=bp
            )
        else:
            bp = self._base_path()
            if bp is not None:
                self.processor.set_base_path(bp)
        return self.processor

    def validate_manifest(self) -> tuple[bool, str | None]:
        """매니페스트 데이터베이스 또는 디렉터리 존재 여부 검증.

        Returns:
            (유효_여부, 에러_코드) 튜플:
            - 유효한 경우: (True, None)
            - 기본 경로 미설정 시: (False, 'no_base_path')
            - DB 및 디렉터리 모두 부재 시: (False, 'db_not_found')
        """
        bp = self._base_path()
        if bp is None:
            return False, "no_base_path"
        manifest_db_path = bp / "manifest.db"
        manifest_dir = bp / "manifest"
        if not manifest_db_path.exists() and not manifest_dir.is_dir():
            return False, "db_not_found"
        return True, None

    def start_processing(self) -> threading.Thread:
        """백그라운드 파일 이름 복원 워커 스레드 생성 및 시작.

        워커 스레드 시작 직전에 이전 실행의 취소 신호를 초기화(reset_cancel)하여,
        스레드 시작 이후 전파되는 cancel() 신호가 유실되지 않도록 보장.

        Returns:
            실행 중인 데몬 threading.Thread 인스턴스.
        """
        proc = self.ensure_processor()
        proc.set_get_string_func(self.get_string)
        bp = self._base_path()
        if bp is not None:
            proc.set_base_path(bp)
        # 워커 스레드 시작 직전에 이전 실행의 취소 신호를 초기화하여 잔존 취소 상태 제거
        proc.reset_cancel()
        thread = threading.Thread(target=proc.process_files, daemon=True)
        thread.start()
        return thread

    def cancel(self) -> None:
        """진행 중인 파일 이름 복원 프로세서에 협력적 취소 신호 전파.

        프로세서가 아직 생성되지 않은 경우 아무 동작도 수행하지 않으며,
        존재 시 process_files() 내부 루프가 조기 종료되도록 취소 이벤트를 설정.
        """
        if self.processor is not None:
            self.processor.cancel()

    def classify_result(self, processor: RenameHashedFile) -> dict[str, Any]:
        """프로세서로부터 실행 완료 메트릭 추출 및 요약.

        Args:
            processor: 작업 완료된 RenameHashedFile 인스턴스.

        Returns:
            'total_processed', 'has_error', 'unprocessed', 'total_files' 키를 포함하는 딕셔너리.
        """
        total_processed = getattr(processor, "processed_count_rename", 0) + getattr(processor, "processed_count_check", 0)
        has_error = getattr(processor, "has_error", False)
        unprocessed = getattr(processor, "unprocessed_files", [])
        total_files = getattr(processor, "total_files", 0)
        return {
            "total_processed": total_processed,
            "has_error": has_error,
            "unprocessed": list(unprocessed),
            "total_files": total_files,
        }

    def generate_error_log(self, unprocessed_files: list[str], error_message: str | None) -> None:
        """실패 및 미매칭 파일에 대한 표준화된 에러 로그 리포트 파일 생성.

        통합 헤더 및 에러 항목 포맷터를 활용하여
        logs/RenamerLog_YYYY-MM-DD_HHMMSS.log 경로에 기록.

        Args:
            unprocessed_files: 매칭에 실패한 미처리 파일 경로 목록.
            error_message: 예외 발생 시의 에러 메시지.
        """
        try:
            app_base = get_application_base_path()
            target_base = self._base_path()
            extra_report = [
                f"[REPORT]  Target Folder:   {target_base if target_base else 'Unknown'}",
                f"[REPORT]  Total Failed:    {len(unprocessed_files)}",
            ]
            if error_message:
                extra_report.append(f"[REPORT]  Fatal Error:     {error_message}")
            opened = open_task_log("RenamerLog", "Renamer Task Log", app_base, extra_report)
            if opened is None:
                return
            _log_path, f, now_ts = opened
            try:
                reason = self.get_string("backend_unprocessed_error", error="Hash mismatch or unknown format")
                write_log_items(
                    f,
                    unprocessed_files,
                    item_header="[ERROR ITEM #{idx}]",
                    timestamp=now_ts,
                    context="File Rename",
                    message_fn=lambda _: reason,
                )
            finally:
                f.close()
        except OSError as e:
            logger.exception("Failed to write RenamerLog: %s", e)
