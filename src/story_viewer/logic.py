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
    choice_indices: list[int] = field(default_factory=list)
    indent_level: int = 0
    is_loop: bool = False


@dataclass
class StoryBranchStructure:
    """스토리 전체 분기 그룹, 씬 매핑, 합류점 구조 캡슐화."""

    branch_groups: dict[str, list[StoryBranchInfo]]
    scene_to_branch: dict[str, StoryBranchInfo]
    merge_scenes: set[str]
    tag_to_scene: dict[str, str]
    branch_starts: dict[str, list[StoryBranchInfo]] = field(default_factory=dict)
    branch_ends: dict[str, list[StoryBranchInfo]] = field(default_factory=dict)
    transition_scenes: set[str] = field(default_factory=set)


class ScriptChoice(NamedTuple):
    """대본(script) 모드 선택지 렌더링 데이터 (순번, 본문, 태그, 이동 대상 씬)."""

    idx: int
    text: str
    tag: str
    target_scene: str | None


ScriptNodeKind = Literal[
    'header', 'merge', 'branch_start', 'place', 'print', 'choice',
    'branch_end', 'no_dialogue', 'transition_scene', 'movie', 'still'
]


@dataclass(slots=True)
class ScriptNode:
    """대본(script) 모드 공용 렌더링 노드 (장면 순회 산출 단위).

    헤더/합류 씬/분기 시작/전환 씬/장소/대사/연출(무비, 스틸)/선택지/분기 종료/대사 없음 노드가
    단일 순회(StoryFormatter.iter_script_nodes)에서 산출되어, txt 태그 렌더러와 마크다운 렌더러가
    동일한 순회 결과를 소비.
    """

    kind: ScriptNodeKind
    scene_key: str = ''
    in_branch: bool = False
    indent_level: int = 0
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
    movie_id: str = ''
    still_id: str = ''


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

        def has_story_content(scene: Any) -> bool:
            return isinstance(scene, dict) and bool(
                'print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene
                or 'movie' in scene or 'still' in scene
            )

        # 단일 선택지 태그 및 전환 대상 씬 감지
        single_choice_tags: set[str] = set()
        single_choice_targets: set[str] = set()
        for k in scene_keys:
            s = data[k]
            if isinstance(s, dict):
                c = s.get('choice')
                if isinstance(c, list) and len(c) == 1 and isinstance(c[0], dict):
                    t = str(c[0].get('tag', '') or '').strip()
                    if t:
                        single_choice_tags.add(t)
                        if t in tag_to_scene:
                            single_choice_targets.add(tag_to_scene[t])
                    else:
                        curr_idx = scene_keys.index(k)
                        if curr_idx + 1 < len(scene_keys):
                            single_choice_targets.add(scene_keys[curr_idx + 1])

        # 다중 선택지 씬 키 추출
        multi_choice_keys = [
            k for k in scene_keys
            if isinstance(data[k], dict) and isinstance(data[k].get('choice'), list) and len(data[k]['choice']) > 1
        ]

        branch_groups: dict[str, list[StoryBranchInfo]] = {}

        for k in multi_choice_keys:
            s = data[k]
            choices = s['choice']
            curr_idx = scene_keys.index(k)

            # 각 선택지의 목적지 씬 계산
            targets: list[str | None] = []
            for c in choices:
                t = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                targets.append(tag_to_scene.get(t))

            explicit_targets = [tgt for tgt in targets if tgt is not None]
            max_explicit = max((int(et) for et in explicit_targets), default=int(k))

            # 합류 씬 후보 계산
            merge_candidate: str | None = None
            next_multi = next((m for m in multi_choice_keys if int(m) > max_explicit), None)

            scan_limit = scene_keys.index(next_multi) if next_multi else len(scene_keys)
            for scan_i in range(curr_idx + 1, scan_limit):
                sk = scene_keys[scan_i]
                sd = data.get(sk, {})
                if isinstance(sd, dict):
                    g = str(sd.get('goto', '') or '').strip()
                    if g and g in tag_to_scene:
                        g_sc = tag_to_scene[g]
                        if int(g_sc) > max_explicit:
                            merge_candidate = g_sc
                            break

            # 미존재 GOTO 태그(goto: 5) 보정 (tag 7 씬으로 대체)
            if not merge_candidate and any(str(data.get(scene_keys[si], {}).get('goto', '')) == '5' for si in range(curr_idx, min(curr_idx + 3, len(scene_keys)))):
                if '7' in tag_to_scene and int(tag_to_scene['7']) > max_explicit:
                    merge_candidate = tag_to_scene['7']

            if not merge_candidate:
                if next_multi:
                    merge_candidate = next_multi
                else:
                    max_exp_idx = scene_keys.index(str(max_explicit))
                    for scan_i in range(max_exp_idx + 1, len(scene_keys)):
                        sk = scene_keys[scan_i]
                        sd = data.get(sk, {})
                        if isinstance(sd, dict):
                            t = str(sd.get('tag', '') or '').strip()
                            c = sd.get('choice')
                            if c or (t and t not in single_choice_tags):
                                merge_candidate = sk
                                break

            # 누락된 선택지 태그 목적지 보정 (폴스루/스킵)
            for i in range(len(choices)):
                if targets[i] is None:
                    if i == len(choices) - 1:
                        targets[i] = merge_candidate if merge_candidate else str(int(k) + 1)
                    else:
                        next_t = next((targets[j] for j in range(i + 1, len(choices)) if targets[j]), None)
                        targets[i] = next_t if next_t else str(int(k) + 1)

            # 분기 블록 구성 (합류 씬으로 바로 건너뛰는 스킵 선택지는 별도 대화 블록 미생성)
            grouped_by_target: dict[str, list[tuple[int, dict[str, Any]]]] = {}
            for idx, c in enumerate(choices, 1):
                if isinstance(c, dict):
                    tgt = targets[idx - 1]
                    c_tag = str(c.get('tag', '') or '').strip()
                    is_skip = (c_tag not in tag_to_scene) and (tgt == merge_candidate)
                    if tgt and tgt in scene_keys and not is_skip:
                        grouped_by_target.setdefault(tgt, []).append((idx, c))

            branches: list[StoryBranchInfo] = []
            for tgt, items in grouped_by_target.items():
                first_idx, first_c = items[0]
                indices = [item[0] for item in items]
                b = StoryBranchInfo(
                    choice_scene=k,
                    choice_idx=first_idx,
                    tag=str(first_c.get('tag', '') or '').strip(),
                    choice_text=str(first_c.get('text', '') or '').strip(),
                    start_scene=tgt,
                    scenes=[],
                    choice_indices=indices
                )
                branches.append(b)

            if branches:
                branch_groups[k] = branches

        def _safe_start_key(b: Any) -> int:
            try:
                return int(b.start_scene)
            except (ValueError, TypeError):
                return 0

        all_starts = sorted([_safe_start_key(b) for bg in branch_groups.values() for b in bg])

        scene_to_branch: dict[str, StoryBranchInfo] = {}
        branch_starts: dict[str, list[StoryBranchInfo]] = {}
        branch_ends: dict[str, list[StoryBranchInfo]] = {}
        merge_scenes: set[str] = set()

        for choice_sc, branches in branch_groups.items():
            # 분기 시작 씬 번호 기준 오름차순 정렬
            branches.sort(key=_safe_start_key)
            max_start = max(_safe_start_key(b) for b in branches)

            curr_idx = scene_keys.index(choice_sc)
            candidates: list[int] = []
            next_multi = next((m for m in multi_choice_keys if int(m) > max_start), None)
            if next_multi:
                candidates.append(int(next_multi))

            curr_starts = {_safe_start_key(b) for b in branches}
            other_starts = [s for s in all_starts if s > max_start and s not in curr_starts]
            if other_starts:
                candidates.append(min(other_starts))

            boundary_num = min(candidates) if candidates else None
            boundary_sc = str(boundary_num) if boundary_num is not None else None
            scan_limit = scene_keys.index(boundary_sc) if boundary_sc and boundary_sc in scene_keys else len(scene_keys)

            merge_cand: str | None = None
            for b in branches:
                curr_b_idx = scene_keys.index(b.start_scene)
                for scan_i in range(curr_b_idx, scan_limit):
                    sk = scene_keys[scan_i]
                    sd = data.get(sk, {})
                    if isinstance(sd, dict):
                        g = str(sd.get('goto', '') or '').strip()
                        if g and g in tag_to_scene and int(tag_to_scene[g]) > max_start:
                            merge_cand = tag_to_scene[g]
                            break
                if merge_cand:
                    break

            if not merge_cand and any(str(data.get(scene_keys[si], {}).get('goto', '')) == '5' for si in range(curr_idx, min(curr_idx + 3, len(scene_keys)))):
                if '7' in tag_to_scene and int(tag_to_scene['7']) > max_start:
                    merge_cand = tag_to_scene['7']

            if not merge_cand:
                if boundary_sc:
                    merge_cand = boundary_sc
                else:
                    last_branch_idx = scene_keys.index(str(max_start))
                    for scan_i in range(last_branch_idx + 1, len(scene_keys)):
                        sk = scene_keys[scan_i]
                        sd = data.get(sk, {})
                        if isinstance(sd, dict):
                            t = str(sd.get('tag', '') or '').strip()
                            c = sd.get('choice')
                            if c or (t and t not in single_choice_tags):
                                merge_cand = sk
                                break

            for i, b in enumerate(branches):
                start_idx = scene_keys.index(b.start_scene)
                if i + 1 < len(branches):
                    end_idx = scene_keys.index(branches[i + 1].start_scene)
                else:
                    end_idx = scene_keys.index(merge_cand) if merge_cand and merge_cand in scene_keys else len(scene_keys)

                raw_scenes: list[str] = []
                for scan_i in range(start_idx, end_idx):
                    sk = scene_keys[scan_i]
                    raw_scenes.append(sk)
                    sd = data.get(sk, {})
                    if isinstance(sd, dict):
                        g = str(sd.get('goto', '') or '').strip()
                        if g:
                            if g in tag_to_scene:
                                target_g = tag_to_scene[g]
                                if int(target_g) <= int(choice_sc):
                                    b.destination = target_g
                                    b.is_loop = True
                                    break
                                elif int(target_g) > max_start:
                                    b.destination = target_g
                                    break
                            else:
                                p_text = str(sd.get('print', {}).get('text', '') or '') if isinstance(sd.get('print'), dict) else ''
                                if 'もう一度' in p_text or '考え直して' in p_text:
                                    b.destination = choice_sc
                                    b.is_loop = True
                                    break

                if not b.destination:
                    if merge_cand in [str(s) for s in all_starts]:
                        enclosing_dest = None
                        for prev_sc, prev_branches in branch_groups.items():
                            if int(prev_sc) < int(choice_sc):
                                for pb in prev_branches:
                                    if pb.destination and int(pb.start_scene) <= int(choice_sc):
                                        enclosing_dest = pb.destination
                        b.destination = enclosing_dest if enclosing_dest else merge_cand
                    else:
                        b.destination = merge_cand

                b.scenes = [sc for sc in raw_scenes if has_story_content(data.get(sc))]
                if b.scenes:
                    branch_starts.setdefault(b.scenes[0], []).append(b)
                    branch_ends.setdefault(b.scenes[-1], []).append(b)
                    for sc in b.scenes:
                        scene_to_branch[sc] = b

            if merge_cand and merge_cand not in [str(s) for s in all_starts]:
                merge_scenes.add(merge_cand)

        transition_scenes: set[str] = set()
        for tgt in single_choice_targets:
            if tgt not in merge_scenes and tgt not in branch_starts:
                transition_scenes.add(tgt)

        return StoryBranchStructure(
            branch_groups=branch_groups,
            scene_to_branch=scene_to_branch,
            merge_scenes=merge_scenes,
            tag_to_scene=tag_to_scene,
            branch_starts=branch_starts,
            branch_ends=branch_ends,
            transition_scenes=transition_scenes,
        )

    @staticmethod
    def iter_script_nodes(data: dict[str, Any], lang_dict: dict[str, str] | None = None) -> Iterator[ScriptNode]:
        """대본(script) 모드 공용 장면 순회 제너레이터.

        txt 태그 렌더러(_format_script_mode)와 마크다운 렌더러(_format_script_mode_markdown)가
        동일한 순회 결과를 소비하도록, 헤더/합류 씬/분기 시작/전환 씬/장소/대사/연출(무비, 스틸)/선택지/분기 종료 노드를
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
        branch_leads_to_fmt = lang_dict.get('script_branch_leads_to', '[Scene {scene}]') if lang_dict else '[Scene {scene}]'
        branch_end_label = lang_dict.get('script_branch_end', '[End of Story]') if lang_dict else '[End of Story]'
        branch_label_fmt = (
            lang_dict.get('script_branch_label_fmt', "{dialogue_label} for {choice_label} #{idx}")
            if lang_dict else "{dialogue_label} for {choice_label} #{idx}"
        )

        structure = StoryFormatter.resolve_story_branches(data)
        merge_scenes = structure.merge_scenes
        tag_to_scene = structure.tag_to_scene
        branch_starts = structure.branch_starts
        branch_ends = structure.branch_ends
        transition_scenes = structure.transition_scenes

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
        active_branch_stack: list[StoryBranchInfo] = []

        for key in scene_keys:
            scene = data[key]
            if not isinstance(scene, dict):
                continue

            has_scene_content = (
                'print' in scene or 'choice' in scene or 'place' in scene or 'situation' in scene
                or 'movie' in scene or 'still' in scene
            )
            if key != '0' and not has_scene_content:
                continue

            # 합류 씬 헤더 (최상위 레벨)
            if key != '0' and key in merge_scenes and not active_branch_stack:
                yield ScriptNode(kind='merge', scene_key=key)

            # 분기 시작 노드
            if key in branch_starts:
                for b in branch_starts[key]:
                    active_branch_stack.append(b)
                    b.indent_level = len(active_branch_stack)
                    scene_range_str = f"Scene {b.scenes[0]}~{b.scenes[-1]}" if len(b.scenes) > 1 else f"Scene {key}"
                    if len(b.choice_indices) > 1:
                        indices_str = ", ".join(f"#{idx}" for idx in b.choice_indices)
                        branch_label_str = f"{branch_dialogue_label}: {choice_item_label} {indices_str}"
                        tag_str = ""
                    else:
                        branch_label_str = branch_label_fmt.format(
                            choice_label=choice_item_label,
                            idx=b.choice_idx,
                            dialogue_label=branch_dialogue_label,
                        )
                        tag_str = f" (Tag {b.tag})" if b.tag else ""
                    has_dialogue = True
                    yield ScriptNode(
                        kind='branch_start', scene_key=key, in_branch=True, indent_level=b.indent_level,
                        scene_range=scene_range_str, branch_label=branch_label_str, tag_suffix=tag_str
                    )

            curr_indent = len(active_branch_stack)
            in_branch = bool(active_branch_stack)

            # 전환 씬 헤더 (단일 선택지 직후 씬 등)
            if key in transition_scenes and key not in merge_scenes and key not in branch_starts:
                yield ScriptNode(kind='transition_scene', scene_key=key, in_branch=in_branch, indent_level=curr_indent)

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
                yield ScriptNode(kind='place', scene_key=key, in_branch=in_branch, indent_level=curr_indent, place=place_str)

            # 대사 (print)
            p_data = scene.get('print')
            if p_data and isinstance(p_data, dict):
                speaker = str(p_data.get('name', '') or '').strip()
                dialogue = str(p_data.get('text', '') or '').strip()

                if dialogue:
                    has_dialogue = True
                    yield ScriptNode(
                        kind='print', scene_key=key, in_branch=in_branch, indent_level=curr_indent,
                        speaker=speaker, lines=dialogue.splitlines()
                    )

            # 인게임 무비 (애니메이션 컷신)
            raw_movie = scene.get('movie')
            if raw_movie:
                movie_id = ""
                if isinstance(raw_movie, list) and raw_movie:
                    first = raw_movie[0]
                    if isinstance(first, list) and first:
                        movie_id = str(first[0]).strip()
                    elif isinstance(first, str):
                        movie_id = first.strip()
                elif isinstance(raw_movie, str):
                    movie_id = raw_movie.strip()

                if movie_id:
                    has_dialogue = True
                    yield ScriptNode(
                        kind='movie', scene_key=key, in_branch=in_branch, indent_level=curr_indent, movie_id=movie_id
                    )

            # 스틸컷 일러스트
            raw_still = scene.get('still')
            if raw_still:
                still_id = ""
                if isinstance(raw_still, list) and raw_still:
                    first = raw_still[0]
                    if isinstance(first, list) and first:
                        val = str(first[0]).strip()
                        if val.lower() not in ('end', 'none', ''):
                            still_id = val
                    elif isinstance(first, str):
                        val = first.strip()
                        if val.lower() not in ('end', 'none', ''):
                            still_id = val
                elif isinstance(raw_still, str) and raw_still.strip().lower() not in ('end', 'none', ''):
                    still_id = raw_still.strip()

                if still_id:
                    has_dialogue = True
                    yield ScriptNode(
                        kind='still', scene_key=key, in_branch=in_branch, indent_level=curr_indent, still_id=still_id
                    )

            # 선택지 (choice)
            choices = scene.get('choice')
            if choices and isinstance(choices, list) and len(choices) > 0:
                has_dialogue = True
                prepared_choices: list[ScriptChoice] = []
                if len(choices) == 1:
                    c = choices[0]
                    c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                    c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                    tgt = tag_to_scene.get(c_tag)
                    if not tgt:
                        c_idx = scene_keys.index(key)
                        if c_idx + 1 < len(scene_keys):
                            tgt = scene_keys[c_idx + 1]
                    prepared_choices.append(ScriptChoice(idx=1, text=c_text, tag=c_tag, target_scene=tgt))
                else:
                    bg = structure.branch_groups.get(key, [])
                    choice_target_map: dict[int, str] = {}
                    for b in bg:
                        for ci in b.choice_indices:
                            choice_target_map[ci] = b.start_scene
                    merge_target = bg[0].destination if bg else None
                    for idx, c in enumerate(choices, 1):
                        c_text = c.get('text', '') if isinstance(c, dict) else str(c)
                        c_tag = str(c.get('tag', '') or '').strip() if isinstance(c, dict) else ""
                        tgt = tag_to_scene.get(c_tag) or choice_target_map.get(idx) or merge_target
                        prepared_choices.append(ScriptChoice(idx=idx, text=c_text, tag=c_tag, target_scene=tgt))

                yield ScriptNode(
                    kind='choice', scene_key=key, in_branch=in_branch, indent_level=curr_indent, choices=prepared_choices
                )

            # 분기 씬 박스 마감 노드
            if key in branch_ends:
                for b in reversed(branch_ends[key]):
                    if b.is_loop:
                        label = f"← [Scene {b.destination}]"
                    elif b.destination:
                        label = branch_leads_to_fmt.format(scene=b.destination)
                    else:
                        label = branch_end_label
                    yield ScriptNode(
                        kind='branch_end', scene_key=key, in_branch=True, indent_level=b.indent_level, leads_to=label
                    )
                    if b in active_branch_stack:
                        active_branch_stack.remove(b)

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
        movie_label = lang_dict.get('script_movie_label', '애니메이션 컷신') if lang_dict else '애니메이션 컷신'
        still_label = lang_dict.get('script_still_label', '스틸컷 일러스트') if lang_dict else '스틸컷 일러스트'

        for node in StoryFormatter.iter_script_nodes(data, lang_dict):
            indent = ("│ " * node.indent_level) if node.indent_level > 0 else ""

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
                    (f"{indent}┌─ [ {node.scene_range} | {node.branch_label}{node.tag_suffix} ] ─┐\n", 'script_branch')
                )

            # 전환 씬 헤더 노드 (단일 선택지 직후 씬 등)
            elif node.kind == 'transition_scene':
                content_list.append((f"{indent}── ▶ [ Scene {node.scene_key} ] ──\n", 'script_transition'))

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

            # 애니메이션 컷신 노드
            elif node.kind == 'movie':
                content_list.append((f"{indent}[{movie_label}: {node.movie_id}]\n\n", 'script_movie'))

            # 스틸컷 일러스트 노드
            elif node.kind == 'still':
                content_list.append((f"{indent}[{still_label}: {node.still_id}]\n\n", 'script_still'))

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
                    content_list.append((f"{indent}\n" if node.in_branch else "\n", None))
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
                    content_list.append((f"{indent}\n" if node.in_branch else "\n", None))

            # 분기 씬 박스 마감 노드
            elif node.kind == 'branch_end':
                line_prefix = f"{indent}└── ▶ "
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
