from __future__ import annotations
import os
import shutil
import sqlite3
import contextlib
import hashlib
import concurrent.futures
import threading
import xxhash
from typing import Callable
from collections.abc import Sequence
from queue import Queue
from pathlib import Path

from src.constants import RENAMER_TARGET_FOLDERS, HASH_CHUNK_SIZE, SHA1_LENGTH
from src.queue_events import LogEvent, ProgressEvent
from src.utils.base_path import get_application_base_path

class RenameHashedFile:
    # --- 백엔드 클래스 초기화 메서드 ---
    def __init__(self, log_queue: Queue, progress_queue: Queue, get_string_func: Callable[[str], str], base_path: Path | None = None) -> None:
        """
        RenameHashedFile 클래스의 인스턴스를 초기화합니다.
        
        Args:
            log_queue (queue.Queue): 로그 메시지를 GUI로 보내기 위한 큐.
            progress_queue (queue.Queue): 진행률 정보를 GUI로 보내기 위한 큐.
            get_string_func (function): 다국어 문자열을 반환하는 GUI의 함수.
            base_path (Path | None): 프로그램 실행 기준 경로. None이면 자동 감지.
        """
        # 프로그램 실행 기준 경로 (os.getcwd() 대신 안전한 절대 경로 사용)
        if base_path is not None:
            self.base_path = base_path
        else:
            self.base_path = get_application_base_path()
        
        self.target_folders: Sequence[str] = RENAMER_TARGET_FOLDERS  # 파일 이름 변경 작업을 수행할 대상 폴더 목록
        self.hash_list: dict[str, str] = {}  # DB 및 매니페스트에서 불러온 {해시: 파일명} 데이터를 저장할 딕셔너리
        self.content_hash_map: dict[str, str] = {}  # {콘텐츠 해시: 파일명} 딕셔너리
        self.unprocessed_files: list[str] = []  # 1차 해시 대조에서 실패한 파일들의 경로를 저장할 리스트
        self.log_queue = log_queue  # GUI와의 통신을 위한 큐 참조
        self.progress_queue = progress_queue
        self.get_string = get_string_func
        self._rename_lock = threading.Lock()

        self.total_files: int = 0
        self.processed_count_rename: int = 0
        self.processed_count_check: int = 0
        self.has_error: bool = False
        self.error_message: str | None = None

    def set_get_string_func(self, get_string_func: Callable[[str], str]) -> None:
        """GUI에서 언어가 변경되었을 때, 이 클래스가 사용하는 번역 함수를 업데이트합니다."""
        self.get_string = get_string_func

    def set_base_path(self, new_base_path: Path) -> None:
        """사용자가 GUI에서 새 대상 폴더를 선택했을 때 기준 경로를 업데이트합니다."""
        self.base_path = new_base_path

    # --- GUI로의 정보 전달 메서드 ---
    def _add_log_event(self, key: str, **kwargs) -> None:
        self.log_queue.put(LogEvent(key=key, kwargs=kwargs))
        
    def _add_progress_event(self, value: int, current: int, total: int) -> None:
        self.progress_queue.put(ProgressEvent(value=value, current=current, total=total))

    def log(self, key: str, **kwargs) -> None:
        """로그 메시지를 GUI 통신 큐에 추가하는 public API입니다."""
        self._add_log_event(key, **kwargs)

    def update_progress(self, value: int, current: int, total: int) -> None:
        """진행률 정보를 GUI 통신 큐에 추가하는 public API입니다."""
        self._add_progress_event(value, current, total)

    def load_manifests(self) -> None:
        """
        manifest/ 폴더의 텍스트 매니페스트 파일들과 manifest.db 파일로부터
        파일명 해시(SHA1) 및 콘텐츠 해시 -> 원본 경로 매핑을 메모리로 로드합니다.
        """
        self.hash_list.clear()
        self.content_hash_map.clear()

        # 1. manifest/ 폴더 내 텍스트 매니페스트 파일들 먼저 로드
        manifest_dir = self.base_path / "manifest"
        if manifest_dir.is_dir():
            for manifest_file in manifest_dir.glob("*"):
                if not manifest_file.is_file():
                    continue
                try:
                    with open(manifest_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split(",")
                            if len(parts) >= 2:
                                target_path = parts[0].strip()
                                if target_path and ("/" in target_path or "\\" in target_path):
                                    target_clean = target_path.replace("\\", "/")
                                    basename = Path(target_clean).name
                                    sha1_name = hashlib.sha1(basename.encode("utf-8")).hexdigest().lower()
                                    self.hash_list[sha1_name] = target_clean

                                    sha1_full = hashlib.sha1(target_clean.encode("utf-8")).hexdigest().lower()
                                    if sha1_full not in self.hash_list:
                                        self.hash_list[sha1_full] = target_clean

                                    content_hash = parts[1].strip().lower()
                                    if content_hash:
                                        self.content_hash_map[content_hash] = target_clean
                except Exception:
                    pass

        # 2. manifest.db 파일 로드 (최신 권한 데이터로 덮어쓰기/보강)
        manifest_db_path = self.base_path / "manifest.db"
        if manifest_db_path.exists():
            with contextlib.closing(sqlite3.connect(manifest_db_path)) as connection:
                cursor = connection.cursor()
                cursor.execute("PRAGMA table_info(t)")
                cols = [row[1].lower() for row in cursor.fetchall()]
                if "k" in cols and "v" in cols:
                    cursor.execute("SELECT k, v FROM t")
                elif "name" in cols and "hash" in cols:
                    cursor.execute("SELECT name, hash FROM t")
                else:
                    cursor.execute("SELECT * FROM t")

                rows = cursor.fetchall()
                for row in rows:
                    target_path = str(row[0]).strip()
                    target_clean = target_path.replace("\\", "/")
                    basename = Path(target_clean).name
                    sha1_name = hashlib.sha1(basename.encode("utf-8")).hexdigest().lower()
                    self.hash_list[sha1_name] = target_clean

                    sha1_full = hashlib.sha1(target_clean.encode("utf-8")).hexdigest().lower()
                    if sha1_full not in self.hash_list:
                        self.hash_list[sha1_full] = target_clean

                    if len(row) > 1 and row[1]:
                        content_hash = str(row[1]).strip().lower()
                        if content_hash:
                            self.content_hash_map[content_hash] = target_clean

    # --- 메인 파일 처리 로직 ---
    def process_files(self) -> None:
        """파일 이름 변경 작업의 전체 과정을 순차적으로 실행합니다."""
        self.has_error = False
        self.error_message = None
        self.processed_count_rename = 0
        self.processed_count_check = 0
        self.unprocessed_files.clear()
        self.total_files = 0

        try:
            # 1. manifest.db 또는 manifest 폴더 존재 확인
            manifest_db_path = self.base_path / "manifest.db"
            manifest_dir = self.base_path / "manifest"
            if not manifest_db_path.exists() and not manifest_dir.exists():
                self.log('backend_warning_db_not_found')
                self.has_error = True
                return
                
            # 2. 작업 시작 안내 로그 전송
            self.log('backend_info_long_time')
            self.log('backend_info_auto_rename')
            self.log('backend_searching_files')
            
            # 3. 대상 폴더에서 모든 처리 대상 파일 검색
            files = self.get_all_files_in_folders(self.target_folders)
            self.total_files = len(files)
            
            self.update_progress(0, 0, self.total_files)  # 진행률 0%로 초기화

            if not files:  # 처리할 파일이 없으면 작업 종료
                self.log('backend_no_files_found')
                return
                
            self.log('backend_found_files', count=self.total_files)

            # 4. manifest.db 및 manifest 폴더에서 매니페스트 해시 매핑 로드
            self.load_manifests()

            # 5. ThreadPoolExecutor를 사용한 병렬 파일 처리
            final_unprocessed_files = []
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(self.process, file): file for file in files}
                
                processed_futures = 0
                for future in concurrent.futures.as_completed(futures):
                    processed_futures += 1
                    progress = int((processed_futures / self.total_files) * 100.0)
                    self.update_progress(progress, processed_futures, self.total_files)
                    
                    try:
                        was_successful, data = future.result()
                        if was_successful:
                            self.processed_count_rename += 1
                        else:
                            self.unprocessed_files.append(data)
                    except Exception as exc:
                        file_path = futures[future]
                        self.log('backend_file_process_fail', path=file_path, exc=str(exc))
                        self.unprocessed_files.append(file_path)

            # 6. 1차 처리에서 실패한 파일들에 대한 예외 처리 로직
            if self.unprocessed_files:
                self.log('backend_unprocessed_header')
                for file_path in self.unprocessed_files:
                    renamed_by_content = False
                    try:
                        # 파일의 첫 줄을 읽어 파일 유형을 추측 (매니페스트 파일 대상)
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                            first_line = file.readline().strip()
                        
                        # 특정 경로 문자열이 포함되어 있으면 해당 매니페스트 파일로 간주
                        new_filename = None
                        if 'a/bdl' in first_line: new_filename = os.path.join("manifest", "bdl_assetmanifest")
                        elif 'manifest/' in first_line: new_filename = os.path.join("manifest", "manifest_assetmanifest")
                        elif 'm/' in first_line: new_filename = os.path.join("manifest", "movie2manifest")
                        elif 'b/' in first_line: new_filename = os.path.join("manifest", "soundmanifest")
                        
                        if new_filename:
                            new_filepath = self.get_unique_filename(self.base_path / new_filename)
                            new_filepath.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(file_path), str(new_filepath))
                            self.processed_count_check += 1
                            try:
                                relative_file_path = Path(file_path).relative_to(self.base_path)
                            except ValueError:
                                relative_file_path = Path(file_path)
                            
                            self.log('backend_rename_exception_block', original=str(relative_file_path), new=str(Path(new_filename)))
                            renamed_by_content = True
                    except OSError as e:
                        self.log('backend_unprocessed_error', error=str(e))
                    
                    # 예외 처리 로직으로도 이름 변경에 실패한 경우, 최종 미처리 파일 목록에 추가
                    if not renamed_by_content:
                        final_unprocessed_files.append(file_path)

            # 7. 최종 작업 결과 요약 로그 전송
            total_processed = self.processed_count_rename + self.processed_count_check
            self.log('backend_job_summary', total_processed=total_processed)
            if final_unprocessed_files:
                self.log('backend_unprocessed_summary', count=len(final_unprocessed_files))


        except Exception as exc:
            self.has_error = True
            self.error_message = str(exc)
            self.log('backend_file_process_fail', path='manifest', exc=str(exc))

    # --- 개별 파일 처리 ---
    def process(self, file_path: str) -> tuple[bool, str]:
        """
        단일 파일에 대해 해시(파일명 SHA1, stem SHA1, 콘텐츠 xxHash64/MD5)를 대조하여 이름 변경을 시도합니다.
        
        Returns:
            (bool, str): (성공 여부, 파일 경로) 튜플을 반환.
        """
        file_name = Path(file_path).name.lower()

        # 1. 파일 이름(SHA1 해시)으로 직접 대조 (O(1) 메모리 조회)
        if file_name in self.hash_list:
            return self.rename_file(file_path, self.hash_list[file_name])

        # 2. 확장자가 붙어 있는 경우 stem으로 대조
        file_stem = Path(file_path).stem.lower()
        if file_stem in self.hash_list:
            return self.rename_file(file_path, self.hash_list[file_stem])

        # 3. 파일 내용 해시 대조 (단일 스트림 순회로 xxHash64와 MD5 동시 계산)
        try:
            hash_xxhash64_value, hash_md5_value = self.calculate_dual_hashes(file_path)
            if hash_xxhash64_value in self.content_hash_map:
                return self.rename_file(file_path, self.content_hash_map[hash_xxhash64_value])
            if hash_xxhash64_value in self.hash_list:
                return self.rename_file(file_path, self.hash_list[hash_xxhash64_value])
            if hash_md5_value in self.content_hash_map:
                return self.rename_file(file_path, self.content_hash_map[hash_md5_value])
            if hash_md5_value in self.hash_list:
                return self.rename_file(file_path, self.hash_list[hash_md5_value])
        except Exception:
            pass

        # 모든 해시 불일치 시, 처리 실패로 간주하고 원본 파일 경로 반환
        return False, file_path

    def rename_file(self, file_path: str, new_filename: str) -> tuple[bool, str]:
        """실제로 파일의 이름을 변경하고, 성공 또는 실패 결과를 로그로 남깁니다."""
        new_filepath = self.base_path / Path(new_filename)
        new_filepath.parent.mkdir(parents=True, exist_ok=True)  # 대상 폴더가 없으면 생성

        # 이름 변경하려는 파일이 이미 존재할 경우, 중복을 피하기 위해 새 이름 생성
        with self._rename_lock:
            # 원본과 변경 대상이 이미 동일한 경로인 경우 성공 처리
            try:
                if Path(file_path).resolve() == new_filepath.resolve():
                    return True, str(new_filepath)
            except Exception:
                pass

            if new_filepath.exists():
                new_filepath = self.get_unique_filename(new_filepath)
                
            try:
                shutil.move(str(file_path), str(new_filepath))
                try:
                    relative_file_path = Path(file_path).relative_to(self.base_path)  # 로그에 표시할 상대 경로
                except ValueError:
                    relative_file_path = Path(file_path)
                
                self.log('backend_rename_block', original=str(relative_file_path), new=str(Path(new_filename)))
                return True, str(new_filepath)
            except (OSError, PermissionError) as e:
                self.log('backend_rename_error', error=str(e))
                return False, file_path

    # --- 유틸리티 메서드 ---
    def calculate_dual_hashes(self, file_path: str) -> tuple[str, str]:
        """단일 스트림 순회로 xxHash64와 MD5를 동시에 계산합니다."""
        xxhash64_hash = xxhash.xxh64()
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(HASH_CHUNK_SIZE), b""):
                xxhash64_hash.update(chunk)
                md5_hash.update(chunk)
        return xxhash64_hash.hexdigest().lower(), md5_hash.hexdigest().lower()

    def get_all_files_in_folders(self, target_folders: Sequence[str]) -> list[str]:
        """지정된 모든 폴더와 그 하위 폴더를 재귀적으로 탐색하여 SHA1 형식의 파일 목록을 반환합니다."""
        all_files = []
        for folder in target_folders:
            folder_path = self.base_path / folder
            if folder_path.is_dir():
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        if self.is_sha1(file_name):  # 파일명이 SHA1 형식인지 확인
                            all_files.append(str(Path(root) / file_name))
        return all_files

    def is_sha1(self, s: str) -> bool:
        """주어진 문자열이 SHA1 해시 형식(길이 40의 16진수 문자열)인지 확인합니다."""
        return len(s) == SHA1_LENGTH and all(c in "0123456789abcdefABCDEF" for c in s)

    def get_unique_filename(self, file_path: Path) -> Path:
        """
        주어진 파일 경로가 이미 존재할 경우, 중복되지 않는 새 파일 경로를 생성하여 반환합니다.
        예: 'file.txt' -> 'file_(Duplicate_1).txt'
        """
        counter = 1
        new_file_path = file_path
        while new_file_path.exists():
            new_file_path = file_path.with_name(f"{file_path.stem}_(Duplicate_{counter}){file_path.suffix}")
            counter += 1
        return new_file_path
