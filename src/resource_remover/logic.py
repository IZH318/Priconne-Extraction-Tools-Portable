from __future__ import annotations
import os
import logging
from pathlib import Path
from datetime import datetime
from collections.abc import Sequence
from send2trash import send2trash

from src.utils.base_path import get_application_base_path

# 삭제 대상에서 제외할 보호 디렉터리 목록 (개발 환경 안전장치)
_PROTECTED_DIRS: frozenset[str] = frozenset({
    'src', 'tests', '.git', '.github', '.venv', 'venv',
    'node_modules', '__pycache__', '.mypy_cache',
})

class ResourceRemoverLogic:
    def __init__(self, base_path: str | Path | None = None) -> None:
        """
        ResourceRemoverLogic 인스턴스를 초기화합니다.

        Args:
            base_path (str | Path | None): 리소스 파일을 검색할 기준 경로.
                None인 경우 실행 파일 기준 경로를 자동 감지합니다.
                PyInstaller 빌드 환경에서도 안전하게 동작합니다.
        """
        if base_path is not None:
            self.base_path = Path(base_path).resolve()
        else:
            self.base_path = get_application_base_path()

    def count_resources(self, extensions_to_remove: Sequence[str]) -> list[Path]:
        """
        주어진 확장자에 해당하는 파일 수를 삭제하지 않고 카운트합니다.
        매칭되는 파일들의 Path 객체 리스트를 반환합니다.

        Note:
            보호 디렉터리(_PROTECTED_DIRS)는 순회 대상에서 자동 제외됩니다.
        """
        found_files = []
        target_exts = tuple(extensions_to_remove)
        search_path = self.base_path

        for root, dirs, files in os.walk(search_path):
            # 보호 디렉터리를 순회 대상에서 제외 (in-place 수정으로 os.walk에 반영)
            dirs[:] = [d for d in dirs if d not in _PROTECTED_DIRS]
            for file in files:
                if file.lower().endswith(target_exts):
                    found_files.append(Path(root) / file)
        return found_files

    def remove_resources(self, target_files: Sequence[Path | str], extensions_to_remove: Sequence[str], use_trash: bool = True) -> tuple[int, list[str], str]:
        """
        제공된 리소스 파일들을 삭제하고 삭제된 파일 수를 반환합니다.
        치명적 오류 발생 시 예외를 발생시킵니다.
        """
        
        deleted_files = []
        errors = []
        for file_path in target_files:
            try:
                if use_trash:
                    send2trash(file_path)
                else:
                    os.remove(file_path)
                deleted_files.append(str(file_path))  # 로그 기록용 문자열 변환
            except Exception as e:
                errors.append(f"{file_path}: {e}")
                
        # 로그 파일 생성
        log_filename: Path | None = None
        if deleted_files or errors:
            now = datetime.now()
            timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
            # 로그 파일이 중앙 집중된 logs 폴더에 생성되도록 보장
            log_dir = get_application_base_path() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_filename = log_dir / f"DeletionLog_{timestamp_str}.log"
            try:
                import platform
                import multiprocessing
                from src.constants import SEPARATOR_LONG, APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER
                
                python_ver = platform.python_version()
                os_ver = platform.platform()
                cpu_cores = multiprocessing.cpu_count()
                
                exec_path = str(get_application_base_path())

                with open(log_filename, 'w', encoding='utf-8') as f:
                    f.write(f"{SEPARATOR_LONG}\n")
                    f.write(f"[SESSION] Resource Deletion Log Started at {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                    f.write(f"{SEPARATOR_LONG}\n")
                    f.write(f"[TOOL]    App Version:     {APP_VERSION} ({APP_LAST_UPDATE})\n")
                    f.write(f"[TOOL]    Developer:       {APP_DEVELOPER}\n")
                    f.write(f"[ENGINE]  Python Version:  {python_ver}\n")
                    f.write(f"[SYSTEM]  OS Version:      {os_ver}\n")
                    f.write(f"[SYSTEM]  Processor Count: {cpu_cores} Cores\n")
                    f.write(f"[PATH]    Exec Path:       {exec_path}\n")
                    f.write(f"[REPORT]  Target Exts:     {', '.join(extensions_to_remove)}\n")
                    f.write(f"[REPORT]  Moved to Trash:  {use_trash}\n")
                    f.write(f"[REPORT]  Total Deleted:   {len(deleted_files)}\n")
                    f.write(f"[REPORT]  Total Errors:    {len(errors)}\n")
                    f.write(f"{SEPARATOR_LONG}\n\n")

                    if deleted_files:
                        for idx, p in enumerate(deleted_files, 1):
                            f.write(f"[OK ITEM #{idx}]\n")
                            f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                            f.write(f"Context   : Resource Deletion\n")
                            f.write(f"File      : {p}\n")
                            f.write(f"{SEPARATOR_LONG}\n\n")
                            
                    if errors:
                        for idx, e in enumerate(errors, 1):
                            f.write(f"[ERROR ITEM #{idx}]\n")
                            f.write(f"Timestamp : {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
                            f.write(f"Context   : Resource Deletion\n")
                            f.write(f"Message   : {e}\n")
                            f.write(f"{SEPARATOR_LONG}\n\n")
            except OSError as e:
                import logging
                logging.warning("Failed to create log file %s: %s", log_filename, e)
                log_filename = None  # 로그 파일 생성 실패 표시
                
        return len(deleted_files), errors, str(log_filename) if log_filename else ""

