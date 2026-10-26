"""전역 상수 및 외부 종속 도구 구성 모듈.

애플리케이션 메타데이터, GUI 폴링 주기, 파일 해시 버퍼 크기,
서브도구별 지원 확장자 및 외부 도구(FFmpeg, UsmToolkit, vgmstream) 다운로드/실행
관련 상수 정의.

참고:
    일부 네트워크 URL 및 타임아웃 상수는 모듈 임포트 시점 디스크 I/O 방지 및
    런타임 환경변수(PRICONNE_*) 오버라이드 지원을 위해 PEP 562 __getattr__ 기반
    지연 평가(Lazy Evaluation) 방식으로 처리.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal

logger = logging.getLogger(__name__)

# === AV Converter 탭 구분 타입 ===
TabType = Literal['video', 'audio']

# === 애플리케이션 메타데이터 ===
APP_VERSION: Final[str] = "3.0.0"
APP_LAST_UPDATE: Final[str] = "2026-10-10"
APP_DEVELOPER: Final[str] = "(Github) IZH318"
APP_WEBSITE: Final[str] = "https://github.com/IZH318"
APP_COPYRIGHT_YEAR: Final[str] = "2026"

# === GUI 갱신 및 큐 폴링 간격 (밀리초) ===
GUI_POLLING_INTERVAL_MS: Final[int] = 100  # Controller 큐 이벤트 폴링 기본 주기 (100ms)
GUI_UPDATE_INTERVAL_MS: Final[int] = 10    # 세밀한 프로그레스 및 로그 UI 갱신 주기 (10ms)

# === 로그 출력 구분선 ===
SEPARATOR_LONG: Final[str] = "-" * 100
SEPARATOR_MEDIUM: Final[str] = "-" * 60

# === 파일 처리 및 해시 계산 관련 상수 ===
HASH_CHUNK_SIZE: Final[int] = 65536  # 스트리밍 해시 계산용 64KB I/O 버퍼 크기
SHA1_LENGTH: Final[int] = 40        # SHA-1 16진수 문자열 길이 (40자)

# === Manifest File Renamer 대상 폴더 ===
# 프린세스 커넥트 에셋 캐시의 1글자 폴더 및 manifest 폴더 이름
RENAMER_TARGET_FOLDERS: Final[tuple[str, ...]] = ('a', 'b', 'm', 'manifest', 's', 'v')

# === Audio / Video Converter 도구 관련 상수 ===
AV_TEMP_EXTENSIONS: Final[tuple[str, ...]] = ('.adx', '.bin', '.m2v', '.wav')
AV_VIDEO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.usm',)
AV_AUDIO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.awb',)
FFMPEG_TARGET_VERSION: Final[str] = "7.1.1"

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


def __getattr__(name: str) -> Any:
    """PEP 562 모듈 레벨 속성 조회 훅.

    지연 평가 상수(_LAZY_CONSTS)에 대해 환경변수 오버라이드 및 deps.json 설정 우선 조회 후
    기본값 적용 반환. import 타임 디스크 I/O 방지.

    Args:
        name: 요청된 상수 이름.

    Returns:
        동적으로 결정된 상수 값 (URL 문자열 또는 타임아웃 정수초).

    Raises:
        AttributeError: 지정된 이름이 모듈 상수로 정의되어 있지 않은 경우.
    """
    if name in _LAZY_CONSTS:
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
            return _env_int('PRICONNE_PREVIEW_TIMEOUT', 30)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# === 외부 도구 기본 다운로드 URL 및 아카이브 파일명 ===
USMTOOLKIT_DEFAULT_URL: Final[str] = "https://github.com/Rikux3/UsmToolkit/releases/download/0.2/publish.zip"
USMTOOLKIT_ZIP_FILENAME: Final[str] = "usmtoolkit_temp.zip"
USMTOOLKIT_EXE_NAME: Final[str] = "UsmToolkit.exe"

FFMPEG_DEFAULT_URL: Final[str] = "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip"
VGMSTREAM_ZIP_FILENAME: Final[str] = "vgmstream_temp.zip"
VGMSTREAM_EXE_NAME: Final[str] = "vgmstream-cli.exe"


def _env_int(name: str, default: int) -> int:
    """환경 변수를 정수로 파싱하고 실패 시 기본값 반환.

    Args:
        name: 환경 변수 이름.
        default: 파싱 실패 또는 누락 시 사용할 기본 정수값.

    Returns:
        int: 파싱된 정수값 또는 기본값.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using default %d", name, raw, default)
        return default


# === 외부 바이너리 무결성 검증용 SHA-256 해시 ===
FFMPEG_EXPECTED_SHA256: Final[str] = "04861d3339c5ebe38b56c19a15cf2c0cc97f5de4fa8910e4d47e5e6404e4a2d4"
# 외부 도구(UsmToolkit 및 vgmstream)는 버전 변동이 잦으므로 해시가 비어있으면 검증 건너뜀
USMTOOLKIT_EXPECTED_SHA256: Final[str] = ""
VGMSTREAM_EXPECTED_SHA256: Final[str] = ""

# === FFmpeg 파일명 및 버전 마커 경로 ===
FFMPEG_ZIP_FILENAME: Final[str] = "ffmpeg_temp.zip"
FFMPEG_EXE_NAME: Final[str] = "ffmpeg.exe"
FFMPEG_VERSION_FILENAME: Final[str] = ".ffmpeg_version"
FFMPEG_VERSION_MARKER_PATH: Final[Path] = Path(__file__).resolve().parent / "av_converter" / FFMPEG_VERSION_FILENAME

# === 백그라운드 큐 통신용 센티넬(종료 신호) 상수 ===
SENTINEL_VIDEO_DONE: Final[str] = "__VIDEO_DONE__"
SENTINEL_AUDIO_DONE: Final[str] = "__AUDIO_DONE__"

# === Unity Converter Tool 관련 상수 ===
UNITY_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.unity3d',)
DEFAULT_UNITY_VERSION: Final[str] = "2021.3.20f1"
UNITY_VERSION_PRESETS: Final[tuple[str, ...]] = ("2021.3.20f1", "6000.0.58.57061")

# === Original Resource Remover Tool 리소스 확장자 카테고리 ===
# 불변성 유지를 위해 MappingProxyType 튜플로 정의
EXTENSION_CATEGORIES: Final[tuple[MappingProxyType[str, Any], ...]] = (
    MappingProxyType({"key": "chk_assetbundle", "extensions": (".unity3d",)}),
    MappingProxyType({"key": "chk_audio", "extensions": (".acb", ".awb")}),
    MappingProxyType({"key": "chk_video", "extensions": (".usm",)}),
)

