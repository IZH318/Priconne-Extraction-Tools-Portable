from __future__ import annotations
import json
import os
import re
import sqlite3
import tkinter as tk
from typing import Any, Callable, TYPE_CHECKING
import queue

from src.queue_events import ActionEvent
from .logic import StoryDataLoader, StoryFormatter
from . import db_helper

if TYPE_CHECKING:
    from .view import StoryViewerView
    from .db_manager import StoryDBManager


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
    """윈도우 파일 시스템 금지 문자를 전각 문자로 1:1 치환합니다."""
    return name.translate(FILENAME_SANITIZE_MAP).strip()


def resolve_export_filename(
    filename: str,
    naming_rule: str,
    file_titles: dict[str, str],
    ext: str = ".txt",
    duplicate_titles: set[str] | None = None,
) -> str:
    """선택된 명명 규칙에 따라 안전한 내보내기 파일명을 생성합니다.

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
    match = re.match(r'^storydata_(\d+)$', base_name)
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
    """대본(script) 모드 데이터를 마크다운 문법에 완벽히 맞춰 포매팅합니다."""
    scene_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))

    # 1. 태그 -> 씬 번호 매핑
    tag_to_scene: dict[str, str] = {}
    for k in scene_keys:
        s = data[k]
        if isinstance(s, dict) and 'tag' in s:
            tag_to_scene[str(s['tag']).strip()] = k

    # 2. 선택지 태그 정보 매핑
    tag_to_choice_info: dict[str, tuple[str, int, str]] = {}
    for k in scene_keys:
        s = data[k]
        if isinstance(s, dict) and 'choice' in s and isinstance(s['choice'], list):
            for idx, c in enumerate(s['choice'], 1):
                if isinstance(c, dict) and 'tag' in c:
                    tag_to_choice_info[str(c['tag']).strip()] = (k, idx, c.get('text', ''))

    branch_scenes_set = {
        k for k, s in data.items()
        if isinstance(s, dict) and str(s.get('tag', '') or '').strip() in tag_to_choice_info
    }

    # 3. 다중 선택지 합류 씬 계산
    multi_choice_merge: dict[str, str] = {}
    for key in scene_keys:
        scene = data[key]
        if not isinstance(scene, dict):
            continue
        choices = scene.get('choice')
        if choices and isinstance(choices, list) and len(choices) > 1:
            branch_scenes: list[int] = []
            for c in choices:
                if isinstance(c, dict):
                    t = str(c.get('tag', '') or '').strip()
                    if t in tag_to_scene and tag_to_scene[t].isdigit():
                        branch_scenes.append(int(tag_to_scene[t]))
            for bs in list(branch_scenes):
                sub_s = data.get(str(bs), {})
                if isinstance(sub_s, dict):
                    sub_ch = sub_s.get('choice')
                    if sub_ch and isinstance(sub_ch, list):
                        for sc in sub_ch:
                            if isinstance(sc, dict):
                                st = str(sc.get('tag', '') or '').strip()
                                if st in tag_to_scene and tag_to_scene[st].isdigit():
                                    branch_scenes.append(int(tag_to_scene[st]))
            if branch_scenes:
                max_bs = max(branch_scenes)
                cand_merge = str(max_bs + 1)
                cand_scene = data.get(cand_merge)
                if cand_merge in data and isinstance(cand_scene, dict) and (
                    'print' in cand_scene or 'choice' in cand_scene or 'place' in cand_scene or 'situation' in cand_scene
                ):
                    multi_choice_merge[key] = cand_merge

    merge_target_scenes = set(multi_choice_merge.values())

    # 4. 분기 목적지 사전 계산
    branch_destinations: dict[str, str | None] = {}
    for b_key in sorted(branch_scenes_set, key=lambda x: int(x) if x.isdigit() else float('inf')):
        b_scene = data.get(b_key, {})
        if not isinstance(b_scene, dict):
            continue
        if bool(b_scene.get('choice') and isinstance(b_scene.get('choice'), list) and len(b_scene.get('choice')) > 0):
            branch_destinations[b_key] = None
            continue
        b_dest = None
        g_tag = str(b_scene.get('goto', '') or '').strip()
        if g_tag and g_tag in tag_to_scene:
            t_sc = tag_to_scene[g_tag]
            t_data = data.get(t_sc, {})
            if isinstance(t_data, dict) and ('print' in t_data or 'choice' in t_data or 'place' in t_data or 'situation' in t_data):
                b_dest = t_sc
        b_tag = str(b_scene.get('tag', '') or '').strip()
        if not b_dest and b_tag in tag_to_choice_info:
            from_sc, _, _ = tag_to_choice_info[b_tag]
            m_sc = multi_choice_merge.get(from_sc)
            if m_sc and m_sc in data:
                m_data = data.get(m_sc, {})
                if isinstance(m_data, dict) and ('print' in m_data or 'choice' in m_data or 'place' in m_data or 'situation' in m_data):
                    b_dest = m_sc
        if not b_dest:
            b_idx = scene_keys.index(b_key) if b_key in scene_keys else -1
            if b_idx >= 0:
                for next_k in scene_keys[b_idx + 1:]:
                    next_s = data.get(next_k, {})
                    if isinstance(next_s, dict) and ('print' in next_s or 'choice' in next_s or 'place' in next_s or 'situation' in next_s):
                        if next_k not in branch_scenes_set:
                            b_dest = next_k
                            break
        branch_destinations[b_key] = b_dest
        if b_dest and b_dest not in branch_scenes_set:
            merge_target_scenes.add(b_dest)

    # 5. 다국어 라벨 로드 (정규 script_* 키 매핑)
    outline_title = lang_dict.get('script_outline_title', '줄거리')
    branch_point_label = lang_dict.get('script_branch_point', '분기점')
    choice_item_label = lang_dict.get('script_choice_item', '선택')
    branch_dialogue_label = lang_dict.get('script_branch_dialogue', '분기 대사')
    branch_leads_to_fmt = lang_dict.get('script_branch_leads_to', '[Scene {scene}] (으)로 이어짐')
    branch_end_label = lang_dict.get('script_branch_end', '[스토리 종료]')
    place_prefix = lang_dict.get('script_place_prefix', '장소')
    no_dialogue_msg = lang_dict.get('script_no_dialogue', '대사 데이터가 없는 스토리입니다')

    md_out: list[str] = []
    scene_0 = data.get('0', {})
    title = str(scene_0.get('title', '') or '').strip() if isinstance(scene_0, dict) else ''
    situation = str(scene_0.get('situation', '') or '').strip() if isinstance(scene_0, dict) else ''
    outline = str(scene_0.get('outline', '') or '').strip() if isinstance(scene_0, dict) else ''

    if title and situation and title != situation:
        md_out.append(f"# {title}\n\n### {situation}\n\n")
    elif title:
        md_out.append(f"# {title}\n\n")
    elif situation:
        md_out.append(f"# {situation}\n\n")

    if outline:
        md_out.append(f"---\n\n### 【 {outline_title} 】\n\n{outline}\n\n---\n\n")
    elif title or situation:
        md_out.append("---\n\n")

    has_dialogue = False
    last_place = None

    for key in scene_keys:
        scene = data[key]
        if not isinstance(scene, dict):
            continue
        has_content = ('print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene)
        if key != '0' and not has_content:
            continue

        if key != '0' and key in merge_target_scenes:
            md_out.append(f"---\n\n### ═ [ Scene {key} ] ═\n\n")

        raw_place = scene.get('place')
        p_str = ""
        if isinstance(raw_place, list) and raw_place:
            p_str = str(raw_place[0]).strip()
        elif isinstance(raw_place, str):
            p_str = raw_place.strip()

        if p_str and p_str != title and p_str != situation and p_str != last_place:
            md_out.append(f"*[{place_prefix}: {p_str}]*\n\n")
            last_place = p_str
            has_dialogue = True

        branch_tag = str(scene.get('tag', '') or '').strip()
        is_branch = (key != '0' and bool(branch_tag) and branch_tag in tag_to_choice_info and has_content)

        if is_branch:
            from_sc, ch_idx, _ = tag_to_choice_info[branch_tag]
            lbl = f"{choice_item_label} {ch_idx}번 {branch_dialogue_label}" if branch_dialogue_label == "분기 대사" else f"{choice_item_label} {ch_idx} {branch_dialogue_label}"
            md_out.append(f"> #### ┌─ [ Scene {key} | {lbl} (Tag {branch_tag}) ] ─┐\n>\n")
            has_dialogue = True

        b_prefix = "> " if is_branch else ""

        p_data = scene.get('print')
        if p_data and isinstance(p_data, dict):
            speaker = str(p_data.get('name', '') or '').strip()
            text = str(p_data.get('text', '') or '').strip()
            if text:
                has_dialogue = True
                if speaker:
                    md_out.append(f"{b_prefix}**[{speaker}]**  \n")
                for line in text.splitlines():
                    md_out.append(f"{b_prefix}{line}  \n")
                md_out.append(f"{b_prefix}\n")

        choices = scene.get('choice')
        if choices and isinstance(choices, list) and len(choices) > 0:
            has_dialogue = True
            if len(choices) > 1:
                target_merge = multi_choice_merge.get(key)
                md_out.append(f"{b_prefix}> ### ▼ [{branch_point_label} | Scene {key}]\n{b_prefix}>\n")
                for idx, c in enumerate(choices, 1):
                    c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                    c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                    target_sc = tag_to_scene.get(c_tag)
                    dest = f"[Scene {target_sc}]" if target_sc else (f"[Scene {target_merge}]" if target_merge else "")
                    tag_str = f" *(Tag {c_tag})*" if c_tag else ""
                    dest_str = f" ➔ **{dest}**" if dest else ""
                    md_out.append(f"{b_prefix}> - **[{choice_item_label} {idx}]** {c_text}{tag_str}{dest_str}\n")
                md_out.append(f"{b_prefix}\n")
            else:
                c = choices[0]
                c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                target_sc = tag_to_scene.get(c_tag)
                target_dest = f" ➔ **[Scene {target_sc}]**" if target_sc else ""
                tag_str = f" *(Tag {c_tag})*" if c_tag else ""
                md_out.append(f"{b_prefix}> **─ [ {choice_item_label} | Scene {key} ] ─**  \n")
                md_out.append(f"{b_prefix}> 1. {c_text}{tag_str}{target_dest}\n{b_prefix}\n")

        if is_branch:
            has_own_choice = bool(scene.get('choice') and isinstance(scene.get('choice'), list) and len(scene.get('choice')) > 0)
            if not has_own_choice:
                dest_scene = branch_destinations.get(key)
                label = branch_leads_to_fmt.format(scene=dest_scene) if dest_scene else branch_end_label
                md_out.append(f"> └───▶ **{label}**\n\n")

    if not has_dialogue and not (title or outline):
        md_out.append(f"*({no_dialogue_msg})*\n")

    return "".join(md_out)


def _format_generic_mode_markdown(rendered: list[tuple[str, str | None]]) -> str:
    """심플/상세 모드 태그 텍스트를 마크다운 헤딩 및 리스트로 변환합니다."""
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
    """스토리 데이터를 선택된 형식(txt/md)과 서식 모드(script/simple/detailed)로 렌더링합니다."""
    if file_format != 'md':
        rendered = StoryFormatter.format_story_data(data, view_mode, lang_dict)
        return "".join([text for text, _ in rendered])

    if view_mode == 'script':
        return _format_script_mode_markdown(data, lang_dict)
    else:
        rendered = StoryFormatter.format_story_data(data, view_mode, lang_dict)
        return _format_generic_mode_markdown(rendered)


class StoryExportHandler:
    """Story Viewer의 데이터 내보내기 기능을 전담하는 핸들러 클래스입니다."""

    def __init__(
        self,
        get_lang_dict: Callable[[], dict[str, str]],
        task_queue: queue.Queue[ActionEvent],
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
        self._task_queue = task_queue
        self._master = master
        self._view_mode_var = view_mode_var
        self._get_current_filenames = get_current_filenames
        self._get_loaded_filenames = get_loaded_filenames
        self._get_all_files = get_all_files
        self._get_search_data = get_search_data
        self._get_server_db_info = get_server_db_info
        self._get_db_manager = get_db_manager
        self._view = view
        self._get_file_titles = get_file_titles or (lambda: {})

    @staticmethod
    def _save_list_to_file(data_list: list[str], filename_suffix: str, output_folder: str, header: str = "") -> tuple[bool, Exception | None]:
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    if header:
                        f.write(f"--- {header} ---\n\n")
                    for item in data_list:
                        f.write(f"{item}\n")
                else:
                    f.write(f"(No data found for {filename_suffix})\n")
            return True, None
        except OSError as e:
            return False, e

    def export_master_thread(
        self,
        selected_options: dict[str, Any],
        output_folder: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
        check_cancelled: Callable[[], bool] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        """선택된 여러 유형의 데이터들을 백그라운드 스레드에서 파일로 내보냅니다."""
        lang_dict = self._get_lang_dict()
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []
        file_titles = self._get_file_titles()

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
                return sorted(list(voices))
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
            return sorted(list(collected))

        other_export_types = [
            {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': lambda: sorted(list(loaded_filenames)), 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
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

        # 3. 안 B: 전체 작업 총합 계산 (스토리 파일 수 + 기타 목록 수)
        total_items = (len(filenames_to_export) if selected_options.get('story_data') else 0) + len(active_other_tasks)
        current_step = 0
        was_cancelled = False

        # --- A. 스토리 데이터 추출 진행 ---
        if selected_options.get('story_data'):
            if not filenames_to_export:
                export_results['story_data'] = {'success': 0, 'failed': 0, 'details': ["No story data files selected for export."]}
            else:
                type_name = lang_dict.get('export_type_story_data', '스토리 데이터')
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
                for i, filename in enumerate(filenames_to_export):
                    if check_cancelled and check_cancelled():
                        was_cancelled = True
                        break

                    current_step += 1
                    if progress_callback:
                        progress_callback(current_step, total_items, type_name)

                    def _update_status(tn=type_name, s=success_count, f=fail_count, step=current_step, tot=total_items):
                        self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=step, t=tot)
                    self._task_queue.put(ActionEvent(action=_update_status))

                    filepath = all_files.get(filename)
                    if not filepath:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (File Not Found)")
                        continue

                    is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
                    if not is_valid or not isinstance(data, dict):
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Parse Error)")
                        continue

                    out_fname = resolve_export_filename(
                        filename, naming_rule, file_titles, target_ext, duplicate_titles=duplicate_titles
                    )

                    # 2차 충돌 안전 방어 (혹시 이미 사용된 파일명이 존재하는 경우)
                    if out_fname in used_filenames:
                        f_base, f_ext = os.path.splitext(out_fname)
                        match_id = re.match(r'^storydata_(\d+)$', os.path.splitext(filename)[0])
                        adv_id_val = match_id.group(1) if match_id else None
                        if adv_id_val and f"({adv_id_val})" not in f_base:
                            out_fname = f"{f_base} ({adv_id_val}){f_ext}"
                        counter = 2
                        while out_fname in used_filenames:
                            out_fname = f"{f_base} ({counter}){f_ext}"
                            counter += 1

                    used_filenames.add(out_fname)
                    output_path = os.path.join(output_folder, out_fname)
                    try:
                        text_to_write = format_content_for_export(data, target_view_mode, self._get_lang_dict(), file_format)
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(text_to_write)
                        success_count += 1
                    except (OSError, json.JSONDecodeError) as e:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Error: {e})")

                export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        # --- B. 기타 목록 데이터 추출 진행 ---
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

                self._task_queue.put(ActionEvent(action=lambda tn=type_name: self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0)))
                try:
                    data_list = task['data_func']()
                    if not data_list:
                        export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                        continue

                    success, error = self._save_list_to_file(
                        data_list, task['file_suffix'], output_folder,
                        lang_dict.get(task['header_key'], type_name) if 'event_list' in task_type else ""
                    )
                    if success:
                        total_exported_count += 1
                    else:
                        total_failed_count += 1
                        all_failed_details.append(f"{type_name} (Error: {error})")
                except (sqlite3.Error, OSError) as e:
                    total_failed_count += 1
                    all_failed_details.append(f"{type_name} (Unexpected Error: {e})")

        # 4. 종료 처리
        def _on_complete_ui():
            if on_finish:
                on_finish()
            self._finish_export(
                total_exported_count, total_failed_count, all_failed_details,
                was_cancelled=was_cancelled,
                open_folder_after=selected_options.get('open_folder_after', False),
                output_folder=output_folder
            )

        self._task_queue.put(ActionEvent(action=_on_complete_ui))

    def _finish_export(
        self,
        exported_count: int,
        failed_count: int,
        failed_list: list[str],
        was_cancelled: bool = False,
        open_folder_after: bool = False,
        output_folder: str = "",
    ) -> None:
        """데이터 내보내기 작업 완료 후 결과를 UI와 사용자에게 알립니다."""
        from tkinter import messagebox
        lang_dict = self._get_lang_dict()

        if was_cancelled:
            messagebox.showinfo(
                lang_dict.get('msgbox_export_cancelled_title', '추출 취소'),
                lang_dict.get('msgbox_export_cancelled_msg', '데이터 내보내기 작업이 사용자에 의해 취소되었습니다.'),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_initial')
            return

        if exported_count > 0:
            messagebox.showinfo(
                lang_dict['msgbox_export_complete_title'],
                lang_dict['msgbox_export_complete_msg'].format(exported_count=exported_count),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
            if open_folder_after and output_folder and os.path.exists(output_folder):
                try:
                    os.startfile(output_folder)
                except Exception:
                    pass
        else:
            messagebox.showwarning(
                lang_dict['msgbox_export_failed_title'],
                lang_dict['msgbox_export_failed_msg'].format(failed_count=failed_count),
                parent=self._master
            )
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)

        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(
                lang_dict['msgbox_export_error_details_title'],
                lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg),
                parent=self._master
            )
