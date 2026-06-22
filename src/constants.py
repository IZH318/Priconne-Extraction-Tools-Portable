from __future__ import annotations
import os
from typing import Final

# === External URLs (환경 변수로 오버라이드 가능) ===
DB_DOWNLOAD_BASE_URL: Final[str] = os.environ.get(
    'PRICONNE_DB_URL',
    "https://raw.githubusercontent.com/Expugn/priconne-database/master/"
)

# === Application Metadata ===
APP_VERSION: Final[str] = "3.0.0"
APP_LAST_UPDATE: Final[str] = "2026-03-17"
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
HASH_CHUNK_SIZE: Final[int] = 4096
SHA1_LENGTH: Final[int] = 40

# === Renamer Tool ===
RENAMER_TARGET_FOLDERS: Final[tuple[str, ...]] = ('a', 'b', 'm', 'manifest', 's', 'v')

# === AV Converter Tool ===
AV_TEMP_EXTENSIONS: Final[tuple[str, ...]] = ('.adx', '.bin', '.m2v', '.wav')
FFMPEG_URL: Final[str] = os.environ.get(
    'PRICONNE_FFMPEG_URL',
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
)
FFMPEG_ZIP_FILENAME: Final[str] = "ffmpeg_temp.zip"
FFMPEG_EXE_NAME: Final[str] = "ffmpeg.exe"
SENTINEL_VIDEO_DONE: Final[str] = "__VIDEO_DONE__"
SENTINEL_AUDIO_DONE: Final[str] = "__AUDIO_DONE__"

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
