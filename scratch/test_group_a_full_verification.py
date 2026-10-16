import os
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from src.story_viewer.controller import _load_db_config
from src.story_viewer.schema_resolver import resolve_server_config, resolve_all_servers_parallel
from src.story_viewer import db_helper

print("=== 1. DB Config & Schema Resolution Test ===")
server_db_info = _load_db_config()
jp_info = server_db_info['JP']

print("Before resolution:")
for k in ['legion_special_battle_table', 'byway_battle_quest_data_table', 'byway_quest_data_table']:
    print(f"  {k}: {jp_info.get(k)}")

resolve_server_config('src/master_jp_10052900.db', 'master_jp.db', jp_info)

print("After resolution:")
for k in [
    'legion_special_battle_table', 'legion_special_battle_mode_col', 'legion_special_battle_mode_start_col', 'legion_special_battle_mode_end_col',
    'byway_battle_quest_data_table', 'byway_battle_quest_data_quest_id_col', 'byway_battle_quest_data_wavestart_col', 'byway_battle_quest_data_waveend_col',
    'byway_quest_data_table', 'byway_quest_data_quest_id_col', 'byway_quest_data_quest_name_col'
]:
    print(f"  {k}: {jp_info.get(k)}")

print("\n=== 2. Fetch Group A (9 IDs) ===")
target_9_ids = [
    '9003516', '9003517', '9003518',
    '9066157', '9066158',
    '9067157', '9067158',
    '9068157', '9068158'
]

results = db_helper.fetch_legion_and_byway_battle_titles_batch(jp_info, target_9_ids)
for tid in target_9_ids:
    print(f"  {tid} -> {results.get(tid)}")

assert len(results) == 9, f"Expected 9 results, got {len(results)}"
assert results['9003516'] == '[王都終末決戦] SPECIAL MODE 1 (wavestart)'
assert results['9003517'] == '[王都終末決戦] SPECIAL MODE 1 (waveend)'
assert results['9003518'] == '[王都終末決戦] SPECIAL MODE 2 (waveend)'
assert results['9066157'] == '《EX》天才発明家の三女、襲来 (wavestart)'
assert results['9066158'] == '《EX》天才発明家の三女、襲来 (waveend)'
assert results['9067157'] == '《EX》受難体質の次女、遭難 (wavestart)'
assert results['9067158'] == '《EX》受難体質の次女、遭難 (waveend)'
assert results['9068157'] == '《EX》豪放磊落の長女、狂酔 (wavestart)'
assert results['9068158'] == '《EX》豪放磊落の長女、狂酔 (waveend)'
print("\n[SUCCESS] All 9 Group A IDs resolved exactly as defined!")
