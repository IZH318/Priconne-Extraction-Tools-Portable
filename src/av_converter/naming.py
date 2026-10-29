"""AV Converter 파일명/확장자 처리 헬퍼 모듈.

오디오 스트림 이름의 Windows 금지 문자 전각 치환과 UsmToolkit config 기반 출력 확장자
결정 등, 변환 엔진과 미리보기 핸들러가 공유하는 순수 헬퍼를 제공한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

FULLWIDTH_CHAR_MAP: Final[dict[str, str]] = {
    '\\': '＼',  # U+FF3C
    '/':  '／',  # U+FF0F
    ':':  '：',  # U+FF1A
    '*':  '＊',  # U+FF0A
    '?':  '？',  # U+FF1F
    '"':  '＂',  # U+FF02
    '<':  '＜',  # U+FF1C
    '>':  '＞',  # U+FF1E
    '|':  '｜',  # U+FF5C
}


def sanitize_stream_filename(name: str) -> str:
    """Windows 파일시스템 금지 문자를 전각 유니코드 문자로 치환 및 유효한 파일명으로 정제.

    Args:
        name (str): 원본 오디오 스트림 또는 큐 시트 이름.

    Returns:
        str: Windows 예약 특수문자 및 제어문자가 제거/치환된 안전한 파일명.
    """
    table = str.maketrans(FULLWIDTH_CHAR_MAP)
    sanitized = name.translate(table)
    sanitized = re.sub(r'[\x00-\x1f]', '', sanitized)
    return sanitized.strip('. ')


def expected_output_extension(usmtoolkit_dir: Path) -> str:
    """usmtoolkit/config.json 의 OutputFormat 을 읽어 실제 출력 파일 확장자를 결정.

    UsmToolkit 은 동일 폴더의 config.json 값을 사용해 인코딩/먹싱을 수행하므로,
    이 값과 기대 확장자가 어긋나면 성공한 변환을 실패로 오판하게 된다.

    Args:
        usmtoolkit_dir (Path): UsmToolkit.exe 가 위치한 폴더 경로.

    Returns:
        str: 점(.) 없는 소문자 확장자. 파일 미존재/파싱 실패 시 기본값 'mp4'.
    """
    try:
        config = json.loads((usmtoolkit_dir / "config.json").read_text(encoding="utf-8"))
        fmt = str(config.get("OutputFormat", "mp4")).strip().lstrip(".").lower()
    except (OSError, ValueError, AttributeError):
        return "mp4"
    return fmt if fmt.isalnum() else "mp4"
