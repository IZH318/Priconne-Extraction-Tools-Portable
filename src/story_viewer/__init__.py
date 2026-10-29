"""스토리 데이터 뷰어 및 스크립트 내보내기 패키지(Story Viewer).

UnityPy 등을 통해 변환된 스토리 JSON 파일(storydata_*.json) 구문 분석,
JP/KR/EN 등 공식 master.db와의 자동 매핑을 통한 에피소드 제목, 등장 캐릭터,
분기 선택지, 대사 다국어 하이라이팅 표시 및 TXT/Markdown 내보내기 지원.
"""

from .gui import StoryViewerApp

__all__ = ["StoryViewerApp"]

