"""Unity Converter 에셋 추출 서비스 모듈.

Unity3D 변환기 모듈의 입력 검증, 워커 스레드 간 라운드로빈 배치 분할,
표준화된 배치 에러 리포트 생성 로직 제공.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants import APP_DEVELOPER, APP_LAST_UPDATE, APP_VERSION
from src.utils.base_path import get_application_base_path
from src.utils.error_log import write_log_header, write_log_items

logger = logging.getLogger(__name__)


class UnityExtractionService:
    """Unity3D 에셋 추출 워크플로 서비스 클래스.

    입력 검증, 워커 배치 분할, 실패 리포팅 조정.

    Attributes:
        _shared_state: 공유 의존성 컨테이너.
        _controller: 상위 MVC 컨트롤러 참조.
    """

    def __init__(
        self,
        shared_state: Any = None,
        controller: Any = None,
    ) -> None:
        """UnityExtractionService 초기화.

        Args:
            shared_state: 콜백 및 구성을 제공하는 SharedState 객체.
            controller: 상위 컨트롤러 참조.
        """
        self._shared_state = shared_state
        self._controller = controller
        if shared_state is not None and callable(getattr(shared_state, "get_lang_dict", None)):
            self._get_lang_dict = shared_state.get_lang_dict
        elif controller is not None and hasattr(controller, "get_lang_dict"):
            self._get_lang_dict = controller.get_lang_dict
        else:
            self._get_lang_dict = dict

    def get_lang_dict(self) -> dict[str, str]:
        """현재 활성화된 언어 번역 딕셔너리 안전 조회.

        Returns:
            번역 키와 로컬라이즈된 문자열 매핑 딕셔너리.
        """
        try:
            return self._get_lang_dict() or {}
        except (TypeError, ValueError, AttributeError, RuntimeError):
            return {}

    # ------------------------------------------------------------------
    # 검증 메서드
    # ------------------------------------------------------------------
    def validate_start(self, file_paths: Any = None, output_path: Any = None) -> tuple[bool, str | None]:
        """입력 대상 파일 및 출력 디렉터리 경로 설정 여부 사전 검증.

        Args:
            file_paths: 번들 파일 경로 리스트.
            output_path: 출력 디렉터리 경로 문자열.

        Returns:
            (유효_여부, 에러_코드) 튜플:
            - 유효한 경우: (True, None)
            - 파일 미선택 시: (False, 'no_files')
            - 출력 경로 미지정 시: (False, 'no_output')
        """
        if file_paths is None and self._controller is not None:
            file_paths = getattr(self._controller, "file_paths", None)
        if output_path is None and self._controller is not None:
            output_path = getattr(self._controller, "output_path", None)

        if not file_paths:
            return False, "no_files"
        if not output_path:
            return False, "no_output"
        return True, None

    def validate_extraction(self, file_paths: Any = None, output_path: Any = None) -> tuple[bool, str | None]:
        """validate_start 호환성 별칭 메서드."""
        return self.validate_start(file_paths, output_path)

    def validate_files(self, file_paths: Any = None, output_path: Any = None) -> tuple[bool, str | None]:
        """validate_start 호환성 별칭 메서드."""
        return self.validate_start(file_paths, output_path)

    # ------------------------------------------------------------------
    # 배치 분할 메서드
    # ------------------------------------------------------------------
    def prepare_batches(self, file_paths: Any = None) -> list[list[str]]:
        """CPU 코어 수에 맞추어 입력 파일 목록을 워커별 라운드로빈 배치로 분할.

        Args:
            file_paths: 대상 번들 파일 경로 리스트.

        Returns:
            워커별 처리 대상 파일 경로 서브리스트 목록.
        """
        if file_paths is None and self._controller is not None:
            file_paths = getattr(self._controller, "file_paths", None)
        file_paths = list(file_paths or [])

        if not file_paths:
            return []

        cpu_count = (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or os.cpu_count() or 1
        num_workers = min(cpu_count, len(file_paths))
        batches: list[list[str]] = [[] for _ in range(num_workers)] if num_workers > 0 else []
        for idx, fp in enumerate(file_paths):
            if batches:
                batches[idx % num_workers].append(fp)
        batches = [b for b in batches if b]
        if not batches:
            batches = [list(file_paths)]
        return batches

    def prepare_file_batches(self, file_paths: Any = None) -> list[list[str]]:
        """prepare_batches 호환성 별칭 메서드."""
        return self.prepare_batches(file_paths)

    # ------------------------------------------------------------------
    # 에러 로그 생성 메서드
    # ------------------------------------------------------------------
    def generate_error_log(
        self,
        failed_files: Any,
        base_input_path: Any = None,
        output_path: Any = None,
        context: str = "Asset Extraction",
    ) -> None:
        """손상되거나 처리 실패한 번들 파일에 대한 표준화된 에러 로그 리포트 파일 생성.

        통합 헤더 및 항목 번호 포맷터를 활용하여
        logs/UnityConverterLog_YYYY-MM-DD_HHMMSS.log 경로에 기록.

        Args:
            failed_files: 실패한 파일 경로 또는 (경로, 원인) 튜플 컬렉션.
            base_input_path: 로깅 컨텍스트용 공통 입력 루트 폴더 경로.
            output_path: 로깅 컨텍스트용 출력 디렉터리 경로.
            context: 컨텍스트 식별 문자열 (예: 'Asset Extraction', 'Asset Preview').
        """
        try:
            exec_path = None
            if self._shared_state is not None and callable(getattr(self._shared_state, "get_base_path", None)):
                try:
                    bp = self._shared_state.get_base_path()
                    if bp is not None:
                        exec_path = str(bp)
                except (TypeError, ValueError, AttributeError, RuntimeError):
                    exec_path = None
            if exec_path is None and self._controller is not None and getattr(self._controller, "base_path", None):
                exec_path = str(self._controller.base_path)
            if exec_path is None:
                exec_path = str(get_application_base_path())

            log_dir = Path(exec_path) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            now = datetime.now()
            log_filename = log_dir / f"UnityConverterLog_{now.strftime('%Y-%m-%d_%H%M%S')}.log"

            app_info = {
                "APP_VERSION": APP_VERSION,
                "APP_LAST_UPDATE": APP_LAST_UPDATE,
                "APP_DEVELOPER": APP_DEVELOPER,
            }
            extra_report = [
                f"[REPORT]  Context:         {context}",
                f"[REPORT]  Base Input:      {base_input_path if base_input_path else 'Files'}",
                f"[REPORT]  Output Path:     {output_path if output_path else 'Temp/Preview'}",
                f"[REPORT]  Total Failed:    {len(failed_files or [])}",
            ]

            with open(log_filename, "w", encoding="utf-8") as f:
                now_ts = write_log_header(f, "Unity Converter Task Log", exec_path, app_info, extra_report)
                write_log_items(
                    f,
                    list(failed_files or []),
                    item_label="File",
                    item_header="[ERROR ITEM #{idx}]",
                    timestamp=now_ts,
                    context=context,
                    reason_fn=lambda item: (item[1] if isinstance(item, (tuple, list)) and len(item) > 1 else str(item) or "").strip()
                    or "Unknown",
                )
        except (OSError, ValueError, TypeError) as e:
            logger.error("Failed to write UnityConverterLog: %s", e)

    def completion_message(self, total_extracted_assets: int = 0, cancelled: bool = False) -> str | None:
        """작업 완료 메시지 훅 메서드 (항상 None 반환)."""
        return None
