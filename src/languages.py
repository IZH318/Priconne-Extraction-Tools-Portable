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

from src.constants import DEFAULT_LANG

logger = logging.getLogger(__name__)

_json_path = Path(__file__).parent / 'languages.json'

_load_error: str | None = None
_loaded_ok: bool = False
_logger_lang_data_cache: dict[str, Any] | None = None
_full_data: dict[str, Any] = {}
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

        try:
            with open(_json_path, encoding='utf-8') as _f:
                _loaded = json.load(_f)
            if not isinstance(_loaded, dict):
                raise TypeError("languages.json root must be a JSON object")
            _full_data = _loaded
            _loaded_ok = True
        except FileNotFoundError:
            _load_error = f"languages.json not found at {_json_path}"
            logger.exception("languages.json not found at %s. Using empty fallback.", _json_path)
            _full_data = {}
        except json.JSONDecodeError as _e:
            _load_error = f"languages.json is malformed: {_e}"
            logger.exception("languages.json is malformed: %s. Using empty fallback.", _e)
            _full_data = {}
        except (OSError, UnicodeDecodeError) as _e:
            _load_error = f"languages.json could not be read: {_e}"
            logger.exception("languages.json could not be read: %s. Using empty fallback.", _e)
            _full_data = {}
        except (TypeError, ValueError) as _e:
            _load_error = str(_e)
            logger.exception("%s. Using empty fallback.", _e)
            _full_data = {}

        if isinstance(_full_data, dict):
            globals()['AV_CONVERTER_LANGUAGES'] = _full_data.get('av_converter', {}) if isinstance(_full_data.get('av_converter', {}), dict) else {}
            globals()['RENAMER_LANGUAGES'] = _full_data.get('renamer', {}) if isinstance(_full_data.get('renamer', {}), dict) else {}
            globals()['RESOURCE_REMOVER_LANGUAGES'] = _full_data.get('resource_remover', {}) if isinstance(_full_data.get('resource_remover', {}), dict) else {}
            globals()['STORY_VIEWER_LANGUAGES'] = _full_data.get('story_viewer', {}) if isinstance(_full_data.get('story_viewer', {}), dict) else {}
            globals()['UNITY_CONVERTER_LANGUAGES'] = _full_data.get('unity_converter', {}) if isinstance(_full_data.get('unity_converter', {}), dict) else {}
            globals()['MAIN_MENU_LANGUAGES'] = _full_data.get('main_menu', {}) if isinstance(_full_data.get('main_menu', {}), dict) else {}

        # 로드 및 전역 주입이 모두 끝난 뒤에 완료로 표시한다.
        # (도중 예외로 중단되면 다음 호출에서 재시도하도록 _ensure_done을 미설정 상태로 둔다)
        _ensure_done = True


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


def get_logger_lang_data_map() -> dict[str, Any]:
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


def pick_language(lang_code: str, table: dict[str, Any]) -> dict[str, str]:
    """언어 코드에 해당하는 번역 딕셔너리 선택 (미지원 코드는 기본 언어로 폴백).

    모든 서브도구 컨트롤러가 동일한 폴백 정책(선택 언어 → 기본 언어(영어))을 사용하도록
    단일 진입점을 제공한다.

    Args:
        lang_code (str): 언어 코드 (예: 'ko', 'en', 'ja').
        table (dict[str, Any]): 언어 코드 → 번역 딕셔너리 매핑 테이블.

    Returns:
        dict[str, str]: 선택된 언어의 번역 딕셔너리. 미지원/누락 시 기본 언어(영어) 폴백.
    """
    selected = table.get(lang_code)
    if isinstance(selected, dict) and selected:
        # 호출자가 반환값을 수정하더라도 전역 언어 테이블이 오염되지 않도록 사본을 반환
        return dict(selected)
    fallback = table.get(DEFAULT_LANG)
    return dict(fallback) if isinstance(fallback, dict) else {}


def format_text(lang_dict: dict[str, Any], key: str, default: str, **kwargs: Any) -> str:
    """번역 템플릿을 안전하게 포맷 (키 누락/플레이스홀더 불일치 시 원문 반환).

    플레이스홀더가 번역본과 맞지 않아 발생하는 KeyError/IndexError 등으로 UI 갱신
    핸들러가 중단되는 것을 방지한다.

    Args:
        lang_dict (dict[str, Any]): 번역 딕셔너리.
        key (str): 번역 키.
        default (str): 키가 없을 때 사용할 기본 문구.
        **kwargs: 포맷 인자.

    Returns:
        str: 포맷된 문자열. 포맷 실패 시 템플릿 원문.
    """
    template = lang_dict.get(key, default) if isinstance(lang_dict, dict) else default
    try:
        return str(template).format(**kwargs)
    except (KeyError, ValueError, IndexError, TypeError):
        return str(template)


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

