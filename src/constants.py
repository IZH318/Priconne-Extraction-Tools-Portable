from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Final, Literal

# === AV Converter Tab Type ===
TabType = Literal['video', 'audio']

# === External URLs (환경 변수로 오버라이드 가능) ===
DB_DOWNLOAD_BASE_URL: Final[str] = os.environ.get(
    'PRICONNE_DB_URL',
    "https://raw.githubusercontent.com/Expugn/priconne-database/master/"
)

# === Application Metadata ===
APP_VERSION: Final[str] = "3.0.0"
APP_LAST_UPDATE: Final[str] = "2026-10-10"
APP_DEVELOPER: Final[str] = "(Github) IZH318"
APP_WEBSITE: Final[str] = "https://github.com/IZH318"
APP_COPYRIGHT_YEAR: Final[str] = "2026"

# === GUI Update Intervals (ms) ===
GUI_POLLING_INTERVAL_MS: Final[int] = 100
GUI_UPDATE_INTERVAL_MS: Final[int] = 10

# === Log Separators ===
SEPARATOR_LONG: Final[str] = "-" * 100
SEPARATOR_MEDIUM: Final[str] = "-" * 60
SEPARATOR_SHORT: Final[str] = "-" * 50
SEPARATOR_MINI: Final[str] = "-" * 30


# === File Processing Constants ===
HASH_CHUNK_SIZE: Final[int] = 65536
SHA1_LENGTH: Final[int] = 40

# === Renamer Tool ===
RENAMER_TARGET_FOLDERS: Final[tuple[str, ...]] = ('a', 'b', 'm', 'manifest', 's', 'v')

# === AV Converter Tool ===
AV_TEMP_EXTENSIONS: Final[tuple[str, ...]] = ('.adx', '.bin', '.m2v', '.wav')
AV_VIDEO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.usm',)
AV_AUDIO_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.awb',)
FFMPEG_TARGET_VERSION: Final[str] = "7.1.1"

def _load_deps_config() -> dict[str, str]:
    """src/av_converter/deps.json 또는 src/deps.json에서 도구 종속성 URL을 로드합니다."""
    for cand in [
        Path(__file__).resolve().parent / "av_converter" / "deps.json",
        Path(__file__).resolve().parent / "deps.json",
    ]:
        if cand.exists():
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

_DEPS_CONFIG = _load_deps_config()

USMTOOLKIT_DEFAULT_URL: Final[str] = "https://github.com/Rikux3/UsmToolkit/releases/download/0.2/publish.zip"
USMTOOLKIT_URL: Final[str] = os.environ.get(
    'PRICONNE_USMTOOLKIT_URL',
    _DEPS_CONFIG.get("UsmToolkit", USMTOOLKIT_DEFAULT_URL)
)
USMTOOLKIT_ZIP_FILENAME: Final[str] = "usmtoolkit_temp.zip"
USMTOOLKIT_EXE_NAME: Final[str] = "UsmToolkit.exe"

FFMPEG_DEFAULT_URL: Final[str] = "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-essentials_build.zip"
FFMPEG_URL: Final[str] = os.environ.get(
    'PRICONNE_FFMPEG_URL',
    _DEPS_CONFIG.get("FFmpeg", FFMPEG_DEFAULT_URL)
)
VGMSTREAM_URL: Final[str] = _DEPS_CONFIG.get(
    "Vgmstream",
    "https://github.com/vgmstream/vgmstream/releases/download/r2117/vgmstream-win.zip"
)
VGMSTREAM_ZIP_FILENAME: Final[str] = "vgmstream_temp.zip"
VGMSTREAM_EXE_NAME: Final[str] = "vgmstream-cli.exe"
DOWNLOAD_SOCKET_TIMEOUT: Final[int] = int(os.environ.get('PRICONNE_DOWNLOAD_TIMEOUT', 120))
FFMPEG_EXPECTED_SHA256: Final[str] = os.environ.get(
    'PRICONNE_FFMPEG_SHA256',
    "04861d3339c5ebe38b56c19a15cf2c0cc97f5de4fa8910e4d47e5e6404e4a2d4"
)
FFMPEG_ZIP_FILENAME: Final[str] = "ffmpeg_temp.zip"
FFMPEG_EXE_NAME: Final[str] = "ffmpeg.exe"
FFMPEG_VERSION_FILENAME: Final[str] = ".ffmpeg_version"
FFMPEG_VERSION_MARKER_PATH: Final[Path] = Path(__file__).resolve().parent / "av_converter" / FFMPEG_VERSION_FILENAME
SENTINEL_VIDEO_DONE: Final[str] = "__VIDEO_DONE__"
SENTINEL_AUDIO_DONE: Final[str] = "__AUDIO_DONE__"
SUBPROCESS_VIDEO_CONVERT_TIMEOUT: Final[int] = int(os.environ.get('PRICONNE_VIDEO_TIMEOUT', 300))
SUBPROCESS_AUDIO_CONVERT_TIMEOUT: Final[int] = int(os.environ.get('PRICONNE_AUDIO_TIMEOUT', 60))
SUBPROCESS_PREVIEW_TIMEOUT: Final[int] = int(os.environ.get('PRICONNE_PREVIEW_TIMEOUT', 30))

# === Unity Converter Tool ===
UNITY_SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = ('.unity3d',)
DEFAULT_UNITY_VERSION: Final[str] = "2021.3.20f1"
UNITY_VERSION_PRESETS: Final[tuple[str, ...]] = ("2021.3.20f1", "6000.0.58.57061")

# === Resource Remover Tool ===
EXTENSION_CATEGORIES: Final = (
    {
        "key": "chk_assetbundle",
        "extensions": (".unity3d",),
    },
    {
        "key": "chk_audio",
        "extensions": (".awb", ".acb"),
    },
    {
        "key": "chk_video",
        "extensions": (".usm",),
    },
)
