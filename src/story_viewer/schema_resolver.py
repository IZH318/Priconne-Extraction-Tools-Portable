import os
import re
import sqlite3
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any, Optional

# ==============================================================================
# schema_lineage_v1.2 휴리스틱 및 역난독화 엔진 (extract_event_stories.py 기반)
# ==============================================================================

SUPPORTED_EXTENSIONS: Tuple[str, ...] = (".db", ".sqlite", ".sqlite3")
SQLITE_READONLY_URI_MODE: str = "?mode=ro"

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


def escape_identifier(identifier: str) -> str:
    """SQLite 식별자(테이블 및 컬럼명)를 안전하게 이스케이프합니다."""
    return '"' + identifier.replace('"', '""') + '"'


def natural_sort_key(s: str) -> List[Any]:
    """버전명이나 숫자가 포함된 문자열을 올바른 순서대로 정렬합니다."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def extract_signature_samples(conn: sqlite3.Connection, table_name: str) -> Tuple[int, List[frozenset], bool]:
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
    signature_rows: list,
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
    original_base_types: dict = None
) -> Tuple[List[str], Dict[str, str]]:
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

                matches = sum(1 for v1, v2 in zip(c_vec, r_vec) if v1 == v2)
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

        vector_groups = {}
        for c_name, pair in matched_assignments.items():
            v_tuple = tuple(cand_vectors[c_name])
            if v_tuple not in vector_groups:
                vector_groups[v_tuple] = []
            vector_groups[v_tuple].append((c_name, pair))

        new_cand_to_human_map = {}
        mapping_lines = []

        for v_tuple, group in vector_groups.items():
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
                                score += (1.0 / (abs(dist_cand - dist_ref) + 1.0)) + (1.0 / dist_sum)

                        affinity_scores.append((score, c_cand, r_ref))

                affinity_scores.sort(key=lambda x: x[0], reverse=True)
                assigned_cands = set()
                assigned_refs = set()

                for score, c_cand, r_ref in affinity_scores:
                    if c_cand not in assigned_cands and r_ref not in assigned_refs:
                        if score > 0.0:
                            assigned_cands.add(c_cand)
                            assigned_refs.add(r_ref)
                            new_cand_to_human_map[c_cand] = r_ref
                            mapping_lines.append(f"  {c_cand} ===> {r_ref} (Spatial Neighbor-Affinity)")

                rem_c = [c for c in cand_pool if c not in assigned_cands]
                rem_r = [r for r in ref_pool if r not in assigned_refs]
                if rem_c and rem_r:
                    rem_c.sort(key=lambda x: cand_col_index.get(x, 0))
                    rem_r.sort(key=lambda x: ref_col_index.get(x, 0))
                    for c, r in zip(rem_c, rem_r):
                        new_cand_to_human_map[c] = r
                        mapping_lines.append(f"  {c} ===> {r} (Ordinal Fallback)")

        return mapping_lines, new_cand_to_human_map

    except Exception as e:
        return [f"  (Failed to resolve column mapping: {str(e)})"], {}


class StoryDataExtractor:
    def __init__(self, baseline_db_path: str, latest_db_path: str):
        self.base_db = os.path.abspath(baseline_db_path)
        self.target_db = self._resolve_target_db(latest_db_path)
        self._table_cache: Dict[str, Tuple[str, Dict[str, str]]] = {}

    def _resolve_target_db(self, path: str) -> str:
        if os.path.isfile(path):
            return os.path.abspath(path)

        if os.path.isdir(path):
            candidates = []
            for root_dir, _, files in os.walk(path):
                for f in files:
                    if f.lower().endswith(SUPPORTED_EXTENSIONS):
                        candidates.append({
                            "path": os.path.join(root_dir, f),
                            "folder": os.path.basename(root_dir),
                            "filename": f
                        })

            if not candidates:
                raise FileNotFoundError(f"No SQLite DB files found in the directory: {path}")

            candidates.sort(key=lambda x: (natural_sort_key(x["folder"]), natural_sort_key(x["filename"])))
            return os.path.abspath(candidates[-1]["path"])

        raise FileNotFoundError(f"Not a valid DB file or directory: {path}")

    def _get_ro_connection(self, db_path: str) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{db_path}{SQLITE_READONLY_URI_MODE}", uri=True)

    def _find_and_deobfuscate_table(self, base_table_name: str) -> Tuple[str, Dict[str, str]]:
        if base_table_name in self._table_cache:
            return self._table_cache[base_table_name]

        with self._get_ro_connection(self.base_db) as base_conn, \
             self._get_ro_connection(self.target_db) as target_conn:

            base_col_count, base_sigs, is_small = extract_signature_samples(base_conn, base_table_name)
            base_cur = base_conn.cursor()
            base_cur.execute(f"PRAGMA table_info({escape_identifier(base_table_name)});")
            orig_base_types = {r[1]: (r[2].upper().strip() if r[2] else "NONE") for r in base_cur.fetchall()}

            target_cur = target_conn.cursor()
            target_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            cand_tables = [r[0] for r in target_cur.fetchall()]

            best_table = None
            best_score = -1.0

            if base_table_name in cand_tables:
                fast_score = calculate_match_score(
                    target_conn, base_table_name, base_col_count, base_sigs, DEFAULT_COLUMN_DIFF_TOLERANCE, is_small
                )
                if fast_score >= FAST_TRACK_SCORE_THRESHOLD:
                    best_table = base_table_name
                    best_score = fast_score

            if not best_table:
                for cand in cand_tables:
                    score = calculate_match_score(
                        target_conn, cand, base_col_count, base_sigs, DEFAULT_COLUMN_DIFF_TOLERANCE, is_small
                    )
                    if score >= TABLE_MATCH_RATIO and score > best_score:
                        best_score = score
                        best_table = cand

            if not best_table:
                raise RuntimeError(f"Could not find a matching obfuscated table for '{base_table_name}' in the latest DB.")

            _, cand_to_human_map = resolve_column_mapping(
                ref_conn=base_conn,
                ref_tbl=base_table_name,
                cand_conn=target_conn,
                cand_tbl=best_table,
                original_base_types=orig_base_types
            )

            human_to_hash_map = {human: cand_hash for cand_hash, human in cand_to_human_map.items()}
            self._table_cache[base_table_name] = (best_table, human_to_hash_map)
            return best_table, human_to_hash_map


def resolve_single_table_worker(args: tuple) -> tuple:
    """단일 테이블에 대해 역난독화 매핑을 수행하는 최상위 독립 워커 함수입니다.
    
    Args:
        args: (server_key, table_key, base_db_path, target_db_path, base_table_name, target_tables_with_col)
    Returns:
        (server_key, table_key, base_table_name, best_table, human_to_hash_map)
    """
    server_key, table_key, base_db_path, target_db_path, base_table_name, target_tables_with_col = args
    if not base_table_name or base_table_name.startswith("v1_"):
        return server_key, table_key, base_table_name, base_table_name, {}

    if not os.path.exists(base_db_path) or not os.path.exists(target_db_path):
        return server_key, table_key, base_table_name, None, {}

    try:
        with sqlite3.connect(f"file:{base_db_path}?mode=ro", uri=True) as base_conn, \
             sqlite3.connect(f"file:{target_db_path}?mode=ro", uri=True) as target_conn:

            base_col_count, base_sigs, is_small = extract_signature_samples(base_conn, base_table_name)
            base_cur = base_conn.cursor()
            base_cur.execute(f"PRAGMA table_info({escape_identifier(base_table_name)});")
            orig_base_types = {r[1]: (r[2].upper().strip() if r[2] else "NONE") for r in base_cur.fetchall()}

            # 허용 오차 범위 내의 후보 테이블 필터링
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

            # 조기 탈출 없이 모든 후보를 전수 검사하여 최댓값 산출 (기존 로직 100% 유지)
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

    except Exception as e:
        logging.error(f"Worker failed for {server_key}.{table_key} ({base_table_name}): {e}")
        return server_key, table_key, base_table_name, None, {}


def resolve_all_servers_parallel(
    server_db_info: dict, 
    root_dir: str, 
    src_dir: str, 
    progress_callback: Optional[callable] = None
) -> None:
    """모든 서버의 DB 설정(server_db_info)을 멀티프로세스 병렬 풀을 활용하여 고속으로 역난독화합니다.

    Args:
        server_db_info: 서버별 설정 딕셔너리 (JP, KR 등). 제자리(in-place)에서 수정됩니다.
        root_dir: 프로젝트 루트 경로.
        src_dir: src 폴더 경로.
        progress_callback: 각 테이블 분석 완료 시 (server_key, table_key)를 인자로 호출할 콜백 함수.
    """
    all_tasks = []
    
    for server_key, info in server_db_info.items():
        if not isinstance(info, dict) or 'db_path' not in info:
            continue
            
        event_list_table = info.get("event_list_table", "")
        # 이미 난독화 해시로 시작한다면 완료된 것으로 간주
        if event_list_table.startswith("v1_"):
            continue

        db_path = os.path.join(root_dir, info['db_path'])
        baseline_path = os.path.join(src_dir, info.get('baseline_db_path', ''))
        
        if not os.path.exists(baseline_path) or not os.path.exists(db_path):
            continue

        # 타겟 DB의 모든 테이블 및 컬럼 수 1회 일괄 인덱싱 (PRAGMA 중복 호출 방지)
        target_tables_with_col = []
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                all_tables = [r[0] for r in cur.fetchall()]
                for t in all_tables:
                    cur.execute(f"PRAGMA table_info({escape_identifier(t)});")
                    target_tables_with_col.append((t, len(cur.fetchall())))
        except Exception as e:
            logging.error(f"Failed to inspect tables in {db_path}: {e}")
            continue

        # 각 테이블 정의 태스크 등록
        table_keys = [
            ("event_list_table", info.get("event_list_table", ""), baseline_path),
            ("event_details_table", info.get("event_details_table", ""), baseline_path),
            ("birthday_table", info.get("birthday_table", ""), baseline_path),
            ("quest_table", info.get("quest_table", ""), baseline_path),
            ("story_detail_table", info.get("story_detail_table", ""), baseline_path),
            ("dear_story_detail_table", info.get("dear_story_detail_table", ""), baseline_path),
            ("tower_story_detail_table", info.get("tower_story_detail_table", ""), baseline_path),
        ]
        
        # 알케스 연금당 숏드라마 스토리 상세 테이블
        alchemy_table = info.get("alchemy_story_detail_table", "")
        if alchemy_table:
            alchemy_base_key = info.get("alchemy_story_detail_baseline", "10059300")
            b_info = info.get("baseline_dbs", {}).get(alchemy_base_key, {})
            alchemy_base_filename = b_info.get("db_path", f"master_{server_key.lower()}_{alchemy_base_key}.db")
            alchemy_base_path = os.path.join(src_dir, alchemy_base_filename)
            table_keys.append(("alchemy_story_detail_table", alchemy_table, alchemy_base_path))

        # 만우절 레이드 sekai 테이블들
        if info.get("sekai_top_data_table"):
            table_keys.append(("sekai_top_data_table", info.get("sekai_top_data_table", ""), baseline_path))
        if info.get("sekai_top_story_data_table"):
            table_keys.append(("sekai_top_story_data_table", info.get("sekai_top_story_data_table", ""), baseline_path))

        # 이벤트 톱 ADV 및 유닛 테이블
        if info.get("event_top_adv_table"):
            table_keys.append(("event_top_adv_table", info.get("event_top_adv_table", ""), baseline_path))
        if info.get("unit_table"):
            table_keys.append(("unit_table", info.get("unit_table", ""), baseline_path))

        for t_key, tbl_name, b_path in table_keys:
            if tbl_name and not tbl_name.startswith("v1_"):
                all_tasks.append((server_key, t_key, b_path, db_path, tbl_name, target_tables_with_col))

    if not all_tasks:
        return

    # 컬럼 매핑 관계 정의
    COLUMN_MAPPINGS = {
        "event_list_table": ["event_name_col_list", "event_group_id_col_list"],
        "event_details_table": ["event_info_col_details", "event_id_col_details", "event_group_id_col_details"],
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
        ]
    }

    try:
        max_workers = min(len(all_tasks), os.cpu_count() or 4)
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(resolve_single_table_worker, task) for task in all_tasks]
            for future in as_completed(futures):
                s_key, t_key, base_tbl, best_tbl, col_map = future.result()
                if progress_callback:
                    progress_callback(s_key, t_key)
                
                if best_tbl and s_key in server_db_info:
                    s_info = server_db_info[s_key]
                    s_info[t_key] = best_tbl
                    
                    target_col_keys = COLUMN_MAPPINGS.get(t_key, [])
                    for col_k in target_col_keys:
                        orig_col_val = s_info.get(col_k)
                        if orig_col_val and orig_col_val in col_map:
                            s_info[col_k] = col_map[orig_col_val]
                            
        logging.info("Successfully executed parallel schema resolution across all servers.")
    except Exception as e:
        logging.warning(f"ProcessPoolExecutor parallel resolution failed ({e}), falling back to sequential: {e}")
        for server_key, info in server_db_info.items():
            if isinstance(info, dict) and 'db_path' in info:
                db_path = os.path.join(root_dir, info['db_path'])
                baseline_path = os.path.join(src_dir, info.get('baseline_db_path', ''))
                if os.path.exists(baseline_path) and os.path.exists(db_path):
                    resolve_server_config(baseline_path, db_path, info, progress_callback=progress_callback)


def resolve_server_config(baseline_path: str, latest_path: str, server_info: dict, progress_callback: Optional[callable] = None) -> None:
    """
    서버별 DB 설정 딕셔너리(server_info)의 원본 테이블/컬럼명을 실시간 역난독화 해시값으로 변환합니다.
    이 함수는 server_info를 직접 제자리(in-place)에서 수정합니다.
    """
    server_key = server_info.get("version_key", "Unknown")
    # 이미 해시(예: 'v1_...')로 시작한다면 무시
    event_list_table = server_info.get("event_list_table", "")
    if event_list_table.startswith("v1_"):
        if progress_callback:
            progress_callback(server_key, "event_list_table")
            progress_callback(server_key, "event_details_table")
            progress_callback(server_key, "birthday_table")
            progress_callback(server_key, "quest_table")
            progress_callback(server_key, "story_detail_table")
            progress_callback(server_key, "dear_story_detail_table")
            progress_callback(server_key, "tower_story_detail_table")
            if server_info.get("alchemy_story_detail_table"):
                progress_callback(server_key, "alchemy_story_detail_table")
            if server_info.get("sekai_top_data_table"):
                progress_callback(server_key, "sekai_top_data_table")
            if server_info.get("sekai_top_story_data_table"):
                progress_callback(server_key, "sekai_top_story_data_table")
            if server_info.get("event_top_adv_table"):
                progress_callback(server_key, "event_top_adv_table")
            if server_info.get("unit_table"):
                progress_callback(server_key, "unit_table")
        return

    if not os.path.exists(baseline_path):
        logging.error(f"Baseline DB file does not exist, skipping schema mapping: {baseline_path}")
        return

    if not os.path.exists(latest_path):
        logging.error(f"Latest DB file does not exist, skipping schema mapping: {latest_path}")
        return

    try:
        extractors = {}
        def get_extractor(b_path: str) -> StoryDataExtractor:
            if b_path not in extractors:
                extractors[b_path] = StoryDataExtractor(b_path, latest_path)
            return extractors[b_path]

        extractor = get_extractor(baseline_path)

        # 1. 이벤트 목록 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "event_list_table")
        obf_list_table, list_col_map = extractor._find_and_deobfuscate_table(event_list_table)
        server_info["event_list_table"] = obf_list_table
        
        event_name_col_list = server_info.get("event_name_col_list")
        if event_name_col_list and event_name_col_list in list_col_map:
            server_info["event_name_col_list"] = list_col_map[event_name_col_list]

        event_group_id_col_list = server_info.get("event_group_id_col_list")
        if event_group_id_col_list and event_group_id_col_list in list_col_map:
            server_info["event_group_id_col_list"] = list_col_map[event_group_id_col_list]

        # 2. 이벤트 상세 정보 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "event_details_table")
        event_details_table = server_info.get("event_details_table", "")
        if event_details_table and not event_details_table.startswith("v1_"):
            obf_details_table, details_col_map = extractor._find_and_deobfuscate_table(event_details_table)
            server_info["event_details_table"] = obf_details_table
            
            event_info_col_details = server_info.get("event_info_col_details")
            if event_info_col_details and event_info_col_details in details_col_map:
                server_info["event_info_col_details"] = details_col_map[event_info_col_details]

            event_id_col_details = server_info.get("event_id_col_details")
            if event_id_col_details and event_id_col_details in details_col_map:
                server_info["event_id_col_details"] = details_col_map[event_id_col_details]

            event_group_id_col_details = server_info.get("event_group_id_col_details")
            if event_group_id_col_details and event_group_id_col_details in details_col_map:
                server_info["event_group_id_col_details"] = details_col_map[event_group_id_col_details]

        # 3. 생일 로그인 보너스 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "birthday_table")
        birthday_table = server_info.get("birthday_table", "")
        if birthday_table and not birthday_table.startswith("v1_"):
            obf_birthday_table, birthday_col_map = extractor._find_and_deobfuscate_table(birthday_table)
            server_info["birthday_table"] = obf_birthday_table
            
            birthday_name_col = server_info.get("birthday_name_col")
            if birthday_name_col and birthday_name_col in birthday_col_map:
                server_info["birthday_name_col"] = birthday_col_map[birthday_name_col]

            birthday_adv_id_col = server_info.get("birthday_adv_id_col")
            if birthday_adv_id_col and birthday_adv_id_col in birthday_col_map:
                server_info["birthday_adv_id_col"] = birthday_col_map[birthday_adv_id_col]

        # 4. 퀘스트 데이터 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "quest_table")
        quest_table = server_info.get("quest_table", "")
        if quest_table and not quest_table.startswith("v1_"):
            obf_quest_table, quest_col_map = extractor._find_and_deobfuscate_table(quest_table)
            server_info["quest_table"] = obf_quest_table
            
            quest_name_col = server_info.get("quest_name_col")
            if quest_name_col and quest_name_col in quest_col_map:
                server_info["quest_name_col"] = quest_col_map[quest_name_col]

            quest_wavestart_col = server_info.get("quest_wavestart_col")
            if quest_wavestart_col and quest_wavestart_col in quest_col_map:
                server_info["quest_wavestart_col"] = quest_col_map[quest_wavestart_col]

            quest_waveend_col = server_info.get("quest_waveend_col")
            if quest_waveend_col and quest_waveend_col in quest_col_map:
                server_info["quest_waveend_col"] = quest_col_map[quest_waveend_col]

        # 5. 스토리 상세 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "story_detail_table")
        story_detail_table = server_info.get("story_detail_table", "")
        if story_detail_table and not story_detail_table.startswith("v1_"):
            obf_story_detail_table, story_detail_col_map = extractor._find_and_deobfuscate_table(story_detail_table)
            server_info["story_detail_table"] = obf_story_detail_table
            
            story_detail_id_col = server_info.get("story_detail_id_col")
            if story_detail_id_col and story_detail_id_col in story_detail_col_map:
                server_info["story_detail_id_col"] = story_detail_col_map[story_detail_id_col]

            story_detail_title_col = server_info.get("story_detail_title_col")
            if story_detail_title_col and story_detail_title_col in story_detail_col_map:
                server_info["story_detail_title_col"] = story_detail_col_map[story_detail_title_col]

            story_detail_sub_title_col = server_info.get("story_detail_sub_title_col")
            if story_detail_sub_title_col and story_detail_sub_title_col in story_detail_col_map:
                server_info["story_detail_sub_title_col"] = story_detail_col_map[story_detail_sub_title_col]

        # 6. 신뢰도 스토리 상세 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "dear_story_detail_table")
        dear_story_detail_table = server_info.get("dear_story_detail_table", "")
        if dear_story_detail_table and not dear_story_detail_table.startswith("v1_"):
            obf_dear_table, dear_col_map = extractor._find_and_deobfuscate_table(dear_story_detail_table)
            server_info["dear_story_detail_table"] = obf_dear_table
            
            dear_id_col = server_info.get("dear_story_detail_id_col")
            if dear_id_col and dear_id_col in dear_col_map:
                server_info["dear_story_detail_id_col"] = dear_col_map[dear_id_col]

            dear_title_col = server_info.get("dear_story_detail_title_col")
            if dear_title_col and dear_title_col in dear_col_map:
                server_info["dear_story_detail_title_col"] = dear_col_map[dear_title_col]

            dear_sub_title_col = server_info.get("dear_story_detail_sub_title_col")
            if dear_sub_title_col and dear_sub_title_col in dear_col_map:
                server_info["dear_story_detail_sub_title_col"] = dear_col_map[dear_sub_title_col]

        # 7. 루나의 탑 스토리 상세 테이블 매핑
        if progress_callback:
            progress_callback(server_key, "tower_story_detail_table")
        tower_story_detail_table = server_info.get("tower_story_detail_table", "")
        if tower_story_detail_table and not tower_story_detail_table.startswith("v1_"):
            obf_tower_table, tower_col_map = extractor._find_and_deobfuscate_table(tower_story_detail_table)
            server_info["tower_story_detail_table"] = obf_tower_table
            
            tower_id_col = server_info.get("tower_story_detail_id_col")
            if tower_id_col and tower_id_col in tower_col_map:
                server_info["tower_story_detail_id_col"] = tower_col_map[tower_id_col]

            tower_title_col = server_info.get("tower_story_detail_title_col")
            if tower_title_col and tower_title_col in tower_col_map:
                server_info["tower_story_detail_title_col"] = tower_col_map[tower_title_col]

            tower_sub_title_col = server_info.get("tower_story_detail_sub_title_col")
            if tower_sub_title_col and tower_sub_title_col in tower_col_map:
                server_info["tower_story_detail_sub_title_col"] = tower_col_map[tower_sub_title_col]

        # 8. 알케스 연금당 숏드라마 스토리 상세 테이블 매핑
        alchemy_table = server_info.get("alchemy_story_detail_table", "")
        if alchemy_table:
            if progress_callback:
                progress_callback(server_key, "alchemy_story_detail_table")
            
            alchemy_base_key = server_info.get("alchemy_story_detail_baseline", "10059300")
            b_info = server_info.get("baseline_dbs", {}).get(alchemy_base_key, {})
            alchemy_base_filename = b_info.get("db_path", f"master_{server_key.lower()}_{alchemy_base_key}.db")
            alchemy_base_path = os.path.join(os.path.dirname(baseline_path), alchemy_base_filename)
            
            if os.path.exists(alchemy_base_path):
                alchemy_extractor = get_extractor(alchemy_base_path)
                obf_alchemy_table, alchemy_col_map = alchemy_extractor._find_and_deobfuscate_table(alchemy_table)
                server_info["alchemy_story_detail_table"] = obf_alchemy_table
                
                alchemy_id_col = server_info.get("alchemy_story_detail_id_col")
                if alchemy_id_col and alchemy_id_col in alchemy_col_map:
                    server_info["alchemy_story_detail_id_col"] = alchemy_col_map[alchemy_id_col]
                    
                alchemy_title_col = server_info.get("alchemy_story_detail_title_col")
                if alchemy_title_col and alchemy_title_col in alchemy_col_map:
                    server_info["alchemy_story_detail_title_col"] = alchemy_col_map[alchemy_title_col]

        # 9. 만우절 레이드 sekai_top_data 테이블 매핑
        sekai_table = server_info.get("sekai_top_data_table", "")
        if sekai_table and not sekai_table.startswith("v1_"):
            if progress_callback:
                progress_callback(server_key, "sekai_top_data_table")
            obf_sekai_table, sekai_col_map = extractor._find_and_deobfuscate_table(sekai_table)
            server_info["sekai_top_data_table"] = obf_sekai_table

            for col_key in [
                "sekai_top_data_id_col",
                "sekai_top_data_name_col",
                "sekai_top_data_boss_mode_col",
                "sekai_top_data_boss_time_from_col",
                "sekai_top_data_boss_hp_from_col",
            ]:
                val = server_info.get(col_key)
                if val and val in sekai_col_map:
                    server_info[col_key] = sekai_col_map[val]

        # 10. 만우절 레이드 sekai_top_story_data 테이블 매핑
        sekai_story_table = server_info.get("sekai_top_story_data_table", "")
        if sekai_story_table and not sekai_story_table.startswith("v1_"):
            if progress_callback:
                progress_callback(server_key, "sekai_top_story_data_table")
            obf_sekai_story_table, sekai_story_col_map = extractor._find_and_deobfuscate_table(sekai_story_table)
            server_info["sekai_top_story_data_table"] = obf_sekai_story_table

            for col_key in [
                "sekai_top_story_data_id_col",
                "sekai_top_story_data_boss_time_from_col",
                "sekai_top_story_data_boss_time_to_col",
            ]:
                val = server_info.get(col_key)
                if val and val in sekai_story_col_map:
                    server_info[col_key] = sekai_story_col_map[val]

        # 11. event_top_adv 테이블 매핑
        top_table = server_info.get("event_top_adv_table", "")
        if top_table and not top_table.startswith("v1_"):
            if progress_callback:
                progress_callback(server_key, "event_top_adv_table")
            obf_top_table, top_col_map = extractor._find_and_deobfuscate_table(top_table)
            server_info["event_top_adv_table"] = obf_top_table

            for col_key in ["event_top_adv_id_col", "event_top_adv_character_id_col", "event_top_adv_event_id_col"]:
                val = server_info.get(col_key)
                if val and val in top_col_map:
                    server_info[col_key] = top_col_map[val]

        # 12. unit_data 테이블 매핑
        unit_table = server_info.get("unit_table", "")
        if unit_table and not unit_table.startswith("v1_"):
            if progress_callback:
                progress_callback(server_key, "unit_table")
            obf_unit_table, unit_col_map = extractor._find_and_deobfuscate_table(unit_table)
            server_info["unit_table"] = obf_unit_table

            for col_key in ["unit_id_col", "unit_name_col"]:
                val = server_info.get(col_key)
                if val and val in unit_col_map:
                    server_info[col_key] = unit_col_map[val]

        logging.info("Successfully extracted obfuscated table/column names from the latest DB.")
    except Exception as e:
        logging.error(f"Schema automatic analysis failed: {e}")
