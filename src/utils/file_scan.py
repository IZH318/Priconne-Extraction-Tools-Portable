"""재귀 폴더 탐색 공통 유틸리티 모듈.

여러 서브도구가 각자 구현하던 os.walk 기반 파일 수집 루프를 단일 제너레이터로
통합한다(이름/확장자 필터, 제외 디렉터리, 깊이/개수 상한, 취소 콜백 지원).
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator

__all__ = ["iter_files"]


def iter_files(
    root: str | os.PathLike[str],
    *,
    predicate: Callable[[str], bool] | None = None,
    skip_dir_names: Iterable[str] | None = None,
    max_files: int | None = None,
    max_depth: int | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Iterator[str]:
    """디렉터리를 재귀 탐색하며 조건에 맞는 파일 경로를 순차 산출한다.

    Args:
        root: 탐색 루트 경로.
        predicate: 파일명을 받아 수집 여부를 반환하는 콜백(None이면 모두 수집).
        skip_dir_names: 모든 깊이에서 제외할 디렉터리명(대소문자 무시).
        max_files: 최대 수집 개수(None이면 무제한).
        max_depth: 최대 탐색 깊이(루트 직계 파일=0, None이면 무제한).
        cancel: True를 반환하면 탐색을 중단하는 콜백.

    Yields:
        str: 조건에 맞는 파일의 전체 경로.
    """
    root_path = os.fspath(root)
    skip_dirs = {name.lower() for name in skip_dir_names} if skip_dir_names else set()
    collected = 0

    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
        if cancel is not None and cancel():
            return

        if skip_dirs:
            dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]

        if max_depth is not None:
            try:
                rel = os.path.relpath(dirpath, root_path)
            except ValueError:
                rel = "."
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > max_depth:
                dirnames[:] = []
                continue

        for filename in filenames:
            if predicate is not None and not predicate(filename):
                continue
            if max_files is not None and collected >= max_files:
                return
            yield os.path.join(dirpath, filename)
            collected += 1
