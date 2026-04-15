"""
Resource Remover Logic Unit Tests
ResourceRemoverLogic의 리소스 파일 검색 및 삭제 기능을 검증합니다.
"""
from __future__ import annotations
import pytest
from pathlib import Path
from src.resource_remover.logic import ResourceRemoverLogic


class TestResourceRemoverLogic:
    """ResourceRemoverLogic의 핵심 기능을 검증합니다."""

    def test_count_resources(self, base_test_dir) -> None:
        """확장자 기반 파일 검색이 대소문자 무관하게 올바르게 동작하는지 확인합니다."""
        remover = ResourceRemoverLogic(base_path=base_test_dir)
        
        # 더미 파일 생성
        (base_test_dir / "test1.txt").write_text("dummy")
        (base_test_dir / "test2.log").write_text("dummy")
        (base_test_dir / "test3.png").write_text("dummy")
        
        # 하위 폴더 생성 및 대소문자 혼용 확장자
        sub_dir = base_test_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "test4.TXT").write_text("dummy")
        
        # .txt와 .log만 검색 (대소문자 무관하게 3개 출력되어야 함)
        found_files = remover.count_resources([".txt", ".log"])
        assert len(found_files) == 3
        
        # 반환된 파일 목록이 올바른지 확인
        names = [f.name.lower() for f in found_files]
        assert "test1.txt" in names
        assert "test2.log" in names
        assert "test4.txt" in names
        assert "test3.png" not in names

    def test_remove_resources(self, base_test_dir) -> None:
        """파일 삭제 및 로그 파일 생성이 올바르게 동작하는지 확인합니다."""
        remover = ResourceRemoverLogic(base_path=base_test_dir)
        
        f1 = base_test_dir / "del1.txt"
        f2 = base_test_dir / "del2.txt"
        f1.write_text("dummy")
        f2.write_text("dummy")
        
        paths_to_delete = [f1, f2]
        
        # use_trash=False 로 영구 삭제 수행하여 테스트 환경 오염 방지
        del_count, errors, log_file = remover.remove_resources(paths_to_delete, [".txt"], use_trash=False)
        
        assert del_count == 2
        assert len(errors) == 0
        assert not f1.exists()
        assert not f2.exists()
        
        # 로그 파일이 생성되었는지 확인
        assert log_file != ""
        assert Path(log_file).exists()

    def test_count_resources_empty_directory(self, base_test_dir) -> None:
        """빈 디렉토리에서 검색 시 빈 목록을 반환하는지 확인합니다."""
        remover = ResourceRemoverLogic(base_path=base_test_dir)
        found_files = remover.count_resources([".txt"])
        assert len(found_files) == 0

    def test_remove_resources_nonexistent_file(self, base_test_dir) -> None:
        """존재하지 않는 파일 삭제 시도 시 에러가 기록되는지 확인합니다."""
        remover = ResourceRemoverLogic(base_path=base_test_dir)
        
        fake_path = base_test_dir / "nonexistent.txt"
        del_count, errors, log_file = remover.remove_resources([fake_path], [".txt"], use_trash=False)
        
        assert del_count == 0
        assert len(errors) == 1
