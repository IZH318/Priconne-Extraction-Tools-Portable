"""Story Viewer 파일 목록 표현 및 표시 모드 관리 서비스 모듈.

스토리 파일 목록의 4가지 표시 모드(파일명+제목, 제목+파일명, 파일명 전용, 제목 전용),
표시 이름과 실제 파일명 간의 양방향 매핑, 선택 파일 제거 및 작업 공간 초기화(Clear Workspace),
비동기 갱신 경쟁 상태(Race condition) 방지용 세대(Generation) 카운터 관리.
"""

from __future__ import annotations

import contextlib
import logging
import re
import tkinter as tk
from collections.abc import Callable
from typing import Any

from src.utils.file_list_mixin import FileListMixin

logger = logging.getLogger(__name__)


class StoryFileListService:
    """스토리 파일 목록 UI 표현 형식 및 항목 추가/제거 서비스.

    메모리 상의 파일 경로 맵과 리스트박스 표시 문자열 간의 동기화를 유지하며,
    다중 선택 삭제 및 워크스페이스 비우기 지원.
    """


    def __init__(
        self,
        view: Any,
        display_mode_var: Any,
        # 가변 상태 접근자(Mutable state accessors)
        get_is_loading: Callable[[], bool],
        get_current_filenames_in_list: Callable[[], list[str]],
        set_current_filenames_in_list: Callable[[list[str]], None],
        get_loaded_filenames: Callable[[], list[str]],
        set_loaded_filenames: Callable[[list[str]], None],
        get_all_files: Callable[[], dict[str, str]],
        set_all_files: Callable[[dict[str, str]], None],
        get_file_titles: Callable[[], dict[str, str]],
        set_file_titles: Callable[[dict[str, str]], None],
        get_raw_file_titles: Callable[[], dict[str, str]],
        set_raw_file_titles: Callable[[dict[str, str]], None],
        get_file_situations: Callable[[], dict[str, str]],
        set_file_situations: Callable[[dict[str, str]], None],
        get_file_outlines: Callable[[], dict[str, str]],
        set_file_outlines: Callable[[dict[str, str]], None],
        get_file_voice_adv_ids: Callable[[], dict[str, str]],
        set_file_voice_adv_ids: Callable[[dict[str, str]], None],
        get_file_speakers: Callable[[], dict[str, str]],
        set_file_speakers: Callable[[dict[str, str]], None],
        get_display_name_to_filename: Callable[[], dict[str, str]],
        set_display_name_to_filename: Callable[[dict[str, str]], None],
        get_base_search_files: Callable[[], list[str]],
        set_base_search_files: Callable[[list[str]], None],
        get_search_data: Callable[[], dict[str, Any]],
        set_search_data: Callable[[dict[str, Any]], None],
        get_server_titles_cache: Callable[[], dict],
        set_server_titles_cache: Callable[[dict], None],
        get_story_data_cache: Callable[[], Any],
        set_story_data_cache: Callable[[Any], None],
        get_current_file_path: Callable[[], Any],
        set_current_file_path: Callable[[Any], None],
        get_populate_generation: Callable[[], int],
        set_populate_generation: Callable[[int], None],
        shared_state: Any = None,
    ) -> None:
        self._view = view
        self._display_mode_var = display_mode_var

        self._get_is_loading = get_is_loading

        self._get_current_filenames_in_list = get_current_filenames_in_list
        self._set_current_filenames_in_list = set_current_filenames_in_list

        self._get_loaded_filenames = get_loaded_filenames
        self._set_loaded_filenames = set_loaded_filenames

        self._get_all_files = get_all_files
        self._set_all_files = set_all_files

        self._get_file_titles = get_file_titles
        self._set_file_titles = set_file_titles

        self._get_raw_file_titles = get_raw_file_titles
        self._set_raw_file_titles = set_raw_file_titles

        self._get_file_situations = get_file_situations
        self._set_file_situations = set_file_situations

        self._get_file_outlines = get_file_outlines
        self._set_file_outlines = set_file_outlines

        self._get_file_voice_adv_ids = get_file_voice_adv_ids
        self._set_file_voice_adv_ids = set_file_voice_adv_ids

        self._get_file_speakers = get_file_speakers
        self._set_file_speakers = set_file_speakers

        self._get_display_name_to_filename = get_display_name_to_filename
        self._set_display_name_to_filename = set_display_name_to_filename

        self._get_base_search_files = get_base_search_files
        self._set_base_search_files = set_base_search_files

        self._get_search_data = get_search_data
        self._set_search_data = set_search_data

        self._get_server_titles_cache = get_server_titles_cache
        self._set_server_titles_cache = set_server_titles_cache

        self._get_story_data_cache = get_story_data_cache
        self._set_story_data_cache = set_story_data_cache

        self._get_current_file_path = get_current_file_path
        self._set_current_file_path = set_current_file_path

        self._get_populate_generation = get_populate_generation
        self._set_populate_generation = set_populate_generation

    def remove_selected_files(self, event: Any = None) -> None:
        """선택된 파일(들) 목록에서 제거."""
        if self._get_is_loading():
            return
        selected_indices = self._view.file_listbox.curselection()
        if not selected_indices:
            return

        to_remove = set()
        for idx in selected_indices:
            if 0 <= idx < len(self._get_current_filenames_in_list()):
                to_remove.add(self._get_current_filenames_in_list()[idx])
            else:
                try:
                    display_name = self._view.file_listbox.get(idx)
                    if fn := self._get_display_name_to_filename().get(display_name):
                        to_remove.add(fn)
                except tk.TclError:
                    continue

        if not to_remove:
            return

        FileListMixin._remove_selected_from_file_list(self._get_current_filenames_in_list(), selected_indices)
        self._set_loaded_filenames([f for f in self._get_loaded_filenames() if f not in to_remove])
        for fn in to_remove:
            _p = self._get_all_files().get(fn)
            self._get_all_files().pop(fn, None)
            self._get_file_titles().pop(fn, None)
            self._get_raw_file_titles().pop(fn, None)
            self._get_file_situations().pop(fn, None)
            self._get_file_outlines().pop(fn, None)
            self._get_file_voice_adv_ids().pop(fn, None)
            self._get_file_speakers().pop(fn, None)
            if _p is not None:
                self._get_story_data_cache().pop(_p, None)
        self._set_base_search_files([f for f in self._get_base_search_files() if f not in to_remove])
        if isinstance(self._get_search_data(), dict) and 'filenames' in self._get_search_data():
            self._get_search_data()['filenames'] = [f for f in self._get_search_data()['filenames'] if f not in to_remove]
        with contextlib.suppress(AttributeError, KeyError):
            self._get_server_titles_cache().clear()

        if self._get_current_filenames_in_list():
            self.update_file_list(
                self._get_current_filenames_in_list(),
                status_key='removed_selected_files',
                count=len(to_remove),
                total=len(self._get_current_filenames_in_list())
            )
        else:
            self._set_populate_generation(self._get_populate_generation() + 1)
            self._get_display_name_to_filename().clear()
            self._set_current_file_path(None)
            self._view.file_listbox.delete(0, tk.END)
            self._view.update_story_text([])
            self._view.btn_export.config(state=tk.DISABLED)
            self._view.btn_copy.config(state=tk.DISABLED)
            self._view.update_status_bar('removed_selected_files', count=len(to_remove), total=0)

    def remove_all_files(self, event: Any = None) -> None:
        """모든 파일 목록에서 제거."""
        if self._get_is_loading():
            return
        if not self._get_current_filenames_in_list() and not self._get_all_files():
            return

        total_removed = len(self._get_all_files()) or len(self._get_current_filenames_in_list())
        self._set_populate_generation(self._get_populate_generation() + 1)
        FileListMixin._clear_file_list(self._get_current_filenames_in_list())
        self._get_all_files().clear()
        self._get_loaded_filenames().clear()
        self._get_display_name_to_filename().clear()
        self._set_current_file_path(None)
        self._get_file_titles().clear()
        self._get_raw_file_titles().clear()
        self._get_file_situations().clear()
        self._get_file_outlines().clear()
        self._get_file_voice_adv_ids().clear()
        self._get_file_speakers().clear()
        self._get_search_data().clear()
        self._get_base_search_files().clear()
        self._get_story_data_cache().clear()
        with contextlib.suppress(AttributeError, KeyError):
            self._get_server_titles_cache().clear()

        self._view.file_listbox.delete(0, tk.END)
        self._view.update_story_text([])
        self._view.btn_export.config(state=tk.DISABLED)
        self._view.btn_copy.config(state=tk.DISABLED)
        self._view.update_status_bar('removed_all_files', count=total_removed)

    def update_file_list(self, filenames: list[str], status_key: str | None = None, **status_kwargs: Any) -> None:
        """지정된 파일 목록으로 리스트박스 렌더링 및 UI 갱신."""
        self._set_populate_generation(self._get_populate_generation() + 1)
        current_gen = self._get_populate_generation()
        self._view.update_story_text([])
        self._set_current_file_path(None)
        self._set_current_filenames_in_list(sorted(filenames))
        target_files = list(self._get_current_filenames_in_list())
        self._get_display_name_to_filename().clear()
        self._view.file_listbox.delete(0, tk.END)
        total, chunk_size = len(target_files), 200
        display_mode = self._display_mode_var.get()
        duplicate_titles: set[str] = set()
        if display_mode == 'title':
            title_counts: dict[str, int] = {}
            for fn in target_files:
                t = self._get_file_titles().get(fn, fn)
                title_counts[t] = title_counts.get(t, 0) + 1
            duplicate_titles = {t for t, count in title_counts.items() if count > 1}

        def _populate_list(index: int = 0) -> None:
            if current_gen != self._get_populate_generation():
                return
            if index >= total:
                if status_key:
                    self._view.update_status_bar(status_key, **status_kwargs)
                else:
                    self._view.update_status_bar('status_bar_list_updated', count=total)
                if total > 0:
                    self._view.file_listbox.selection_set(0)
                    self._view.file_listbox.event_generate("<<ListboxSelect>>")
                else:
                    self._view.update_status_bar('status_bar_ready')
                return
            self._view.update_status_bar('status_bar_list_updating', i=index + 1, t=total)
            end_index = min(index + chunk_size, total)
            display_chunk = []
            for i in range(index, end_index):
                filename = target_files[i]
                display_name = filename
                match = re.match(r'^storydata_(\d+)(?:\.[^.]+)?$', filename)
                adv_id = match.group(1) if match else ""

                if display_mode == 'title':
                    title = self._get_file_titles().get(filename, filename)
                    if title:
                        if title in duplicate_titles and adv_id:
                            display_name = f"{title} ({adv_id})"
                        else:
                            display_name = f"{title}"
                elif display_mode == 'id_title':
                    title = self._get_file_titles().get(filename, filename)
                    display_name = f"[{adv_id}] {title}" if adv_id else f"{title}"
                unique_display = display_name
                suffix = 1
                while unique_display in self._get_display_name_to_filename():
                    unique_display = f"{display_name} ({suffix})"
                    suffix += 1
                display_chunk.append(unique_display)
                self._get_display_name_to_filename()[unique_display] = filename
            try:
                self._view.file_listbox.insert(tk.END, *display_chunk)
            except tk.TclError as exc:
                logger.debug("file_listbox insert failed: %s", exc)
            self._view.after(1, lambda: _populate_list(end_index))
        _populate_list()
