"""다국어(i18n) 번역 데이터 로더 및 지연 로드(Lazy Load) 캐시 모듈.

languages.json 파일의 스레드 안전 지연 로드(최초 접근 시 1회 디스크 I/O) 및
각 서브도구(AV Converter, Renamer, Resource Remover, Story Viewer, Unity Converter, Main Menu)에
필요한 언어별 딕셔너리(AV_CONVERTER_LANGUAGES 등) 모듈 속성 제공.
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_json_path = Path(__file__).parent / 'languages.json'

_load_error: str | None = None
_loaded_ok: bool = False
_logger_lang_data_cache: dict | None = None
_full_data: dict = {}
_ensure_done: bool = False
_load_lock = threading.Lock()

_LANG_KEYS = (
    'AV_CONVERTER_LANGUAGES',
    'RENAMER_LANGUAGES',
    'RESOURCE_REMOVER_LANGUAGES',
    'STORY_VIEWER_LANGUAGES',
    'UNITY_CONVERTER_LANGUAGES',
    'MAIN_MENU_LANGUAGES',
)


def _ensure_loaded() -> None:
    """languages.json 파일 메모리 로드.

    임포트 시점 디스크 I/O 방지. 파일 미존재, JSON 문법 오류,
    인코딩 문제 발생 시 빈 딕셔너리 폴백 및 에러 상태 기록.
    """
    global _load_error, _loaded_ok, _full_data, _ensure_done
    with _load_lock:
        if _ensure_done:
            return
        _ensure_done = True

        try:
            with open(_json_path, encoding='utf-8') as _f:
                _loaded = json.load(_f)
            if not isinstance(_loaded, dict):
                raise TypeError("languages.json root must be a JSON object")
            _full_data = _loaded
            _loaded_ok = True
        except FileNotFoundError:
            _load_error = f"languages.json not found at {_json_path}"
            logger.error("languages.json not found at %s. Using empty fallback.", _json_path)
            _full_data = {}
        except json.JSONDecodeError as _e:
            _load_error = f"languages.json is malformed: {_e}"
            logger.error("languages.json is malformed: %s. Using empty fallback.", _e)
            _full_data = {}
        except (OSError, UnicodeDecodeError) as _e:
            _load_error = f"languages.json could not be read: {_e}"
            logger.error("languages.json could not be read: %s. Using empty fallback.", _e)
            _full_data = {}
        except (TypeError, ValueError) as _e:
            _load_error = str(_e)
            logger.error("%s. Using empty fallback.", _e)
            _full_data = {}

        if isinstance(_full_data, dict):
            globals()['AV_CONVERTER_LANGUAGES'] = _full_data.get('av_converter', {}) if isinstance(_full_data.get('av_converter', {}), dict) else {}
            globals()['RENAMER_LANGUAGES'] = _full_data.get('renamer', {}) if isinstance(_full_data.get('renamer', {}), dict) else {}
            globals()['RESOURCE_REMOVER_LANGUAGES'] = _full_data.get('resource_remover', {}) if isinstance(_full_data.get('resource_remover', {}), dict) else {}
            globals()['STORY_VIEWER_LANGUAGES'] = _full_data.get('story_viewer', {}) if isinstance(_full_data.get('story_viewer', {}), dict) else {}
            globals()['UNITY_CONVERTER_LANGUAGES'] = _full_data.get('unity_converter', {}) if isinstance(_full_data.get('unity_converter', {}), dict) else {}
            globals()['MAIN_MENU_LANGUAGES'] = _full_data.get('main_menu', {}) if isinstance(_full_data.get('main_menu', {}), dict) else {}
        else:
            for k in _LANG_KEYS:
                globals()[k] = {}


def __getattr__(name: str) -> Any:
    """속성 접근 시 서브 도구별 언어 딕셔너리 반환 (지연 로드).

    Args:
        name (str): 요청된 언어 딕셔너리 상수명 (예: 'RENAMER_LANGUAGES').

    Returns:
        Any: 해당 도구의 다국어 딕셔너리 (언어 코드별 서브 딕셔너리 매핑).

    Raises:
        AttributeError: 지원하지 않는 속성 이름인 경우.
    """
    if name in _LANG_KEYS:
        _ensure_loaded()
        return globals().get(name, {})
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_logger_lang_data_map() -> dict:
    """에러 로거용 언어 딕셔너리 반환.

    캐시된 데이터를 재사용하여 중복 I/O 방지.

    Returns:
        dict: 전체 다국어 데이터 매핑 딕셔너리.
    """
    _ensure_loaded()
    global _logger_lang_data_cache
    with _load_lock:
        if _logger_lang_data_cache is None:
            _logger_lang_data_cache = copy.deepcopy(_full_data)
        return copy.deepcopy(_logger_lang_data_cache)


def get_language_load_error() -> str | None:
    """languages.json 파일 로드 중 발생한 오류 메시지 반환.

    Returns:
        str | None: 정상 로드 시 None, 실패 시 사용자 친화적 에러 사유 문자열.
    """
    _ensure_loaded()
    if _load_error is not None:
        return _load_error
    if not _loaded_ok:
        return "languages.json is empty or contains no valid language data."
    return None

