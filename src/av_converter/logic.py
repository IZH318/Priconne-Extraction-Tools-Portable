"""AV Converter 호환 shim 모듈.

구 모놀리식 모듈을 분리한 뒤, 기존 `from .logic import ...` 경로를 그대로 유지하기 위한
재-export 전용 shim. 실제 구현은 각 하위 모듈에 있다.

- 변환 엔진: `conversion_engine.ConversionLogic`
- 다운로더/파이프라인: `media_tools.{ffmpeg,usmtoolkit,vgmstream,pipeline}`
- 헬퍼: `naming`
"""
from __future__ import annotations

from .conversion_engine import ConversionLogic
from .media_tools.ffmpeg import FFmpegDownloader
from .media_tools.pipeline import ToolPipelineManager
from .media_tools.usmtoolkit import UsmToolkitDownloader
from .media_tools.vgmstream import VgmstreamDownloader
from .naming import expected_output_extension, sanitize_stream_filename

__all__ = [
    "ConversionLogic",
    "FFmpegDownloader",
    "ToolPipelineManager",
    "UsmToolkitDownloader",
    "VgmstreamDownloader",
    "expected_output_extension",
    "sanitize_stream_filename",
]
