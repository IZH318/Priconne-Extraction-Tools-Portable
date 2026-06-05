from __future__ import annotations
import os
import re
import shlex
import tkinter as tk


class FileListMixin:
    """파일 리스트 추가/제거/클리어/DnD 파싱 공통 로직을 제공하는 Mixin.

    AV Converter와 Unity Converter 등 파일 목록을 다루는
    Controller에서 공통으로 상속하여 사용합니다.

    Note:
        이 Mixin은 단일 리스트 기준의 유틸리티 메서드를 제공합니다.
        여러 리스트(예: video/audio)를 관리하는 Controller에서는
        호출 시 적절한 리스트와 위젯을 인자로 전달해야 합니다.
    """

    @staticmethod
    def _parse_dnd_paths(tk_root: tk.Misc, data: str) -> list[str]:
        """드래그 앤 드롭된 파일 경로 문자열을 파싱하여 리스트로 반환합니다.

        Tkinter의 ``tk.splitlist``를 우선 시도하고, 실패 시
        ``shlex.split`` → 정규식 폴백 순서로 파싱합니다.

        Args:
            tk_root: Tkinter 최상위 위젯 (splitlist 호출용).
            data: 드래그 앤 드롭 이벤트로 전달된 파일 경로 문자열.

        Returns:
            파싱된 파일 경로 문자열 리스트.
        """
        try:
            return list(tk_root.tk.splitlist(data))
        except (AttributeError, tk.TclError):
            try:
                return shlex.split(data)
            except ValueError:
                return [p.strip('{}') for p in re.findall(r'\{[^{}]*\}|[^ ]+', data) if p.strip()]

    @staticmethod
    def _add_paths_to_file_list(
        new_paths: list[str],
        file_paths: list[str],
        supported_exts: tuple[str, ...] | None = None,
    ) -> list[str]:
        """새 파일 경로들을 중복 검사 후 리스트에 추가합니다.

        Args:
            new_paths: 추가할 후보 파일 경로 리스트.
            file_paths: 현재 유지 중인 전체 파일 경로 리스트 (in-place 수정).
            supported_exts: 허용할 파일 확장자 튜플 (None이면 모든 파일 허용).

        Returns:
            실제로 추가된 (중복 제외) 파일 경로 리스트.
        """
        existing = set(file_paths)
        added: list[str] = []
        for p in new_paths:
            if p in existing:
                continue
            if supported_exts and not p.lower().endswith(supported_exts):
                continue
            file_paths.append(p)
            existing.add(p)
            added.append(p)
        return added

    @staticmethod
    def _remove_selected_from_file_list(
        file_paths: list[str],
        selected_indices: tuple[int, ...],
    ) -> int:
        """선택된 인덱스의 항목을 리스트에서 제거합니다.

        Args:
            file_paths: 전체 파일 경로 리스트 (in-place 수정).
            selected_indices: 제거할 인덱스 튜플 (Listbox.curselection() 결과).

        Returns:
            제거된 항목 수.
        """
        if not selected_indices:
            return 0
        for i in sorted(selected_indices, reverse=True):
            del file_paths[i]
        return len(selected_indices)

    @staticmethod
    def _clear_file_list(file_paths: list[str]) -> int:
        """파일 리스트의 모든 항목을 제거합니다.

        Args:
            file_paths: 전체 파일 경로 리스트 (in-place 수정).

        Returns:
            제거된 항목 수.
        """
        count = len(file_paths)
        file_paths.clear()
        return count

    @staticmethod
    def _collect_files_from_paths(
        paths: list[str],
        supported_exts: tuple[str, ...],
    ) -> list[str]:
        """파일/폴더 경로 목록에서 지원 확장자 파일만 수집합니다.

        파일이면 확장자 검사 후 추가, 폴더이면 재귀 탐색합니다.

        Args:
            paths: 파일 및 폴더 경로 혼합 리스트.
            supported_exts: 허용할 파일 확장자 튜플.

        Returns:
            매칭된 파일 경로 리스트.
        """
        found: list[str] = []
        for path in paths:
            if os.path.isfile(path) and path.lower().endswith(supported_exts):
                found.append(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for f in files:
                        if f.lower().endswith(supported_exts):
                            found.append(os.path.join(root, f))
        return found
