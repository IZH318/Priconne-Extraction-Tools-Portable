"""Story Viewer 비즈니스 로직 및 스토리 파싱/포맷팅 엔진 모듈.

스토리 JSON 데이터의 유효성 검증(StoryDataLoader), 선택지 분기 및 합류 구조 분석
(StoryBranchInfo, StoryBranchStructure), 씬 데이터 다중 조건 검색(SearchEngine),
스토리 대사 텍스트/마크다운 렌더링 포맷터(StoryFormatter) 제공.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, NamedTuple

from src.constants import SEPARATOR_MEDIUM


@dataclass
class StoryBranchInfo:
    """단일 분기 경로의 메타데이터 및 포함된 씬 범위 관리."""

    choice_scene: str
    choice_idx: int
    tag: str
    choice_text: str
    start_scene: str
    scenes: list[str] = field(default_factory=list)
    destination: str | None = None


@dataclass
class StoryBranchStructure:
    """스토리 전체 분기 그룹, 씬 매핑, 합류점 구조 캡슐화."""

    branch_groups: dict[str, list[StoryBranchInfo]]
    scene_to_branch: dict[str, StoryBranchInfo]
    merge_scenes: set[str]
    tag_to_scene: dict[str, str]


class ScriptChoice(NamedTuple):
    """대본(script) 모드 선택지 렌더링 데이터 (순번, 본문, 태그, 이동 대상 씬)."""

    idx: int
    text: str
    tag: str
    target_scene: str | None


ScriptNodeKind = Literal['header', 'merge', 'branch_start', 'place', 'print', 'choice', 'branch_end', 'no_dialogue']


@dataclass(slots=True)
class ScriptNode:
    """대본(script) 모드 공용 렌더링 노드 (장면 순회 산출 단위).

    헤더/합류 씬/분기 시작/장소/대사/선택지/분기 종료/대사 없음 노드가 단일 순회
    (StoryFormatter.iter_script_nodes)에서 산출되어, txt 태그 렌더러와 마크다운 렌더러가
    동일한 순회 결과를 소비.
    """

    kind: ScriptNodeKind
    scene_key: str = ''
    in_branch: bool = False
    title: str = ''
    situation: str = ''
    outline: str = ''
    outline_title: str = ''
    scene_range: str = ''
    branch_label: str = ''
    tag_suffix: str = ''
    place: str = ''
    speaker: str = ''
    lines: list[str] = field(default_factory=list)
    choices: list[ScriptChoice] = field(default_factory=list)
    leads_to: str = ''
    message: str = ''


class StoryDataLoader:
    """스토리 데이터 JSON 파일 유효성 검증 및 에셋 이름 추출 담당."""

    @staticmethod
    def is_valid_storydata(file_path: str, lang_dict: dict[str, str] | None = None) -> tuple[bool, dict[str, Any] | None, str | None]:

        """스토리 데이터 JSON 파일 유효성 검사.

        Args:
            file_path: 검사할 JSON 파일 경로.
            lang_dict: 오류 메시지 다국어 처리를 위한 딕셔너리.

        Returns:
            (유효성 여부, 파싱된 데이터 딕셔너리, 에러 메시지) 튜플.
        """
        if lang_dict is None:
            lang_dict = {}
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data:
                return False, None, lang_dict.get('log_reason_empty', "File content is empty or not in dictionary format.")
            if '0' in data and isinstance(data['0'], dict) and ('title' in data['0'] or 'outline' in data['0']):
                return True, data, None
            else:
                return False, None, lang_dict.get('log_reason_not_storydata', "Does not seem to be a storydata file (missing '0' key or title/outline).")
        except json.JSONDecodeError as e:
            return False, None, lang_dict.get('log_reason_json_error', "JSON format error: {e}").format(e=e)
        except OSError as e:
            return False, None, lang_dict.get('log_reason_os_error', "File read/other error: {e}").format(e=e)
        except (ValueError, TypeError, AttributeError) as e:
            return False, None, lang_dict.get('log_reason_unexpected_error', "Unexpected fatal error: {e}").format(e=e)

    @staticmethod
    def extract_asset_name(value: Any) -> str | None:
        """스토리 데이터 값에서 에셋(배경, BGM 등) 이름 추출.

        Args:
            value: 추출할 원본 값.

        Returns:
            추출된 문자열 이름 또는 None.
        """
        if isinstance(value, str): return value
        if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
        return None

class SearchEngine:
    """스토리 데이터 다중 조건 검색 기능 제공."""
    @staticmethod
    def check_scene(
        scene: dict[str, Any],
        criteria: dict[str, str],
        char_type_search: str | None = None,
        char_type_speaker: str | None = None,
        is_speaker: bool | None = None,
    ) -> bool:
        """단일 씬(Scene) 데이터의 주어진 검색 조건 일치 여부 확인.

        Args:
            scene: 씬 데이터 딕셔너리.
            criteria: 소문자로 변환된 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입 문자열 (하위 호환).
            char_type_speaker: '화자'에 해당하는 문자열 (하위 호환).
            is_speaker: 화자 검색 여부 (직접 지정 시 우선).

        Returns:
            조건 일치 여부 (bool).
        """
        if not isinstance(scene, dict):
            return False
        print_data = scene.get('print') if isinstance(scene.get('print'), dict) else {}
        if 'content' in criteria and not (isinstance(print_data, dict) and criteria['content'] in print_data.get('text', '').lower()):
            return False
        if 'bgm' in criteria and not ('bgm' in scene and criteria['bgm'] in str(scene.get('bgm', '')).lower()):
            return False
        if 'background' in criteria and not ('background' in scene and criteria['background'] in str(scene.get('background', '')).lower()):
            return False
        if 'char_name' in criteria:
            char_name_crit = criteria['char_name']
            speaker_mode = is_speaker if is_speaker is not None else (char_type_search == char_type_speaker)
            char_found = False
            if isinstance(print_data, dict) and (
                speaker_mode and char_name_crit in str(print_data.get('name', '')).lower()
                or not speaker_mode and char_name_crit in print_data.get('text', '').lower()
            ):
                char_found = True
            if not char_found:
                return False
        return True

    @staticmethod
    def check_file_content(
        data: dict[str, Any],
        criteria: dict[str, str],
        char_type_search: str | None = None,
        char_type_speaker: str | None = None,
        is_speaker: bool | None = None,
    ) -> bool:
        """파일 전체 내용의 주어진 검색 조건 일치 여부 확인.

        Args:
            data: 스토리 데이터 전체 딕셔너리.
            criteria: 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입.
            char_type_speaker: '화자'에 해당하는 문자열.
            is_speaker: 화자 검색 여부.

        Returns:
            조건 일치 여부 (bool).
        """
        lower_criteria = {k: v.lower() for k, v in criteria.items()}
        scene_0 = data.get('0', {}) if isinstance(data, dict) else {}
        if not isinstance(scene_0, dict):
            scene_0 = {}

        if 'title' in lower_criteria and lower_criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in lower_criteria and lower_criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        # 배경음악(BGM) 및 배경은 파일 전체 범위에서 만족하는 씬이 존재하는지 개별 평가
        if 'bgm' in lower_criteria:
            bgm_crit = lower_criteria['bgm']
            if not any(isinstance(s, dict) and 'bgm' in s and bgm_crit in str(s.get('bgm', '')).lower() for s in data.values()):
                return False

        if 'background' in lower_criteria:
            bg_crit = lower_criteria['background']
            if not any(isinstance(s, dict) and 'background' in s and bg_crit in str(s.get('background', '')).lower() for s in data.values()):
                return False

        # 대사/화자 조건 (char_name, content)
        dialogue_criteria = {k: v for k, v in lower_criteria.items() if k in ('char_name', 'content')}
        if not dialogue_criteria:
            return True

        for scene in data.values():
            if isinstance(scene, dict) and SearchEngine.check_scene(scene, dialogue_criteria, char_type_search, char_type_speaker, is_speaker):
                return True
        return False

    @staticmethod
    def check_file_for_search(
        filename: str,
        criteria: dict[str, str],
        char_type_search: str | None = None,
        char_type_speaker: str | None = None,
        all_files: dict[str, str] | None = None,
        is_speaker: bool | None = None,
    ) -> bool:
        """파일 이름과 내용 모두 포함한 검색 조건 일치 여부 확인.

        Args:
            filename: 파일 이름.
            criteria: 검색 조건 딕셔너리.
            char_type_search: 검색할 캐릭터 타입.
            char_type_speaker: '화자'에 해당하는 문자열.
            all_files: 전체 파일 경로 딕셔너리.
            is_speaker: 화자 검색 여부.

        Returns:
            조건 일치 여부 (bool).
        """
        if 'filename' in criteria and criteria['filename'].lower() not in filename.lower():
            return False

        if all_files is None:
            return False
        filepath = all_files.get(filename)
        if not filepath:
            return False
        is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
        if not is_valid or not isinstance(data, dict):
            return False

        content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
        if not content_criteria:
            return True

        return SearchEngine.check_file_content(data, content_criteria, char_type_search, char_type_speaker, is_speaker)

class StoryFormatter:
    """스토리 데이터를 UI에 맞춘 텍스트 및 태그 포맷으로 변환하는 서식 유틸리티.

    모든 메서드가 정적(stateless)이므로 클래스에서 직접 호출 가능.
    """
    _FIELD_ORDER: ClassVar[list[str]] = [
        'title', 'outline', 'movie', 'shake_anime', 'place',
        'vo', 'face', 'print', 'nod', 'wait', 'window_visible', 'change', 'chara_full',
        'fadein', 'focus', 'jump', 'fadeout_all', 'fadeout', 'pop', 'voice_effect',
        'change_window', 'ignore_bgm', 'eye_open', 'emotion', 'emotion_end', 'se', 'fadein_all',
        'effect', 'effect_delete', 'se_pause', 'multi_lipsync', 'bgm', 'tag',
        'choice', 'goto', 'text_size', 'scale', 'ui_visible', 'transition', 'black_out', 'white_out', 'bright_change',
        'background', 'situation', 'bg_pan', 'env_stop', 'env', 'background_color',
        'shake', 'sway', 'out_l', 'out_r', 'in_r', 'character_up_down', 'pan', 'camera_zoom',
        'still', 'still_unit', 'still_move', 'still_normalize', 'background_blur',
        'unknown'
    ]

    _DISPATCH_TABLE: ClassVar[dict[str, Callable[..., None]] | None] = None

    @classmethod
    def _get_dispatch_table(cls) -> dict[str, Callable[..., None]]:
        """필드별 포매터 디스패치 테이블 반환 (최초 1회만 생성)."""
        if cls._DISPATCH_TABLE is None:
            cls._DISPATCH_TABLE = {
                'print': cls._format_print,
                'chara_full': cls._format_generic_id_list,
                'fadein': cls._format_generic_id_list,
                'fadeout': cls._format_generic_id_list,
                'face': cls._format_generic_id_list,
                'nod': cls._format_simple_id_list,
                'shake': cls._format_simple_id_list,
                'focus': cls._format_simple_id_list,
                'choice': cls._format_choice,
            }
        return cls._DISPATCH_TABLE

    @staticmethod
    def resolve_story_branches(data: dict[str, Any]) -> StoryBranchStructure:
        """스토리 데이터 선택지 분기, 연쇄 씬 묶음, goto 점프 및 공통 합류 지점 계산."""
        scene_keys = sorted([k for k in data if isinstance(k, str) and k.isascii() and k.isdigit()], key=int)

        tag_to_scene: dict[str, str] = {}
        for k in scene_keys:
            s = data[k]
            if isinstance(s, dict):
                t = str(s.get('tag', '') or '').strip()
                if t:
                    tag_to_scene[t] = k

        branch_groups: dict[str, list[StoryBranchInfo]] = {}
        scene_to_branch: dict[str, StoryBranchInfo] = {}
        merge_scenes: set[str] = set()

        def has_story_content(scene: Any) -> bool:
            return isinstance(scene, dict) and bool(
                'print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene
            )

        # 다중 선택지 씬 추출
        for k in scene_keys:
            s = data[k]
            if not isinstance(s, dict):
                continue
            choices = s.get('choice')
            if choices and isinstance(choices, list) and len(choices) > 1:
                branches: list[StoryBranchInfo] = []
                for idx, c in enumerate(choices, 1):
                    if isinstance(c, dict):
                        c_tag = str(c.get('tag', '') or '').strip()
                        c_text = str(c.get('text', '') or '').strip()
                        if c_tag in tag_to_scene:
                            b = StoryBranchInfo(
                                choice_scene=k,
                                choice_idx=idx,
                                tag=c_tag,
                                choice_text=c_text,
                                start_scene=tag_to_scene[c_tag],
                                scenes=[]
                            )
                            branches.append(b)
                if branches:
                    branch_groups[k] = branches

        # 각 분기 그룹의 씬 범위, 목적지(goto) 및 합류 씬 계산
        for branches in branch_groups.values():
            def _safe_start_key(b: Any) -> int:
                try:
                    return int(b.start_scene)
                except (ValueError, TypeError):
                    return 0
            branches.sort(key=_safe_start_key)

            merge_candidate: str | None = None
            for b in branches:
                if b.start_scene not in scene_keys:
                    continue
                curr_idx = scene_keys.index(b.start_scene)
                for look_k in scene_keys[curr_idx:curr_idx + 30]:
                    look_s = data.get(look_k, {})
                    if isinstance(look_s, dict):
                        g = str(look_s.get('goto', '') or '').strip()
                        if g and g in tag_to_scene:
                            g_sc = tag_to_scene[g]
                            try:
                                if int(g_sc) > int(b.start_scene):
                                    merge_candidate = g_sc
                                    break
                            except (ValueError, TypeError):
                                pass
                if merge_candidate:
                    break

            for i, b in enumerate(branches):
                if b.start_scene not in scene_keys:
                    continue
                start_idx = scene_keys.index(b.start_scene)
                if i + 1 < len(branches) and branches[i + 1].start_scene in scene_keys:
                    end_idx = scene_keys.index(branches[i + 1].start_scene)
                else:
                    if merge_candidate and merge_candidate in scene_keys:
                        end_idx = scene_keys.index(merge_candidate)
                    else:
                        end_idx = min(start_idx + 1, len(scene_keys))
                        for scan_i in range(start_idx + 1, len(scene_keys)):
                            scan_k = scene_keys[scan_i]
                            scan_s = data.get(scan_k, {})
                            if isinstance(scan_s, dict) and (scan_s.get('tag') or scan_s.get('choice')):
                                end_idx = scan_i
                                merge_candidate = scan_k
                                break

                raw_scenes: list[str] = []
                for scan_i in range(start_idx, end_idx):
                    sc_k = scene_keys[scan_i]
                    raw_scenes.append(sc_k)
                    sc_data = data.get(sc_k, {})
                    if isinstance(sc_data, dict):
                        g = str(sc_data.get('goto', '') or '').strip()
                        if g and g in tag_to_scene:
                            b.destination = tag_to_scene[g]
                            break

                if not b.destination:
                    b.destination = merge_candidate

                b.scenes = [sc for sc in raw_scenes if has_story_content(data.get(sc))]
                for sc_k in b.scenes:
                    scene_to_branch[sc_k] = b

            if merge_candidate:
                merge_scenes.add(merge_candidate)

        return StoryBranchStructure(
            branch_groups=branch_groups,
            scene_to_branch=scene_to_branch,
            merge_scenes=merge_scenes,
            tag_to_scene=tag_to_scene
        )

    @staticmethod
    def iter_script_nodes(data: dict[str, Any], lang_dict: dict[str, str] | None = None) -> Iterator[ScriptNode]:
        """대본(script) 모드 공용 장면 순회 제너레이터.

        txt 태그 렌더러(_format_script_mode)와 마크다운 렌더러(_format_script_mode_markdown)가
        동일한 순회 결과를 소비하도록, 헤더/합류 씬/분기 시작/장소/대사/선택지/분기 종료 노드를
        장면 순서대로 산출.

        Args:
            data: 스토리 데이터 딕셔너리.
            lang_dict: 다국어 딕셔너리 (None일 경우 기본 라벨 적용).

        Yields:
            ScriptNode: 장면 순회 순서대로 산출되는 의미 노드.
        """
        scene_keys = sorted(
            data.keys(),
            key=lambda x: int(x) if isinstance(x, str) and x.isascii() and x.isdigit() else float('inf'),
        )

        # 다국어 라벨 획득
        branch_dialogue_label = lang_dict.get('script_branch_dialogue', 'Branch Dialogue') if lang_dict else 'Branch Dialogue'
        choice_item_label = lang_dict.get('script_choice_item', 'Choice') if lang_dict else 'Choice'
        outline_title = lang_dict.get('script_outline_title', 'Synopsis') if lang_dict else 'Synopsis'
        no_dialogue_msg = lang_dict.get('script_no_dialogue', 'This story has no dialogue data') if lang_dict else 'This story has no dialogue data'
        branch_leads_to_fmt = lang_dict.get('script_branch_leads_to', 'Leads to [Scene {scene}]') if lang_dict else 'Leads to [Scene {scene}]'
        branch_end_label = lang_dict.get('script_branch_end', '[End of Story]') if lang_dict else '[End of Story]'
        branch_label_fmt = (
            lang_dict.get('script_branch_label_fmt', "{dialogue_label} for {choice_label} #{idx}")
            if lang_dict else "{dialogue_label} for {choice_label} #{idx}"
        )

        structure = StoryFormatter.resolve_story_branches(data)
        scene_to_branch = structure.scene_to_branch
        merge_scenes = structure.merge_scenes
        tag_to_scene = structure.tag_to_scene

        # 상단 타이틀 및 줄거리 (Scene 0)
        scene_0 = data.get('0', {})
        title = ""
        situation = ""
        outline = ""
        if isinstance(scene_0, dict):
            title = str(scene_0.get('title', '') or '').strip()
            situation = str(scene_0.get('situation', '') or '').strip()
            outline = str(scene_0.get('outline', '') or '').strip()

        yield ScriptNode(kind='header', title=title, situation=situation, outline=outline, outline_title=outline_title)

        has_dialogue = False
        last_place = None

        for key in scene_keys:
            scene = data[key]
            if not isinstance(scene, dict):
                continue

            has_scene_content = ('print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene)
            if key != '0' and not has_scene_content:
                continue

            # 합류 씬 헤더
            if key != '0' and key in merge_scenes:
                yield ScriptNode(kind='merge', scene_key=key)

            b = scene_to_branch.get(key)
            is_branch_start = bool(b and b.scenes and b.scenes[0] == key)
            is_branch_end = bool(b and b.scenes and b.scenes[-1] == key)
            in_branch = b is not None

            # 분기 씬 헤더
            if is_branch_start:
                assert b is not None
                scene_range_str = f"Scene {b.scenes[0]}~{b.scenes[-1]}" if len(b.scenes) > 1 else f"Scene {key}"
                branch_label_str = branch_label_fmt.format(
                    choice_label=choice_item_label,
                    idx=b.choice_idx,
                    dialogue_label=branch_dialogue_label,
                )
                tag_str = f" (Tag {b.tag})" if b.tag else ""
                has_dialogue = True
                yield ScriptNode(
                    kind='branch_start', scene_key=key, in_branch=True,
                    scene_range=scene_range_str, branch_label=branch_label_str, tag_suffix=tag_str
                )

            # 장소 안내
            raw_place = scene.get('place')
            place_str = ""
            if isinstance(raw_place, list) and raw_place:
                place_str = str(raw_place[0]).strip()
            elif isinstance(raw_place, str):
                place_str = raw_place.strip()

            if place_str and place_str != title and place_str != situation and place_str != last_place:
                has_dialogue = True
                last_place = place_str
                yield ScriptNode(kind='place', scene_key=key, in_branch=in_branch, place=place_str)

            # 대사 (print)
            p_data = scene.get('print')
            if p_data and isinstance(p_data, dict):
                speaker = str(p_data.get('name', '') or '').strip()
                dialogue = str(p_data.get('text', '') or '').strip()

                if dialogue:
                    has_dialogue = True
                    yield ScriptNode(
                        kind='print', scene_key=key, in_branch=in_branch, speaker=speaker, lines=dialogue.splitlines()
                    )

            # 선택지 (choice)
            choices = scene.get('choice')
            if choices and isinstance(choices, list) and len(choices) > 0:
                has_dialogue = True
                prepared_choices: list[ScriptChoice] = []
                for idx, c in enumerate(choices, 1):
                    c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                    c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                    prepared_choices.append(
                        ScriptChoice(idx=idx, text=c_text, tag=c_tag, target_scene=tag_to_scene.get(c_tag))
                    )
                yield ScriptNode(kind='choice', scene_key=key, in_branch=in_branch, choices=prepared_choices)

            # 분기 씬 박스 마감
            if is_branch_end:
                assert b is not None
                dest_scene = b.destination
                if dest_scene:
                    label = branch_leads_to_fmt.format(scene=dest_scene)
                else:
                    label = branch_end_label
                yield ScriptNode(kind='branch_end', scene_key=key, in_branch=True, leads_to=label)

        if not has_dialogue and not (title or outline):
            yield ScriptNode(kind='no_dialogue', message=no_dialogue_msg)

    @staticmethod
    def _format_script_mode(
        data: dict[str, Any],
        lang_dict: dict[str, str] | None = None,
    ) -> list[tuple[str, str | None]]:
        """스토리 데이터를 대본/소설 형식으로 가독성 높게 변환.

        Args:
            data: 포맷팅할 스토리 데이터 딕셔너리.
            lang_dict: 다국어 딕셔너리 (None일 경우 기본 언어 적용).

        Returns:
            (포맷팅된 문자열, 태그) 튜플의 리스트.
        """
        content_list: list[tuple[str, str | None]] = []

        # 다국어 라벨 획득
        place_prefix = lang_dict.get('script_place_prefix', 'Place') if lang_dict else 'Place'
        branch_point_label = lang_dict.get('script_branch_point', 'Branch Point') if lang_dict else 'Branch Point'
        choice_item_label = lang_dict.get('script_choice_item', 'Choice') if lang_dict else 'Choice'

        for node in StoryFormatter.iter_script_nodes(data, lang_dict):
            indent = "│ " if node.in_branch else ""

            # 상단 타이틀 및 줄거리 노드
            if node.kind == 'header':
                if node.title and node.situation and node.title != node.situation:
                    content_list.append((f"■ {node.title}\n", 'script_title'))
                    content_list.append((f"▶ {node.situation}\n", 'script_subtitle'))
                elif node.title:
                    content_list.append((f"■ {node.title}\n", 'script_title'))
                elif node.situation:
                    content_list.append((f"■ {node.situation}\n", 'script_title'))

                if node.outline:
                    content_list.append(("─" * 37 + "\n", 'script_divider'))
                    content_list.append((f"【 {node.outline_title} 】\n", 'script_outline_header'))
                    content_list.append((f"{node.outline}\n", 'script_narration'))

                if node.title or node.situation or node.outline:
                    content_list.append(("─" * 37 + "\n\n", 'script_divider'))

            # 합류 씬 헤더 노드
            elif node.kind == 'merge':
                content_list.append((f"═ [ Scene {node.scene_key} ] ═\n", 'script_branch'))

            # 분기 씬 헤더 노드
            elif node.kind == 'branch_start':
                content_list.append(
                    (f"┌─ [ {node.scene_range} | {node.branch_label}{node.tag_suffix} ] ─┐\n", 'script_branch')
                )

            # 장소 노드
            elif node.kind == 'place':
                content_list.append((f"{indent}[{place_prefix}: {node.place}]\n\n", 'script_place'))

            # 대사 노드
            elif node.kind == 'print':
                if node.speaker:
                    content_list.append((f"{indent}[{node.speaker}]\n", 'script_speaker'))

                dialogue_tag = 'script_dialogue' if node.speaker else 'script_narration'
                for line in node.lines:
                    content_list.append((f"{indent}{line}\n", dialogue_tag))

                content_list.append((f"{indent}\n" if node.in_branch else "\n", None))

            # 선택지 노드
            elif node.kind == 'choice':
                if len(node.choices) > 1:
                    content_list.append((f"{indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", 'script_divider'))
                    content_list.append(
                        (f"{indent}▼ [{branch_point_label} | Scene {node.scene_key}]\n", 'script_branch')
                    )
                    for choice in node.choices:
                        is_last = (choice.idx == len(node.choices))
                        prefix = "└─" if is_last else "├─"
                        sub_indent = "       └─ ▶ " if is_last else "  │   └─ ▶ "

                        dest = f"[Scene {choice.target_scene}]" if choice.target_scene else ""
                        tag_str = f" (Tag {choice.tag})" if choice.tag else ""

                        content_list.append(
                            (f"{indent}  {prefix} [{choice_item_label} {choice.idx}] {choice.text}", 'script_choice')
                        )
                        if tag_str:
                            content_list.append((tag_str, 'script_choice_tag'))
                        content_list.append(("\n", None))
                        if dest:
                            content_list.append((f"{indent}{sub_indent}{dest}\n", 'script_choice_tag'))

                    content_list.append((f"{indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n", 'script_divider'))
                    if not node.in_branch:
                        content_list.append(("\n", None))
                else:
                    choice = node.choices[0]
                    target_dest = f" ─ ▶ [Scene {choice.target_scene}]" if choice.target_scene else ""
                    tag_str = f" (Tag {choice.tag})" if choice.tag else ""

                    content_list.append(
                        (f"{indent}─ [ {choice_item_label} | Scene {node.scene_key} ] ─\n", 'script_choice')
                    )
                    content_list.append((f"{indent}   1. {choice.text}", 'script_choice'))
                    if tag_str:
                        content_list.append((tag_str, 'script_choice_tag'))
                    if target_dest:
                        content_list.append((target_dest, 'script_choice_tag'))
                    content_list.append(("\n", None))
                    if not node.in_branch:
                        content_list.append(("\n", None))

            # 분기 씬 박스 마감 노드
            elif node.kind == 'branch_end':
                line_prefix = "└── ▶ "
                content_list.append((line_prefix, 'script_divider'))
                content_list.append((node.leads_to, 'script_choice_tag'))
                content_list.append((" " + "─" * 37 + "\n\n", 'script_divider'))

            # 대사 없음 안내 노드
            elif node.kind == 'no_dialogue':
                content_list.append((f"({node.message})\n", 'script_narration'))

        return content_list

    @staticmethod
    def format_story_data(data: dict[str, Any], view_mode: str, lang_dict: dict[str, str] | None = None) -> list[tuple[str, str | None]]:
        """스토리 데이터를 지정된 뷰 모드의 서식화된 텍스트 및 태그 리스트로 변환.

        Args:
            data: 포맷팅할 스토리 데이터 딕셔너리.
            view_mode: 뷰 모드 ('script', 'simple', 'detailed').
            lang_dict: 다국어 딕셔너리 (None일 경우 기본 언어 적용).

        Returns:
            (포맷팅된 문자열, 태그) 튜플의 리스트.
        """
        if view_mode == 'script':
            return StoryFormatter._format_script_mode(data, lang_dict)

        dispatch = StoryFormatter._get_dispatch_table()
        content_list: list[tuple[str, str | None]] = []
        if not isinstance(data, dict):
            return content_list
        scene_keys = sorted(
            data.keys(),
            key=lambda x: int(x) if isinstance(x, str) and x.isascii() and x.isdigit() else float('inf'),
        )

        for key in scene_keys:
            scene = data[key]
            if not isinstance(scene, dict):
                continue
            content_list.append((f" S# {key} \n", 'scene_header'))
            if view_mode == 'simple':
                keys_to_display = [k for k in ['title', 'outline', 'tag', 'vo', 'print', 'choice'] if k in scene]
            else:
                existing_keys = [k for k in StoryFormatter._FIELD_ORDER if k in scene]
                other_keys = sorted([k for k in scene if k not in StoryFormatter._FIELD_ORDER])
                keys_to_display = existing_keys + other_keys

            for fld in keys_to_display:
                value = scene[fld]
                content_list.append(("    " + f"{fld}\n", 'key'))
                formatter = dispatch.get(fld, StoryFormatter._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append((SEPARATOR_MEDIUM + "\n\n", None))
        return content_list

    @staticmethod
    def _format_print(value: dict[str, Any], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        name, text = str(value.get('name', '???')), value.get('text', '')
        formatted_text = text.replace('\n', '\n' + indent)
        content_list.extend([(indent + f"- name: {name}\n", 'print_sub_key'), (indent + f"- text: “{formatted_text}”\n", 'print_sub_key')])

    @staticmethod
    def _format_choice(value: list[dict[str, Any]], content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        for i, item in enumerate(value, 1):
            choice_text = item.get('text', '') if isinstance(item, dict) else str(item)
            tag_str = f" (→ S# {item['tag']})" if isinstance(item, dict) and 'tag' in item else ""
            content_list.append((indent + f"{i}. {choice_text}", 'choice'))
            if tag_str:
                content_list.append((f"{tag_str}\n", 'choice_tag'))
            else:
                content_list.append(("\n", None))

    @staticmethod
    def _format_default(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        content_list.append(("        " + f"{value!s}\n", 'value'))

    @staticmethod
    def _format_generic_id_list(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list):
            StoryFormatter._format_default(value, content_list)
            return
        for item in value:
            if isinstance(item, list) and item:
                details = ", ".join(map(str, item[1:]))
                content_list.extend([(indent + f"- {item[0]!s}", 'value'), (f" ({details})\n" if details else "\n", 'value')])
            else:
                content_list.append((indent + f"- {item!s}\n", 'value'))

    @staticmethod
    def _format_simple_id_list(value: Any, content_list: list[tuple[str, str | None]]) -> None:
        indent = "        "
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {item!s}\n", 'value'))
