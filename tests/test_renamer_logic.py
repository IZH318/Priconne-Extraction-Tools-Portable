"""
Renamer Logic Unit Tests
RenameHashedFile의 파일 이름 변경 로직을 검증합니다.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from src.renamer.logic import RenameHashedFile


class TestRenameHashedFile:
    """RenameHashedFile의 핵심 기능을 검증합니다."""

    def test_renamer_success_scenario(self, base_test_dir, mock_log_queue, mock_progress_queue, mock_get_string) -> None:
        """RenameHashedFile가 DB에서 해시를 읽어 정상적으로 파일 이름을 변경하는지 검증합니다."""
        # 1. 가짜 manifest.db 설정
        db_path = base_test_dir / "manifest.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE t (name TEXT, hash TEXT)")
        cursor.execute("INSERT INTO t VALUES ('a/fake_asset', '31bfb9730ae51af73953ba720c8660d7')")
        conn.commit()
        conn.close()

        # 2. 테스트용 타겟 폴더와 파일 생성
        target_folder = base_test_dir / "a" / "fake"
        target_folder.mkdir(parents=True)
        
        test_file_name = "1" * 40
        test_file = target_folder / test_file_name
        test_file.write_bytes(b"dummy data")

        # 3. RenameHashedFile 객체 생성
        renamer = RenameHashedFile(
            log_queue=mock_log_queue,
            progress_queue=mock_progress_queue,
            get_string_func=mock_get_string,
            base_path=base_test_dir
        )
        renamer.set_target_folders([str(base_test_dir)])

        # 4. 파일 처리 실행
        renamer.process_files()

        # 5. 검증
        expected_new_file = base_test_dir / "a" / "fake_asset"
        assert expected_new_file.exists(), f"File should be renamed to {expected_new_file}"
        assert not test_file.exists(), "Original file should no longer exist"

    def test_renamer_no_files_found(self, base_test_dir, mock_log_queue, mock_progress_queue, mock_get_string) -> None:
        """처리 대상 파일이 없을 때 정상적으로 종료되는지 검증합니다."""
        db_path = base_test_dir / "manifest.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE t (name TEXT, hash TEXT)")
        conn.commit()
        conn.close()

        renamer = RenameHashedFile(
            log_queue=mock_log_queue,
            progress_queue=mock_progress_queue,
            get_string_func=mock_get_string,
            base_path=base_test_dir
        )
        renamer.set_target_folders([str(base_test_dir)])

        # 빈 디렉토리에서 처리 — 예외 없이 정상 종료되어야 함
        renamer.process_files()

    def test_is_sha1_valid(self, base_test_dir, mock_log_queue, mock_progress_queue, mock_get_string) -> None:
        """is_sha1() 메서드가 SHA1 형식을 정확히 판별하는지 검증합니다."""
        renamer = RenameHashedFile(
            log_queue=mock_log_queue,
            progress_queue=mock_progress_queue,
            get_string_func=mock_get_string,
            base_path=base_test_dir
        )
        # 40자 hex → True
        assert renamer.is_sha1("a" * 40) is True
        # 39자 → False
        assert renamer.is_sha1("a" * 39) is False
        # 비-hex 문자 포함 → False
        assert renamer.is_sha1("g" * 40) is False
        # 빈 문자열 → False
        assert renamer.is_sha1("") is False
