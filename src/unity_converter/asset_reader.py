"""Unity 번들 로드 및 오브젝트 표시 이름 공통 헬퍼 모듈.

extractor(배치 추출)와 asset_browser(미리보기)가 중복 구현하던 UnityPy 로드
(FALLBACK_UNITY_VERSION 보정)와 오브젝트 표시 이름 계산을 단일화한다.
UnityPy import는 호출 시점까지 지연한다(불필요한 임포트 비용/부작용 방지).
"""
from __future__ import annotations

from typing import Any

from src.constants import DEFAULT_UNITY_VERSION


def open_bundle(file_path: str, unity_version: str | None = None, *, force_version: bool = False) -> Any:
    """Unity 번들을 로드하고 필요 시 FALLBACK_UNITY_VERSION을 보정한다.

    Args:
        file_path: 로드할 번들 경로.
        unity_version: 사용할 Unity 버전(없으면 DEFAULT_UNITY_VERSION).
        force_version: True면 기존 설정과 무관하게 지정 버전으로 덮어쓴다.
            (extractor는 False: 미설정일 때만, asset_browser는 True: 항상 지정 버전 사용)

    Returns:
        UnityPy.Environment: 로드된 번들 환경.
    """
    import UnityPy
    from UnityPy import config

    if force_version or not getattr(config, 'FALLBACK_UNITY_VERSION', None):
        config.FALLBACK_UNITY_VERSION = unity_version or DEFAULT_UNITY_VERSION  # type: ignore[assignment]
    return UnityPy.load(file_path)


def get_object_name(obj: Any) -> str:
    """오브젝트의 표시 이름(m_Name)을 반환하고, 없으면 PathID 기반 폴백.

    Args:
        obj: UnityPy ObjectReader.

    Returns:
        str: 에셋 이름 또는 'PathID_<id>' 폴백.
    """
    try:
        data = obj.parse_as_object()
        return getattr(data, 'm_Name', '') or f"PathID_{obj.path_id}"
    except AttributeError:
        return f"PathID_{obj.path_id}"
