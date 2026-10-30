"""Unity 3D 에셋 번들 추출 및 변환 패키지(Unity Converter).

UnityPy 기반으로 Unity3D 번들 파일 내부의 Texture2D, Sprite, AudioClip, TextAsset,
Mesh, MovieTexture 등의 바이너리 에셋을 자동 감지하고 고품질 PNG, WAV, OGG, JSON 등으로
변환 및 일괄 추출 기능 제공.
"""
from __future__ import annotations

from .gui import AssetExtractorApp

__all__ = ["AssetExtractorApp"]

