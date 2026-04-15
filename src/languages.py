from __future__ import annotations
"""
다국어 데이터 로더 모듈.
languages.json을 안전하게 로드하고, 모듈별 언어 딕셔너리를 제공합니다.
"""
import json
import logging
import os

_json_path = os.path.join(os.path.dirname(__file__), 'languages.json')

try:
    with open(_json_path, 'r', encoding='utf-8') as _f:
        _full_data = json.load(_f)
except FileNotFoundError:
    logging.error("languages.json not found at %s. Using empty fallback.", _json_path)
    _full_data = {}
except json.JSONDecodeError as _e:
    logging.error("languages.json is malformed: %s. Using empty fallback.", _e)
    _full_data = {}

AV_CONVERTER_LANGUAGES: dict = _full_data.get('av_converter', {})
RENAMER_LANGUAGES: dict = _full_data.get('renamer', {})
RESOURCE_REMOVER_LANGUAGES: dict = _full_data.get('resource_remover', {})
STORY_VIEWER_LANGUAGES: dict = _full_data.get('story_viewer', {})
UNITY_CONVERTER_LANGUAGES: dict = _full_data.get('unity_converter', {})
MAIN_MENU_LANGUAGES: dict = _full_data.get('main_menu', {})
