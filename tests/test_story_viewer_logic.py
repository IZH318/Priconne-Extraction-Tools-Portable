"""
Story Viewer Logic Unit Tests
StoryDataLoader 및 SearchEngine의 핵심 기능을 검증합니다.
"""
from __future__ import annotations
import pytest
import json
from src.story_viewer.logic import SearchEngine, StoryDataLoader


class TestStoryDataLoader:
    """StoryDataLoader의 파일 검증 기능을 검증합니다."""

    def test_valid_storydata(self, base_test_dir) -> None:
        """정상적인 storydata 파일이 올바르게 검증되는지 확인합니다."""
        valid_file = base_test_dir / "valid.json"
        valid_data = {"0": {"title": "Test Title"}}
        valid_file.write_text(json.dumps(valid_data), encoding='utf-8')
        res, data, err = StoryDataLoader.is_valid_storydata(str(valid_file))
        assert res is True
        assert data == valid_data

    def test_invalid_json(self, base_test_dir) -> None:
        """잘못된 JSON 파일이 올바르게 거부되는지 확인합니다."""
        invalid_json = base_test_dir / "invalid.json"
        invalid_json.write_text("{invalid json", encoding='utf-8')
        res, data, err = StoryDataLoader.is_valid_storydata(str(invalid_json))
        assert res is False
        assert "JSON format error" in err

    def test_non_dict_data(self, base_test_dir) -> None:
        """딕셔너리가 아닌 데이터 구조가 올바르게 거부되는지 확인합니다."""
        not_dict = base_test_dir / "not_dict.json"
        not_dict.write_text("[]", encoding='utf-8')
        res, data, err = StoryDataLoader.is_valid_storydata(str(not_dict))
        assert res is False
        assert "dictionary format" in err

    def test_missing_zero_key(self, base_test_dir) -> None:
        """'0' 키 또는 title/outline 누락이 올바르게 감지되는지 확인합니다."""
        missing_key = base_test_dir / "missing.json"
        missing_key.write_text(json.dumps({"1": {"text": "ah"}}), encoding='utf-8')
        res, data, err = StoryDataLoader.is_valid_storydata(str(missing_key))
        assert res is False
        assert "missing '0' key" in err


class TestSearchEngine:
    """SearchEngine의 컨텐츠 검색 기능을 검증합니다."""

    MOCK_DATA = {
        "0": {
            "title": "공주님과의 영원한 만남",
            "outline": "어느 날 나타난 기억 상실증 기사"
        },
        "1": {
            "print": {"name": "페코린느", "text": "안녕! 밥은 먹었어?"},
            "bgm": "bgm_01",
            "background": "bg_001"
        },
        "2": {
            "print": {"name": "콧코로", "text": "주인님, 안녕하십니까."},
            "bgm": "bgm_02",
            "background": "bg_002"
        }
    }

    def test_title_matching(self) -> None:
        """타이틀 키워드 매칭이 올바르게 동작하는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"title": "공주님"}, char_type_search="speaker", char_type_speaker="speaker"
        ) is True

    def test_cross_scene_condition_fail(self) -> None:
        """서로 다른 씬에 분포된 조건이 AND로 매칭되지 않는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"content": "안녕하십니까", "bgm": "bgm_01"}, "speaker", "speaker"
        ) is False

    def test_same_scene_and_matching(self) -> None:
        """같은 씬 내 다중 조건 AND 매칭이 올바르게 동작하는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"char_name": "페코", "content": "안녕"}, "speaker", "speaker"
        ) is True

    def test_speaker_name_search(self) -> None:
        """화자 이름 기반 검색이 올바르게 동작하는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"char_name": "콧코로"}, "speaker", "speaker"
        ) is True

    def test_text_content_search_mode(self) -> None:
        """텍스트 기반 이름 검색 모드에서 화자 이름이 매칭되지 않는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"char_name": "페코린느"}, "text", "speaker"
        ) is False

    def test_keyword_in_text_search(self) -> None:
        """대사 텍스트 내 키워드 매칭 검색이 올바르게 동작하는지 확인합니다."""
        assert SearchEngine.check_file_content(
            self.MOCK_DATA, {"char_name": "밥"}, "text", "speaker"
        ) is True


class TestStoryFormatter:
    """StoryFormatter의 데이터 포맷 변환 기능을 검증합니다."""

    @pytest.fixture
    def formatter(self):
        from src.story_viewer.logic import StoryFormatter
        return StoryFormatter()

    def test_format_empty_data(self, formatter) -> None:
        """빈 데이터에 대해 빈 결과를 반환하는지 확인합니다."""
        result = formatter.format_story_data({}, 'simple')
        assert result == []

    def test_format_simple_mode_title(self, formatter) -> None:
        """simple 모드에서 title 필드가 포함되는지 확인합니다."""
        data = {"0": {"title": "테스트 타이틀", "outline": "테스트 개요"}}
        result = formatter.format_story_data(data, 'simple')
        texts = [text for text, tag in result]
        combined = "".join(texts)
        assert "테스트 타이틀" in combined or "title" in combined

    def test_format_detailed_mode_has_more_fields(self, formatter) -> None:
        """detailed 모드가 simple 모드보다 더 많은 필드를 렌더링하는지 확인합니다."""
        data = {
            "0": {"title": "Title", "outline": "Outline", "bgm": "bgm_01", "background": "bg_01"}
        }
        simple_result = formatter.format_story_data(data, 'simple')
        detailed_result = formatter.format_story_data(data, 'detailed')
        assert len(detailed_result) >= len(simple_result)

    def test_format_choice_field(self, formatter) -> None:
        """choice 필드가 올바르게 포맷되는지 확인합니다."""
        data = {
            "0": {"title": "Choice Test"},
            "1": {"choice": [{"text": "선택지 A", "tag": "2"}, {"text": "선택지 B", "tag": "3"}]}
        }
        result = formatter.format_story_data(data, 'detailed')
        texts = "".join(text for text, tag in result)
        assert "선택지 A" in texts
        assert "선택지 B" in texts

    def test_format_print_field(self, formatter) -> None:
        """print 필드의 name/text가 올바르게 포맷되는지 확인합니다."""
        data = {
            "0": {"title": "Print Test"},
            "1": {"print": {"name": "페코린느", "text": "안녕!"}}
        }
        result = formatter.format_story_data(data, 'simple')
        texts = "".join(text for text, tag in result)
        assert "페코린느" in texts
        assert "안녕!" in texts

    def test_format_scene_header_tags(self, formatter) -> None:
        """씬 헤더에 'scene_header' 태그가 올바르게 적용되는지 확인합니다."""
        data = {"0": {"title": "Header Test"}}
        result = formatter.format_story_data(data, 'simple')
        header_tags = [tag for text, tag in result if tag == 'scene_header']
        assert len(header_tags) >= 1
