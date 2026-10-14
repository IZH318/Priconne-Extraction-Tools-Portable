from __future__ import annotations
# src/story_viewer/logic.py
import json
import re
from typing import Any, Callable

from src.constants import SEPARATOR_MEDIUM

class StoryDataLoader:
    """스토리 데이터 JSON 파일의 유효성 검증 및 에셋 이름 추출을 담당합니다."""
    @staticmethod
    def is_valid_storydata(file_path: str, lang_dict: dict[str, str] | None = None) -> tuple[bool, dict[str, Any] | None, str | None]:
        """스토리 데이터 JSON 파일이 유효한지 검사합니다.

        Args:
            file_path: 검사할 JSON 파일 경로.
            lang_dict: 오류 메시지 다국어 처리를 위한 딕셔너리.

        Returns:
            (유효성 여부, 파싱된 데이터 딕셔너리, 에러 메시지) 튜플.
        """
        if lang_dict is None:
            lang_dict = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data:
                return False, None, lang_dict.get('log_reason_empty', "File content is empty or not in dictionary format")
            if '0' in data and isinstance(data['0'], dict) and ('title' in data['0'] or 'outline' in data['0']):
                return True, data, None
            else:
                return False, None, lang_dict.get('log_reason_not_storydata', "Does not seem to be a storydata file (missing '0' key or title/outline)")
        except json.JSONDecodeError as e:
            return False, None, lang_dict.get('log_reason_json_error', "JSON format error: {e}").format(e=e)
        except OSError as e:
            return False, None, lang_dict.get('log_reason_os_error', "File read/other error: {e}").format(e=e)
        except Exception as e:
            return False, None, f"Unexpected fatal error: {e}"

    @staticmethod
    def extract_asset_name(value: Any) -> str | None:
        """스토리 데이터 값에서 에셋(배경, BGM 등)의 이름을 추출합니다.

        Args:
            value: 추출할 원본 값.

        Returns:
            추출된 문자열 이름 또는 None.
        """
        if isinstance(value, str): return value
        if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
        return None

class SearchEngine:
    """스토리 데이터에 대한 다중 조건 검색 기능을 제공합니다."""
    @staticmethod
    def check_scene(scene: dict[str, Any], criteria: dict[str, str], char_type_search: str, char_type_speaker: str) -> bool:
        """단일 씬(Scene) 데이터가 주어진 검색 조건과 일치하는지 확인합니다.

        Args:
            scene: 씬 데이터 딕셔너리.
            criteria: 소문자로 변환된 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입.
            char_type_speaker: '화자'에 해당하는 문자열.

        Returns:
            조건 일치 여부 (bool).
        """
        if 'content' in criteria and not ('print' in scene and criteria['content'] in scene['print'].get('text', '').lower()):
            return False
        if 'bgm' in criteria and not ('bgm' in scene and criteria['bgm'] in str(scene.get('bgm', '')).lower()):
            return False
        if 'background' in criteria and not ('background' in scene and criteria['background'] in str(scene.get('background', '')).lower()):
            return False
        if 'char_name' in criteria:
            char_name_crit = criteria['char_name']
            char_found = False
            if 'print' in scene:
                if char_type_search == char_type_speaker and char_name_crit in str(scene['print'].get('name', '')).lower():
                    char_found = True
                elif char_type_search != char_type_speaker and char_name_crit in scene['print'].get('text', '').lower():
                    char_found = True
            if not char_found:
                return False
        return True

    @staticmethod
    def check_file_content(data: dict[str, Any], criteria: dict[str, str], char_type_search: str, char_type_speaker: str) -> bool:
        """파일 전체 내용이 주어진 검색 조건과 일치하는지 확인합니다.

        Args:
            data: 스토리 데이터 전체 딕셔너리.
            criteria: 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입.
            char_type_speaker: '화자'에 해당하는 문자열.

        Returns:
            조건 일치 여부 (bool).
        """
        lower_criteria = {k: v.lower() for k, v in criteria.items()}
        scene_0 = data.get('0', {})
        
        if 'title' in lower_criteria and lower_criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in lower_criteria and lower_criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        # BGM 및 배경은 파일 전체 범위에서 만족하는 씬이 존재하는지 개별 평가
        if 'bgm' in lower_criteria:
            bgm_crit = lower_criteria['bgm']
            if not any('bgm' in s and bgm_crit in str(s.get('bgm', '')).lower() for s in data.values()):
                return False

        if 'background' in lower_criteria:
            bg_crit = lower_criteria['background']
            if not any('background' in s and bg_crit in str(s.get('background', '')).lower() for s in data.values()):
                return False

        # 대사/화자 조건 (char_name, content)
        dialogue_criteria = {k: v for k, v in lower_criteria.items() if k in ('char_name', 'content')}
        if not dialogue_criteria:
            return True

        for scene in data.values():
            if SearchEngine.check_scene(scene, dialogue_criteria, char_type_search, char_type_speaker):
                return True
        return False

    @staticmethod
    def check_file_for_search(filename: str, criteria: dict[str, str], char_type_search: str, char_type_speaker: str, all_files: dict[str, str]) -> bool:
        """파일 이름과 내용을 모두 포함하여 검색 조건과 일치하는지 확인합니다.

        Args:
            filename: 파일 이름.
            criteria: 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입.
            char_type_speaker: '화자'에 해당하는 문자열.
            all_files: 전체 파일 경로 딕셔너리.

        Returns:
            조건 일치 여부 (bool).
        """
        if 'filename' in criteria and criteria['filename'].lower() not in filename.lower():
            return False
        
        filepath = all_files.get(filename)
        if not filepath:
            return False
        is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
        if not is_valid:
            return False

        content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
        if not content_criteria:
            return True
            
        return SearchEngine.check_file_content(data, content_criteria, char_type_search, char_type_speaker)

class StoryFormatter:
    """스토리 데이터를 UI에 표시하기 쉬운 텍스트 및 태그 포맷으로 변환하는 유틸리티 클래스입니다.

    모든 메서드가 정적(stateless)이므로 인스턴스 생성 없이 클래스에서 직접 호출할 수 있습니다.
    """
    _FIELD_ORDER: list[str] = [
        'title', 'outline', 'movie', 'shake_anime', 'place',
        'vo', 'face', 'print', 'nod', 'wait', 'window_visible', 'change', 'chara_full', 
        'fadein', 'focus', 'jump', 'fadeout_all', 'fadeout', 'pop', 'voice_effect', 
        'change_window', 'ignore_bgm', 'eye_open', 'emotion', 'emotion_end', 'se', 'fadein_all', 
        'effect', 'effect_delete', 'se_pause', 'multi_lipsync', 'bgm', 'tag', 
        'choice', 'goto', 'text_size', 'scale', 'ui_visible', 'transition', 'black_out', 'white_out', 'bright_change', 
        'background', 'situation', 'bg_pan', 'env_stop', 'env', 'background_color', 
        'shake', 'sway', 'out_l', 'out_r', 'in_r', 'character_up_down', 'pan', 'camera_zoom', 
        'still', 'still_unit', 'still_move', 'still_normalize', 'background_blur', 
        'unknown'
    ]

    _DISPATCH_TABLE: dict[str, Callable[..., None]] | None = None

    @classmethod
    def _get_dispatch_table(cls) -> dict[str, Callable[..., None]]:
        """필드별 포매터 디스패치 테이블을 반환합니다 (최초 1회만 생성)."""
        if cls._DISPATCH_TABLE is None:
            cls._DISPATCH_TABLE = {
                'print': cls._format_print,
                'chara_full': cls._format_generic_id_list,
                'fadein': cls._format_generic_id_list,
                'fadeout': cls._format_generic_id_list,
                'face': cls._format_generic_id_list,
                'nod': cls._format_simple_id_list,
                'shake': cls._format_simple_id_list,
                'focus': cls._format_simple_id_list,
                'choice': cls._format_choice,
            }
        return cls._DISPATCH_TABLE

    @staticmethod
    def _format_script_mode(data: dict[str, Any], lang_dict: dict[str, str] | None = None) -> list[tuple[str, str | None]]:
        """스토리 데이터를 대본/소설 형식으로 가독성 높게 변환합니다."""
        content_list: list[tuple[str, str | None]] = []
        scene_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))

        # 다국어 라벨 획득
        place_prefix = lang_dict.get('script_place_prefix', '장소') if lang_dict else '장소'
        branch_point_label = lang_dict.get('script_branch_point', '분기점') if lang_dict else '분기점'
        branch_dialogue_label = lang_dict.get('script_branch_dialogue', '분기 대사') if lang_dict else '분기 대사'
        choice_item_label = lang_dict.get('script_choice_item', '선택') if lang_dict else '선택'
        outline_title = lang_dict.get('script_outline_title', '줄거리') if lang_dict else '줄거리'
        no_dialogue_msg = lang_dict.get('script_no_dialogue', '대사 데이터가 없는 스토리입니다') if lang_dict else '대사 데이터가 없는 스토리입니다'
        branch_leads_to_fmt = lang_dict.get('script_branch_leads_to', '[Scene {scene}] (으)로 이어짐') if lang_dict else '[Scene {scene}] (으)로 이어짐'
        branch_end_label = lang_dict.get('script_branch_end', '[스토리 종료]') if lang_dict else '[스토리 종료]'

        # 1. 씬 tag -> 씬 키 매핑
        tag_to_scene: dict[str, str] = {}
        for k, s in data.items():
            if isinstance(s, dict):
                t_val = str(s.get('tag', '') or '').strip()
                if t_val:
                    tag_to_scene[t_val] = k

        # 2. 선택지 tag -> (발생 씬 키, 선택지 번호, 선택지 텍스트) 매핑
        tag_to_choice_info: dict[str, tuple[str, int, str]] = {}
        for k, s in data.items():
            if isinstance(s, dict) and 'choice' in s and isinstance(s['choice'], list):
                for idx, item in enumerate(s['choice'], 1):
                    if isinstance(item, dict) and 'tag' in item:
                        t = str(item['tag'] or '').strip()
                        if t:
                            tag_to_choice_info[t] = (k, idx, str(item.get('text', '')).strip())

        branch_scenes_set = {
            k for k, s in data.items()
            if isinstance(s, dict) and str(s.get('tag', '') or '').strip() in tag_to_choice_info
        }

        # 3. 다중 선택지 합류 씬 계산 (multi_choice_merge)
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
                # 연쇄 분기 씬(Chain scenes) 탐색
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
                    has_cand_content = isinstance(cand_scene, dict) and (
                        'print' in cand_scene or 'choice' in cand_scene or 'place' in cand_scene or 'situation' in cand_scene
                    )
                    if cand_merge in data and has_cand_content:
                        multi_choice_merge[key] = cand_merge

        merge_target_scenes: set[str] = set(multi_choice_merge.values())

        # 4. 분기 목적지 사전 계산 (단일/다중 분기 복귀 씬 수집)
        branch_destinations: dict[str, str | None] = {}
        for b_key in sorted(branch_scenes_set, key=lambda x: int(x) if x.isdigit() else float('inf')):
            b_scene = data.get(b_key, {})
            if not isinstance(b_scene, dict):
                continue

            has_own_choice = bool(b_scene.get('choice') and isinstance(b_scene.get('choice'), list) and len(b_scene.get('choice')) > 0)
            if has_own_choice:
                branch_destinations[b_key] = None
                continue

            b_dest = None
            g_tag = str(b_scene.get('goto', '') or '').strip()
            if g_tag and g_tag in tag_to_scene:
                t_sc = tag_to_scene[g_tag]
                t_data = data.get(t_sc, {})
                if isinstance(t_data, dict) and (
                    'print' in t_data or 'choice' in t_data or 'place' in t_data or 'situation' in t_data
                ):
                    b_dest = t_sc

            b_tag = str(b_scene.get('tag', '') or '').strip()
            if not b_dest and b_tag in tag_to_choice_info:
                from_sc, _, _ = tag_to_choice_info[b_tag]
                m_sc = multi_choice_merge.get(from_sc)
                if m_sc and m_sc in data:
                    m_data = data.get(m_sc, {})
                    if isinstance(m_data, dict) and (
                        'print' in m_data or 'choice' in m_data or 'place' in m_data or 'situation' in m_data
                    ):
                        b_dest = m_sc

            if not b_dest:
                b_idx = scene_keys.index(b_key) if b_key in scene_keys else -1
                if b_idx >= 0:
                    for next_k in scene_keys[b_idx + 1:]:
                        next_s = data.get(next_k, {})
                        if isinstance(next_s, dict) and (
                            'print' in next_s or 'choice' in next_s or 'place' in next_s or 'situation' in next_s
                        ):
                            if next_k not in branch_scenes_set:
                                b_dest = next_k
                                break

            branch_destinations[b_key] = b_dest
            if b_dest and b_dest not in branch_scenes_set:
                merge_target_scenes.add(b_dest)

        # 5. 상단 타이틀 및 줄거리 (Scene 0)
        scene_0 = data.get('0', {})
        title = ""
        situation = ""
        outline = ""
        if isinstance(scene_0, dict):
            title = str(scene_0.get('title', '') or '').strip()
            situation = str(scene_0.get('situation', '') or '').strip()
            outline = str(scene_0.get('outline', '') or '').strip()

        if title and situation and title != situation:
            content_list.append((f"■ {title}\n", 'script_title'))
            content_list.append((f"▶ {situation}\n", 'script_subtitle'))
        elif title:
            content_list.append((f"■ {title}\n", 'script_title'))
        elif situation:
            content_list.append((f"■ {situation}\n", 'script_title'))

        if outline:
            content_list.append(("─" * 37 + "\n", 'script_divider'))
            content_list.append((f"【 {outline_title} 】\n", 'script_outline_header'))
            content_list.append((f"{outline}\n", 'script_narration'))

        if title or situation or outline:
            content_list.append(("─" * 37 + "\n\n", 'script_divider'))

        has_dialogue = False
        last_place = None

        for i, key in enumerate(scene_keys):
            scene = data[key]
            if not isinstance(scene, dict):
                continue

            has_scene_content = ('print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene)
            if key != '0' and not has_scene_content:
                continue

            # 합류 씬 헤더
            if key != '0' and key in merge_target_scenes:
                content_list.append((f"═ [ Scene {key} ] " + "═" + "\n", 'script_branch'))

            # 장소 안내 (실제 물리적 지명만 출력)
            raw_place = scene.get('place')
            place_str = ""
            if isinstance(raw_place, list) and raw_place:
                place_str = str(raw_place[0]).strip()
            elif isinstance(raw_place, str):
                place_str = raw_place.strip()

            if place_str and place_str != title and place_str != situation and place_str != last_place:
                content_list.append((f"[{place_prefix}: {place_str}]\n\n", 'script_place'))
                last_place = place_str
                has_dialogue = True

            # 분기 씬 판정
            branch_tag = str(scene.get('tag', '') or '').strip()
            has_scene_content = ('print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene)
            is_branch_scene = (key != '0' and bool(branch_tag) and branch_tag in tag_to_choice_info and has_scene_content)

            # 분기 씬 헤더
            if is_branch_scene:
                from_sc, ch_idx, ch_text = tag_to_choice_info[branch_tag]
                branch_label_str = f"{choice_item_label} {ch_idx}번 {branch_dialogue_label}" if branch_dialogue_label == "분기 대사" else f"{choice_item_label} {ch_idx} {branch_dialogue_label}"
                content_list.append((f"┌─ [ Scene {key} | {branch_label_str} (Tag {branch_tag}) ] ─┐\n", 'script_branch'))
                has_dialogue = True

            indent = "│ " if is_branch_scene else ""

            # 대사 (print)
            p_data = scene.get('print')
            if p_data and isinstance(p_data, dict):
                speaker = str(p_data.get('name', '') or '').strip()
                dialogue = str(p_data.get('text', '') or '').strip()

                if dialogue:
                    has_dialogue = True
                    if speaker:
                        content_list.append((f"{indent}[{speaker}]\n", 'script_speaker'))

                    dialogue_tag = 'script_dialogue' if speaker else 'script_narration'
                    txt_lines = dialogue.splitlines()
                    for line in txt_lines:
                        content_list.append((f"{indent}{line}\n", dialogue_tag))

                    if is_branch_scene and ('choice' in scene and scene['choice']):
                        content_list.append((f"{indent}\n", None))
                    elif not is_branch_scene:
                        content_list.append(("\n", None))

            # 선택지 (choice)
            choices = scene.get('choice')
            if choices and isinstance(choices, list) and len(choices) > 0:
                has_dialogue = True
                if len(choices) > 1:
                    target_merge = multi_choice_merge.get(key)
                    content_list.append((f"{indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", 'script_divider'))
                    content_list.append((f"{indent}▼ [{branch_point_label} | Scene {key}]\n", 'script_branch'))
                    for idx, c in enumerate(choices, 1):
                        c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                        c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                        target_sc = tag_to_scene.get(c_tag)
                        is_last = (idx == len(choices))
                        prefix = "└─" if is_last else "├─"
                        sub_indent = "       └─▶ " if is_last else "  │   └─▶ "

                        dest = f"[Scene {target_sc}]" if target_sc else (f"[Scene {target_merge}]" if target_merge else "")
                        tag_str = f" (Tag {c_tag})" if c_tag else ""

                        content_list.append((f"{indent}  {prefix} [{choice_item_label} {idx}] {c_text}", 'script_choice'))
                        if tag_str:
                            content_list.append((tag_str, 'script_choice_tag'))
                        content_list.append(("\n", None))
                        if dest:
                            content_list.append((f"{indent}{sub_indent}{dest}\n", 'script_choice_tag'))

                    content_list.append((f"{indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", 'script_divider'))
                    if not is_branch_scene:
                        content_list.append(("\n", None))
                else:
                    c = choices[0]
                    c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                    c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                    target_sc = tag_to_scene.get(c_tag)
                    target_dest = f" ─▶ [Scene {target_sc}]" if target_sc else ""
                    tag_str = f" (Tag {c_tag})" if c_tag else ""

                    content_list.append((f"{indent}─ [ {choice_item_label} | Scene {key} ] ─\n", 'script_choice'))
                    content_list.append((f"{indent}   1. {c_text}", 'script_choice'))
                    if tag_str:
                        content_list.append((tag_str, 'script_choice_tag'))
                    if target_dest:
                        content_list.append((target_dest, 'script_choice_tag'))
                    content_list.append(("\n", None))
                    if not is_branch_scene:
                        content_list.append(("\n", None))

            # 분기 씬 박스 마감 (시안 B: 목적지 씬 명시 1줄 마감)
            if is_branch_scene:
                has_own_choice = bool(scene.get('choice') and isinstance(scene.get('choice'), list) and len(scene.get('choice')) > 0)
                if has_own_choice:
                    content_list.append(("└─" + "─" * 35 + "\n\n", 'script_divider'))
                else:
                    dest_scene = branch_destinations.get(key)
                    if dest_scene:
                        label = branch_leads_to_fmt.format(scene=dest_scene)
                    else:
                        label = branch_end_label

                    line_prefix = "└───▶ "
                    pad = max(4, 38 - len(line_prefix + label))
                    content_list.append((line_prefix, 'script_divider'))
                    content_list.append((label, 'script_choice_tag'))
                    content_list.append((" " + "─" * pad + "\n\n", 'script_divider'))

        if not has_dialogue and not (title or outline):
            content_list.append((f"({no_dialogue_msg})\n", 'script_narration'))

        return content_list

    @staticmethod
    def format_story_data(data: dict[str, Any], view_mode: str, lang_dict: dict[str, str] | None = None) -> list[tuple[str, str | None]]:
        """스토리 데이터를 UI에 표시할 수 있는 포맷된 텍스트 및 태그 리스트로 변환합니다.

        Args:
            data: 포맷팅할 스토리 데이터 딕셔너리.
            view_mode: 뷰 모드 ('script', 'simple', 'detailed').
            lang_dict: 다국어 딕셔너리 (None일 경우 기본 언어 적용).

        Returns:
            (포맷팅된 문자열, 태그) 튜플의 리스트.
        """
        if view_mode == 'script':
            return StoryFormatter._format_script_mode(data, lang_dict)

        dispatch = StoryFormatter._get_dispatch_table()
        content_list: list[tuple[str, str | None]] = []
        scene_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf')) 
        
        for key in scene_keys:
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            if view_mode == 'simple':
                keys_to_display = [k for k in ['title', 'outline', 'tag', 'vo', 'print', 'choice'] if k in scene]
            else:
                existing_keys = [k for k in StoryFormatter._FIELD_ORDER if k in scene]
                other_keys = sorted([k for k in scene.keys() if k not in StoryFormatter._FIELD_ORDER])
                keys_to_display = existing_keys + other_keys

            for field in keys_to_display:
                value = scene[field]
                content_list.append(("    " + f"{field}\n", 'key'))
                formatter = dispatch.get(field, StoryFormatter._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append((SEPARATOR_MEDIUM + "\n\n", None))
        return content_list

    @staticmethod
    def _format_print(value: dict[str, Any], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        name, text = str(value.get('name', '???')), value.get('text', '')
        formatted_text = text.replace('\n', '\n' + indent)
        content_list.extend([(indent + f"- name: {name}\n", 'print_sub_key'), (indent + f"- text: “{formatted_text}”\n", 'print_sub_key')])

    @staticmethod
    def _format_choice(value: list[dict[str, Any]], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        for i, item in enumerate(value, 1):
            choice_text = item.get('text', '') if isinstance(item, dict) else str(item)
            tag_str = f" (→ S# {item['tag']})" if isinstance(item, dict) and 'tag' in item else ""
            content_list.append((indent + f"{i}. {choice_text}", 'choice'))
            if tag_str:
                content_list.append((f"{tag_str}\n", 'choice_tag'))
            else:
                content_list.append(("\n", None))

    @staticmethod
    def _format_default(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        content_list.append(("        " + f"{str(value)}\n", 'value'))

    @staticmethod
    def _format_generic_id_list(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list):
            StoryFormatter._format_default(value, content_list)
            return
        for item in value:
            if isinstance(item, list) and item:
                details = ", ".join(map(str, item[1:]))
                content_list.extend([(indent + f"- {str(item[0])}", 'value'), (f" ({details})\n" if details else "\n", 'value')])
            else:
                content_list.append((indent + f"- {str(item)}\n", 'value'))

    @staticmethod
    def _format_simple_id_list(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {str(item)}\n", 'value'))
