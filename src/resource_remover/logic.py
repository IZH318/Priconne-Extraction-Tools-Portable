"""원본 게임 리소스 파일 탐색 및 안전 삭제 비즈니스 로직 모듈.

에셋 추출 완료 후 불필요해진 원본 클라이언트 캐시 파일(.unity3d, .acb, .awb, .usm 등)
디스크 검색 후 휴지통(send2trash) 이동 또는 영구 삭제.
개발 환경 소스코드 및 형상관리 폴더 보호용 _PROTECTED_DIRS 필터링 및
루트 디렉터리 탈출 방지(is_relative_to) 안전장치 내장.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from src.utils.base_path import get_application_base_path

logger = logging.getLogger(__name__)

# 삭제 대상에서 엄격히 제외할 시스템/개발 보호 디렉터리 화이트리스트
_PROTECTED_DIRS: frozenset[str] = frozenset({
    'src', 'tests', '.git', '.github', '.venv', 'venv',
    'node_modules', '__pycache__', '.mypy_cache',
})


class ResourceRemoverLogic:
    """원본 리소스 파일 검색, 유효성 검증 및 삭제를 수행하는 도메인 로직 클래스."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        """ResourceRemoverLogic 초기화.

        Args:
            base_path (str | Path | None): 리소스 파일 검색 기준 루트 경로.
                None인 경우 실행 파일 기준 경로(get_application_base_path()) 자동 감지 적용.
        """
        if base_path is not None:
            self.base_path = Path(base_path).resolve()
        else:
            self.base_path = get_application_base_path()

    def count_resources(self, extensions_to_remove: Sequence[str]) -> list[Path]:
        """지정 확장자 파일 검색 및 삭제 대상 목록 반환.

        보호 디렉터리(_PROTECTED_DIRS)는 os.walk의 dirs 슬라이싱을 통해 순회 대상 즉시 배제.

        Args:
            extensions_to_remove (Sequence[str]): 검색할 대상 확장자 목록 (예: ['.unity3d', '.awb']).

        Returns:
            list[Path]: 발견된 일치 파일들의 절대 Path 객체 리스트.
        """
        found_files = []
        target_exts = tuple(extensions_to_remove)
        search_path = self.base_path

        for root, dirs, files in os.walk(search_path):
            # 최상위 루트 순회 시 개발 보호 디렉터리를 사전 배제 (in-place 수정)
            if Path(root).resolve() == search_path:
                dirs[:] = [d for d in dirs if d not in _PROTECTED_DIRS]
            for file in files:
                if file.lower().endswith(target_exts):
                    found_files.append(Path(root) / file)
        return found_files

    def remove_resources(
        self,
        target_files: Sequence[Path | str],
        extensions_to_remove: Sequence[str],
        use_trash: bool = True,
    ) -> tuple[int, list[str], str]:
        """선택 리소스 파일 삭제(또는 휴지통 이동) 및 결과 리포트 반환.

        보안 검증 단계:
        1. 경로 격리 검증: 대상 파일이 self.base_path 하위에 존재하는지 확인 (is_relative_to).
        2. 확장자 검증: 허용된 확장자 목록(extensions_to_remove)에 속하는지 재확인.
        3. 안전 삭제: use_trash=True인 경우 send2trash로 휴지통 복구 가능하게 이동, False면 영구 삭제.
        4. 감사 로그 작성: 성공 및 실패 항목을 logs/DeletionLog_*.log에 기록.

        Args:
            target_files (Sequence[Path | str]): 삭제 대상 파일 경로 시퀀스.
            extensions_to_remove (Sequence[str]): 허용된 삭제 대상 확장자 시퀀스.
            use_trash (bool): True이면 OS 휴지통으로 이동, False이면 즉시 영구 삭제.

        Returns:
            tuple[int, list[str], str]: (삭제 성공 파일 수, 에러 메시지 리스트, 생성된 로그 파일 경로 문자열).
        """
        deleted_files = []
        errors = []
        allowed_exts = tuple(extensions_to_remove)
        for file_path in target_files:
            try:
                p = Path(file_path).resolve()
                # 1. 대상 경로가 베이스 디렉터리 내부에 포함되어 있는지 검증
                if not p.is_relative_to(self.base_path):
                    errors.append(f"{file_path}: path outside base directory")
                    continue
                # 2. 허용된 확장자인지 재검증
                if not p.name.lower().endswith(allowed_exts):
                    errors.append(f"{file_path}: extension not allowed")
                    continue
                # 3. 휴지통 이동 또는 영구 삭제 수행
                if use_trash:
                    send2trash(p)
                else:
                    os.remove(p)
                deleted_files.append(str(p))
            except OSError as e:
                errors.append(f"{file_path}: {e}")

        # 4. 삭제 결과 로그 파일 작성
        log_filename: Path | None = None
        if deleted_files or errors:
            now = datetime.now()
            timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
            log_dir = get_application_base_path() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_filename = log_dir / f"DeletionLog_{timestamp_str}.log"
            try:
                from src.constants import (
                    APP_DEVELOPER,
                    APP_LAST_UPDATE,
                    APP_VERSION,
                    SEPARATOR_LONG,
                )
                from src.utils.error_log import write_log_header

                app_info = {'APP_VERSION': APP_VERSION, 'APP_LAST_UPDATE': APP_LAST_UPDATE, 'APP_DEVELOPER': APP_DEVELOPER}
                extra_report = [
                    f"[REPORT]  Target Exts:     {', '.join(extensions_to_remove)}",
                    f"[REPORT]  Moved to Trash:  {use_trash}",
                    f"[REPORT]  Total Deleted:   {len(deleted_files)}",
                    f"[REPORT]  Total Errors:    {len(errors)}",
                ]

                with open(log_filename, 'w', encoding='utf-8') as f:
                    now = write_log_header(f, "Resource Deletion Log", get_application_base_path(), app_info, extra_report)

                    if deleted_files:
                        for idx, del_path in enumerate(deleted_files, 1):
                            f.write(f"[OK ITEM #{idx}]\n")
                            f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                            f.write("Context   : Resource Deletion\n")
                            f.write(f"File      : {del_path}\n")
                            f.write(f"{SEPARATOR_LONG}\n\n")

                    if errors:
                        from src.utils.error_log import write_log_items
                        write_log_items(f, errors, item_label="Message", item_header="[ERROR ITEM #{idx}]", timestamp=now, context="Resource Deletion")
            except (OSError, ImportError, ValueError) as e:
                logger.warning("Failed to create log file %s: %s", log_filename, e)
                log_filename = None

        return len(deleted_files), errors, str(log_filename) if log_filename else ""


