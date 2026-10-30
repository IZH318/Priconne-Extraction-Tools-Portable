"""GUI 파일 목록 관리 및 드래그 앤 드롭(DnD) 경로 파싱 공통 믹스인 모듈.

AV Converter 및 Unity Converter 등 다수의 대상 파일을 다루는 GUI 컨트롤러에서
파일/폴더 드래그 앤 드롭 문자열 파싱, 지원 확장자 기반 재귀 파일 탐색,
중복 추가 방지 및 항목 제거/클리어 로직 캡슐화 제공.
"""
from __future__ import annotations

import logging
import os
import re
import tkinter as tk

from src.utils.file_scan import iter_files

logger = logging.getLogger(__name__)


class FileListMixin:
    """파일 목록 갱신 및 TkinterDnD 이벤트 경로 해석 공통 기능을 제공하는 믹스인 클래스.

    Tkinter 드래그 앤 드롭 시 공백 포함 경로는 중괄호({path with space}) 묶음 전달되므로,
    Tcl splitlist -> 정규식 순서의 2중 폴백으로 안전하게 경로 분리.
    """

    @staticmethod
    def _parse_dnd_paths(tk_root: tk.Misc, data: str) -> list[str]:
        """드래그 앤 드롭으로 전달된 파일 경로 문자열 파싱.

        파싱 전략:
        1. Tcl C-API 레벨의 tk.splitlist 우선 시도 (중괄호 공백 경로 기본 지원).
        2. TclError 또는 AttributeError 발생 시 중괄호 매칭 정규식 폴백 적용
           (shlex.split은 Windows 백슬래시를 이스케이프로 해석해 경로를 훼손하므로 사용하지 않음).

        Args:
            tk_root (tk.Misc): Tcl 인터프리터 컨텍스트 접근용 Tk 위젯 인스턴스.
            data (str): 드롭 이벤트로 전달된 원시 문자열 (예: '{C:/My Files/a.usm} D:/b.usm').

        Returns:
            list[str]: 파싱 완료된 개별 파일 경로 문자열 리스트.
        """
        try:
            return list(tk_root.tk.splitlist(data))
        except (AttributeError, tk.TclError):
            try:
                return [p.strip('{}') for p in re.findall(r'\{[^{}]*\}|[^ ]+', data) if p.strip()]
            except (re.error, ValueError) as _exc:
                logger.debug("regex fallback failed: %s", _exc)
                return [data]

    @staticmethod
    def _add_paths_to_file_list(
        new_paths: list[str],
        file_paths: list[str],
        supported_exts: tuple[str, ...] | None = None,
    ) -> list[str]:
        """확장자 검사 및 중복 제거 후 파일 목록에 추가.

        Args:
            new_paths (list[str]): 추가를 시도할 대상 파일 경로 리스트.
            file_paths (list[str]): 컨트롤러가 관리 중인 현재 파일 경로 리스트 (In-place 수정).
            supported_exts (tuple[str, ...] | None): 허용할 확장자 튜플 (None이면 모든 파일 허용).

        Returns:
            list[str]: 실제로 새롭게 추가된 고유 파일 경로 리스트.
        """
        # Windows는 대소문자를 구분하지 않으므로 정규화 키로 중복 판정
        exts = tuple(e.lower() for e in supported_exts) if supported_exts else None
        existing = {os.path.normcase(os.path.abspath(p)) for p in file_paths}
        added: list[str] = []
        for p in new_paths:
            key = os.path.normcase(os.path.abspath(p))
            if key in existing:
                continue
            if exts is not None and not p.lower().endswith(exts):
                continue
            file_paths.append(p)
            existing.add(key)
            added.append(p)
        return added

    @staticmethod
    def _remove_selected_from_file_list(
        file_paths: list[str],
        selected_indices: tuple[int, ...],
    ) -> int:
        """선택된 항목을 역순으로 순회하며 안전하게 제거.

        인덱스 변위(Index Drift) 방지 목적의 내림차순(reverse=True) 정렬 삭제 적용.

        Args:
            file_paths (list[str]): 전체 파일 경로 리스트 (In-place 수정).
            selected_indices (tuple[int, ...]): 제거할 항목 인덱스 튜플 (Listbox.curselection() 결과).

        Returns:
            int: 실제로 리스트에서 제거된 항목 수.
        """
        if not selected_indices:
            return 0
        removed = 0
        for i in sorted(selected_indices, reverse=True):
            if 0 <= i < len(file_paths):
                del file_paths[i]
                removed += 1
        return removed

    @staticmethod
    def _clear_file_list(file_paths: list[str]) -> int:
        """파일 목록 전체 비우기 및 삭제된 항목 개수 반환.

        Args:
            file_paths (list[str]): 전체 파일 경로 리스트 (In-place 수정).

        Returns:
            int: 제거된 전체 항목 수.
        """
        count = len(file_paths)
        file_paths.clear()
        return count

    @staticmethod
    def _collect_files_from_paths(
        paths: list[str],
        supported_exts: tuple[str, ...],
        max_files: int = 100_000,
    ) -> list[str]:
        """경로 목록을 검색하여 지원 확장자에 맞는 파일 수집.

        폴더 포함 시 공용 재귀 탐색기 `iter_files`(os.walk followlinks=False)를 재사용하여
        심볼릭 링크 순환(루프)을 방지하고, 중복 제거 및 max_files 초과 시 탐색 중단을 관리.

        Args:
            paths (list[str]): 파일 및 디렉터리 경로가 혼합된 입력 리스트.
            supported_exts (tuple[str, ...]): 수집할 허용 파일 확장자 튜플 (예: ('.usm',)).
            max_files (int): 수집할 최대 파일 개수 제한 (기본값: 100,000).

        Returns:
            list[str]: 조건에 부합하는 고유 파일 절대 경로 리스트.
        """
        _exts = tuple(e.lower() for e in supported_exts)
        found: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            key = os.path.normcase(os.path.abspath(candidate))
            if key not in seen:
                seen.add(key)
                found.append(candidate)

        for path in paths:
            if len(found) >= max_files:
                break
            if os.path.isfile(path) and path.lower().endswith(_exts):
                _add(path)
            elif os.path.isdir(path):
                for full in iter_files(path, predicate=lambda name: name.lower().endswith(_exts)):
                    if len(found) >= max_files:
                        break
                    _add(full)
        return found

