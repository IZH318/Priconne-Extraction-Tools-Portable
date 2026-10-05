from __future__ import annotations
"""
다국어 데이터 로더 모듈.
languages.json을 안전하게 로드하고, 모듈별 언어 딕셔너리를 제공합니다.

TypedDict 타입을 적용하여 IDE 자동완성 및 정적 타입 검사를 지원합니다.
lang_types.py의 TypedDict 클래스는 gen_lang_types.py로 자동 생성됩니다.
"""
import json
import logging
from pathlib import Path
import copy

from src.lang_types import (
    AVConverterLangDict,
    RenamerLangDict,
    ResourceRemoverLangDict,
    StoryViewerLangDict,
    UnityConverterLangDict,
    MainMenuLangDict,
)

_json_path = Path(__file__).parent / 'languages.json'

_load_error: str | None = None

try:
    with open(_json_path, 'r', encoding='utf-8') as _f:
        _full_data = json.load(_f)
except FileNotFoundError:
    _load_error = f"languages.json not found at {_json_path}"
    logging.error("languages.json not found at %s. Using empty fallback.", _json_path)
    _full_data = {}
except json.JSONDecodeError as _e:
    _load_error = f"languages.json is malformed: {_e}"
    logging.error("languages.json is malformed: %s. Using empty fallback.", _e)
    _full_data = {}

AV_CONVERTER_LANGUAGES: dict[str, AVConverterLangDict] = _full_data.get('av_converter', {})
RENAMER_LANGUAGES: dict[str, RenamerLangDict] = _full_data.get('renamer', {})
RESOURCE_REMOVER_LANGUAGES: dict[str, ResourceRemoverLangDict] = _full_data.get('resource_remover', {})
STORY_VIEWER_LANGUAGES: dict[str, StoryViewerLangDict] = _full_data.get('story_viewer', {})
UNITY_CONVERTER_LANGUAGES: dict[str, UnityConverterLangDict] = _full_data.get('unity_converter', {})
MAIN_MENU_LANGUAGES: dict[str, MainMenuLangDict] = _full_data.get('main_menu', {})


def get_logger_lang_data_map() -> dict:
    """logger.py의 setup_global_logging에 전달할 최상위 언어 딕셔너리를 반환합니다.

    container.py에서 별도로 languages.json을 다시 로드하지 않고,
    이 모듈에서 이미 로드한 _full_data를 재사용합니다.
    """
    return copy.deepcopy(_full_data)


def get_language_load_error() -> str | None:
    """languages.json 로드 중 발생한 오류 메시지를 반환합니다. 정상 로드 시 None입니다."""
    if _load_error is not None:
        return _load_error
    if not _full_data:
        return "languages.json is empty or contains no valid language data."
    return None


