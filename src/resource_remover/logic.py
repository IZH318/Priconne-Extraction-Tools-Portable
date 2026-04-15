from __future__ import annotations
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from collections.abc import Sequence
from send2trash import send2trash

from src.constants import SEPARATOR_SHORT

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
            # PyInstaller frozen 빌드 또는 일반 스크립트 실행 환경 자동 감지
            if getattr(sys, 'frozen', False):
                self.base_path = Path(sys.executable).parent
            else:
                self.base_path = Path(__file__).resolve().parent.parent.parent

    def count_resources(self, extensions_to_remove: Sequence[str]) -> list[Path]:
        """
        주어진 확장자에 해당하는 파일 수를 삭제하지 않고 카운트합니다.
        매칭되는 파일들의 Path 객체 리스트를 반환합니다.
        """
        found_files = []
        target_exts = tuple(extensions_to_remove)
        search_path = self.base_path

        for root, dirs, files in os.walk(search_path):
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
            except OSError as e:
                errors.append(f"{file_path}: {e}")
                
        # 로그 파일 생성
        log_filename = ""
        if deleted_files or errors:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 로그 파일이 기준 경로에 생성되도록 보장
            log_dir = self.base_path
            log_filename = log_dir / f"deletion_log_{timestamp}.txt"
            try:
                with open(log_filename, 'w', encoding='utf-8') as f:
                    f.write(f"Resource Deletion Log - {timestamp}\n")
                    f.write(f"Base Path: {self.base_path}\n")
                    f.write(f"Target Extensions: {extensions_to_remove}\n")
                    f.write(f"Moved to Trash: {use_trash}\n")
                    f.write(f"{SEPARATOR_SHORT}\n")
                    f.write(f"Deleted: {len(deleted_files)} file(s)\n")
                    for p in deleted_files:
                        f.write(f"[OK] {p}\n")
                    if errors:
                        f.write(f"{SEPARATOR_SHORT}\n")
                        f.write(f"Errors: {len(errors)} file(s)\n")
                        for e in errors:
                            f.write(f"[ERROR] {e}\n")
            except OSError as e:
                logging.warning("Failed to create log file %s: %s", log_filename, e)
                log_filename = ""  # 로그 파일 생성 실패 표시
                
        return len(deleted_files), errors, str(log_filename)

