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
        choice_title = lang_dict.get('script_choice_title', '선택지') if lang_dict else '선택지'
        branch_prefix = lang_dict.get('script_branch', '분기') if lang_dict else '분기'
        outline_title = lang_dict.get('script_outline_title', '줄거리') if lang_dict else '줄거리'
        no_dialogue_msg = lang_dict.get('script_no_dialogue', '대사 데이터가 없는 스토리입니다') if lang_dict else '대사 데이터가 없는 스토리입니다'

        # 선택지 태그 매핑 (선택지 tag -> (인덱스, 텍스트))
        tag_to_choice: dict[str, tuple[int, str]] = {}
        for s in data.values():
            if 'choice' in s and isinstance(s['choice'], list):
                for idx, item in enumerate(s['choice'], 1):
                    if isinstance(item, dict) and 'tag' in item:
                        tag_to_choice[str(item['tag'])] = (idx, str(item.get('text', '')).strip())

        # 1. 상단 타이틀 및 줄거리 (Scene 0)
        scene_0 = data.get('0', {})
        title = str(scene_0.get('title', '') or '').strip()
        outline = str(scene_0.get('outline', '') or '').strip()

        if title:
            content_list.append((f"■ {title}\n", 'script_title'))

        if outline:
            content_list.append(("─" * 37 + "\n", 'script_divider'))
            content_list.append((f"【 {outline_title} 】\n", 'script_outline_header'))
            content_list.append((f"{outline}\n", 'script_narration'))

        if title or outline:
            content_list.append(("─" * 37 + "\n\n", 'script_divider'))

        has_dialogue = False
        last_place = None

        for key in scene_keys:
            scene = data[key]

            # 장소 / 상황 변경 안내 (에피소드 제목과 동일한 중복 장소 표기는 건너뜀)
            place = scene.get('place')
            situation = scene.get('situation')
            loc = place if place else situation
            if loc:
                loc_str = str(loc).strip()
                if loc_str and loc_str != title and loc_str != last_place:
                    content_list.append((f"[{place_prefix}: {loc_str}]\n\n", 'script_place'))
                    last_place = loc_str
                    has_dialogue = True

            # 분기 씬 안내 표기 (씬에 tag 속성이 있고 대사/선택지 등 유의미한 내용이 존재하는 경우)
            branch_tag = str(scene.get('tag', '') or '').strip()
            has_scene_content = ('print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene)
            if branch_tag and key != '0' and has_scene_content:
                c_info = tag_to_choice.get(branch_tag)
                if c_info and c_info[1]:
                    header = f"─ [ S# {branch_tag} ] {c_info[1]} ─"
                else:
                    header = f"─ [ S# {branch_tag} ] ─"
                content_list.append((f"{header}\n", 'script_branch'))
                has_dialogue = True

            # 대사 (print)
            if 'print' in scene and isinstance(scene['print'], dict):
                p_data = scene['print']
                speaker = str(p_data.get('name', '')).strip()
                dialogue = str(p_data.get('text', '')).strip()

                if dialogue:
                    has_dialogue = True
                    if speaker:
                        content_list.append((f"[{speaker}]\n", 'script_speaker'))
                        content_list.append((f"{dialogue}\n\n", 'script_dialogue'))
                    else:
                        content_list.append((f"{dialogue}\n\n", 'script_narration'))

            # 선택지 (choice)
            if 'choice' in scene and isinstance(scene['choice'], list):
                has_dialogue = True
                content_list.append((f"▶ [{choice_title}]\n", 'script_choice'))
                for idx, item in enumerate(scene['choice'], 1):
                    if isinstance(item, dict):
                        choice_text = item.get('text', '')
                        tag = item.get('tag')
                    else:
                        choice_text = str(item)
                        tag = None

                    content_list.append((f"   {idx}. {choice_text}", 'script_choice'))
                    if tag is not None and str(tag).strip():
                        content_list.append((f" (→ S# {tag})", 'script_choice_tag'))
                    content_list.append(("\n", None))
                content_list.append(("─" * 37 + "\n\n", 'script_divider'))

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
