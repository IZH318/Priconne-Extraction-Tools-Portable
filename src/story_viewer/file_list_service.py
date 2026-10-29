"""Story Viewer 파일 목록 표현 및 표시 모드 관리 서비스 모듈.

스토리 파일 목록의 4가지 표시 모드(파일명+제목, 제목+파일명, 파일명 전용, 제목 전용),
표시 이름과 실제 파일명 간의 양방향 매핑, 선택 파일 제거 및 작업 공간 초기화(Clear Workspace),
비동기 갱신 경쟁 상태(Race condition) 방지용 세대(Generation) 카운터 관리.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from typing import Any

from src.constants import STORYDATA_ADV_ID_RE
from src.story_viewer.workspace_state import StoryWorkspaceState
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
        workspace: StoryWorkspaceState,
    ) -> None:
        self._view = view
        self._display_mode_var = display_mode_var
        self._workspace = workspace

    def remove_selected_files(self, event: Any = None) -> None:
        """선택된 파일(들) 목록에서 제거."""
        if self._workspace.is_loading:
            return
        selected_indices = self._view.file_listbox.curselection()
        if not selected_indices:
            return

        to_remove = set()
        for idx in selected_indices:
            if 0 <= idx < len(self._workspace.current_filenames_in_list):
                to_remove.add(self._workspace.current_filenames_in_list[idx])
            else:
                try:
                    display_name = self._view.file_listbox.get(idx)
                    if fn := self._workspace.display_name_to_filename.get(display_name):
                        to_remove.add(fn)
                except tk.TclError:
                    continue

        if not to_remove:
            return

        FileListMixin._remove_selected_from_file_list(self._workspace.current_filenames_in_list, selected_indices)
        self._workspace.loaded_filenames = [f for f in self._workspace.loaded_filenames if f not in to_remove]
        for fn in to_remove:
            _p = self._workspace.all_files.get(fn)
            self._workspace.all_files.pop(fn, None)
            self._workspace.file_titles.pop(fn, None)
            self._workspace.raw_file_titles.pop(fn, None)
            self._workspace.file_situations.pop(fn, None)
            self._workspace.file_outlines.pop(fn, None)
            self._workspace.file_voice_adv_ids.pop(fn, None)
            self._workspace.file_speakers.pop(fn, None)
            if _p is not None:
                self._workspace.story_data_cache.pop(_p, None)
        self._workspace.base_search_files = [f for f in self._workspace.base_search_files if f not in to_remove]
        if isinstance(self._workspace.search_data, dict) and 'filenames' in self._workspace.search_data:
            self._workspace.search_data['filenames'] = [f for f in self._workspace.search_data['filenames'] if f not in to_remove]
        with contextlib.suppress(AttributeError, KeyError):
            self._workspace.server_titles_cache.clear()

        if self._workspace.current_filenames_in_list:
            self.update_file_list(
                self._workspace.current_filenames_in_list,
                status_key='removed_selected_files',
                count=len(to_remove),
                total=len(self._workspace.current_filenames_in_list)
            )
        else:
            self._workspace.populate_generation = self._workspace.populate_generation + 1
            self._workspace.display_name_to_filename.clear()
            self._workspace.current_file_path = None
            self._view.file_listbox.delete(0, tk.END)
            self._view.update_story_text([])
            self._view.btn_export.config(state=tk.DISABLED)
            self._view.btn_copy.config(state=tk.DISABLED)
            self._view.update_status_bar('removed_selected_files', count=len(to_remove), total=0)

    def remove_all_files(self, event: Any = None) -> None:
        """모든 파일 목록에서 제거."""
        if self._workspace.is_loading:
            return
        if not self._workspace.current_filenames_in_list and not self._workspace.all_files:
            return

        total_removed = len(self._workspace.all_files) or len(self._workspace.current_filenames_in_list)
        self._workspace.populate_generation = self._workspace.populate_generation + 1
        FileListMixin._clear_file_list(self._workspace.current_filenames_in_list)
        self._workspace.all_files.clear()
        self._workspace.loaded_filenames.clear()
        self._workspace.display_name_to_filename.clear()
        self._workspace.current_file_path = None
        self._workspace.file_titles.clear()
        self._workspace.raw_file_titles.clear()
        self._workspace.file_situations.clear()
        self._workspace.file_outlines.clear()
        self._workspace.file_voice_adv_ids.clear()
        self._workspace.file_speakers.clear()
        self._workspace.search_data.clear()
        self._workspace.base_search_files.clear()
        self._workspace.story_data_cache.clear()
        with contextlib.suppress(AttributeError, KeyError):
            self._workspace.server_titles_cache.clear()

        self._view.file_listbox.delete(0, tk.END)
        self._view.update_story_text([])
        self._view.btn_export.config(state=tk.DISABLED)
        self._view.btn_copy.config(state=tk.DISABLED)
        self._view.update_status_bar('removed_all_files', count=total_removed)

    def update_file_list(self, filenames: list[str], status_key: str | None = None, **status_kwargs: Any) -> None:
        """지정된 파일 목록으로 리스트박스 렌더링 및 UI 갱신."""
        self._workspace.populate_generation = self._workspace.populate_generation + 1
        current_gen = self._workspace.populate_generation
        self._view.update_story_text([])
        self._workspace.current_file_path = None
        self._workspace.current_filenames_in_list = sorted(filenames)
        target_files = list(self._workspace.current_filenames_in_list)
        self._workspace.display_name_to_filename.clear()
        self._view.file_listbox.delete(0, tk.END)
        total, chunk_size = len(target_files), 200
        display_mode = self._display_mode_var.get()
        duplicate_titles: set[str] = set()
        if display_mode == 'title':
            title_counts: dict[str, int] = {}
            for fn in target_files:
                t = self._workspace.file_titles.get(fn, fn)
                title_counts[t] = title_counts.get(t, 0) + 1
            duplicate_titles = {t for t, count in title_counts.items() if count > 1}

        def _populate_list(index: int = 0) -> None:
            if current_gen != self._workspace.populate_generation:
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
                match = STORYDATA_ADV_ID_RE.match(filename)
                adv_id = match.group(1) if match else ""

                if display_mode == 'title':
                    title = self._workspace.file_titles.get(filename, filename)
                    if title:
                        if title in duplicate_titles and adv_id:
                            display_name = f"{title} ({adv_id})"
                        else:
                            display_name = f"{title}"
                elif display_mode == 'id_title':
                    title = self._workspace.file_titles.get(filename, filename)
                    display_name = f"[{adv_id}] {title}" if adv_id else f"{title}"
                unique_display = display_name
                suffix = 1
                while unique_display in self._workspace.display_name_to_filename:
                    unique_display = f"{display_name} ({suffix})"
                    suffix += 1
                display_chunk.append(unique_display)
                self._workspace.display_name_to_filename[unique_display] = filename
            try:
                self._view.file_listbox.insert(tk.END, *display_chunk)
                self._view.after(1, lambda: _populate_list(end_index))
            except tk.TclError as exc:
                logger.debug("file_listbox insert failed: %s", exc)
        _populate_list()
