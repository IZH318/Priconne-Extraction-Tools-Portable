"""전역 상수 및 외부 종속 도구 구성 모듈.

애플리케이션 메타데이터, GUI 폴링 주기, 파일 해시 버퍼 크기,
서브도구별 지원 확장자 및 외부 도구(FFmpeg, UsmToolkit, vgmstream) 다운로드/실행
관련 상수 정의.

참고:
    일부 네트워크 URL 및 타임아웃 상수는 모듈 임포트 시점 디스크 I/O 방지 및
    런타임 환경변수(PRICONNE_*) 오버라이드 지원을 위해 PEP 562 __getattr__ 기반
    지연 평가(Lazy Evaluation) 방식으로 처리. 해석 결과는 최초 접근 시 1회만 반영 후 캐시.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

logger = logging.getLogger(__name__)

# AV Converter 탭 구분 타입
TabType = Literal['video', 'audio']

# 애플리케이션 메타데이터
APP_VERSION: Final[str] = "3.0.0"
APP_LAST_UPDATE: Final[str] = "2026-10-10"
APP_DEVELOPER: Final[str] = "(Github) IZH318"
APP_WEBSITE: Final[str] = "https://github.com/IZH318"
APP_COPYRIGHT_YEAR: Final[str] = "2026"

# GUI 갱신 및 큐 폴링 간격 (밀리초)
GUI_POLLING_INTERVAL_MS: Final[int] = 100  # Controller 큐 이벤트 폴링 기본 주기 (100ms)
IDLE_POLLING_INTERVAL_MS: Final[int] = 500  # 유휴 상태 폴링 대기 간격 (500ms)

# 리소스 정리(스레드 조인) 타임아웃 (초)
RENAMER_CLEANUP_JOIN_TIMEOUT: Final[float] = 1.0
AV_CLEANUP_JOIN_TIMEOUT: Final[float] = 3.0
STORY_CLEANUP_JOIN_TIMEOUT: Final[float] = 5.0
RESOURCE_REMOVER_CLEANUP_JOIN_TIMEOUT: Final[float] = 3.0

# DB 네트워크 타임아웃 (초)
DB_VERSION_API_TIMEOUT: Final[float] = 5.0
DB_DOWNLOAD_TIMEOUT: Final[float] = 30.0

# 외부 도구/런타임 버전 프로브 타임아웃 (초)
DOTNET_RUNTIME_PROBE_TIMEOUT: Final[int] = 2
USMTOOLKIT_VERSION_PROBE_TIMEOUT: Final[int] = 3
FFMPEG_VERSION_PROBE_TIMEOUT: Final[int] = 5

# 로그 출력 구분선
SEPARATOR_LONG: Final[str] = "-" * 100
SEPARATOR_MEDIUM: Final[str] = "-" * 60

# 파일 처리 및 해시 계산 관련 상수
HASH_CHUNK_SIZE: Final[int] = 65536  # 스트리밍 해시 계산용 64KB I/O 버퍼 크기
SHA1_LENGTH: Final[int] = 40        # SHA-1 16진수 문자열 길이 (40자)
DOWNLOAD_CHUNK_SIZE: Final[int] = 65536  # 스트리밍 파일 다운로드용 64KB I/O 버퍼 크기

# Manifest File Renamer 대상 폴더
# 프린세스 커넥트 에셋 캐시의 1글자 폴더 및 manifest 폴더 이름
RENAMER_TARGET_FOLDERS: Final[tuple[str, ...]] = ('a', 'b', 'm', 'manifest', 's', 'v')

# Audio / Video Converter 도구 관련 상수
AV_TEMP_EXTENSIONS: Final[tuple[str, ...]] = ('.adx', '.bin', '.m2v', '.wav')
AV_VIDEO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.usm',)
AV_AUDIO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.awb',)
FFMPEG_TARGET_VERSION: Final[str] = "7.1.1"
# 권장 버전과 동일 메이저(예: 7.x.x)는 그대로 사용
FFMPEG_ACCEPTED_MAJOR: Final[int] = 7
# 사용자가 직접 배치해 사용할 수 있는 최소 지원 버전 (예: 4.4)
FFMPEG_MIN_SUPPORTED: Final[tuple[int, int, int]] = (4, 4, 0)


def _load_deps_config() -> dict[str, str]:
    """외부 도구 종속성 설정 파일(deps.json) 로드.

    src/av_converter/deps.json 또는 src/deps.json 경로 순차 확인.
    파일 미존재 또는 JSON 형식 오류 시 빈 딕셔너리 반환.

    Returns:
        dict[str, str]: 도구 이름을 키로, 다운로드 URL 또는 경로를 값으로 가지는 딕셔너리.
    """
    for cand in [
        Path(__file__).resolve().parent / "av_converter" / "deps.json",
        Path(__file__).resolve().parent / "deps.json",
    ]:
        if cand.exists():
            try:
                with open(cand, encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.warning("Failed to load deps config from %s: %s", cand, exc)
    return {}

# 지연 로드 캐시: import 시점 파일 I/O 방지용 스레드 락과 함께 사용
_DEPS_CONFIG_CACHE: dict[str, str] | None = None
_DEPS_CONFIG_LOCK = threading.Lock()

# 지연 상수 해석 결과 메모이제이션 캐시: 반복 접근 시 O(1) 조회 보장.
# 환경변수/deps.json 조회는 최초 1회 수행하며, 캐시 기록만 _DEPS_CONFIG_LOCK으로 보호.
_RESOLVED_CACHE: dict[str, Any] = {}


def _get_deps_config() -> dict[str, str]:
    """스레드 안전 외부 도구 설정 캐시 반환 또는 최초 로드."""
    global _DEPS_CONFIG_CACHE
    with _DEPS_CONFIG_LOCK:
        if _DEPS_CONFIG_CACHE is None:
            _DEPS_CONFIG_CACHE = _load_deps_config()
        return _DEPS_CONFIG_CACHE


# 환경 변수 또는 deps.json을 통해 동적으로 평가할 지연 상수 목록
_LAZY_CONSTS = {
    'USMTOOLKIT_URL',
    'FFMPEG_URL',
    'VGMSTREAM_URL',
    'DOWNLOAD_SOCKET_TIMEOUT',
    'SUBPROCESS_VIDEO_CONVERT_TIMEOUT',
    'SUBPROCESS_AUDIO_CONVERT_TIMEOUT',
    'SUBPROCESS_PREVIEW_TIMEOUT',
}

if TYPE_CHECKING:
    # PEP 562 __getattr__로 지연 평가되는 상수들의 실제 타입 선언.
    # 런타임에는 존재하지 않지만 정적 분석기(mypy) 및 IDE가 실제 속성으로 인식하도록 함.
    USMTOOLKIT_URL: str
    FFMPEG_URL: str
    VGMSTREAM_URL: str
    DOWNLOAD_SOCKET_TIMEOUT: int
    SUBPROCESS_VIDEO_CONVERT_TIMEOUT: int
    SUBPROCESS_AUDIO_CONVERT_TIMEOUT: int
    SUBPROCESS_PREVIEW_TIMEOUT: int


def _resolve_lazy_const(name: str) -> Any:
    """단일 지연 상수 이름에 대한 실제 값 해석 (메모이제이션 이전 단계).

    환경변수(PRICONNE_*) 오버라이드 > deps.json 설정 > 기본값 순서의
    우선순위와 기본값을 기존 동작과 동일하게 유지.

    Args:
        name: 해석할 지연 상수 이름 (_LAZY_CONSTS 구성원).

    Returns:
        Any: 해석된 상수 값 (URL 문자열 또는 타임아웃 정수초).

    Raises:
        AttributeError: _LAZY_CONSTS에 포함되나 해석 규칙이 정의되지 않은 경우.
    """
    cfg = _get_deps_config()
    if name == 'USMTOOLKIT_URL':
        _env = (os.environ.get('PRICONNE_USMTOOLKIT_URL') or '').strip()
        return _env or cfg.get("UsmToolkit", USMTOOLKIT_DEFAULT_URL)
    if name == 'FFMPEG_URL':
        _env = (os.environ.get('PRICONNE_FFMPEG_URL') or '').strip()
        return _env or cfg.get("FFmpeg", FFMPEG_DEFAULT_URL)
    if name == 'VGMSTREAM_URL':
        return cfg.get("Vgmstream", "https://github.com/vgmstream/vgmstream/releases/download/r2117/vgmstream-win.zip")
    if name == 'DOWNLOAD_SOCKET_TIMEOUT':
        return _env_int('PRICONNE_DOWNLOAD_TIMEOUT', 120)
    if name == 'SUBPROCESS_VIDEO_CONVERT_TIMEOUT':
        return _env_int('PRICONNE_VIDEO_TIMEOUT', 300)
    if name == 'SUBPROCESS_AUDIO_CONVERT_TIMEOUT':
        return _env_int('PRICONNE_AUDIO_TIMEOUT', 60)
    if name == 'SUBPROCESS_PREVIEW_TIMEOUT':
        # 미리보기도 본 변환과 동일한 설정으로 재인코딩하므로 30초는 정상 클립까지 실패시킨다
        return _env_int('PRICONNE_PREVIEW_TIMEOUT', 60)
    # 예외 분기: _LAZY_CONSTS에 포함되나 해석 규칙이 누락된 경우
    raise AttributeError(f"module {__name__!r} has no resolvable lazy constant {name!r}")


def __getattr__(name: str) -> Any:
    """PEP 562 모듈 레벨 속성 조회 훅.

    지연 평가 상수(_LAZY_CONSTS) 최초 접근 시 환경변수 오버라이드 및 deps.json 설정을
    우선 조회하여 기본값을 결정하고 _RESOLVED_CACHE에 메모이제이션한다.
    이후 동일 상수 접근은 캐시 조회(O(1))로 반환되어 환경변수/파일 재조회 비용을 제거.

    Note:
        해석(_resolve_lazy_const)은 _DEPS_CONFIG_LOCK 밖에서 수행하여 내부적으로 동일 락을
        획득하는 _get_deps_config 호출과의 재진입 교착(Deadlock)을 방지하고,
        캐시 기록은 setdefault를 사용해 경쟁 상태에서도 최초 해석값 하나만 유지.

    Args:
        name: 요청된 상수 이름.

    Returns:
        Any: 동적으로 결정된 상수 값 (URL 문자열 또는 타임아웃 정수초).

    Raises:
        AttributeError: 지정된 이름이 모듈 상수로 정의되어 있지 않은 경우.
    """
    if name in _LAZY_CONSTS:
        try:
            return _RESOLVED_CACHE[name]
        except KeyError:
            pass
        value = _resolve_lazy_const(name)
        with _DEPS_CONFIG_LOCK:
            return _RESOLVED_CACHE.setdefault(name, value)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def refresh_lazy_constants() -> None:
    """지연 평가 상수 캐시를 초기화하여 다음 접근 시 환경변수/deps.json 재해석 유도.

    지연 상수는 최초 접근 시 1회 해석(환경변수 PRICONNE_* > deps.json > 기본값) 후
    _RESOLVED_CACHE에 캐시되므로, 프로세스 실행 중 환경변수 변경이나 deps.json 수정은
    자동으로 반영되지 않는다. 본 함수를 호출하면 _RESOLVED_CACHE와 _DEPS_CONFIG_CACHE를
    함께 비우므로, 이후 지연 상수 접근부터 최신 설정값이 적용된다.

    Note:
        캐시 초기화는 _DEPS_CONFIG_LOCK으로 보호되며, 해석 결과 및 deps.json 설정이
        모두 폐기되므로 다음 접근 시 파일 I/O(디스크 재조회)가 다시 발생할 수 있음.
        해석 우선순위 및 기본값 규칙은 변경하지 않음.

    Args:
        없음: 인자를 받지 않는다.

    Returns:
        None: 반환값 없음 (캐시 초기화만 수행).
    """
    global _DEPS_CONFIG_CACHE
    with _DEPS_CONFIG_LOCK:
        _RESOLVED_CACHE.clear()
        _DEPS_CONFIG_CACHE = None


# 외부 도구 기본 다운로드 URL 및 아카이브 파일명
USMTOOLKIT_DEFAULT_URL: Final[str] = "https://github.com/Rikux3/UsmToolkit/releases/download/0.2/publish.zip"
USMTOOLKIT_ZIP_FILENAME: Final[str] = "usmtoolkit_temp.zip"
USMTOOLKIT_EXE_NAME: Final[str] = "UsmToolkit.exe"

FFMPEG_DEFAULT_URL: Final[str] = "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip"
VGMSTREAM_ZIP_FILENAME: Final[str] = "vgmstream_temp.zip"
VGMSTREAM_EXE_NAME: Final[str] = "vgmstream-cli.exe"


def _env_int(name: str, default: int) -> int:
    """환경 변수를 정수로 파싱하고 실패 시 기본값 반환.

    파싱된 값은 1 이상 86400(24시간) 이하로 클램프하여 0/음수 타임아웃으로 인한
    서브프로세스 즉시 만료를 방지.

    Args:
        name: 환경 변수 이름.
        default: 파싱 실패 또는 누락 시 사용할 기본 정수값.

    Returns:
        int: 1~86400 범위로 클램프된 정수값 또는 기본값.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using default %d", name, raw, default)
        return default
    # 허용 범위(1초 ~ 86400초)를 벗어나면 클램프하고 경고 기록
    clamped = max(1, min(value, 86400))
    if clamped != value:
        logger.warning("Clamped %s=%d to %d (allowed range 1..86400)", name, value, clamped)
    return clamped


# FFmpeg 파일명 및 버전 마커 경로
FFMPEG_ZIP_FILENAME: Final[str] = "ffmpeg_temp.zip"
FFMPEG_EXE_NAME: Final[str] = "ffmpeg.exe"
FFMPEG_VERSION_FILENAME: Final[str] = ".ffmpeg_version"
FFMPEG_VERSION_MARKER_PATH: Final[Path] = Path(__file__).resolve().parent / "av_converter" / FFMPEG_VERSION_FILENAME

# 백그라운드 큐 통신용 센티넬(종료 신호) 상수
SENTINEL_VIDEO_DONE: Final[str] = "__VIDEO_DONE__"
SENTINEL_AUDIO_DONE: Final[str] = "__AUDIO_DONE__"

# Unity Converter Tool 관련 상수
UNITY_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.unity3d',)
DEFAULT_UNITY_VERSION: Final[str] = "2021.3.20f1"
UNITY_VERSION_PRESETS: Final[tuple[str, ...]] = ("2021.3.20f1", "6000.0.58.57061")

# Original Resource Remover Tool 리소스 확장자 카테고리
# 불변성 유지를 위해 MappingProxyType 튜플로 정의
EXTENSION_CATEGORIES: Final[tuple[MappingProxyType[str, Any], ...]] = (
    MappingProxyType({"key": "chk_assetbundle", "extensions": (".unity3d",)}),
    MappingProxyType({"key": "chk_audio", "extensions": (".acb", ".awb")}),
    MappingProxyType({"key": "chk_video", "extensions": (".usm",)}),
)

