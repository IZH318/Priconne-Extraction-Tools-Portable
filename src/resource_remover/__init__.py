"""원본 리소스 파일 정리(Resource Remover) 서브툴 패키지.

에셋 추출 완료 후 불필요해진 원본 리소스 캐시 파일 자동 검색 및 안전 삭제(휴지통/영구 삭제) 기능 제공.
중요 시스템/개발 폴더 보호 및 2단계 삭제 확인 안전장치 내장.
"""

from .gui import ResourceRemoverApp

__all__ = ["ResourceRemoverApp"]
