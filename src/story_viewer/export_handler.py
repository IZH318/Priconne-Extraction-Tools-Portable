"""Story Viewer 텍스트/마크다운/JSON 내보내기 핸들러 모듈.

단일/다중 스토리 스크립트 파일을 텍스트(.txt) 또는 마크다운(.md)으로 변환 내보내기,
선택지 포함 여부 및 화자 서식 지정, 파일 명명 규칙(원본/제목/ID_제목),
데이터베이스 부가 데이터(캐릭터 프로필, 음성 대사, 이벤트 목록) 일괄 내보내기 담당.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypedDict

from src.constants import STORYDATA_ADV_ID_BARE_RE
from src.utils.filename import WINDOWS_RESERVED_DEVICE_NAMES
from src.utils.tk_safe import post_to_ui
from src.utils.platform_open import open_with_default_app

from . import db_helper
from .logic import StoryDataLoader, StoryFormatter

if TYPE_CHECKING:
    from .db_manager import StoryDBManager
    from .view import StoryViewerView


class OtherExportTask(TypedDict):
    """데이터베이스 부가 정보 내보내기 작업 정의 TypedDict."""

    type: str
    name_key: str
    data_func: Callable[[], list[str]]
    file_suffix: str
    header_key: str



FILENAME_SANITIZE_MAP = str.maketrans({
    '\\': '＼',
    '/': '／',
    ':': '：',
    '*': '＊',
    '?': '？',
    '"': '＂',
    '<': '＜',
    '>': '＞',
    '|': '｜',
})


def sanitize_filename(name: str) -> str:
    """윈도우 파일 시스템 금지 문자를 전각 문자로 1:1 치환하고 예약어 충돌 방지."""
    sanitized = name.translate(FILENAME_SANITIZE_MAP).strip().rstrip(" .")
    # Windows 예약 디바이스명(CON, NUL, COM1 등)은 확장자와 무관하게 예약되어 접두사(_)를 붙여 충돌 방지
    if sanitized.split(".", 1)[0].upper() in WINDOWS_RESERVED_DEVICE_NAMES:
        sanitized = f"_{sanitized}"
    return sanitized


def make_unique_export_path(output_path: str) -> str:
    """이미 존재하는 경로면 덮어쓰지 않고 ' (n)' 접미사를 붙인 고유 경로를 반환.

    Args:
        output_path: 후보 출력 파일 경로.

    Returns:
        str: 기존 파일이 없으면 원본 경로, 있으면 충돌을 피한 새 경로.
    """
    if not os.path.exists(output_path):
        return output_path
    base, ext = os.path.splitext(output_path)
    counter = 2
    candidate = f"{base} ({counter}){ext}"
    while os.path.exists(candidate):
        counter += 1
        candidate = f"{base} ({counter}){ext}"
    return candidate


def resolve_export_filename(
    filename: str,
    naming_rule: str,
    file_titles: dict[str, str],
    ext: str = ".txt",
    duplicate_titles: set[str] | None = None,
) -> str:
    """선택된 명명 규칙에 따라 안전한 내보내기 파일명 생성.

    Args:
        filename: 원본 파일명 (예: storydata_5136000.json).
        naming_rule: 명명 규칙 ('original', 'title', 'id_title').
        file_titles: 파일명->DB 타이틀 매핑 딕셔너리.
        ext: 파일 확장자 (예: .txt, .md).
        duplicate_titles: 중복된 타이틀 집합 (동일 타이틀 발견 시 ({adv_id}) 추가용).

    Returns:
        금지 문자가 전각으로 치환된 최종 파일명.
    """
    base_name = os.path.splitext(filename)[0]
    adv_id = None
    match = STORYDATA_ADV_ID_BARE_RE.match(base_name)
    if match:
        adv_id = match.group(1)

    title = file_titles.get(filename, "").strip()
    if title == filename or not title:
        title = ""

    if naming_rule == 'title':
        if title:
            sanitized_title = sanitize_filename(title)
            # 동일 타이틀이 발견된 경우 타이틀 끝에 ({adv_id}) 추가
            if duplicate_titles and title in duplicate_titles and adv_id:
                candidate = f"{sanitized_title} ({adv_id})"
            else:
                candidate = sanitized_title
        else:
            candidate = sanitize_filename(base_name)
    elif naming_rule == 'id_title':
        if adv_id and title:
            candidate = f"[{adv_id}] {sanitize_filename(title)}"
        elif title:
            candidate = sanitize_filename(title)
        else:
            candidate = sanitize_filename(base_name)
    else:  # 'original'
        candidate = sanitize_filename(base_name)

    return candidate + ext


def _format_script_mode_markdown(data: dict[str, Any], lang_dict: dict[str, str]) -> str:
    """대본(script) 모드 데이터를 마크다운 규격에 맞춰 포매팅.

    StoryFormatter.iter_script_nodes의 공용 장면 순회 결과를 마크다운으로 렌더링.

    Args:
        data: 포맷팅할 스토리 데이터 딕셔너리.
        lang_dict: 다국어 딕셔너리.

    Returns:
        마크다운 문자열.
    """
    # 다국어 라벨 획득
    branch_point_label = lang_dict.get('script_branch_point', 'Branch Point')
    choice_item_label = lang_dict.get('script_choice_item', 'Choice')
    place_prefix = lang_dict.get('script_place_prefix', 'Place')

    md_out: list[str] = []
    for node in StoryFormatter.iter_script_nodes(data, lang_dict):
        b_prefix = "> " if node.in_branch else ""

        # 상단 타이틀 및 줄거리 노드
        if node.kind == 'header':
            if node.title and node.situation and node.title != node.situation:
                md_out.append(f"# {node.title}\n\n### {node.situation}\n\n")
            elif node.title:
                md_out.append(f"# {node.title}\n\n")
            elif node.situation:
                md_out.append(f"# {node.situation}\n\n")

            if node.outline:
                md_out.append(f"---\n\n### 【 {node.outline_title} 】\n\n{node.outline}\n\n---\n\n")
            elif node.title or node.situation:
                md_out.append("---\n\n")

        # 합류 씬 헤더 노드
        elif node.kind == 'merge':
            md_out.append(f"---\n\n### ═ [ Scene {node.scene_key} ] ═\n\n")

        # 분기 씬 헤더 노드
        elif node.kind == 'branch_start':
            md_out.append(f"> #### ┌─ [ {node.scene_range} | {node.branch_label}{node.tag_suffix} ] ─┐\n>\n")

        # 장소 노드
        elif node.kind == 'place':
            md_out.append(f"{b_prefix}*[{place_prefix}: {node.place}]*\n{b_prefix}\n")

        # 대사 노드
        elif node.kind == 'print':
            if node.speaker:
                md_out.append(f"{b_prefix}**[{node.speaker}]**  \n")
            for line in node.lines:
                md_out.append(f"{b_prefix}{line}  \n")
            md_out.append(f"{b_prefix}\n")

        # 선택지 노드
        elif node.kind == 'choice':
            if len(node.choices) > 1:
                md_out.append(f"{b_prefix}**▼ [{branch_point_label} | Scene {node.scene_key}]**\n{b_prefix}\n")
                for choice in node.choices:
                    dest = f"[Scene {choice.target_scene}]" if choice.target_scene else ""
                    tag_str = f" *(Tag {choice.tag})*" if choice.tag else ""
                    dest_str = f" ➔ **{dest}**" if dest else ""
                    md_out.append(f"{b_prefix}- **[{choice_item_label} {choice.idx}]** {choice.text}{tag_str}{dest_str}  \n")
                md_out.append(f"{b_prefix}\n")
            else:
                choice = node.choices[0]
                target_dest = f" ➔ **[Scene {choice.target_scene}]**" if choice.target_scene else ""
                tag_str = f" *(Tag {choice.tag})*" if choice.tag else ""
                md_out.append(f"{b_prefix}**─ [ {choice_item_label} | Scene {node.scene_key} ] ─**  \n")
                md_out.append(f"{b_prefix}1. {choice.text}{tag_str}{target_dest}  \n{b_prefix}\n")

        # 분기 씬 박스 마감 노드
        elif node.kind == 'branch_end':
            md_out.append(f">\n> └── ▶ **{node.leads_to}**\n\n")

        # 대사 없음 안내 노드
        elif node.kind == 'no_dialogue':
            md_out.append(f"*({node.message})*\n")

    return "".join(md_out)


def _format_generic_mode_markdown(rendered: list[tuple[str, str | None]]) -> str:
    """심플/상세 모드 태그 텍스트를 마크다운 헤딩 및 리스트로 변환."""
    md_lines: list[str] = []
    for text, tag in rendered:
        if tag == 'scene_header':
            clean = text.strip()
            md_lines.append(f"## {clean}\n\n")
        elif tag == 'key':
            clean = text.strip()
            md_lines.append(f"#### {clean}\n")
        elif tag == 'print_sub_key':
            clean = text.strip()
            md_lines.append(f"- {clean}\n")
        elif tag == 'choice':
            clean = text.strip()
            md_lines.append(f"- {clean}")
        elif tag == 'choice_tag':
            clean = text.strip()
            md_lines.append(f" *{clean}*\n")
        else:
            if '----------------' in text or '━━━━━━━━' in text:
                md_lines.append("\n---\n\n")
            else:
                md_lines.append(text)
    return "".join(md_lines)


def format_content_for_export(
    data: dict[str, Any],
    view_mode: str,
    lang_dict: dict[str, str],
    file_format: str = "txt",
) -> str:
    """스토리 데이터를 선택된 형식(txt/md)과 서식 모드(script/simple/detailed)로 렌더링."""
    if file_format != 'md':
        rendered = StoryFormatter.format_story_data(data, view_mode, lang_dict)
        return "".join([text for text, _ in rendered])

    if view_mode == 'script':
        return _format_script_mode_markdown(data, lang_dict)
    else:
        rendered = StoryFormatter.format_story_data(data, view_mode, lang_dict)
        return _format_generic_mode_markdown(rendered)


class StoryExportHandler:
    """Story Viewer 데이터 내보내기 처리 핸들러."""

    def __init__(
        self,
        get_lang_dict: Callable[[], dict[str, str]],
        master: tk.Tk | tk.Toplevel,
        view_mode_var: tk.StringVar,
        get_current_filenames: Callable[[], list[str]],
        get_loaded_filenames: Callable[[], list[str]],
        get_all_files: Callable[[], dict[str, str]],
        get_search_data: Callable[[], dict[str, list[str]]],
        get_server_db_info: Callable[[], dict[str, Any]],
        get_db_manager: Callable[[], StoryDBManager],
        view: StoryViewerView,
        get_file_titles: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._get_lang_dict = get_lang_dict
        self._master = master
        self._view_mode_var = view_mode_var
        self._get_current_filenames = get_current_filenames
        self._get_loaded_filenames = get_loaded_filenames
        self._get_all_files = get_all_files
        self._get_search_data = get_search_data
        self._get_server_db_info = get_server_db_info
        self._get_db_manager = get_db_manager
        self._view = view
        self._get_file_titles = get_file_titles or (dict)

    @staticmethod
    def _save_list_to_file(data_list: list[str], filename_suffix: str, output_folder: str, header: str = "", empty_msg: str | None = None) -> tuple[bool, Exception | None]:
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        output_path = make_unique_export_path(output_path)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    if header:
                        f.write(f"--- {header} ---\n\n")
                    f.writelines(f"{item}\n" for item in data_list)
                else:
                    if empty_msg is None:
                        empty_msg = f"(No data found for {filename_suffix})"
                    f.write(f"{empty_msg}\n")
            return True, None
        except (OSError, UnicodeError) as e:
            return False, e

    def export_master_thread(
        self,
        selected_options: dict[str, Any],
        output_folder: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        """선택된 여러 유형의 데이터를 백그라운드 스레드에서 파일로 내보내기 실행."""
        lang_dict = self._get_lang_dict()
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []
        file_titles = self._get_file_titles()
        was_cancelled = False

        try:
            naming_rule = selected_options.get('naming_rule', 'original')
            file_format = selected_options.get('file_format', 'txt')
            target_ext = f".{file_format}"
            target_view_mode = selected_options.get('view_mode', self._view_mode_var.get())

            # 1. 대상 스토리 파일 목록 산출
            filenames_to_export: list[str] = []
            if selected_options.get('story_data'):
                story_data_scope = selected_options.get('story_data_scope', 'current_list')
                if story_data_scope == 'single_file':
                    filenames_to_export = list(selected_options.get('target_filenames', []))
                elif story_data_scope == 'current_list':
                    filenames_to_export = self._get_current_filenames()
                elif story_data_scope == 'all_loaded':
                    filenames_to_export = self._get_loaded_filenames()

            # 2. 기타 목록 태스크 정의
            loaded_filenames = self._get_loaded_filenames()
            search_data = self._get_search_data()

            def _get_voices() -> list[str]:
                voices = search_data.get('voices', [])
                if voices:
                    return sorted(voices)
                collected = set()
                all_files_map = self._get_all_files()
                for fp in all_files_map.values():
                    is_val, d, _ = StoryDataLoader.is_valid_storydata(fp)
                    if is_val and isinstance(d, dict):
                        for sc in d.values():
                            if isinstance(sc, dict) and 'vo' in sc:
                                v_name = StoryDataLoader.extract_asset_name(sc['vo'])
                                if v_name:
                                    collected.add(v_name)
                return sorted(collected)

            other_export_types: list[OtherExportTask] = [
                {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': lambda: sorted(loaded_filenames), 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
                {'type': 'character_names', 'name_key': 'export_type_character_names', 'data_func': lambda: sorted(search_data.get('character_names', [])), 'file_suffix': 'character_names', 'header_key': 'export_type_character_names'},
                {'type': 'bgm_names', 'name_key': 'export_type_bgm_names', 'data_func': lambda: sorted(search_data.get('bgms', [])), 'file_suffix': 'bgm_names', 'header_key': 'export_type_bgm_names'},
                {'type': 'background_names', 'name_key': 'export_type_background_names', 'data_func': lambda: sorted(search_data.get('backgrounds', [])), 'file_suffix': 'background_names', 'header_key': 'export_type_background_names'},
                {'type': 'voice_names', 'name_key': 'export_type_voice_names', 'data_func': _get_voices, 'file_suffix': 'voice_names', 'header_key': 'export_type_voice_names'},
            ]

            if selected_options.get('event_list_master'):
                server_db_info = self._get_server_db_info()
                db_manager = self._get_db_manager()

                def get_event_list(server_key: str) -> list[str]:
                    db_info = server_db_info.get(server_key)
                    if not db_info or not db_manager.db_status.get(server_key):
                        return []
                    try:
                        return sorted(db_helper.fetch_event_names(db_info))
                    except sqlite3.Error:
                        return []

                other_export_types.extend([
                    {'type': 'event_list_jp', 'name_key': 'export_type_event_list_jp', 'data_func': lambda: get_event_list('JP'), 'file_suffix': 'event_list_jp', 'header_key': 'export_type_event_list_jp'},
                    {'type': 'event_list_kr', 'name_key': 'export_type_event_list_kr', 'data_func': lambda: get_event_list('KR'), 'file_suffix': 'event_list_kr', 'header_key': 'export_type_event_list_kr'},
                ])

            active_other_tasks = [t for t in other_export_types if selected_options.get(t['type'])]

            # 3. 전체 작업 총합 계산 (스토리 파일 수 + 기타 목록 수)
            total_items = (len(filenames_to_export) if selected_options.get('story_data') else 0) + len(active_other_tasks)
            current_step = 0

            # 스토리 데이터 내보내기 진행
            if selected_options.get('story_data'):
                if not filenames_to_export:
                    no_files_msg = lang_dict.get('msgbox_no_export_files_msg', 'There are no files to export.')
                    export_results['story_data'] = {'success': 0, 'failed': 0, 'details': [no_files_msg]}
                else:
                    type_name = lang_dict.get('export_type_story_data', 'Story Data')
                    success_count = 0
                    fail_count = 0
                    current_failed_details = []

                    # 중복 타이틀 사전 집계 (동일 타이틀 감지 시 끝에 ({adv_id}) 추가용)
                    title_counts: dict[str, int] = {}
                    for fn in filenames_to_export:
                        t = file_titles.get(fn, "").strip()
                        if t and t != fn:
                            title_counts[t] = title_counts.get(t, 0) + 1
                    duplicate_titles = {t for t, count in title_counts.items() if count > 1}
                    used_filenames: set[str] = set()

                    all_files = self._get_all_files()
                    for filename in filenames_to_export:
                        if check_cancelled and check_cancelled():
                            was_cancelled = True
                            break

                        current_step += 1
                        if progress_callback:
                            progress_callback(current_step, total_items, type_name)

                        def _update_status(tn: str = type_name, s: int = success_count, f: int = fail_count, step: int = current_step, tot: int = total_items) -> None:
                            self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=step, t=tot)
                        post_to_ui(_update_status)

                        filepath = all_files.get(filename)
                        if not filepath:
                            fail_count += 1
                            fnf_msg = lang_dict.get('export_err_file_not_found', 'File Not Found')
                            current_failed_details.append(f"{filename} ({fnf_msg})")
                            continue

                        is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
                        if not is_valid or not isinstance(data, dict):
                            fail_count += 1
                            parse_err_msg = lang_dict.get('export_err_parse_error', 'Parse Error')
                            current_failed_details.append(f"{filename} ({parse_err_msg})")
                            continue

                        out_fname = resolve_export_filename(
                            filename, naming_rule, file_titles, target_ext, duplicate_titles=duplicate_titles
                        )

                        # 2차 파일명 충돌 방지 (혹시 이미 사용된 파일명이 존재하는 경우)
                        if out_fname in used_filenames:
                            f_base, f_ext = os.path.splitext(out_fname)
                            match_id = STORYDATA_ADV_ID_BARE_RE.match(os.path.splitext(filename)[0])
                            adv_id_val = match_id.group(1) if match_id else None
                            if adv_id_val and f"({adv_id_val})" not in f_base:
                                out_fname = f"{f_base} ({adv_id_val}){f_ext}"
                            counter = 2
                            while out_fname in used_filenames:
                                out_fname = f"{f_base} ({counter}){f_ext}"
                                counter += 1

                        used_filenames.add(out_fname)
                        output_path = make_unique_export_path(os.path.join(output_folder, out_fname))
                        # 접미사가 붙은 실제 파일명도 중복 집합에 등록해 후속 항목과의 충돌을 방지
                        used_filenames.add(os.path.basename(output_path))
                        try:
                            text_to_write = format_content_for_export(data, target_view_mode, self._get_lang_dict(), file_format)
                            with open(output_path, 'w', encoding='utf-8') as f:
                                f.write(text_to_write)
                            success_count += 1
                        except (OSError, json.JSONDecodeError, UnicodeError) as e:
                            fail_count += 1
                            err_fmt = lang_dict.get('export_err_detail_format', '{name} (Error: {e})')
                            current_failed_details.append(err_fmt.format(name=filename, e=e, item=filename, err=e))

                    export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                    total_exported_count += success_count
                    total_failed_count += fail_count
                    all_failed_details.extend(current_failed_details)

            # 기타 목록 데이터 내보내기 진행
            if not was_cancelled:
                for task in active_other_tasks:
                    if check_cancelled and check_cancelled():
                        was_cancelled = True
                        break

                    current_step += 1
                    task_type = task['type']
                    type_name = lang_dict.get(task['name_key'], task_type)

                    if progress_callback:
                        progress_callback(current_step, total_items, type_name)

                    def _make_status_action(tn: str = type_name) -> Callable[[], None]:
                        return lambda: self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0)
                    post_to_ui(_make_status_action(type_name))
                    try:
                        data_list = task['data_func']()
                        if not data_list:
                            no_data_msg = lang_dict.get('export_err_no_data', 'No data found for {name}.').format(name=type_name)
                            export_results[task_type] = {'success': 0, 'failed': 0, 'details': [no_data_msg]}
                            continue

                        empty_list_msg = lang_dict.get('export_empty_list_content', '(No data found for {name})\n').format(name=task['file_suffix'])
                        success, error = self._save_list_to_file(
                            data_list, task['file_suffix'], output_folder,
                            lang_dict.get(task['header_key'], type_name) if 'event_list' in task_type else "",
                            empty_msg=empty_list_msg
                        )
                        if success:
                            total_exported_count += 1
                        else:
                            total_failed_count += 1
                            err_fmt = lang_dict.get('export_err_detail_format', '{name} (Error: {e})')
                            all_failed_details.append(err_fmt.format(name=type_name, e=error, item=type_name, err=error))
                    except (sqlite3.Error, OSError) as e:
                        total_failed_count += 1
                        err_fmt = lang_dict.get('export_err_detail_format', '{name} (Error: {e})')
                        all_failed_details.append(err_fmt.format(name=type_name, e=e, item=type_name, err=e))
        except Exception as e:  # noqa: BLE001
            total_failed_count += 1
            err_fmt = lang_dict.get('export_err_detail_format', '{name} (Error: {e})')
            all_failed_details.append(err_fmt.format(name="Export", e=e, item="Export", err=e))
        finally:
            # 4. 종료 처리
            def _on_complete_ui() -> None:
                if on_finish:
                    on_finish()
                self._finish_export(
                    total_exported_count, total_failed_count, all_failed_details,
                    was_cancelled=was_cancelled,
                    open_folder_after=selected_options.get('open_folder_after', False),
                    output_folder=output_folder
                )

            post_to_ui(_on_complete_ui)

    def _finish_export(
        self,
        exported_count: int,
        failed_count: int,
        failed_list: list[str],
        was_cancelled: bool = False,
        open_folder_after: bool = False,
        output_folder: str = "",
    ) -> None:
        """데이터 내보내기 작업 완료 후 결과를 UI 및 사용자에게 통지."""
        from tkinter import messagebox
        lang_dict = self._get_lang_dict()

        if was_cancelled:
            messagebox.showinfo(
                lang_dict.get('msgbox_export_cancelled_title', 'Export Cancelled'),
                lang_dict.get('msgbox_export_cancelled_msg', 'Data export operation was cancelled.'),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_initial')
            return

        if exported_count > 0:
            msg_fmt = lang_dict.get('msgbox_export_complete_msg', 'Successfully exported {exported_count} files/lists.')
            messagebox.showinfo(
                lang_dict.get('msgbox_export_complete_title', 'Export Complete'),
                msg_fmt.format(exported_count=exported_count),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
            if open_folder_after and output_folder and os.path.exists(output_folder):
                with contextlib.suppress(OSError):
                    open_with_default_app(output_folder)
        else:
            msg_fmt = lang_dict.get('msgbox_export_failed_msg', 'No files/lists were exported. An error occurred in {failed_count} items.')
            messagebox.showwarning(
                lang_dict.get('msgbox_export_failed_title', 'Export Failed'),
                msg_fmt.format(failed_count=failed_count),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)

        if failed_list:
            error_msg = "\n".join(failed_list)
            err_details_fmt = lang_dict.get('msgbox_export_error_details_msg', 'Error occurred while exporting the following files/lists:\n{errors}')
            messagebox.showerror(
                lang_dict.get('msgbox_export_error_details_title', 'Export Error Details'),
                err_details_fmt.format(errors=error_msg),
                parent=self._master
            )
