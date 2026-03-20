from __future__ import annotations
# src/story_viewer/logic.py
import json
import re
import os
import sqlite3
import concurrent.futures
from datetime import datetime
from collections import OrderedDict
from typing import Any, Iterable

class LRUCache:
    """크기 제한이 있는 LRU 캐시."""
    def __init__(self, max_size: int = 1024) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size: int = max_size
    
    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]
        
    def put(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
            
    def clear(self) -> None:
        self._cache.clear()
        
    def __len__(self) -> int:
        return len(self._cache)
        
    def __contains__(self, key: str) -> bool:
        return key in self._cache
        
    def items(self) -> Iterable[tuple[str, Any]]:
        return self._cache.items()
        
    def values(self) -> Iterable[Any]:
        return self._cache.values()
        
    def keys(self) -> Iterable[str]:
        return self._cache.keys()


class StoryDataLoader:
    @staticmethod
    def is_valid_storydata(file_path: str) -> tuple[bool, dict[str, Any] | None, str | None]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data:
                return False, None, "File content is empty or not in dictionary format"
            if '0' in data and isinstance(data['0'], dict) and ('title' in data['0'] or 'outline' in data['0']):
                return True, data, None
            else:
                return False, None, "Does not seem to be a storydata file (missing '0' key or title/outline)"
        except json.JSONDecodeError as e:
            return False, None, f"JSON format error: {e}"
        except Exception as e:
            return False, None, f"File read/other error: {e}"

    @staticmethod
    def extract_asset_name(value: Any) -> str | None:
        if isinstance(value, str): return value
        if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
        return None

class SearchEngine:
    @staticmethod
    def check_scene(scene: dict[str, Any], criteria: dict[str, str], char_type_search: str, char_type_speaker: str) -> bool:
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
        lower_criteria = {k: v.lower() for k, v in criteria.items()}
        scene_0 = data.get('0', {})
        
        if 'title' in lower_criteria and lower_criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in lower_criteria and lower_criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        has_scene_level_criteria = any(k in criteria for k in ['char_name', 'content', 'bgm', 'background'])
        if not has_scene_level_criteria:
            return True

        for scene in data.values():
            if SearchEngine.check_scene(scene, lower_criteria, char_type_search, char_type_speaker):
                return True
        return False

    @staticmethod
    def check_file_for_search(filename: str, criteria: dict[str, str], story_data_cache: LRUCache, char_type_search: str, char_type_speaker: str, all_files: dict[str, str]) -> bool:
        if 'filename' in criteria and criteria['filename'].lower() not in filename.lower():
            return False
        
        data = story_data_cache.get(filename)
        if not data:
            filepath = all_files.get(filename)
            if not filepath:
                return False
            is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
            if not is_valid:
                return False
            # Load into cache for later reuse (e.g. clicking the search result)
            story_data_cache.put(filename, data)

        content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
        if not content_criteria:
            return True
            
        return SearchEngine.check_file_content(data, content_criteria, char_type_search, char_type_speaker)

class StoryFormatter:
    def __init__(self) -> None:
        self.field_order = [
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

    def format_story_data(self, data: dict[str, Any], view_mode: str) -> list[tuple[str, str | None]]:
        content_list = []
        scene_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf')) 
        
        for key in scene_keys:
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            if view_mode == 'simple':
                keys_to_display = [k for k in ['title', 'outline', 'vo', 'print'] if k in scene]
            else:
                existing_keys = [k for k in self.field_order if k in scene]
                other_keys = sorted([k for k in scene.keys() if k not in self.field_order])
                keys_to_display = existing_keys + other_keys

            for field in keys_to_display:
                value = scene[field]
                content_list.append(("    " + f"{field}\n", 'key'))
                formatter = getattr(self, f'_format_{field}', self._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append(("-"*60 + "\n\n", None))
        return content_list

    def _format_print(self, value: dict[str, Any], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        name, text = str(value.get('name', '???')), value.get('text', '')
        formatted_text = text.replace('\n', '\n' + indent)
        content_list.extend([(indent + f"- name: {name}\n", 'print_sub_key'), (indent + f"- text: “{formatted_text}”\n", 'print_sub_key')])
    def _format_chara_full(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_generic_id_list(v, c)
    def _format_fadein(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_generic_id_list(v, c)
    def _format_fadeout(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_generic_id_list(v, c)
    def _format_face(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_generic_id_list(v, c)
    def _format_nod(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_simple_id_list(v, c)
    def _format_shake(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_simple_id_list(v, c)
    def _format_focus(self, v: Any, c: list[tuple[str, str | None]]) -> None: self._format_simple_id_list(v, c)
    def _format_choice(self, value: list[dict[str, Any]], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        for i, item in enumerate(value, 1):
            content_list.extend([(indent + f"{i}. {item['text']}", 'choice'), (f" (→ S# {item['tag']})\n", 'choice_tag')])
    def _format_default(self, value: Any, content_list: list[tuple[str, str | None]]) -> None:
        content_list.append(("        " + f"{str(value)}\n", 'value'))
    def _format_generic_id_list(self, value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list):
            self._format_default(value, content_list)
            return
        for item in value:
            if isinstance(item, list) and item:
                details = ", ".join(map(str, item[1:]))
                content_list.extend([(indent + f"- {str(item[0])}", 'value'), (f" ({details})\n" if details else "\n", 'value')])
            else:
                content_list.append((indent + f"- {str(item)}\n", 'value'))
    def _format_simple_id_list(self, value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {str(item)}\n", 'value'))
