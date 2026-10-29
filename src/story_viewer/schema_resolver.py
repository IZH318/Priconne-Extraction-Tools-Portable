"""Story Viewer 마스터 DB 난독화 역추적 및 스키마 매핑 모듈.

프린세스 커넥트! Re:Dive 최신 클라이언트에서 난독화(해시화)된 master.db의 테이블 및
컬럼 이름을 기준(Baseline) DB와의 시그니처 샘플링, 토큰 일치도, 행 데이터 분포 유사도를
통해 자동 역추적하고 역난독화 매핑(db_config.json) 생성/갱신.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from src.utils.task_pool import register_process_pool, unregister_process_pool

from .schema_cache import SchemaCacheManager

logger = logging.getLogger(__name__)

# 대상 테이블 및 컬럼 매핑

DEFAULT_COLUMN_DIFF_TOLERANCE: int = 5
DYNAMIC_FULL_CENSUS_LIMIT: int = 1500
NEIGHBOR_WINDOW_DISTANCE: int = 4
SMALL_TABLE_ROW_THRESHOLD: int = 5
FAST_TRACK_SCORE_THRESHOLD: float = 0.95


ROW_OVERLAP_RATIO: float = 0.65
TABLE_MATCH_RATIO: float = 0.60
COL_VALUE_MATCH_RATIO: float = 0.80
MIN_RESIDUAL_OVERLAP_RATIO: float = 0.15

WEIGHT_SAMPLE_MATCH: float = 0.80
WEIGHT_AVG_OVERLAP: float = 0.15
WEIGHT_COL_PROXIMITY: float = 0.05

COLUMN_MAPPINGS: dict[str, list[str]] = {
    "event_list_table": ["event_name_col_list", "event_group_id_col_list"],
    "event_details_table": ["event_info_col_details", "event_title_col_details", "event_id_col_details", "event_group_id_col_details"],
    "birthday_table": ["birthday_name_col", "birthday_adv_id_col"],
    "quest_table": ["quest_name_col", "quest_wavestart_col", "quest_waveend_col"],
    "story_detail_table": ["story_detail_id_col", "story_detail_title_col", "story_detail_sub_title_col"],
    "dear_story_detail_table": ["dear_story_detail_id_col", "dear_story_detail_title_col", "dear_story_detail_sub_title_col"],
    "tower_story_detail_table": ["tower_story_detail_id_col", "tower_story_detail_title_col", "tower_story_detail_sub_title_col"],
    "alchemy_story_detail_table": ["alchemy_story_detail_id_col", "alchemy_story_detail_title_col"],
    "sekai_top_data_table": [
        "sekai_top_data_id_col", "sekai_top_data_name_col", "sekai_top_data_boss_mode_col",
        "sekai_top_data_boss_time_from_col", "sekai_top_data_boss_hp_from_col"
    ],
    "sekai_top_story_data_table": [
        "sekai_top_story_data_id_col", "sekai_top_story_data_boss_time_from_col", "sekai_top_story_data_boss_time_to_col"
    ],
    "event_top_adv_table": [
        "event_top_adv_id_col", "event_top_adv_character_id_col", "event_top_adv_event_id_col"
    ],
    "unit_table": [
        "unit_id_col", "unit_name_col"
    ],
    "hatsune_boss_table": [
        "hatsune_boss_event_id_col", "hatsune_boss_quest_name_col", "hatsune_boss_wavestart_col", "hatsune_boss_waveend_col"
    ],
    "hatsune_special_battle_table": [
        "hatsune_special_battle_event_id_col", "hatsune_special_battle_mode_col", "hatsune_special_battle_mode_start_col", "hatsune_special_battle_mode_end_col"
    ],
    "legion_special_battle_table": [
        "legion_special_battle_mode_col", "legion_special_battle_mode_start_col", "legion_special_battle_mode_end_col"
    ],
    "byway_battle_quest_data_table": [
        "byway_battle_quest_data_quest_id_col", "byway_battle_quest_data_wavestart_col", "byway_battle_quest_data_waveend_col"
    ],
    "byway_quest_data_table": [
        "byway_quest_data_quest_id_col", "byway_quest_data_quest_name_col"
    ],
    "hatsune_scenario_boss_table": [
        "hatsune_scenario_boss_quest_name_col", "hatsune_scenario_boss_wavestart_col", "hatsune_scenario_boss_waveend_col"
    ],
    "hatsune_boss_v2_table": [
        "hatsune_boss_v2_quest_name_col", "hatsune_boss_v2_wavestart_col", "hatsune_boss_v2_waveend_col",
        "hatsune_boss_v2_boss_id_col", "hatsune_boss_v2_event_id_col", "hatsune_boss_v2_mode_col"
    ],
    "hatsune_sp_battle_v2_table": [
        "hatsune_sp_battle_v2_mode_col", "hatsune_sp_battle_v2_mode_start_col", "hatsune_sp_battle_v2_mode_end_col"
    ],
    "hatsune_ex_battle_table": [
        "hatsune_ex_battle_id_col"
    ],
    "event_cooking_minigame_table": [
        "event_cooking_minigame_id_col", "event_cooking_minigame_title_col"
    ],
    "event_cooking_reaction_table": [
        "event_cooking_reaction_id_col"
    ],
    "event_museum_minigame_table": [
        "event_museum_minigame_id_col", "event_museum_minigame_title_col", "event_museum_minigame_sub_title_col"
    ],
    "event_riddle_minigame_table": [
        "event_riddle_minigame_point_name_col", "event_riddle_minigame_title_col",
        "event_riddle_minigame_start_id_col", "event_riddle_minigame_end_id_col"
    ],
    "event_story_v2_table": [
        "event_story_v2_id_col", "event_story_v2_title_col", "event_story_v2_sub_title_col"
    ],
    "event_secret_minigame_table": [
        "event_secret_minigame_id_col", "event_secret_minigame_title_col"
    ],
    "event_collab_minigame_table": [
        "event_collab_minigame_id_col", "event_collab_minigame_title_col", "event_collab_minigame_sub_title_col"
    ],
    "event_vampire_minigame_table": [
        "event_vampire_minigame_id_col", "event_vampire_minigame_title_col"
    ],
    "event_crybaby_minigame_table": [
        "event_crybaby_minigame_id_col", "event_crybaby_minigame_title_col", "event_crybaby_minigame_sub_title_col"
    ],
    "event_summer_minigame_table": [
        "event_summer_minigame_id_col", "event_summer_minigame_title_col"
    ],
    "event_liberate_minigame_table": [
        "event_liberate_minigame_id_col", "event_liberate_minigame_title_col", "event_liberate_minigame_sub_title_col"
    ],
    "event_hatsune_dream_minigame_table": [
        "event_hatsune_dream_minigame_id_col", "event_hatsune_dream_minigame_title_col"
    ],
    "event_christmas_minigame_table": [
        "event_christmas_minigame_id_col", "event_christmas_minigame_title_col"
    ],
    "event_coaster_minigame_table": [
        "event_coaster_minigame_id_col", "event_coaster_minigame_title_col", "event_coaster_minigame_sub_title_col"
    ],
    "event_nebia_minigame_table": [
        "event_nebia_minigame_id_col", "event_nebia_minigame_title_col"
    ],
    "event_taiso_minigame_table": [
        "event_taiso_minigame_id_col", "event_taiso_minigame_title_col", "event_taiso_minigame_sub_title_col"
    ],
    "event_alces_minigame_table": [
        "event_alces_minigame_id_col", "event_alces_minigame_title_col", "event_alces_minigame_sub_title_col"
    ],
    "event_trip_minigame_table": [
        "event_trip_minigame_id_col", "event_trip_minigame_title_col"
    ],
    "event_house_minigame_table": [
        "event_house_minigame_id_col", "event_house_minigame_title_col"
    ],
    "event_diary_minigame_table": [
        "event_diary_minigame_id_col", "event_diary_minigame_title_col"
    ],
    "event_opening_adv_table": [
        "event_opening_adv_id_col", "event_opening_adv_title_col", "event_opening_adv_sub_title_col"
    ],
    "event_boss_battle_v3_table": [
        "event_boss_battle_v3_id_col", "event_boss_battle_v3_title_col"
    ],
    "event_remember_story_table": [
        "event_remember_story_id_col", "event_remember_story_title_col"
    ],
    "hatsune_present_table": [
        "hatsune_present_id_col", "hatsune_present_title_col"
    ],
    "hatsune_quest_table": [
        "hatsune_quest_id_col", "hatsune_quest_title_col"
    ],
    "hatsune_quiz_table": [
        "hatsune_quiz_point_name_col", "hatsune_quiz_title_col",
        "hatsune_quiz_start_id_col", "hatsune_quiz_end_id_col"
    ]
}

BASELINE_TABLES_LIST: list[str] = [
    "alchemy_story_detail",
    "hatsune_scenario_boss",
    "hatsune_boss_v2",
    "hatsune_sp_battle_v2",
    "hatsune_ex_battle",
    "event_cooking_minigame",
    "event_cooking_reaction",
    "event_museum_minigame",
    "event_story_v2",
    "event_secret_minigame",
    "event_collab_minigame",
    "event_vampire_minigame",
    "event_crybaby_minigame",
    "event_summer_minigame",
    "event_liberate_minigame",
    "event_hatsune_dream_minigame",
    "event_christmas_minigame",
    "event_coaster_minigame",
    "event_nebia_minigame",
    "event_taiso_minigame",
    "event_alces_minigame",
    "event_trip_minigame",
    "event_house_minigame",
    "event_diary_minigame",
    "event_opening_adv",
    "event_boss_battle_v3",
    "event_remember_story",
    "hatsune_present",
    "hatsune_quest",
    "hatsune_quiz"
]


def _get_default_baseline_path(info: dict[str, Any], src_dir: str) -> str:
    """서버 설정에서 기본 베이스라인 DB 파일의 절대 경로 반환."""
    b_dbs = info.get("baseline_dbs", {})
    if isinstance(b_dbs, dict) and "default" in b_dbs:
        b_fname = b_dbs["default"].get("db_path", "")
        if b_fname:
            return os.path.join(src_dir, b_fname)
    return os.path.join(src_dir, info.get("baseline_db_path", ""))


def escape_identifier(identifier: str) -> str:
    """SQLite 식별자(테이블 및 컬럼명) 안전 이스케이프 처리."""
    if not isinstance(identifier, str) or not identifier or '\x00' in identifier:
        raise ValueError(f"Invalid SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def extract_signature_samples(conn: sqlite3.Connection, table_name: str) -> tuple[int, list[frozenset[Any]], bool]:
    cursor = conn.cursor()
    escaped_tbl = escape_identifier(table_name)

    cursor.execute(f"PRAGMA table_info({escaped_tbl});")
    col_count = len(cursor.fetchall())

    cursor.execute(f"SELECT COUNT(*) FROM {escaped_tbl};")
    res = cursor.fetchone()
    total_rows = res[0] if res else 0

    is_small_table = total_rows <= SMALL_TABLE_ROW_THRESHOLD
    if total_rows <= 10:
        sample_size = total_rows
    elif total_rows <= 200:
        sample_size = max(10, min(total_rows, total_rows // 2))
    else:
        sample_size = 50

    cursor.execute(f"SELECT * FROM {escaped_tbl} ORDER BY rowid ASC LIMIT {sample_size};")
    rows = cursor.fetchall()

    min_tokens = 1 if is_small_table else 2
    signature_rows = []
    for r in rows:
        row_set = frozenset(str(val) for val in r if val is not None and str(val).strip() != "")
        if len(row_set) >= min_tokens:
            signature_rows.append(row_set)

    return col_count, signature_rows, is_small_table


def calculate_match_score(
    conn: sqlite3.Connection,
    candidate_tbl: str,
    base_col_count: int,
    signature_rows: list[Any],
    col_tolerance: int,
    is_small_table: bool
) -> float:
    if not signature_rows:
        return 0.0

    cursor = conn.cursor()
    escaped_tbl = escape_identifier(candidate_tbl)

    cursor.execute(f"PRAGMA table_info({escaped_tbl});")
    cand_col_count = len(cursor.fetchall())
    col_diff = abs(cand_col_count - base_col_count)
    if col_diff > col_tolerance:
        return -1.0

    cursor.execute(f"SELECT COUNT(*) FROM {escaped_tbl};")
    res = cursor.fetchone()
    cand_total = res[0] if res else 0

    inspect_limit = cand_total if cand_total <= DYNAMIC_FULL_CENSUS_LIMIT else max(len(signature_rows) * 5, 500)
    cursor.execute(f"SELECT * FROM {escaped_tbl} ORDER BY rowid ASC LIMIT {inspect_limit};")
    cand_rows = cursor.fetchall()
    if not cand_rows:
        return 0.0

    cand_row_sets = [frozenset(str(val) for val in r if val is not None and str(val).strip() != "") for r in cand_rows]

    matched_count = 0
    total_overlap = 0.0

    for sig_set in signature_rows:
        best_overlap = 0.0
        for c_set in cand_row_sets:
            if not sig_set:
                continue
            overlap = len(sig_set & c_set) / len(sig_set)
            if overlap > best_overlap:
                best_overlap = overlap
                if best_overlap >= 1.0:
                    break

        req_overlap = ROW_OVERLAP_RATIO if not is_small_table else max(0.5, ROW_OVERLAP_RATIO)
        if best_overlap >= req_overlap:
            matched_count += 1
            total_overlap += best_overlap

    sample_match_ratio = matched_count / len(signature_rows)
    avg_overlap = (total_overlap / matched_count) if matched_count > 0 else 0.0
    col_proximity = 1.0 - (col_diff / (col_tolerance + 1))

    return (sample_match_ratio * WEIGHT_SAMPLE_MATCH) + (avg_overlap * WEIGHT_AVG_OVERLAP) + (col_proximity * WEIGHT_COL_PROXIMITY)


def resolve_column_mapping(
    ref_conn: sqlite3.Connection,
    ref_tbl: str,
    cand_conn: sqlite3.Connection,
    cand_tbl: str,
    original_base_types: dict[str, Any] | None = None
) -> tuple[list[str], dict[str, str]]:
    try:
        ref_cur = ref_conn.cursor()
        cand_cur = cand_conn.cursor()

        ref_esc = escape_identifier(ref_tbl)
        cand_esc = escape_identifier(cand_tbl)

        ref_cur.execute(f"PRAGMA table_info({ref_esc});")
        ref_info = ref_cur.fetchall()
        ref_col_names = [r[1] for r in ref_info]
        ref_types = {r[1]: (r[2].upper().strip() if r[2] else "NONE") for r in ref_info}

        cand_cur.execute(f"PRAGMA table_info({cand_esc});")
        cand_info = cand_cur.fetchall()
        cand_col_names = [r[1] for r in cand_info]
        cand_types = {r[1]: (r[2].upper().strip() if r[2] else "NONE") for r in cand_info}

        ref_cur.execute(f"SELECT COUNT(*) FROM {ref_esc};")
        res = ref_cur.fetchone()
        total_ref_rows = res[0] if res else 0

        dynamic_limit = total_ref_rows if total_ref_rows <= DYNAMIC_FULL_CENSUS_LIMIT else 2000
        ref_cur.execute(f"SELECT * FROM {ref_esc} ORDER BY rowid ASC LIMIT {dynamic_limit};")
        ref_rows = ref_cur.fetchall()

        cand_cur.execute(f"SELECT * FROM {cand_esc} ORDER BY rowid ASC LIMIT {max(dynamic_limit * 2, 500)};")
        cand_rows = cand_cur.fetchall()

        if not ref_rows or not cand_rows:
            return ["  (No sufficient rows)"], {}

        cand_row_sets = [frozenset(str(v) for v in r if v is not None and str(v).strip() != "") for r in cand_rows]

        aligned_ref_rows = []
        aligned_cand_rows = []

        for r_row in ref_rows:
            r_set = frozenset(str(v) for v in r_row if v is not None and str(v).strip() != "")
            if not r_set:
                continue
            best_c_idx = -1
            best_c_overlap = 0.0
            for c_idx, c_set in enumerate(cand_row_sets):
                overlap = len(r_set & c_set) / len(r_set)
                if overlap > best_c_overlap:
                    best_c_overlap = overlap
                    best_c_idx = c_idx

            if best_c_overlap >= ROW_OVERLAP_RATIO and best_c_idx != -1:
                aligned_ref_rows.append(r_row)
                aligned_cand_rows.append(cand_rows[best_c_idx])

        total_aligned = len(aligned_ref_rows)
        if total_aligned < 2:
            return ["  (Insufficient aligned rows)"], {}

        ref_vectors = {r_name: [str(r[idx]) if r[idx] is not None else "" for r in aligned_ref_rows] for idx, r_name in enumerate(ref_col_names)}
        cand_vectors = {c_name: [str(r[idx]) if r[idx] is not None else "" for r in aligned_cand_rows] for idx, c_name in enumerate(cand_col_names)}

        ref_cardinality = {r: len(set(ref_vectors[r])) for r in ref_col_names}
        cand_cardinality = {c: len(set(cand_vectors[c])) for c in cand_col_names}

        pair_evaluations = []
        for c_name, c_vec in cand_vectors.items():
            c_type = cand_types.get(c_name, "NONE")
            c_card = cand_cardinality[c_name]

            for r_name, r_vec in ref_vectors.items():
                r_type = ref_types.get(r_name, "NONE")
                orig_type = original_base_types.get(r_name, r_type) if original_base_types else r_type

                matches = sum(1 for v1, v2 in zip(c_vec, r_vec, strict=False) if v1 == v2)
                value_sim = matches / total_aligned

                r_card = ref_cardinality[r_name]
                card_sim = min(c_card, r_card) / max(c_card, r_card) if max(c_card, r_card) > 0 else 1.0

                type_compat = (
                    (c_type == orig_type) or
                    (c_type in ("INT", "INTEGER") and orig_type in ("INT", "INTEGER")) or
                    (c_type in ("TEXT", "VARCHAR", "CHAR") and orig_type in ("TEXT", "VARCHAR", "CHAR")) or
                    (c_type == "NONE" and orig_type == "NONE")
                )

                comp_score = (value_sim * 0.85) + (card_sim * 0.10) + (0.05 if type_compat else 0.0)
                pair_evaluations.append({
                    "cand": c_name, "ref": r_name, "value_sim": value_sim,
                    "card_sim": card_sim, "comp_score": comp_score
                })

        pair_evaluations.sort(key=lambda x: (x["comp_score"], x["value_sim"], x["card_sim"]), reverse=True)

        claimed_cands = set()
        claimed_refs = set()
        matched_assignments = {}

        for pair in pair_evaluations:
            if pair["cand"] in claimed_cands or pair["ref"] in claimed_refs:
                continue
            if pair["value_sim"] >= COL_VALUE_MATCH_RATIO:
                claimed_cands.add(pair["cand"])
                claimed_refs.add(pair["ref"])
                matched_assignments[pair["cand"]] = pair

        for pair in pair_evaluations:
            if pair["cand"] in claimed_cands or pair["ref"] in claimed_refs:
                continue
            if pair["value_sim"] >= MIN_RESIDUAL_OVERLAP_RATIO:
                claimed_cands.add(pair["cand"])
                claimed_refs.add(pair["ref"])
                matched_assignments[pair["cand"]] = pair

        ref_col_index = {name: idx for idx, name in enumerate(ref_col_names)}
        cand_col_index = {name: idx for idx, name in enumerate(cand_col_names)}

        vector_groups: dict[Any, Any] = {}
        for c_name, pair in matched_assignments.items():
            v_tuple = tuple(cand_vectors[c_name])
            if v_tuple not in vector_groups:
                vector_groups[v_tuple] = []
            vector_groups[v_tuple].append((c_name, pair))

        new_cand_to_human_map = {}
        mapping_lines = []

        for group in vector_groups.values():
            if len(group) == 1:
                c_name, pair = group[0]
                new_cand_to_human_map[c_name] = pair["ref"]
                mapping_lines.append(f"  {c_name} ===> {pair['ref']}")
            else:
                cand_pool = [item[0] for item in group]
                ref_pool = [item[1]["ref"] for item in group]

                anchor_pairs = [
                    (p["cand"], p["ref"]) for p in matched_assignments.values()
                    if p["cand"] not in cand_pool and p["ref"] not in ref_pool
                ]

                affinity_scores = []
                for c_cand in cand_pool:
                    c_idx = cand_col_index[c_cand]
                    for r_ref in ref_pool:
                        r_idx = ref_col_index.get(r_ref, 0)
                        score = 0.0
                        for c_anc, r_anc in anchor_pairs:
                            anc_c_idx = cand_col_index[c_anc]
                            anc_r_idx = ref_col_index.get(r_anc, 0)
                            dist_cand = abs(c_idx - anc_c_idx)
                            dist_ref = abs(r_idx - anc_r_idx)
                            if dist_cand <= NEIGHBOR_WINDOW_DISTANCE and dist_ref <= NEIGHBOR_WINDOW_DISTANCE:
                                dist_sum = dist_cand + dist_ref
                                if dist_sum == 0:
                                    dist_sum = 1
                                score += (1.0 / (abs(dist_cand - dist_ref) + 1.0)) + (1.0 / dist_sum)

                        affinity_scores.append((score, c_cand, r_ref))

                affinity_scores.sort(key=lambda x: x[0], reverse=True)
                assigned_cands = set()
                assigned_refs = set()

                for score, c_cand, r_ref in affinity_scores:
                    if c_cand not in assigned_cands and r_ref not in assigned_refs and score > 0.0:
                        assigned_cands.add(c_cand)
                        assigned_refs.add(r_ref)
                        new_cand_to_human_map[c_cand] = r_ref
                        mapping_lines.append(f"  {c_cand} ===> {r_ref} (Spatial Neighbor-Affinity)")

                rem_c = [c for c in cand_pool if c not in assigned_cands]
                rem_r = [r for r in ref_pool if r not in assigned_refs]
                if rem_c and rem_r:
                    rem_c.sort(key=lambda x: cand_col_index.get(x, 0))
                    rem_r.sort(key=lambda x: ref_col_index.get(x, 0))
                    for c, r in zip(rem_c, rem_r, strict=False):
                        new_cand_to_human_map[c] = r
                        mapping_lines.append(f"  {c} ===> {r} (Ordinal Fallback)")

        return mapping_lines, new_cand_to_human_map

    except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OSError) as e:
        return [f"  (Failed to resolve column mapping: {e!s})"], {}


def resolve_single_table_worker(args: tuple[Any, ...]) -> tuple[Any, ...]:
    """단일 테이블 역난독화 워커.

    Args:
        args: (server_key, table_key, base_db_path, target_db_path, base_table_name, target_tables_with_col)
    Returns:
        (server_key, table_key, base_table_name, best_table, human_to_hash_map)
    """
    server_key, table_key, base_db_path, target_db_path, base_table_name, target_tables_with_col = args
    if not base_table_name:
        return server_key, table_key, base_table_name, base_table_name, {}

    if base_db_path == target_db_path:
        return server_key, table_key, base_table_name, base_table_name, {}

    if not os.path.exists(base_db_path) or not os.path.exists(target_db_path):
        return server_key, table_key, base_table_name, None, {}

    try:
        with contextlib.closing(sqlite3.connect(f"file:{base_db_path}?mode=ro", uri=True)) as base_conn, \
             contextlib.closing(sqlite3.connect(f"file:{target_db_path}?mode=ro", uri=True)) as target_conn:

            base_cur = base_conn.cursor()
            base_cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (base_table_name,))
            if not base_cur.fetchone():
                return server_key, table_key, base_table_name, None, {}

            base_col_count, base_sigs, is_small = extract_signature_samples(base_conn, base_table_name)
            base_cur.execute(f"PRAGMA table_info({escape_identifier(base_table_name)});")
            orig_base_types = {r[1]: (r[2].upper().strip() if r[2] else "NONE") for r in base_cur.fetchall()}

            # 현재 서버의 대상 테이블 목록
            filtered_candidates = [
                t for t, cnt in target_tables_with_col
                if abs(cnt - base_col_count) <= DEFAULT_COLUMN_DIFF_TOLERANCE
            ]

            best_table = None
            best_score = -1.0

            if base_table_name in filtered_candidates:
                fast_score = calculate_match_score(
                    target_conn, base_table_name, base_col_count, base_sigs, DEFAULT_COLUMN_DIFF_TOLERANCE, is_small
                )
                if fast_score >= FAST_TRACK_SCORE_THRESHOLD:
                    best_table = base_table_name
                    best_score = fast_score

            # 역난독화 컬럼 매핑을 검색하여 매칭 (신뢰도 100% 매칭)
            if not best_table:
                for cand in filtered_candidates:
                    score = calculate_match_score(
                        target_conn, cand, base_col_count, base_sigs, DEFAULT_COLUMN_DIFF_TOLERANCE, is_small
                    )
                    if score >= TABLE_MATCH_RATIO and score > best_score:
                        best_score = score
                        best_table = cand

            if not best_table:
                return server_key, table_key, base_table_name, None, {}

            _, cand_to_human_map = resolve_column_mapping(
                ref_conn=base_conn,
                ref_tbl=base_table_name,
                cand_conn=target_conn,
                cand_tbl=best_table,
                original_base_types=orig_base_types
            )

            human_to_hash_map = {human: cand_hash for cand_hash, human in cand_to_human_map.items()}
            return server_key, table_key, base_table_name, best_table, human_to_hash_map

    except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OSError) as e:
        logger.exception("Worker failed for %s.%s (%s): %s", server_key, table_key, base_table_name, e)
        return server_key, table_key, base_table_name, None, {}


def _iter_resolved_tables(tasks: list[tuple[Any, ...]]) -> Iterator[tuple[Any, ...]]:
    """테이블 역난독화 태스크를 프로세스 풀로 실행하고 결과를 순차 산출한다.

    프로세스 풀 생성/실행이 불가능한 환경에서는 동일한 태스크를 현재 프로세스에서
    직렬 실행하여 누락 없이 같은 결과 집합을 만든다.

    Args:
        tasks: resolve_single_table_worker 인자 튜플 목록.

    Yields:
        tuple: (server_key, table_key, best_table, column_map) 결과 튜플.
    """
    try:
        max_workers = min(len(tasks), (os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()) or os.cpu_count() or 4)
        pool = register_process_pool(ProcessPoolExecutor(max_workers=max_workers))
        try:
            futures = [pool.submit(resolve_single_table_worker, task) for task in tasks]
            for future in as_completed(futures):
                try:
                    res = future.result(timeout=300)
                    yield res[0], res[1], res[3], res[4]
                except TimeoutError as exc:
                    logger.warning("Schema resolution future timed out: %s", exc)
                    with contextlib.suppress(RuntimeError, OSError):
                        future.cancel()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Schema resolution future failed: %s", exc)
        finally:
            unregister_process_pool(pool)
            pool.shutdown(wait=False, cancel_futures=True)
    except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as e:
        logger.warning("ProcessPoolExecutor parallel resolution failed (%s); retrying sequentially", e)
        for task in tasks:
            try:
                res = resolve_single_table_worker(task)
                yield res[0], res[1], res[3], res[4]
            except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
                logger.exception("Sequential schema resolution failed: %s", exc)


def resolve_all_servers_parallel(
    server_db_info: dict[str, Any],
    root_dir: str,
    src_dir: str,
    progress_callback: Callable[..., Any] | None = None,
    force_servers: set[str] | None = None,
) -> None:
    """모든 서버 DB 설정(server_db_info)의 멀티프로세스 병렬 역난독화 실행.

    Args:
        server_db_info: 서버별 설정 딕셔너리 (JP, KR 등, in-place 수정).
        root_dir: 프로젝트 루트 경로.
        src_dir: src 폴더 경로.
        progress_callback: 각 테이블 분석 완료 시 (server_key, table_key)를 인자로 호출할 콜백 함수.
        force_servers: 캐시를 무시하고 강제로 처음부터 재분석할 서버 키 집합(선택 사항).
    """
    cache = SchemaCacheManager.load(src_dir)
    if force_servers:
        for s in force_servers:
            cache.invalidate_server(s)

    for server_key, info in server_db_info.items():
        if not isinstance(info, dict) or 'db_path' not in info:
            continue
        db_path = os.path.join(root_dir, info['db_path'])
        if os.path.exists(db_path) and cache.is_server_signature_changed(server_key, db_path):
            cache.invalidate_server(server_key)

    stale_servers = cache.stale_servers
    cache_applied = 0
    all_tasks = []
    task_meta: dict[tuple[str, str], tuple[str, str, str]] = {}

    for server_key, info in server_db_info.items():
        if not isinstance(info, dict) or 'db_path' not in info:
            continue

        is_stale = server_key in stale_servers
        event_list_table = info.get("event_list_table", "")
        # 이미 정규화 캐시가 존재하고 버전/DB가 변경되지 않았다면 즉시 반환
        if event_list_table.startswith("v1_") and not is_stale:
            continue

        if is_stale:
            # 버전 변경/DB 업데이트로 재분석해야 하는 서버는 기존 메모리 v1_ 해시를 기본 설정값으로 복원
            try:
                from .controller import _load_db_config
                default_all = _load_db_config()
                if server_key in default_all:
                    info.clear()
                    info.update(default_all[server_key])
            except Exception as e:
                logger.debug("Failed to reset server_db_info to baseline for %s: %s", server_key, e)

        db_path = os.path.join(root_dir, info['db_path'])
        baseline_path = _get_default_baseline_path(info, src_dir)

        if not os.path.exists(baseline_path) or not os.path.exists(db_path):
            continue

        # 주 테이블 역난독화 태스크 등록
        table_keys = [
            ("event_list_table", info.get("event_list_table", ""), baseline_path),
            ("event_details_table", info.get("event_details_table", ""), baseline_path),
            ("birthday_table", info.get("birthday_table", ""), baseline_path),
            ("quest_table", info.get("quest_table", ""), baseline_path),
            ("story_detail_table", info.get("story_detail_table", ""), baseline_path),
            ("dear_story_detail_table", info.get("dear_story_detail_table", ""), baseline_path),
            ("tower_story_detail_table", info.get("tower_story_detail_table", ""), baseline_path),
            ("sekai_top_data_table", info.get("sekai_top_data_table", ""), baseline_path),
            ("sekai_top_story_data_table", info.get("sekai_top_story_data_table", ""), baseline_path),
            ("event_top_adv_table", info.get("event_top_adv_table", ""), baseline_path),
            ("unit_table", info.get("unit_table", ""), baseline_path),
            ("hatsune_boss_table", info.get("hatsune_boss_table", ""), baseline_path),
            ("hatsune_special_battle_table", info.get("hatsune_special_battle_table", ""), baseline_path),
            ("legion_special_battle_table", info.get("legion_special_battle_table", ""), baseline_path),
            ("byway_battle_quest_data_table", info.get("byway_battle_quest_data_table", ""), baseline_path),
            ("byway_quest_data_table", info.get("byway_quest_data_table", ""), baseline_path),
        ]

        # 베이스라인(baseline_dbs) 추가 테이블 (alchemy_story_detail 등 미니게임/부가 테이블)
        baseline_dbs = info.get("baseline_dbs", {})
        for tbl_prefix in BASELINE_TABLES_LIST:
            tbl_k = f"{tbl_prefix}_table"
            tbl_v = info.get(tbl_k, "")
            if tbl_v:
                b_key = info.get(f"{tbl_prefix}_baseline") or "default"
                b_info = baseline_dbs.get(b_key, {})
                b_filename = b_info.get("db_path", f"master_{server_key.lower()}_{b_key}.db")
                b_tbl_path = os.path.join(src_dir, b_filename)
                table_keys.append((tbl_k, tbl_v, b_tbl_path))

        # 캐시 적중 항목은 즉시 적용하고, 미적중 항목만 실제 계산 대상으로 남긴다.
        pending_keys: list[tuple[str, str, str]] = []
        for t_key, tbl_name, b_path in table_keys:
            if not (tbl_name and os.path.exists(b_path) and b_path != db_path):
                continue
            cached = None if is_stale else cache.lookup(server_key, t_key, tbl_name, b_path, db_path)
            if cached is not None:
                if cached.resolved:
                    info[t_key] = cached.resolved
                    for col_key, (orig_value, new_value) in cached.columns.items():
                        if info.get(col_key) == orig_value:
                            info[col_key] = new_value
                    cache_applied += 1
                continue
            pending_keys.append((t_key, tbl_name, b_path))

        if not pending_keys:
            continue

        # 실제 계산이 필요한 경우에만 대상 DB의 테이블/컬럼 목록을 열거한다.
        target_tables_with_col = []
        try:
            with contextlib.closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                all_tables = [r[0] for r in cur.fetchall()]
                for t in all_tables:
                    cur.execute(f"PRAGMA table_info({escape_identifier(t)});")
                    target_tables_with_col.append((t, len(cur.fetchall())))
        except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, OSError) as e:
            logger.exception("Failed to inspect tables in %s: %s", db_path, e)
            continue

        for t_key, tbl_name, b_path in pending_keys:
            all_tasks.append((server_key, t_key, b_path, db_path, tbl_name, target_tables_with_col))
            task_meta[(server_key, t_key)] = (tbl_name, b_path, db_path)

    if cache_applied:
        logger.info("Schema cache applied: %d table mapping(s)", cache_applied)

    if not all_tasks:
        cache.save()
        return

    resolved_results: list[tuple[Any, ...]] = []
    try:
        for s_key, t_key, best_tbl, col_map in _iter_resolved_tables(all_tasks):
            if progress_callback:
                progress_callback(s_key, t_key)
            resolved_results.append((s_key, t_key, best_tbl, col_map))
            meta = task_meta.get((s_key, t_key))
            if meta is not None:
                # 무매칭(best_tbl 없음)도 캐시해 동일 탐색을 반복하지 않는다.
                # 컬럼 매핑도 함께 저장해야 웜 스타트에서 동일한 쿼리가 성립한다.
                column_diffs: dict[str, tuple[str, str]] = {}
                s_info = server_db_info.get(s_key)
                if best_tbl and isinstance(s_info, dict) and isinstance(col_map, dict):
                    for col_key in COLUMN_MAPPINGS.get(t_key, []):
                        cur_col_value = s_info.get(col_key)
                        resolved_col = col_map.get(cur_col_value) if isinstance(cur_col_value, str) else None
                        if isinstance(cur_col_value, str) and isinstance(resolved_col, str) and resolved_col != cur_col_value:
                            column_diffs[col_key] = (cur_col_value, resolved_col)
                cache.record(
                    s_key,
                    t_key,
                    meta[0],
                    meta[1],
                    meta[2],
                    str(best_tbl) if best_tbl else "",
                    column_diffs,
                )
    finally:
        cache.save()

    # 모든 작업 완료 후 캐시에 일괄 반영
    for s_key, t_key, best_tbl, col_map in resolved_results:
        if best_tbl and s_key in server_db_info:
            s_info = server_db_info[s_key]
            s_info[t_key] = best_tbl

            target_col_keys = COLUMN_MAPPINGS.get(t_key, [])
            for col_k in target_col_keys:
                orig_col_val = s_info.get(col_k)
                if orig_col_val and orig_col_val in col_map:
                    s_info[col_k] = col_map[orig_col_val]

    logger.info("Successfully executed schema resolution across all servers.")
