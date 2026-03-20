from __future__ import annotations
import os
import sqlite3
import hashlib
import concurrent.futures
import xxhash
from typing import Callable, Optional, Tuple, Any
from queue import Queue

from src.constants import SEPARATOR_LONG, RENAMER_TARGET_FOLDERS, HASH_CHUNK_SIZE, SHA1_LENGTH

# --- 상수 정의 ---
SEPARATOR: str = SEPARATOR_LONG

class RenameHashedFile:
    # --- 백엔드 클래스 초기화 메서드 ---
    def __init__(self, log_queue: Queue, progress_queue: Queue, get_string_func: Callable[[str], str]) -> None:
        """
        RenameHashedFile 클래스의 인스턴스를 초기화합니다.
        
        Args:
            log_queue (queue.Queue): 로그 메시지를 GUI로 보내기 위한 큐.
            progress_queue (queue.Queue): 진행률 정보를 GUI로 보내기 위한 큐.
            get_string_func (function): 다국어 문자열을 반환하는 GUI의 함수.
        """
        self.target_folders: list[str] = RENAMER_TARGET_FOLDERS  # 파일 이름 변경 작업을 수행할 대상 폴더 목록
        self.hash_list: dict[str, str] = {}  # DB에서 불러온 {해시: 파일명} 데이터를 저장할 딕셔너리
        self.unprocessed_files: list[str] = []  # 1차 해시 대조에서 실패한 파일들의 경로를 저장할 리스트
        self.log_queue = log_queue  # GUI와의 통신을 위한 큐 참조
        self.progress_queue = progress_queue
        self.get_string = get_string_func

    def set_get_string_func(self, get_string_func: Callable[[str], str]) -> None:
        """GUI에서 언어가 변경되었을 때, 이 클래스가 사용하는 번역 함수를 업데이트합니다."""
        self.get_string = get_string_func

    # --- GUI로의 정보 전달 메서드 ---
    def log(self, key: str, **kwargs) -> None:
        """로그 메시지를 생성하여 로그 큐에 넣습니다. GUI 스레드가 이를 가져가 화면에 표시합니다."""
        self.log_queue.put((key, kwargs))

    def update_progress(self, value: float, current: int, total: int) -> None:
        """진행률 정보를 생성하여 진행률 큐에 넣습니다."""
        self.progress_queue.put((value, current, total))

    # --- 메인 파일 처리 로직 ---
    def process_files(self) -> None:
        """파일 이름 변경 작업의 전체 과정을 순차적으로 실행합니다."""
        # 1. manifest.db 파일 존재 확인
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            self.log('backend_warning_db_not_found')
            return
            
        # 2. 작업 시작 안내 로그 전송
        self.log('backend_info_long_time')
        self.log('backend_info_auto_rename')
        self.log('backend_searching_files')
        
        # 3. 대상 폴더에서 모든 처리 대상 파일 검색
        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        
        self.update_progress(0, 0, total_files)  # 진행률 0%로 초기화

        if not files:  # 처리할 파일이 없으면 작업 종료
            self.log('backend_no_files_found')
            return
            
        self.log('backend_found_files', count=total_files)

        # 4. SQLite DB에 연결하여 해시 데이터를 메모리(self.hash_list)로 로드
        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename
        
        # 5. 처리 결과 카운트 변수 초기화
        processed_count_rename = 0  # 해시 대조로 이름 변경 성공 카운트
        processed_count_check = 0   # 예외 처리로 이름 변경 성공 카운트
        final_unprocessed_files = [] # 최종적으로 처리 실패한 파일 목록
        self.unprocessed_files.clear()

        # 6. ThreadPoolExecutor를 사용한 병렬 파일 처리
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 각 파일에 대해 process 함수를 실행하는 작업을 스레드 풀에 제출
            futures = {executor.submit(self.process, file): file for file in files}
            
            processed_futures = 0
            # as_completed: 작업이 완료되는 순서대로 결과를 반환받음
            for future in concurrent.futures.as_completed(futures):
                processed_futures += 1
                progress = (processed_futures / total_files) * 100.0
                self.update_progress(progress, processed_futures, total_files) # 진행률 업데이트
                
                try:
                    was_successful, data = future.result()  # 스레드 작업 결과 가져오기
                    if was_successful:
                        processed_count_rename += 1
                    else:  # 해시 불일치 파일
                        self.unprocessed_files.append(data)
                except Exception as exc:  # 스레드 내에서 예외 발생 시
                    file_path = futures[future]
                    self.log('backend_file_process_fail', path=file_path, exc=str(exc))

        # 7. 1차 처리에서 실패한 파일들에 대한 예외 처리 로직
        self.log('backend_unprocessed_header')
        if self.unprocessed_files:
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
                        new_filepath = self.get_unique_filename(new_filename)
                        os.rename(file_path, new_filepath)
                        processed_count_check += 1
                        relative_file_path = os.path.relpath(file_path, os.getcwd())
                        
                        self.log('backend_rename_exception_block', original=relative_file_path, new=new_filename.replace(os.sep, '\\'))
                        renamed_by_content = True
                except Exception as e:
                    self.log('backend_unprocessed_error', error=str(e))
                
                # 예외 처리 로직으로도 이름 변경에 실패한 경우, 최종 미처리 파일 목록에 추가
                if not renamed_by_content:
                    final_unprocessed_files.append(file_path)

        # 8. 최종 작업 결과 요약 로그 전송
        total_processed = processed_count_rename + processed_count_check
        self.log('backend_job_summary', total_processed=total_processed)
        if final_unprocessed_files:
            self.log('backend_unprocessed_summary', count=len(final_unprocessed_files))

    # --- 개별 파일 처리 ---
    def process(self, file_path: str) -> Tuple[bool, str]:
        """
        단일 파일에 대해 해시를 계산하고, self.hash_list와 비교하여 이름 변경을 시도합니다.
        
        Returns:
            (bool, str): (성공 여부, 파일 경로) 튜플을 반환.
        """
        # 1. MD5 해시로 먼저 시도
        hash_md5_value = self.calculate_md5(file_path).hexdigest()
        if hash_md5_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_md5_value])

        # 2. MD5 실패 시, 더 빠른 xxHash64로 시도
        hash_xxhash64_value = self.calculate_xxhash64(file_path).hexdigest()
        if hash_xxhash64_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_xxhash64_value])

        # 두 해시 모두 불일치 시, 처리 실패로 간주하고 원본 파일 경로 반환
        return False, file_path

    def rename_file(self, file_path: str, new_filename: str) -> Tuple[bool, str]:
        """실제로 파일의 이름을 변경하고, 성공 또는 실패 결과를 로그로 남깁니다."""
        new_filepath = os.path.join(os.getcwd(), new_filename)
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)  # 대상 폴더가 없으면 생성

        # 이름 변경하려는 파일이 이미 존재할 경우, 중복을 피하기 위해 새 이름 생성
        if os.path.exists(new_filepath):
            new_filepath = self.get_unique_filename(new_filepath)
            
        try:
            os.rename(file_path, new_filepath)
            relative_file_path = os.path.relpath(file_path, os.getcwd())  # 로그에 표시할 상대 경로
            
            self.log('backend_rename_block', original=relative_file_path, new=new_filename.replace(os.sep, '\\').replace('/', '\\'))
            return True, new_filepath
        except Exception as e:
            self.log('backend_rename_error', error=str(e))
            return False, file_path

    # --- 유틸리티 메서드 ---
    def calculate_md5(self, file_path: str) -> hashlib._Hash:
        """파일을 4KB 청크 단위로 읽어 메모리 효율적으로 MD5 해시를 계산합니다."""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(HASH_CHUNK_SIZE), b""):
                md5_hash.update(chunk)
        return md5_hash

    def calculate_xxhash64(self, file_path: str) -> Any:
        """파일을 4KB 청크 단위로 읽어 메모리 효율적으로 xxHash64 해시를 계산합니다."""
        xxhash64_hash = xxhash.xxh64()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(HASH_CHUNK_SIZE), b""):
                xxhash64_hash.update(chunk)
        return xxhash64_hash

    def get_all_files_in_folders(self, target_folders: list[str]) -> list[str]:
        """지정된 모든 폴더와 그 하위 폴더를 재귀적으로 탐색하여 SHA1 형식의 파일 목록을 반환합니다."""
        all_files = []
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        if self.is_sha1(file_name):  # 파일명이 SHA1 형식인지 확인
                            all_files.append(os.path.join(root, file_name))
        return all_files

    def is_sha1(self, s: str) -> bool:
        """주어진 문자열이 SHA1 해시 형식(길이 40의 16진수 문자열)인지 확인합니다."""
        return len(s) == SHA1_LENGTH and all(c in "0123456789abcdefABCDEF" for c in s)

    def get_unique_filename(self, file_path: str) -> str:
        """
        주어진 파일 경로가 이미 존재할 경우, 중복되지 않는 새 파일 경로를 생성하여 반환합니다.
        예: 'file.txt' -> 'file_(Duplicate_1).txt'
        """
        base, extension = os.path.splitext(file_path)
        counter = 1
        new_file_path = f"{base}{extension}"
        while os.path.exists(new_file_path):
            new_file_path = f"{base}_(Duplicate_{counter}){extension}"
            counter += 1
        return new_file_path
