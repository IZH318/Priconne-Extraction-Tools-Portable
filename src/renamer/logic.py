"""Manifest 기반 파일 이름 복원(Renamer) 백엔드 로직 모듈.

프린세스 커넥트 Re:Dive에서 덤프된 40자리 SHA1 16진수 해시 파일명을 원본 에셋 경로 및 이름으로 복원.
SQLite 데이터베이스(manifest.db) 및 CSV 매니페스트 파일을 활용하여 원본 디렉터리 계층 구조를 재구성하며,
이중 해시 스트리밍 비교(xxHash64 / MD5) 및 시그니처 기반 휴리스틱 매칭 지원.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import csv
import hashlib
import logging
import os
import shutil
import sqlite3
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from queue import Queue
from typing import Any

import xxhash

from src.cancellation_token import CancellationToken
from src.constants import HASH_CHUNK_SIZE, RENAMER_TARGET_FOLDERS, SHA1_LENGTH
from src.queue_events import LogEvent, ProgressEvent
from src.utils.base_path import get_application_base_path
from src.utils.file_scan import iter_files
from src.utils.task_pool import DaemonThreadPoolExecutor

logger = logging.getLogger(__name__)


class RenameHashedFile:
    """SHA1 해시 파일 매칭 및 이름 복원을 담당하는 백엔드 엔진 클래스.

    manifest 디렉터리의 CSV 파일 및 manifest.db SQLite 테이블로부터 파일명 해시 매핑과
    콘텐츠 해시 매핑을 로드. 스레드 풀을 활용하여 병렬로 해시를 계산하고 대상 파일을
    안전하게 원본 디렉터리 경로로 이동.

    스레드 안정성(Thread Safety):
        워커 스레드 풀에서 파일 해시를 병렬로 조회.
        물리 파일 이동 및 중복 경로 파일명 조정 작업은 내부 락(_rename_lock)으로 동기화 보호.

    Attributes:
        base_path: 대상 에셋 폴더 및 매니페스트 DB가 위치한 작업 루트 디렉터리.
        target_folders: SHA1 대상 파일을 재귀 검색할 폴더명 시퀀스.
        hash_list: 소문자 SHA1 해시(40자리)를 원본 상대 경로로 매핑하는 딕셔너리.
        content_hash_map: 파일 내용 해시(xxHash64 또는 MD5)를 원본 경로로 매핑하는 딕셔너리.
        unprocessed_files: 1차 해시 매칭에 실패한 미처리 파일 경로 목록.
        log_queue: UI로 전송할 구조화된 LogEvent 큐.
        progress_queue: UI 프로그레스바 갱신용 ProgressEvent 큐.
        get_string: 다국어 UI 번역 콜백 함수.
        total_files: 탐색된 전체 SHA1 후보 파일 수.
        processed_count_rename: 해시 매칭으로 복원 완료된 파일 수.
        processed_count_check: 폴백 시그니처 검사로 복원 완료된 파일 수.
        has_error: 복구 불가능한 예외 발생 여부 플래그.
        error_message: 예외 발생 시 포맷된 에러 메시지.
        _cancel_token: 협력적 취소 신호 전파용 CancellationToken (새 작업 스레드 시작 직전 reset_cancel()로 초기화).
    """

    def __init__(
        self,
        log_queue: Queue,
        progress_queue: Queue,
        get_string_func: Callable[[str], str],
        base_path: Path | None = None,
    ) -> None:
        """RenameHashedFile 백엔드 엔진 초기화.

        Args:
            log_queue: LogEvent 인스턴스를 수신하는 큐.
            progress_queue: ProgressEvent 인스턴스를 수신하는 큐.
            get_string_func: 다국어 번역 문자열 검색 콜백 함수.
            base_path: 작업 루트 디렉터리 (None인 경우 get_application_base_path()로 자동 확인).
        """
        if base_path is not None:
            self.base_path = base_path
        else:
            self.base_path = get_application_base_path()

        self.target_folders: Sequence[str] = RENAMER_TARGET_FOLDERS
        self.hash_list: dict[str, str] = {}
        self.content_hash_map: dict[str, str] = {}
        self.unprocessed_files: list[str] = []
        self.log_queue = log_queue
        self.progress_queue = progress_queue
        self.get_string = get_string_func
        self._rename_lock = threading.Lock()
        # 협력적 취소 신호 전파용 토큰 (새 작업 스레드 시작 직전 reset_cancel()로 초기화)
        self._cancel_token = CancellationToken()

        self.total_files: int = 0
        self.processed_count_rename: int = 0
        self.processed_count_check: int = 0
        self.has_error: bool = False
        self.error_message: str | None = None

    def set_get_string_func(self, get_string_func: Callable[[str], str]) -> None:
        """언어 변경 시 다국어 번역 검색 콜백 함수 갱신.

        Args:
            get_string_func: 신규 다국어 번역 문자열 검색 콜백 함수.
        """
        self.get_string = get_string_func

    def set_base_path(self, new_base_path: Path) -> None:
        """작업 대상 루트 디렉터리 경로 갱신.

        Args:
            new_base_path: 신규 작업 루트 디렉터리 경로 (Path).
        """
        self.base_path = new_base_path

    def cancel(self) -> None:
        """진행 중인 파일 이름 복원 작업에 협력적 취소 신호 전파.

        백그라운드 워커 스레드는 process_files() 내부 루프에서 본 신호를 주기적으로
        확인하여 잔여 파일 처리를 조기 중단. 아직 시작되지 않은(미시작) 예약 작업은
        executor.shutdown(wait=False, cancel_futures=True)로 폐기되며, 이미 실행 중인
        워커 스레드는 완료까지 계속 실행됨. 인터프리터 종료 시에는 해당 워커 스레드
        조인이 수행되어 종료가 지연될 수 있음.
        """
        self._cancel_token.cancel()

    def reset_cancel(self) -> None:
        """이전 실행의 취소 신호 초기화 (새 작업 스레드 시작 직전 호출).

        start_processing()이 워커 스레드 시작 직전에 호출하여 이전 실행에서 설정된
        취소 상태가 다음 실행에 잔존하지 않도록 보장. 본 호출 이후 전파된 cancel()
        신호는 유지되어 실행 중 조기 중단에 사용됨.
        """
        self._cancel_token.reset()

    @property
    def is_cancelled(self) -> bool:
        """현재 작업에 취소 신호가 설정되었는지 여부 반환.

        Returns:
            bool: cancel() 호출로 취소가 요청된 경우 True, 아니면 False.
        """
        return self._cancel_token.is_cancelled

    def _add_log_event(self, key: str, **kwargs: Any) -> None:
        """UI 이벤트 큐에 구조화된 로그 이벤트 삽입.

        Args:
            key: 다국어 사전 키.
            **kwargs: 로그 메시지 포맷팅 파라미터.
        """
        self.log_queue.put(LogEvent(key=key, kwargs=kwargs))

    def _add_progress_event(self, value: int, current: int, total: int) -> None:
        """UI 프로그레스 큐에 진행률 갱신 이벤트 삽입.

        Args:
            value: 진행률 백분율 (0-100).
            current: 현재 처리 완료 파일 수.
            total: 전체 대상 파일 수.
        """
        self.progress_queue.put(ProgressEvent(value=value, current=current, total=total))

    def log(self, key: str, **kwargs: Any) -> None:
        """UI로 다국어 로그 이벤트를 발행하는 공개 메서드.

        Args:
            key: 다국어 사전 키.
            **kwargs: 로그 문자열 치환용 파라미터.
        """
        self._add_log_event(key, **kwargs)

    def update_progress(self, value: int, current: int, total: int) -> None:
        """UI로 진행률 이벤트를 발행하는 공개 메서드.

        Args:
            value: 진행률 백분율 (0-100).
            current: 현재까지 처리된 파일 수.
            total: 전체 후보 파일 수.
        """
        self._add_progress_event(value, current, total)

    def load_manifests(self) -> None:
        """파일명 SHA1 매핑 및 파일 내용 해시 매핑 메모리 로드.

        manifest 디렉터리의 CSV 텍스트 매니페스트 및 manifest.db(SQLite DB)를 스캔하여
        메모리 내 룩업 테이블 구축:
        1. hash_list: 기본 파일명 및 상대 경로의 SHA1 16진수 다이제스트 -> 정제된 상대 대상 경로.
        2. content_hash_map: 에셋 콘텐츠 해시(xxHash64 또는 MD5) -> 정제된 상대 대상 경로.

        보안(Security):
            절대 경로이거나 상위 디렉터리 이동(..) 세그먼트를 포함하는 경로는 거부하여
            경로 순회(Path Traversal) 방지 검증.
        """
        self.hash_list.clear()
        self.content_hash_map.clear()

        # 1. manifest/ 디렉터리에서 CSV 매니페스트 파일 로드
        manifest_dir = self.base_path / "manifest"
        if manifest_dir.is_dir():
            for manifest_file in manifest_dir.glob("*"):
                if not manifest_file.is_file():
                    continue
                try:
                    with open(manifest_file, encoding="utf-8", errors="ignore", newline="") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if not row:
                                continue
                            if len(row) < 2:
                                continue
                            target_path = row[0].strip()
                            if not target_path or ("/" not in target_path and "\\" not in target_path):
                                continue
                            # 경로 순회(Path Traversal) 방지: 절대 경로 및 '..' 세그먼트 거부
                            _norm = target_path.replace("\\", "/")
                            if Path(_norm).is_absolute() or ".." in _norm.split("/"):
                                logger.warning("Renamer: rejected unsafe manifest path: %s", target_path)
                                continue
                            target_clean = _norm
                            basename = Path(target_clean).name
                            sha1_name = hashlib.sha1(basename.encode("utf-8")).hexdigest().lower()
                            self.hash_list[sha1_name] = target_clean

                            sha1_full = hashlib.sha1(target_clean.encode("utf-8")).hexdigest().lower()
                            if sha1_full not in self.hash_list:
                                self.hash_list[sha1_full] = target_clean

                            content_hash = row[1].strip().lower()
                            if content_hash:
                                self.content_hash_map[content_hash] = target_clean
                except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
                    logger.debug("Renamer: failed to parse manifest file %s: %s", manifest_file, exc)

        # 2. manifest.db SQLite 데이터베이스 로드 (공식 DB 매핑 보충/덮어쓰기)
        manifest_db_path = self.base_path / "manifest.db"
        if manifest_db_path.exists():
            with contextlib.closing(sqlite3.connect(manifest_db_path)) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cursor.fetchall()]
                if "t" not in tables:
                    logger.warning("Renamer: manifest.db has no 't' table; skipping db load (tables=%s)", tables)
                    return
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
                    _norm = target_path.replace("\\", "/")
                    if Path(_norm).is_absolute() or ".." in _norm.split("/"):
                        logger.warning("Renamer: rejected unsafe db path: %s", target_path)
                        continue
                    target_clean = _norm
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

    def process_files(self) -> None:
        """전체 파일 복원 파이프라인 일괄 실행.

        단계별 처리 흐름:
        1. manifest.db 또는 manifest 디렉터리 존재 여부 검증.
        2. UI로 작업 시작 알림 로그 이벤트 발행.
        3. 대상 디렉터리를 재귀 탐색하여 SHA1 명명 후보 파일 검색.
        4. 매니페스트 해시 룩업 테이블 메모리 로드.
        5. ThreadPoolExecutor 기반 다중 작업 스레드에서 파일 병렬 처리.
        6. 1차 해시 매칭에 실패한 파일에 대해 첫 줄 시그니처 검사 기반 폴백 복원.
        7. 처리 완료 수 및 잔여 미처리 파일 요약 로그 발행.

        취소(Cancellation):
            cancel()로 취소 신호가 전파되면 병렬 처리 루프 및 폴백 루프가 조기 중단되고,
            아직 시작되지 않은 예약 작업은 executor.shutdown(cancel_futures=True)로
            폐기됨. 단, 이미 실행 중인 워커 스레드는 완료까지 계속 실행되며,
            인터프리터 종료 시 해당 워커 스레드 조인이 수행될 수 있음.
        """
        self.has_error = False
        self.error_message = None
        self.processed_count_rename = 0
        self.processed_count_check = 0
        self.unprocessed_files.clear()
        self.total_files = 0

        try:
            # 1. 매니페스트 데이터베이스 또는 폴더 존재 검증
            manifest_db_path = self.base_path / "manifest.db"
            manifest_dir = self.base_path / "manifest"
            if not manifest_db_path.exists() and not manifest_dir.is_dir():
                self.log('backend_warning_db_not_found')
                self.has_error = True
                return

            # 2. 초기 진행률 및 상태 로그 이벤트 발행
            self.log('backend_info_long_time')
            self.log('backend_info_auto_rename')
            self.log('backend_searching_files')

            # 3. 대상 폴더에서 SHA1 후보 파일 재귀 탐색
            files = self.get_all_files_in_folders(self.target_folders)
            self.total_files = len(files)

            self.update_progress(0, 0, self.total_files)

            if not files:
                self.log('backend_no_files_found')
                return

            self.log('backend_found_files', count=self.total_files)

            # 4. 매니페스트 룩업 테이블 메모리 로드
            self.load_manifests()

            # 5. 다중 작업 스레드 기반 병렬 파일 매칭 및 복원 실행
            final_unprocessed_files = []
            executor = DaemonThreadPoolExecutor(
                max_workers=min(8, (getattr(os, "cpu_count", lambda: 4)() or 4))
            )
            try:
                futures = {executor.submit(self.process, file): file for file in files}

                for processed_futures, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                    # 협력적 취소 신호 수신 시 잔여 파일 처리 조기 중단
                    if self.is_cancelled:
                        break

                    progress = int((processed_futures / self.total_files) * 100.0)
                    self.update_progress(progress, processed_futures, self.total_files)

                    try:
                        was_successful, data = future.result()
                        if was_successful:
                            self.processed_count_rename += 1
                        else:
                            self.unprocessed_files.append(data)
                    except (OSError, RuntimeError, ValueError, TypeError) as exc:
                        file_path = futures[future]
                        self.log('backend_file_process_fail', path=file_path, exc=str(exc))
                        self.unprocessed_files.append(file_path)
            finally:
                # 미시작 예약 작업을 폐기하고 즉시 반환 (실행 중 워커 스레드는 완료까지 진행됨)
                executor.shutdown(wait=False, cancel_futures=True)

            # 6. 미처리 파일 대상 폴백 복원 (매니페스트 첫 줄 시그니처 탐지)
            if self.unprocessed_files and not self.is_cancelled:
                self.log('backend_unprocessed_header')
                for file_path in self.unprocessed_files:
                    # 협력적 취소 신호 수신 시 폴백 루프도 조기 중단
                    if self.is_cancelled:
                        break

                    renamed_by_content = False
                    try:
                        # 매니페스트 시그니처 판별을 위한 첫 줄 읽기 수행
                        with open(file_path, encoding='utf-8', errors='ignore') as file:
                            first_line = file.readline().strip()

                        new_filename = None
                        if 'a/bdl' in first_line: new_filename = os.path.join("manifest", "bdl_assetmanifest")
                        elif 'manifest/' in first_line: new_filename = os.path.join("manifest", "manifest_assetmanifest")
                        elif 'm/' in first_line: new_filename = os.path.join("manifest", "movie2manifest")
                        elif 'b/' in first_line: new_filename = os.path.join("manifest", "soundmanifest")

                        if new_filename:
                            # 폴백 복원도 락 안에서 수행해 워커 스레드의 파일 이동과의 경쟁 상태(덮어쓰기)를 방지
                            with self._rename_lock:
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

                    if not renamed_by_content:
                        final_unprocessed_files.append(file_path)

            # 7. 최종 작업 요약 로그 발행
            total_processed = self.processed_count_rename + self.processed_count_check
            self.log('backend_job_summary', total_processed=total_processed)
            if final_unprocessed_files:
                self.log('backend_unprocessed_summary', count=len(final_unprocessed_files))

        except Exception as exc:  # noqa: BLE001
            self.has_error = True
            self.error_message = str(exc)
            self.log('backend_file_process_fail', path='manifest', exc=str(exc))
        finally:
            # 취소 토큰의 진행 상태(In-Flight)를 마무리해 다음 실행 reset() 경고를 방지
            self._cancel_token.finish()

    def process(self, file_path: str) -> tuple[bool, str]:
        """3단계 전략을 순차 적용하여 단일 파일 매칭 및 이름 복원 시도.

        매칭 전략 순서:
        1. 파일명 일치 검사: 소문자 파일명이 SHA1 매니페스트 테이블과 일치하는지 확인.
        2. 파일 Stem 일치 검사: 확장자가 추가로 붙은 파일의 순수 Stem 매칭 확인.
        3. 내용 이중 해시 검사: 파일 내용을 단일 패스 스트리밍으로 읽어 xxHash64 및 MD5 다이제스트 계산 후 매핑 확인.

        Args:
            file_path: 후보 파일의 절대 또는 상대 경로 문자열.

        Returns:
            (성공_여부, 결과_경로) 튜플:
            - 성공 시: (True, new_filepath_str)
            - 실패 시: (False, original_file_path_str)
        """
        file_name = Path(file_path).name.lower()

        # 취소 요청 시 추가 파일 해시/이동 없이 즉시 반환
        if self.is_cancelled:
            return False, file_path

        # 1. SHA1 맵과 파일명 정확 매칭 (O(1) 메모리 조회)
        if file_name in self.hash_list:
            return self.rename_file(file_path, self.hash_list[file_name])

        # 2. 파일 Stem 매칭 (이차 확장자가 덧붙은 파일 처리)
        #    수집 단계(get_all_files_in_folders)가 40자리 SHA1 파일명만 통과시키므로
        #    현재는 도달하지 않는 예약 경로이다 (확장자 부착 덤프 지원 시 사용).
        file_stem = Path(file_path).stem.lower()
        if file_stem in self.hash_list:
            return self.rename_file(file_path, self.hash_list[file_stem])

        # 3. 내용 기반 이중 해시 비교 (단일 패스 스트리밍 xxHash64 및 MD5)
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
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Renamer: failed to calculate/compare hashes for %s: %s", file_path, exc)

        return False, file_path

    def rename_file(self, file_path: str, new_filename: str) -> tuple[bool, str]:
        """파일을 복원된 대상 경로로 안전하게 이동하고 충돌 시 중복 번호 부여.

        보안(Security):
            경로 순회 취약점 방지를 위해 대상 경로가 반드시 base_path 하위에 머무르는지
            os.path.commonpath로 검증.

        스레드 안정성(Thread Safety):
            병렬 워커 스레드 간 충돌을 방지하기 위해 대상 경로 존재 확인 및 이동 중
            _rename_lock 획득.

        Args:
            file_path: 디스크 상의 원본 파일 경로.
            new_filename: 이동 대상 상대 파일명 및 디렉터리 경로.

        Returns:
            (성공_여부, 대상_또는_원본_경로) 튜플.
        """
        new_filepath = self.base_path / Path(new_filename)

        # 경로 순회(Path Traversal) 검사: new_filepath가 base_path 내부에 있는지 확인
        try:
            if os.path.commonpath([str(self.base_path.resolve()), str(new_filepath.resolve())]) != str(self.base_path.resolve()):
                self.log('backend_rename_error', error=f"path traversal rejected: {new_filename}")
                return False, file_path
        except (OSError, ValueError):
            self.log('backend_rename_error', error=f"invalid path: {new_filename}")
            return False, file_path

        new_filepath.parent.mkdir(parents=True, exist_ok=True)

        with self._rename_lock:
            # 원본 경로와 대상 경로가 동일 파일인지 확인
            try:
                if Path(file_path).resolve() == new_filepath.resolve():
                    return True, str(new_filepath)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.debug("Failed to resolve rename paths: %s", exc)

            if new_filepath.exists():
                new_filepath = self.get_unique_filename(new_filepath)

            try:
                shutil.move(str(file_path), str(new_filepath))
                try:
                    relative_file_path = Path(file_path).relative_to(self.base_path)
                except ValueError:
                    relative_file_path = Path(file_path)

                self.log('backend_rename_block', original=str(relative_file_path), new=str(Path(new_filename)))
                return True, str(new_filepath)
            except OSError as e:
                self.log('backend_rename_error', error=str(e))
                return False, file_path

    def calculate_dual_hashes(self, file_path: str) -> tuple[str, str]:
        """단일 스트리밍 패스로 xxHash64 및 MD5 16진수 다이제스트 동시 계산.

        대용량 파일 로드로 인한 메모리 고갈을 방지하기 위해
        HASH_CHUNK_SIZE(64KB) 블록 단위로 순차 읽기 수행.

        Args:
            file_path: 디스크 상의 파일 경로.

        Returns:
            소문자 (xxhash64_hex_str, md5_hex_str) 튜플.
        """
        xxhash64_hash = xxhash.xxh64()
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(HASH_CHUNK_SIZE), b""):
                # 대용량 파일 해시 도중에도 취소 요청에 반응 (부분 해시는 매칭 실패로 처리됨)
                if self.is_cancelled:
                    break
                xxhash64_hash.update(chunk)
                md5_hash.update(chunk)
        return xxhash64_hash.hexdigest().lower(), md5_hash.hexdigest().lower()

    def get_all_files_in_folders(self, target_folders: Sequence[str]) -> list[str]:
        """40자리 SHA1 16진수 형식에 일치하는 대상 폴더 내 모든 파일 탐색.

        base_path 하위의 설정된 대상 디렉터리를 재귀적으로 순회.

        Args:
            target_folders: base_path 기준 대상 디렉터리명 시퀀스.

        Returns:
            SHA1 명명 규칙과 일치하는 파일 경로 문자열 리스트.
        """
        all_files: list[str] = []
        for folder in target_folders:
            folder_path = self.base_path / folder
            if folder_path.is_dir():
                all_files.extend(
                    iter_files(
                        folder_path,
                        predicate=self.is_sha1,
                        cancel=lambda: self.is_cancelled,
                    )
                )
        return all_files

    def is_sha1(self, s: str) -> bool:
        """주어진 문자열이 40자리 SHA1 16진수 해시 규격과 일치하는지 판별.

        Args:
            s: 검사할 문자열 (파일명 또는 stem).

        Returns:
            길이가 40자이고 모든 문자가 16진수 문자이면 True, 아니면 False.
        """
        return len(s) == SHA1_LENGTH and all(c in "0123456789abcdefABCDEF" for c in s)

    def get_unique_filename(self, file_path: Path) -> Path:
        """동일 경로에 파일이 이미 존재할 경우 중복 방지 파일 경로 생성.

        중복 시 점진적 번호 접미사 추가: stem_(Duplicate_N).ext.

        Args:
            file_path: 이동 예정 대상 Path.

        Returns:
            기존 파일과 충돌하지 않는 고유한 신규 Path.
        """
        counter = 1
        new_file_path = file_path
        while new_file_path.exists():
            new_file_path = file_path.with_name(f"{file_path.stem}_(Duplicate_{counter}){file_path.suffix}")
            counter += 1
        return new_file_path
