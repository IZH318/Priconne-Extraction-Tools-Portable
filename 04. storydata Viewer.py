# --- 필수 모듈 임포트 ---
# 시스템 및 운영체제 관련 모듈
import os                     # OS 기능 (경로, 파일 확인)

# 데이터 처리 관련 모듈
from datetime import datetime # 현재 시간 (로그 타임스탬프용)
import json                   # JSON 데이터 처리
import re                     # 정규 표현식 (파일명 필터링)
import sqlite3                # SQLite 데이터베이스 연동

# 동시성 및 병렬 처리 관련 모듈
import concurrent.futures     # 병렬 처리 (스레드 풀)
import queue                  # 스레드 간 데이터 통신
import threading              # 스레드 생성/관리

# 그래픽 사용자 인터페이스(GUI) 관련 모듈
import tkinter as tk                                  # GUI 라이브러리
from tkinter import ttk, filedialog, messagebox, font # GUI 확장 위젯 및 대화상자

# --- 프로그램 정보 ---
ABOUT_INFO = {
    'program': "storydata Viewer",
    'version': "1.0.0",
    'updated': "2025-07-26",
    'license': "GNU General Public License v3.0",
    'developer': "(Github) IZH318",
    'website': "https://github.com/IZH318",
}

# --- 다국어 리소스 ---
LANGUAGES = {
    'ko': {
        # --- 전역 및 메뉴 ---
        'window_title': "storydata Viewer",
        'menu_file': "메뉴(Menu)", 'menu_lang': "언어(Language)", 'menu_about': "정보(About)",
        'file_open': "파일 열기", 'folder_open': "폴더 열기", 'export': "내보내기", 'exit': "종료",
        'lang_ko': "한국어", 'lang_en': "English", 'lang_ja': "日本語",
        # --- 메인 UI ---
        'options_group': "옵션",
        'file_options_group': "스토리 파일 목록 옵션",
        'display_original_filename': "원본 파일 이름으로 표시", 'display_title': "title 정보로 표시",
        'detail_options_group': "스토리 상세 정보 옵션",
        'view_simple': "간단히 표시 (title, outline, vo, print)", 'view_detailed': "자세히 표시",
        'list_group_title': "스토리 파일 목록", 'detail_group_title': "스토리 상세 정보",
        'search_button_text': "storydata 고급 검색",
        # --- 상태 표시줄 메시지 ---
        'status_bar_initial': "storydata 파일이나 폴더를 열어주세요.",
        'status_bar_loading_start': "파일 로딩 및 분석 시작...",
        'status_bar_analyzing': "파일 분석 중... ({i}/{t})",
        'status_bar_loading_done': "로드 완료: {loaded}개 성공, {failed}개 실패.",
        'status_bar_ready': "준비",
        'status_bar_displaying': "'{filename}' 표시 완료.",
        'status_bar_cache_error': "오류: '{filename}' 캐시 데이터 없음.",
        'status_bar_list_updated': "{count}개의 파일이 목록에 표시됩니다.",
        'status_bar_list_updating': "목록 업데이트 중... ({i}/{t})",
        'status_bar_export_prep': "내보내기 준비 중...",
        'status_bar_exporting': "내보내기 중... ({i}/{t})",
        'status_bar_export_done': "{exported}개 파일 내보내기 완료. ({failed}개 실패)",
        'status_bar_export_all_failed': "모든 파일 내보내기 실패. ({failed}개 실패)",
        'status_bar_exporting_type': "'{type_name}' 내보내기 중... (성공: {success}, 실패: {failed})",
        'status_bar_export_summary': "내보내기 요약: 성공 {success_total}개, 실패 {failed_total}개",
        # --- 메시지 박스 ---
        'msgbox_loading_title': "작업 중",
        'msgbox_loading_msg': "현재 다른 파일을 로딩하고 있습니다.",
        'msgbox_no_valid_files_title': "알림",
        'msgbox_no_valid_files_msg': "유효한 storydata 파일이 없습니다.",
        'msgbox_load_fail_title': "로드 실패 알림",
        'msgbox_load_fail_msg': "{count}개의 파일이 유효하지 않아 로드에 실패했습니다.\n\n실패한 파일의 목록을 'invalid_storydata_log.txt' 파일로 저장하시겠습니까?",
        'msgbox_log_saved_title': "로그 저장 완료",
        'msgbox_log_saved_msg': "'{filename}' 파일에 실패 목록을 저장했습니다.",
        'msgbox_log_save_error_title': "로그 저장 실패",
        'msgbox_log_save_error_msg': "로그 파일 저장 중 오류가 발생했습니다:\n{e}",
        'msgbox_search_before_load_title': "알림",
        'msgbox_search_before_load_msg': "먼저 storydata 파일이나 폴더를 열어주세요.",
        'msgbox_export_options_title': "내보내기 옵션",
        'msgbox_no_export_files_title': "알림",
        'msgbox_no_export_files_msg': "내보낼 파일이 없습니다.",
        'msgbox_export_folder_title': "저장할 폴더를 선택하세요",
        'msgbox_export_complete_title': "내보내기 완료",
        'msgbox_export_complete_msg': "{exported_count}개의 파일/목록을 성공적으로 내보냈습니다.",
        'msgbox_export_failed_title': "내보내기 실패",
        'msgbox_export_failed_msg': "내보낸 파일/목록이 없습니다. {failed_count}개에서 오류가 발생했습니다.",
        'msgbox_export_error_details_title': "내보내기 오류 상세",
        'msgbox_export_error_details_msg': "다음 파일/목록 내보내기 중 오류 발생:\n{errors}",
        'msgbox_no_export_types_selected': "내보낼 항목을 최소 하나 이상 선택해주세요.",
        # --- 파일 대화상자 ---
        'dialog_title_open_files': "storydata 파일을 선택하세요",
        'dialog_title_open_folder': "storydata 파일이 있는 폴더를 선택하세요",
        'filetype_json': "JSON 파일",
        'filetype_all': "모든 파일",
        # --- 정보 창 ---
        'about_header': "프로그램 정보",
        'about_label_program': "프로그램 이름", 'about_label_version': "버전", 'about_label_updated': "최종 업데이트",
        'about_label_license': "라이선스", 'about_label_developer': "개발자", 'about_label_website': "웹 사이트",
        # --- 검색 창 ---
        'search_window_title': "storydata 고급 검색",
        'basic_search_criteria_frame': "기본 검색 조건",
        'filename_label': "파일 이름:", 'title_label': "제목:", 'outline_label': "개요:",
        'char_name_label': "캐릭터 이름:", 'char_type_label': "검색 타입:", 'content_label': "내용(대사):",
        'bgm_label': "BGM 파일명:", 'background_label': "배경 파일명:",
        'char_type_speaker': "화자", 'char_type_mentioned_in_dialogue': "피호명자(대사)",
        'event_search_frame': "이벤트 스토리 검색",
        'jp_server_radio': "일본 서버 (JP)", 'kr_server_radio': "한국 서버 (KR)",
        'event_list_label': "이벤트 목록:",
        'search_button': "검색", 'reset_button': "초기화",
        'db_not_found_title': "데이터베이스 파일 없음", # <-- FIX 02: 메시지 박스 제목 일관성
        'db_not_found_msg': "다음 데이터베이스 파일을 찾을 수 없습니다:\n\n{paths}\n\n해당 서버의 이벤트 목록을 로드할 수 없습니다.",
        'db_error_title': "데이터베이스 오류", 'db_error_msg': "데이터베이스 처리 중 오류 발생:\n{e}",
        'status_searching': "고급 검색 중...",
        'search_error_title': "검색 오류", 'search_error_msg': "검색 중 오류가 발생했습니다:\n{e}",
        # --- 로그 파일 ---
        'log_header': "--- 로드 실패 로그 ({timestamp}) ---\n",
        'log_total_failed': "총 {count}개 파일 로드 실패\n",
        'log_file_label': "파일",
        'log_reason_label': "원인",
        # --- 내보내기 창 ---
        'export_window_title': "내보내기 옵션 선택",
        'export_type_frame': "내보낼 데이터 종류",
        'export_type_story_data': "스토리 데이터",
        'export_type_filenames': "파일 이름 목록",
        'export_type_character_names': "캐릭터 이름 목록",
        'export_type_bgm_names': "BGM 파일명 목록",
        'export_type_background_names': "배경 파일명 목록",
        'export_type_event_list_jp': "일본 서버 (JP)",
        'export_type_event_list_kr': "한국 서버 (KR)",
        'export_button_text': "내보내기 시작",
        'cancel_button_text': "취소",
        'export_db_not_found_tooltip': "이벤트 DB 파일이 없습니다.",
        'export_scope_frame': "스토리 데이터 내보내기 범위",
        'export_scope_current_list': "현재 목록에 있는 파일만",
        'export_scope_all_loaded': "불러온 모든 파일",
        'export_type_event_list_frame': "이벤트 스토리 서버",
        'export_type_event_list_master': "이벤트 스토리 목록",
    },
    'en': {
        # --- Global & Menu ---
        'window_title': "storydata Viewer",
        'menu_file': "Menu", 'menu_lang': "Language", 'menu_about': "About",
        'file_open': "Open File(s)", 'folder_open': "Open Folder", 'export': "Export", 'exit': "Exit",
        'lang_ko': "한국어", 'lang_en': "English", 'lang_ja': "日本語",
        # --- Main UI ---
        'options_group': "Options",
        'file_options_group': "Story File List Options",
        'display_original_filename': "Display by original filename", 'display_title': "Display by title info",
        'detail_options_group': "Story Detail Options",
        'view_simple': "Simple View (title, outline, vo, print)", 'view_detailed': "Detailed View",
        'list_group_title': "Story File List", 'detail_group_title': "Story Details",
        'search_button_text': "Advanced storydata Search",
        # --- Status Bar Messages ---
        'status_bar_initial': "Please open a file or folder.",
        'status_bar_loading_start': "Starting to load and analyze files...",
        'status_bar_analyzing': "Analyzing files... ({i}/{t})",
        'status_bar_loading_done': "Loading complete: {loaded} succeeded, {failed} failed.",
        'status_bar_ready': "Ready",
        'status_bar_displaying': "Displaying '{filename}' done.",
        'status_bar_cache_error': "Error: Cached data for '{filename}' not found.",
        'status_bar_list_updated': "{count} files are displayed in the list.",
        'status_bar_list_updating': "Updating list... ({i}/{t})",
        'status_bar_export_prep': "Preparing for export...",
        'status_bar_exporting': "Exporting... ({i}/{t})",
        'status_bar_export_done': "Export complete: {exported} files. ({failed} failed)",
        'status_bar_export_all_failed': "Export failed for all files. ({failed} failed)",
        'status_bar_exporting_type': "Exporting '{type_name}'... (Success: {success}, Failed: {failed})",
        'status_bar_export_summary': "Export Summary: {success_total} succeeded, {failed_total} failed",
        # --- Message Boxes ---
        'msgbox_loading_title': "In Progress",
        'msgbox_loading_msg': "Currently loading other files.",
        'msgbox_no_valid_files_title': "Notice",
        'msgbox_no_valid_files_msg': "No valid storydata files found.",
        'msgbox_load_fail_title': "Load Failed",
        'msgbox_load_fail_msg': "{count} files were invalid and failed to load.\n\nDo you want to save the list of failed files to 'invalid_storydata_log.txt'?",
        'msgbox_log_saved_title': "Log Saved",
        'msgbox_log_saved_msg': "The list of failed files has been saved to '{filename}'.",
        'msgbox_log_save_error_title': "Log Save Error",
        'msgbox_log_save_error_msg': "An error occurred while saving the log file:\n{e}",
        'msgbox_search_before_load_title': "Notice",
        'msgbox_search_before_load_msg': "Please open a storydata file or folder first.",
        'msgbox_export_options_title': "Export Options",
        'msgbox_no_export_files_title': "Notice",
        'msgbox_no_export_files_msg': "There are no files to export.",
        'msgbox_export_folder_title': "Select a folder to save files",
        'msgbox_export_complete_title': "Export Complete",
        'msgbox_export_complete_msg': "Successfully exported {exported_count} files/lists.",
        'msgbox_export_failed_title': "Export Failed",
        'msgbox_export_failed_msg': "No files/lists were exported. An error occurred in {failed_count} items.",
        'msgbox_export_error_details_title': "Export Error Details",
        'msgbox_export_error_details_msg': "Error occurred while exporting the following files/lists:\n{errors}",
        'msgbox_no_export_types_selected': "Please select at least one item to export.",
        # --- File Dialogs ---
        'dialog_title_open_files': "Select storydata file(s)",
        'dialog_title_open_folder': "Select the folder with storydata files",
        'filetype_json': "JSON Files",
        'filetype_all': "All Files",
        # --- About Window ---
        'about_header': "About Program",
        'about_label_program': "Program", 'about_label_version': "Version", 'about_label_updated': "Updated",
        'about_label_license': "License", 'about_label_developer': "Developer", 'about_label_website': "Website",
        # --- Search Window ---
        'search_window_title': "Advanced storydata Search",
        'basic_search_criteria_frame': "Basic Search Criteria",
        'filename_label': "Filename:", 'title_label': "Title:", 'outline_label': "Outline:",
        'char_name_label': "Character:", 'char_type_label': "Search Type:", 'content_label': "Content (Dialogue):",
        'bgm_label': "BGM Filename:", 'background_label': "Background Filename:",
        'char_type_speaker': "Speaker", 'char_type_mentioned_in_dialogue': "Mentioned (in dialogue)",
        'event_search_frame': "Event Story Search",
        'jp_server_radio': "Japan Server (JP)", 'kr_server_radio': "Korea Server (KR)",
        'event_list_label': "Event List:",
        'search_button': "Search", 'reset_button': "Reset",
        'db_not_found_title': "Database File Not Found", # <-- FIX 02
        'db_not_found_msg': "The following database files could not be found:\n\n{paths}\n\nCannot load event list for the corresponding server(s).",
        'db_error_title': "Database Error", 'db_error_msg': "An error occurred during database processing:\n{e}",
        'status_searching': "Advanced searching...",
        'search_error_title': "Search Error", 'search_error_msg': "An error occurred during search:\n{e}",
        # --- Log File ---
        'log_header': "--- Load Failure Log ({timestamp}) ---\n",
        'log_total_failed': "Total {count} files failed to load.\n",
        'log_file_label': "File",
        'log_reason_label': "Reason",
        # --- Export Window ---
        'export_window_title': "Select Export Options",
        'export_type_frame': "Data Types to Export",
        'export_type_story_data': "Story Data",
        'export_type_filenames': "Filename List",
        'export_type_character_names': "Character Name List",
        'export_type_bgm_names': "BGM Filename List",
        'export_type_background_names': "Background Filename List",
        'export_type_event_list_jp': "Japan Server (JP)",
        'export_type_event_list_kr': "Korea Server (KR)",
        'export_button_text': "Start Export",
        'cancel_button_text': "Cancel",
        'export_db_not_found_tooltip': "Event DB file not found.",
        'export_scope_frame': "Story Data Export Scope",
        'export_scope_current_list': "Files in current list only",
        'export_scope_all_loaded': "All loaded files",
        'export_type_event_list_frame': "Event Story Servers",
        'export_type_event_list_master': "Event Story Lists",
    },
    'ja': {
        # --- グローバル & メニュー ---
        'window_title': "storydata Viewer",
        'menu_file': "メニュー(Menu)", 'menu_lang': "言語(Language)", 'menu_about': "情報(About)",
        'file_open': "ファイルを開く", 'folder_open': "フォルダーを開く", 'export': "エクスポート", 'exit': "終了",
        'lang_ko': "한국어", 'lang_en': "English", 'lang_ja': "日本語",
        # --- メインUI ---
        'options_group': "オプション",
        'file_options_group': "ストーリーファイルリストのオプション",
        'display_original_filename': "元のファイル名で表示", 'display_title': "title情報で表示",
        'detail_options_group': "ストーリー詳細情報のオプション",
        'view_simple': "簡易表示 (title, outline, vo, print)", 'view_detailed': "詳細表示",
        'list_group_title': "ストーリーファイルリスト", 'detail_group_title': "ストーリー詳細",
        'search_button_text': "storydata 高度な検索",
        # --- ステータスバーメッセージ ---
        'status_bar_initial': "storydata ファイルまたはフォルダーを開いてください。",
        'status_bar_loading_start': "ファイルの読み込みと分析を開始...",
        'status_bar_analyzing': "ファイルを分析中... ({i}/{t})",
        'status_bar_loading_done': "読み込み完了: {loaded}件成功, {failed}件失敗。",
        'status_bar_ready': "準備完了",
        'status_bar_displaying': "'{filename}' の表示完了。",
        'status_bar_cache_error': "エラー: '{filename}' のキャッシュデータがありません。",
        'status_bar_list_updated': "リストに{count}個のファイルが表示されています。",
        'status_bar_list_updating': "リストを更新中... ({i}/{t})",
        'status_bar_export_prep': "エクスポートの準備中...",
        'status_bar_exporting': "エクスポート中... ({i}/{t})",
        'status_bar_export_done': "{exported}件のエクスポート完了。({failed}件失敗)",
        'status_bar_export_all_failed': "すべてのファイルのエクスポートに失敗しました。({failed}件失敗)",
        'status_bar_exporting_type': "'{type_name}' をエクスポート中... (成功: {success}, 失敗: {failed})",
        'status_bar_export_summary': "エクスポート概要: 成功 {success_total}件, 失敗 {failed_total}件",
        # --- メッセージボックス ---
        'msgbox_loading_title': "処理中",
        'msgbox_loading_msg': "現在、他のファイルを読み込んでいます。",
        'msgbox_no_valid_files_title': "通知",
        'msgbox_no_valid_files_msg': "有効なstorydataファイルが見つかりません。",
        'msgbox_load_fail_title': "読み込み失敗",
        'msgbox_load_fail_msg': "{count}個のファイルが無効で読み込みに失敗しました。\n\n失敗したファイルのリストを 'invalid_storydata_log.txt' に保存しますか？",
        'msgbox_log_saved_title': "ログ保存完了",
        'msgbox_log_saved_msg': "失敗リストを'{filename}'に保存しました。",
        'msgbox_log_save_error_title': "ログ保存エラー",
        'msgbox_log_save_error_msg': "ログファイルの保存中にエラーが発生しました:\n{e}",
        'msgbox_search_before_load_title': "通知",
        'msgbox_search_before_load_msg': "まずstorydataファイルまたはフォルダーを開いてください。",
        'msgbox_export_options_title': "エクスポートオプション",
        'msgbox_no_export_files_title': "通知",
        'msgbox_no_export_files_msg': "エクスポートするファイルがありません。",
        'msgbox_export_folder_title': "保存するフォルダーを選択してください",
        'msgbox_export_complete_title': "エクスポート完了",
        'msgbox_export_complete_msg': "{exported_count}個のファイル/リストを正常にエクスポートしました。",
        'msgbox_export_failed_title': "エクスポート失敗",
        'msgbox_export_failed_msg': "エクスポートされたファイル/リストはありません。{failed_count}個の項目でエラーが発生しました。",
        'msgbox_export_error_details_title': "エクスポートエラー詳細",
        'msgbox_export_error_details_msg': "以下のファイル/リストのエクスポート中にエラーが発生しました:\n{errors}",
        'msgbox_no_export_types_selected': "エクスポートする項目を少なくとも1つ選択してください。",
        # --- ファイルダイアログ ---
        'dialog_title_open_files': "storydata ファイルを選択してください",
        'dialog_title_open_folder': "storydata ファイルがあるフォルダーを選択してください",
        'filetype_json': "JSON ファイル",
        'filetype_all': "すべてのファイル",
        # --- 情報ウィンドウ ---
        'about_header': "プログラム情報",
        'about_label_program': "プログラム名", 'about_label_version': "バージョン", 'about_label_updated': "最終更新日",
        'about_label_license': "ライセンス", 'about_label_developer': "開発者", 'about_label_website': "ウェブサイト",
        # --- 検索ウィンドウ ---
        'search_window_title': "storydata 高度な検索",
        'basic_search_criteria_frame': "基本検索条件",
        'filename_label': "ファイル名:", 'title_label': "タイトル:", 'outline_label': "概要:",
        'char_name_label': "キャラクター名:", 'char_type_label': "検索タイプ:", 'content_label': "内容(セリフ):",
        'bgm_label': "BGMファイル名:", 'background_label': "背景ファイル名:",
        'char_type_speaker': "話者", 'char_type_mentioned_in_dialogue': "被呼名者(セリフ)",
        'event_search_frame': "イベントストーリー検索",
        'jp_server_radio': "日本サーバー (JP)", 'kr_server_radio': "韓国サーバー (KR)",
        'event_list_label': "イベントリスト:",
        'search_button': "検索", 'reset_button': "リセット",
        'db_not_found_title': "データベースファイルが見つかりません", # <-- FIX 02
        'db_not_found_msg': "次のデータベースファイルが見つかりません:\n\n{paths}\n\n該当サーバーのイベントリストを読み込めません。",
        'db_error_title': "データベースエラー", 'db_error_msg': "データベース処理中にエラーが発生しました:\n{e}",
        'status_searching': "高度な検索を実行中...",
        'search_error_title': "検索エラー", 'search_error_msg': "検索中にエラーが発生しました:\n{e}",
        # --- ログファイル ---
        'log_header': "--- 読み込み失敗ログ ({timestamp}) ---\n",
        'log_total_failed': "合計{count}個のファイルの読み込みに失敗しました\n",
        'log_file_label': "ファイル",
        'log_reason_label': "原因",
        # --- エクスポートウィンドウ ---
        'export_window_title': "エクスポートオプション選択",
        'export_type_frame': "エクスポートするデータ種類",
        'export_type_story_data': "ストーリーデータ",
        'export_type_filenames': "ファイル名リスト",
        'export_type_character_names': "キャラクター名リスト",
        'export_type_bgm_names': "BGMファイル名リスト",
        'export_type_background_names': "背景ファイル名リスト",
        'export_type_event_list_jp': "日本サーバー (JP)",
        'export_type_event_list_kr': "韓国サーバー (KR)",
        'export_button_text': "エクスポート開始",
        'cancel_button_text': "キャンセル",
        'export_db_not_found_tooltip': "イベントDBファイルが見つかりません。",
        'export_scope_frame': "ストーリーデータエクスポート範囲",
        'export_scope_current_list': "現在のリストのファイルのみ",
        'export_scope_all_loaded': "読み込まれたすべてのファイル",
        'export_type_event_list_frame': "イベントストーリーサーバー",
        'export_type_event_list_master': "イベントストーリーリスト",
    }
}

# ##################################################################
# Class: SearchWindow
#
# 목적: storydata 고급 검색 기능을 위한 별도의 Toplevel 창.
#
# 주요 기능:
# 1. 다양한 조건(파일명, 제목, 캐릭터, 내용 등)으로 storydata를 검색.
# 2. 서버별 이벤트 스토리 검색을 위해 SQLite 데이터베이스와 연동.
# 3. 검색 실행 시 메인 앱의 파일 목록을 필터링된 결과로 업데이트.
# 4. 모든 UI 요소는 다국어를 지원.
# ##################################################################
class SearchWindow(tk.Toplevel):
    def __init__(self, app, all_files_dict, story_data_cache, search_callback, search_data, db_status, server_db_info):
        """
        SearchWindow 인스턴스를 초기화합니다.

        Args:
            app (StoryViewerApp): 메인 애플리케이션 인스턴스.
            all_files_dict (dict): 로드된 모든 파일의 {파일명: 경로} 딕셔너리.
            story_data_cache (dict): 로드된 모든 storydata의 {파일명: JSON 데이터} 캐시.
            search_callback (function): 검색 완료 후 결과를 전달할 콜백 함수.
            search_data (dict): 검색 필드(Combobox)를 채울 데이터.
            db_status (dict): 서버별 DB 파일 존재 여부 상태.
            server_db_info (dict): 서버별 DB 설정 정보.
        """
        super().__init__(app.master)
        
        # 메인 앱 및 데이터 참조
        self.app = app
        self.all_files_dict = all_files_dict
        self.story_data_cache = story_data_cache
        self.search_callback = search_callback
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        # 검색 조건 입력을 위한 UI 변수
        self.search_vars = {
            'filename': tk.StringVar(),
            'title': tk.StringVar(),
            'outline': tk.StringVar(),
            'char_name': tk.StringVar(),
            'char_type': tk.StringVar(),
            'content': tk.StringVar(),
            'bgm': tk.StringVar(),
            'background': tk.StringVar(),
            'event_name': tk.StringVar()
        }
        self.server_var = tk.StringVar(value='JP') # 기본 서버 선택

        self.transient(app.master) # 부모 창 위에 항상 표시
        self.grab_set() # 모달 창으로 동작
        
        self._setup_ui() # UI 구성
        self._on_server_selection_change() # 초기 서버 선택에 따른 이벤트 목록 로드
        
        self.focus_set() # 창에 포커스 설정
        self._center_window(480, 390) # 창 중앙 정렬

    def _center_window(self, width, height):
        """윈도우를 화면 중앙에 배치합니다."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        """검색 창의 UI 위젯들을 생성하고 배치합니다."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # 기본 검색 조건 프레임
        self.criteria_frame = ttk.LabelFrame(main_frame, text="", padding=5)
        self.criteria_frame.pack(fill="x", expand=False, anchor="n", pady=(0, 10))
        
        # 동적 레이아웃을 위한 그리드 열 설정
        self.criteria_frame.columnconfigure(1, weight=1) # 엔트리/콤보박스 열
        self.criteria_frame.columnconfigure(3, weight=1) # char_type_combobox를 위한 열

        pady_value = 4
        
        # 파일 이름 (Filename)
        self.filename_label = ttk.Label(self.criteria_frame, text="")
        self.filename_label.grid(row=0, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['filename'], values=self.search_data.get('filenames', [])).grid(row=0, column=1, columnspan=3, sticky="ew")

        # 제목 (Title)
        self.title_label = ttk.Label(self.criteria_frame, text="")
        self.title_label.grid(row=1, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['title']).grid(row=1, column=1, columnspan=3, sticky="ew")

        # 개요 (Outline)
        self.outline_label = ttk.Label(self.criteria_frame, text="")
        self.outline_label.grid(row=2, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['outline']).grid(row=2, column=1, columnspan=3, sticky="ew")

        # 캐릭터 (Character Name & Type)
        self.char_name_label = ttk.Label(self.criteria_frame, text="")
        self.char_name_label.grid(row=3, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_name'], values=self.search_data.get('character_names', [])).grid(row=3, column=1, sticky="ew")
        
        self.char_type_label = ttk.Label(self.criteria_frame, text="")
        self.char_type_label.grid(row=3, column=2, sticky="e", padx=(5,0))
        
        self.char_type_combobox = ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_type'], width=15, state='readonly')
        self.char_type_combobox.grid(row=3, column=3, sticky="e", padx=(5,0))

        # 내용(대사) (Content)
        self.content_label = ttk.Label(self.criteria_frame, text="")
        self.content_label.grid(row=4, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['content']).grid(row=4, column=1, columnspan=3, sticky="ew")

        # BGM 파일명 (BGM Filename)
        self.bgm_label = ttk.Label(self.criteria_frame, text="")
        self.bgm_label.grid(row=5, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['bgm'], values=self.search_data.get('bgms', [])).grid(row=5, column=1, columnspan=3, sticky="ew")

        # 배경 파일명 (Background Filename)
        self.background_label = ttk.Label(self.criteria_frame, text="")
        self.background_label.grid(row=6, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['background'], values=self.search_data.get('backgrounds', [])).grid(row=6, column=1, columnspan=3, sticky="ew")

        # 이벤트 스토리 검색 프레임 (Event Story Search Frame)
        self.event_search_frame = ttk.LabelFrame(main_frame, text="", padding="5")
        self.event_search_frame.pack(fill="x", expand=True, anchor="n")
        self.event_search_frame.columnconfigure(1, weight=1)

        # 서버 선택 (Server Selection)
        server_frame = ttk.Frame(self.event_search_frame, padding="5")
        server_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,5))
        server_frame.columnconfigure(0, weight=1)
        server_frame.columnconfigure(1, weight=1)
        self.jp_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="JP", command=self._on_server_selection_change)
        self.jp_radio.grid(row=0, column=0, padx=5, sticky="w")
        self.kr_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="KR", command=self._on_server_selection_change)
        self.kr_radio.grid(row=0, column=1, padx=5, sticky="w")

        # 이벤트 목록 (Event List)
        self.event_list_label = ttk.Label(self.event_search_frame, text="")
        self.event_list_label.grid(row=1, column=0, sticky="w", pady=3)
        self.event_combobox = ttk.Combobox(self.event_search_frame, textvariable=self.search_vars['event_name'], state='readonly')
        self.event_combobox.grid(row=1, column=1, columnspan=2, sticky="ew")

        # 하단 버튼 프레임 (Bottom Button Frame)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        self.search_button = ttk.Button(button_frame, text="", command=self.start_search)
        self.search_button.pack(side="right")
        self.reset_button = ttk.Button(button_frame, text="", command=self._reset)
        self.reset_button.pack(side="right", padx=(0, 5))
        
        self._update_ui_text() # UI 텍스트 초기화

    def _update_ui_text(self):
        """UI의 모든 텍스트 요소를 현재 선택된 언어로 갱신합니다."""
        lang_dict = LANGUAGES[self.app.lang.get()]
        
        self.title(lang_dict['search_window_title'])
        self.criteria_frame.config(text=lang_dict['basic_search_criteria_frame'])
        self.filename_label.config(text=lang_dict['filename_label'])
        self.title_label.config(text=lang_dict['title_label'])
        self.outline_label.config(text=lang_dict['outline_label'])
        self.char_name_label.config(text=lang_dict['char_name_label'])
        self.char_type_label.config(text=lang_dict['char_type_label'])
        self.content_label.config(text=lang_dict['content_label'])
        self.bgm_label.config(text=lang_dict['bgm_label'])
        self.background_label.config(text=lang_dict['background_label'])
        
        char_types = [lang_dict['char_type_speaker'], lang_dict['char_type_mentioned_in_dialogue']]
        self.char_type_combobox.config(values=char_types)
        if not self.search_vars['char_type'].get():
            self.search_vars['char_type'].set(char_types[0])

        self.event_search_frame.config(text=lang_dict['event_search_frame'])
        self.jp_radio.config(text=lang_dict['jp_server_radio'])
        self.kr_radio.config(text=lang_dict['kr_server_radio'])
        self.event_list_label.config(text=lang_dict['event_list_label'])

        self.search_button.config(text=lang_dict['search_button'])
        self.reset_button.config(text=lang_dict['reset_button'])

    def _on_server_selection_change(self):
        """서버 선택(라디오 버튼)이 변경될 때 호출되어 해당 서버의 이벤트 목록을 DB에서 로드합니다."""
        selected_server = self.server_var.get()
        db_info = self.server_db_info.get(selected_server)
        lang_dict = LANGUAGES[self.app.lang.get()]
        
        # 이벤트 목록 초기화
        self.event_combobox['values'] = []
        self.search_vars['event_name'].set('')
        
        # DB 파일이 존재할 때만 연결 시도
        if not db_info or not self.db_status.get(selected_server):
            self.event_combobox.config(state='disabled')
            return
        
        # DB 연결 및 데이터 로드 (파일이 존재함이 보장된 상태)
        self.event_combobox.config(state='readonly')
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, db_info['db_path'])
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                query_event_list = f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\""
                cursor.execute(query_event_list)
                # 줄바꿈 문자를 공백으로 바꾸고 양 끝 공백 제거
                event_names = [row[0].replace('\\n', ' ').strip() for row in cursor.fetchall() if row[0]]
            
            self.event_combobox['values'] = event_names
        except sqlite3.Error as e:
            messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=e), parent=self)
            self.event_combobox.config(state='disabled')


    def start_search(self):
        """'검색' 버튼 클릭 시, 검색 작업을 백그라운드 스레드에서 시작합니다."""
        self.app._update_status_bar('status_searching')
        
        # 입력된 검색 조건 수집
        criteria = {key: var.get() for key, var in self.search_vars.items() if var.get()}
        server = self.server_var.get()
        
        # 스레드 생성 및 시작
        thread = threading.Thread(target=self._search_thread, args=(criteria, server))
        thread.daemon = True
        thread.start()
        
        self.destroy() # 검색 창 닫기

    def _search_thread(self, criteria, server):
        """백그라운드에서 실제 검색 로직을 수행하는 스레드 함수."""
        lang_dict = LANGUAGES[self.app.lang.get()]
        try:
            # 초기 파일 목록: 로드된 모든 파일
            initial_matched_files = set(self.all_files_dict.keys())

            # 1. 이벤트 이름으로 필터링 (DB 쿼리)
            if 'event_name' in criteria:
                selected_event_name = criteria.pop('event_name')
                db_info = self.server_db_info.get(server)
                
                # DB 파일이 존재할 때만 연결 시도
                if db_info and self.db_status.get(server):
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    db_path = os.path.join(script_dir, db_info['db_path'])
                    try:
                        with sqlite3.connect(db_path) as conn:
                            cursor = conn.cursor()
                            query = f"SELECT \"{db_info['event_id_col_details']}\" FROM \"{db_info['event_details_table']}\" WHERE \"{db_info['event_info_col_details']}\" LIKE ?"
                            cursor.execute(query, (f"{selected_event_name}%",))
                            
                            # DB에서 찾은 스토리 ID를 파일명 형식으로 변환
                            event_story_ids = {f"storydata_{row[0]}.json" for row in cursor.fetchall()}
                            
                            # 현재 파일 목록과 교집합
                            initial_matched_files.intersection_update(event_story_ids)
                    except sqlite3.Error as e:
                        # 람다에서 예외 객체를 안전하게 캡처
                        self.app.task_queue.put(lambda exc=e: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=exc), parent=self.app.master))
            
            # 2. 나머지 조건으로 필터링 (파일 내용 분석)
            final_matched_files = []
            if not criteria: # 추가 조건이 없으면 현재까지 필터링된 결과 사용
                 final_matched_files = list(initial_matched_files)
            else: # 추가 조건이 있으면 병렬로 파일 내용 검사
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_to_filename = {
                        executor.submit(self._check_file_for_search, filename, criteria): filename 
                        for filename in initial_matched_files
                    }
                    for future in concurrent.futures.as_completed(future_to_filename):
                        if future.result():
                            final_matched_files.append(future_to_filename[future])
            
            # 최종 결과를 콜백 함수를 통해 메인 앱으로 전달
            self.app.task_queue.put(lambda: self.search_callback(sorted(final_matched_files)))

        except Exception as e:
            self.app.task_queue.put(lambda: self._finish_search_error(e))

    def _check_file_for_search(self, filename, criteria):
        """
        병렬 검색을 위한 헬퍼 함수. 단일 파일이 모든 조건을 충족하는지 검사합니다.

        Returns:
            bool: 모든 조건을 만족하면 True, 그렇지 않으면 False.
        """
        # 파일명 조건 검사
        if 'filename' in criteria and criteria['filename'].lower() not in filename.lower():
            return False
        
        # 파일 데이터 캐시에서 로드
        data = self.story_data_cache.get(filename)
        if not data:
            return False

        # 파일명 외의 내용 관련 조건
        content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
        if not content_criteria:
            return True
            
        return self._check_file_content(data, content_criteria)

    def _finish_search_error(self, error):
        """검색 중 오류 발생 시 처리합니다."""
        lang_dict = LANGUAGES[self.app.lang.get()]
        messagebox.showerror(lang_dict['search_error_title'], lang_dict['search_error_msg'].format(e=error), parent=self.app.master)
        self.app._update_status_bar('status_bar_ready')

    def _check_file_content(self, data, criteria):
        """파일 내용(JSON)이 주어진 검색 조건과 일치하는지 확인합니다."""
        lower_criteria = {k: v.lower() for k, v in criteria.items()}
        scene_0 = data.get('0', {}) # 스토리의 메타 정보가 담긴 첫 번째 씬
        
        # title, outline은 scene 0에만 존재
        if 'title' in lower_criteria and lower_criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in lower_criteria and lower_criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        # 씬 단위로 검사해야 하는 조건들
        has_scene_level_criteria = any(k in criteria for k in ['char_name', 'content', 'bgm', 'background'])
        if not has_scene_level_criteria:
            return True

        # 모든 씬을 순회하며 조건 중 하나라도 만족하면 True 반환
        for scene in data.values():
            if self._check_scene(scene, lower_criteria):
                return True
        return False

    def _check_scene(self, scene, criteria):
        """단일 씬이 주어진 검색 조건과 일치하는지 확인합니다."""
        lang_dict = LANGUAGES[self.app.lang.get()]
        # 각 조건 불일치 시 즉시 False 반환
        if 'content' in criteria and not ('print' in scene and criteria['content'] in scene['print'].get('text', '').lower()):
            return False
        if 'bgm' in criteria and not ('bgm' in scene and criteria['bgm'] in str(scene.get('bgm', '')).lower()):
            return False
        if 'background' in criteria and not ('background' in scene and criteria['background'] in str(scene.get('background', '')).lower()):
            return False
        # 캐릭터 이름 검색 로직
        if 'char_name' in criteria:
            char_name_crit = criteria['char_name']
            char_type_search = self.search_vars['char_type'].get()
            char_type_speaker = lang_dict['char_type_speaker']
            
            char_found = False
            if 'print' in scene:
                # 검색 타입이 '화자'일 때
                if char_type_search == char_type_speaker and char_name_crit in str(scene['print'].get('name', '')).lower():
                    char_found = True
                # 검색 타입이 '피호명자'일 때 (대사 내용에서 검색)
                elif char_type_search != char_type_speaker and char_name_crit in scene['print'].get('text', '').lower():
                    char_found = True
            if not char_found:
                return False
        # 모든 조건을 통과하면 True 반환
        return True

    def _reset(self):
        """'초기화' 버튼 클릭 시, 검색 필터를 해제하고 모든 파일을 다시 표시합니다."""
        self.search_callback(list(self.all_files_dict.keys()))
        self.destroy()

# ##################################################################
# Class: ExportWindow
#
# 목적: 스토리 데이터를 다양한 형식으로 내보내기 위한 별도의 Toplevel 창.
#
# 주요 기능:
# 1. 사용자가 내보낼 데이터 종류(스토리, 파일명, 캐릭터명, BGM, 배경, 이벤트 목록)를 체크박스로 선택.
# 2. 이벤트 목록 내보내기는 서버(JP/KR)별로 구분하여 선택 가능하며, 해당 DB 파일 유무에 따라 활성화/비활성화.
# 3. 선택된 데이터들을 지정된 폴더에 각 항목별로 하나의 파일로 저장 (스토리 데이터는 개별 파일).
# 4. 모든 UI 요소는 다국어를 지원.
# ##################################################################
class ExportWindow(tk.Toplevel):
    def __init__(self, app, all_files_dict, story_data_cache, search_data, db_status, server_db_info):
        super().__init__(app.master)
        self.app = app
        self.all_files_dict = all_files_dict
        self.story_data_cache = story_data_cache
        self.search_data = search_data
        self.db_status = db_status
        self.server_db_info = server_db_info

        # 내보내기 옵션 변수
        self.export_options = {
            'story_data': tk.BooleanVar(value=True), # 기본값 True
            'filenames': tk.BooleanVar(value=False),
            'character_names': tk.BooleanVar(value=False),
            'bgm_names': tk.BooleanVar(value=False),
            'background_names': tk.BooleanVar(value=False),
            'event_list_master': tk.BooleanVar(value=False),
            'event_list_jp': tk.BooleanVar(value=False),
            'event_list_kr': tk.BooleanVar(value=False),
        }
        # 스토리 데이터 내보내기 범위 (라디오 버튼용)
        # 'current_list': 현재 목록에 표시된 파일만
        # 'all_loaded': 불러온 모든 파일
        self.story_data_scope = tk.StringVar(value='current_list') 

        self.transient(app.master)
        self.grab_set()
        self._setup_ui()
        self.focus_set()
        self._center_window(400, 420) # 창 크기 조정

        # 초기 상태 설정
        self._toggle_story_data_options() # 스토리 데이터 체크박스 초기 상태에 따라 범위 옵션 활성화/비활성화
        self._toggle_event_list_options() # 이벤트 목록 마스터 체크박스 초기 상태에 따라 하위 옵션 활성화/비활성화


    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        self.options_frame = ttk.LabelFrame(main_frame, text="", padding="10")
        self.options_frame.pack(fill="both", expand=True, pady=(0, 10))

        # 1. 스토리 데이터 체크박스
        self.cb_story_data = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['story_data'],
                                            command=self._toggle_story_data_options)
        self.cb_story_data.pack(anchor="w", pady=2)
        
        # 1-1. 스토리 데이터 내보내기 범위 그룹박스
        self.story_data_scope_frame = ttk.LabelFrame(self.options_frame, text="", padding="5")
        self.story_data_scope_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.story_data_scope_current_list_radio = ttk.Radiobutton(
            self.story_data_scope_frame, text="", variable=self.story_data_scope, value="current_list"
        )
        self.story_data_scope_current_list_radio.pack(anchor="w")

        self.story_data_scope_all_loaded_radio = ttk.Radiobutton(
            self.story_data_scope_frame, text="", variable=self.story_data_scope, value="all_loaded"
        )
        self.story_data_scope_all_loaded_radio.pack(anchor="w")
        
        # 2. 기타 목록 체크박스들
        self.cb_filenames = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['filenames'])
        self.cb_filenames.pack(anchor="w", pady=2)

        self.cb_character_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['character_names'])
        self.cb_character_names.pack(anchor="w", pady=2)

        self.cb_bgm_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['bgm_names'])
        self.cb_bgm_names.pack(anchor="w", pady=2)

        self.cb_background_names = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['background_names'])
        self.cb_background_names.pack(anchor="w", pady=2)
        
        # 3. 이벤트 목록 마스터 체크박스
        self.cb_event_list_master = ttk.Checkbutton(self.options_frame, text="", variable=self.export_options['event_list_master'],
                                                    command=self._toggle_event_list_options)
        self.cb_event_list_master.pack(anchor="w", pady=2)

        # 3-1. 이벤트 목록 그룹박스 (JP/KR 서버)
        self.event_list_group_frame = ttk.LabelFrame(self.options_frame, text="", padding="5")
        self.event_list_group_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.cb_event_list_jp = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_jp'])
        self.cb_event_list_jp.pack(anchor="w", pady=2)
        # 참고: 툴팁은 여기서 추가되며, 상태는 마스터 및 DB 상태에 따라 _toggle_event_list_options에 의해 설정됩니다.
        if not self.db_status.get('JP', False):
            self.cb_event_list_jp.tooltip = ToolTip(self.cb_event_list_jp, text=LANGUAGES[self.app.lang.get()]['export_db_not_found_tooltip'])

        self.cb_event_list_kr = ttk.Checkbutton(self.event_list_group_frame, text="", variable=self.export_options['event_list_kr'])
        self.cb_event_list_kr.pack(anchor="w", pady=2)
        if not self.db_status.get('KR', False):
            self.cb_event_list_kr.tooltip = ToolTip(self.cb_event_list_kr, text=LANGUAGES[self.app.lang.get()]['export_db_not_found_tooltip'])

        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x")

        self.export_button = ttk.Button(button_frame, text="", command=self.start_export)
        self.export_button.pack(side="right")

        self.cancel_button = ttk.Button(button_frame, text="", command=self.destroy)
        self.cancel_button.pack(side="right", padx=(0, 5))

        self._update_ui_text()

    def _toggle_story_data_options(self):
        """스토리 데이터 체크박스 상태에 따라 내보내기 범위 라디오 버튼 활성화/비활성화."""
        is_story_data_selected = self.export_options['story_data'].get()
        state_str = 'normal' if is_story_data_selected else 'disabled'
        
        # 프레임 내의 모든 자식 위젯의 상태를 변경
        for child in self.story_data_scope_frame.winfo_children():
            child.config(state=state_str)
            # 비활성화될 때 라디오 버튼 선택도 해제
        if state_str == 'disabled':
            self.story_data_scope.set('') # 라디오 버튼 선택 해제
        # 스토리 데이터가 선택되었고 아무 라디오 버튼도 선택되지 않았다면 기본값 설정
        elif is_story_data_selected and not self.story_data_scope.get():
            self.story_data_scope.set('current_list')


    def _toggle_event_list_options(self):
        """이벤트 목록 마스터 체크박스 상태에 따라 하위 체크박스들을 활성화/비활성화."""
        is_master_selected = self.export_options['event_list_master'].get()

        # JP 서버 이벤트 목록 체크박스 제어
        jp_can_be_enabled = self.db_status.get('JP', False) # DB 파일 존재 여부
        jp_final_state = 'normal' if is_master_selected and jp_can_be_enabled else 'disabled'
        self.cb_event_list_jp.config(state=jp_final_state)
        if jp_final_state == 'disabled':
            self.export_options['event_list_jp'].set(False) # 비활성화 시 값도 False로 설정

        # KR 서버 이벤트 목록 체크박스 제어
        kr_can_be_enabled = self.db_status.get('KR', False) # DB 파일 존재 여부
        kr_final_state = 'normal' if is_master_selected and kr_can_be_enabled else 'disabled'
        self.cb_event_list_kr.config(state=kr_final_state)
        if kr_final_state == 'disabled':
            self.export_options['event_list_kr'].set(False) # 비활성화 시 값도 False로 설정


    def _update_ui_text(self):
        lang_dict = LANGUAGES[self.app.lang.get()]
        self.title(lang_dict['export_window_title'])
        self.options_frame.config(text=lang_dict['export_type_frame'])
        
        self.cb_story_data.config(text=lang_dict['export_type_story_data'])
        self.story_data_scope_frame.config(text=lang_dict['export_scope_frame']) # 그룹박스 텍스트 업데이트
        self.story_data_scope_current_list_radio.config(text=lang_dict['export_scope_current_list'])
        self.story_data_scope_all_loaded_radio.config(text=lang_dict['export_scope_all_loaded'])

        self.cb_filenames.config(text=lang_dict['export_type_filenames'])
        self.cb_character_names.config(text=lang_dict['export_type_character_names'])
        self.cb_bgm_names.config(text=lang_dict['export_type_bgm_names'])
        self.cb_background_names.config(text=lang_dict['export_type_background_names'])
        
        self.cb_event_list_master.config(text=lang_dict['export_type_event_list_master']) # 마스터 체크박스 텍스트 업데이트
        self.event_list_group_frame.config(text=lang_dict['export_type_event_list_frame']) # 그룹박스 텍스트 업데이트
        self.cb_event_list_jp.config(text=lang_dict['export_type_event_list_jp'])
        self.cb_event_list_kr.config(text=lang_dict['export_type_event_list_kr'])
        
        self.export_button.config(text=lang_dict['export_button_text'])
        self.cancel_button.config(text=lang_dict['cancel_button_text'])

        # 툴팁 텍스트 업데이트 (툴팁 객체가 있을 경우에만)
        if not self.db_status.get('JP', False) and hasattr(self.cb_event_list_jp, 'tooltip'):
            self.cb_event_list_jp.tooltip.text = lang_dict['export_db_not_found_tooltip']
        if not self.db_status.get('KR', False) and hasattr(self.cb_event_list_kr, 'tooltip'):
            self.cb_event_list_kr.tooltip.text = lang_dict['export_db_not_found_tooltip']


    def start_export(self):
        lang_dict = LANGUAGES[self.app.lang.get()]
        # 각 BooleanVar의 현재 값을 가져옴 (disabled 상태이면 False로 설정되어 있음)
        selected_options = {k: v.get() for k, v in self.export_options.items()}
        
        # 스토리 데이터 내보내기가 선택된 경우에만 범위 값을 전달
        selected_options['story_data_scope'] = self.story_data_scope.get() if selected_options['story_data'] else None

        # 어떤 내보내기 항목이든 하나라도 True인지 확인
        # 'story_data_scope'는 내보내기 항목 자체가 아니므로 제외
        # 'event_list_master'도 실제 내보낼 항목이 아니라 하위 항목 제어용이므로 제외
        actual_selected_exports = {k: v for k,v in selected_options.items() if k not in ['story_data_scope', 'event_list_master']}

        if not any(actual_selected_exports.values()):
            messagebox.showwarning(lang_dict['msgbox_export_options_title'], lang_dict['msgbox_no_export_types_selected'], parent=self)
            return

        output_folder = filedialog.askdirectory(title=lang_dict['msgbox_export_folder_title'], parent=self)
        if not output_folder:
            return

        self.app._update_status_bar('status_bar_export_prep')
        self.app.file_menu.entryconfig(3, state="disabled") # 내보내기 버튼 비활성화
        
        # 내보내기 스레드 시작
        thread = threading.Thread(target=self.app._export_master_thread, args=(selected_options, output_folder))
        thread.daemon = True
        thread.start()
        
        self.destroy() # 내보내기 창 닫기


# ##################################################################
# Class: StoryViewerApp
#
# 목적: storydata JSON 파일을 보고 검색하는 메인 애플리케이션 클래스.
#
# 주요 기능:
# 1. 파일/폴더를 열어 storydata(.json) 파일들을 로드 및 분석.
# 2. 로드된 파일 목록을 UI에 표시 (파일명 또는 스토리 제목 기준).
# 3. 선택된 스토리의 상세 내용을 포맷팅하여 뷰어에 표시 (간단/상세 보기).
# 4. 고급 검색 창(SearchWindow)을 통해 다양한 조건으로 스토리 필터링.
# 5. 표시된 스토리를 텍스트 파일로 내보내기.
# 6. 모든 작업은 비동기적으로 처리하여 UI 멈춤 현상 방지.
# ##################################################################
class StoryViewerApp:
    def __init__(self, master):
        """
        StoryViewerApp 인스턴스를 초기화합니다.

        Args:
            master (tk.Tk): Tkinter의 최상위 창(root 윈도우).
        """
        self.master = master # Tkinter의 최상위 창(root 윈도우)
        self.all_files = {} # {파일명: 전체 경로}
        self.story_data_cache = {} # {파일명: JSON 데이터}
        self.search_data = {} # {검색 필드: [값 목록]}
        self.file_titles = {} # {파일명: 스토리 제목}
        self.display_name_to_filename = {} # {표시 이름: 원본 파일명}
        self.current_filenames_in_list = [] # 현재 리스트에 표시된 파일명 목록 (검색 결과에 따라 달라짐)
        self.loaded_filenames = [] # 로드된 모든 파일명 (검색 필터와 무관)
        self.current_file_path = None # 현재 선택된 파일의 전체 경로
        self.is_loading = False # 파일 로딩 중 여부 플래그
        self.task_queue = queue.Queue() # UI 업데이트 작업을 위한 큐

        # UI 상태 변수
        self.lang = tk.StringVar(value='ko')
        self.lang.trace_add('write', self._on_language_change)
        self.display_mode_var = tk.StringVar(value="original") # 파일 목록 표시 모드 (파일명/제목)
        self.view_mode_var = tk.StringVar(value="simple") # 스토리 상세 보기 모드 (간단/상세)

        # DB 관련 상태
        self.db_status = {} # {서버: 존재 여부(bool)}
        self.db_check_done = False
        self.db_warning_shown = False # DB 경고 메시지를 한 번만 표시하기 위한 플래그

        # 서버별 DB 정보
        self.server_db_info = {
            'JP': {
                'db_path': 'master_jp.db',
                'event_list_table': 'v1_8931e2893a2d2290dbf498046bc66faafeebc40b6764dd69334ad51f5aca2e9f', # 1. 일본 서버 이벤트 목록 정보가 있는 테이블 이름
                'event_name_col_list': 'e3f0f79d746654f52125f3c28eb487d9e102f02077fe104d1423f08e80e056e3', # 1-1. 일본 서버 이벤트 목록의 이름이 있는 열
                'event_details_table': 'v1_04d08b8c6bf704241326eca45b6d63cc1a6dd38d03ff256df15b8ec8d4cd2649', # 2. 일본 서버 이벤트의 스토리 데이터 정보가 있는 테이블 이름
                'event_info_col_details': '20d0bf56a9ca7d14b3172ac4dd383fee10c010d4ecd30c9854302d10390d774e', # 2-1. 일본 서버 이벤트 스토리의 이름이 있는 열
                'event_id_col_details': '69d3bbead1844607ef41ecb520a4d5385cae02eddca377aa13721ec7fd01e0ec' # 2-2. 일본 서버 이벤트 스토리의 고유 ID값이 있는 열
            },
            'KR': {
                'db_path': 'master_kr.db',
                'event_list_table': 'v1_4e380b72af2e31867844884ba838095ad9ea8f02bf83037a3c8ed47b8943f164', # 1. 한국 서버 이벤트 목록 정보가 있는 테이블 이름
                'event_name_col_list': 'abb720eaefdc23b376dc5b817b683e633eb66fe9a3941025ae27413c56d56fad', # 1-1. 한국 서버 이벤트 목록의 이름이 있는 열
                'event_details_table': 'v1_ebabad5e41c1f71b3e5d705a8fe81411012e124827b4cbde3dfb2469674f598f', # 2. 한국 서버 이벤트의 스토리 데이터 정보가 있는 테이블 이름
                'event_info_col_details': '45d39837db60a2b9aca5a03c3c17a9999201e08e97c3cff92bb95786dd344355', # 2-1. 한국 서버 이벤트 스토리의 이름이 있는 열
                'event_id_col_details': '9a0ef39c5ee7f28590676ed2b6b857c10aad6d01983252fa6b978b0cb3991880' # 2-2. 한국 서버 이벤트 스토리의 고유 ID값이 있는 열
            }
        }

        # 상세 보기 시 필드 정렬 순서
        self.field_order = [
            # 2025-07-22 storydata 기준 (JP, KR 검증 완료)
            # 파트 1: {0} 그룹의 모든 데이터 (중복 제외)
            'title', 'outline', 'movie', 'shake_anime', 'place',

            # 파트 2: {1} ~ {n} 그룹의 모든 데이터 (원본 순서 기준)
            'vo', 'face', 'print', 'nod', 'wait', 'window_visible', 'change', 'chara_full', 
            'fadein', 'focus', 'jump', 'fadeout_all', 'fadeout', 'pop', 'voice_effect', 
            'change_window', 'ignore_bgm', 'eye_open', 'emotion', 'se', 'fadein_all', 
            'effect', 'effect_delete', 'se_pause', 'multi_lipsync', 'bgm', 'tag', 
            'choice', 'goto', 'text_size', 'ui_visible', 'black_out', 'bright_change', 
            'background', 'situation', 'bg_pan', 'env_stop', 'env', 'background_color', 
            'shake', 'sway', 'out_l', 'in_r', 'character_up_down', 'pan', 'camera_zoom', 
            'still', 'still_unit', 'still_move', 'still_normalize', 'background_blur', 
            'unknown'
        ]
        self.setup_ui() # UI 구성
        self.setup_text_tags() # 텍스트 뷰어 스타일 설정
        self._center_window(800, 600) # 창 중앙 정렬
        self.master.after(100, self._process_queue) # 비동기 작업 큐 처리 시작
        self._update_ui_text() # UI 텍스트 초기화
        self._update_status_bar('status_bar_initial') # 상태 표시줄 초기 메시지 설정

    def _center_window(self, width, height):
        """윈도우를 화면 중앙에 배치합니다."""
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def setup_ui(self):
        """메인 창의 UI 위젯들을 생성하고 배치합니다."""
        self.master.geometry("800x600")
        self.create_menu()
        self.master.grid_rowconfigure(1, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        
        # 옵션 그룹
        self.options_group = ttk.LabelFrame(self.master, text="")
        self.options_group.grid(row=0, column=0, sticky="ew", padx=10, pady=(5,0))
        self.options_group.columnconfigure(0, weight=1)
        self.options_group.columnconfigure(1, weight=1)

        # 파일 목록 옵션
        self.file_options_group = ttk.LabelFrame(self.options_group, text="", padding=5)
        self.file_options_group.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        self.display_orig_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="original", command=self._on_display_mode_change)
        self.display_orig_radio.grid(row=0, column=0, padx=5)
        self.display_title_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="title", command=self._on_display_mode_change)
        self.display_title_radio.grid(row=0, column=1, padx=5)

        # 상세 정보 옵션
        self.detail_options_group = ttk.LabelFrame(self.options_group, text="", padding=5)
        self.detail_options_group.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.view_simple_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="simple", command=self._on_view_mode_change)
        self.view_simple_radio.grid(row=0, column=0, padx=5)
        self.view_detailed_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="detailed", command=self._on_view_mode_change)
        self.view_detailed_radio.grid(row=0, column=1, padx=5)

        # 메인 프레임 (PanedWindow)
        main_frame = ttk.Frame(self.master, padding=(10, 5, 10, 0)) 
        main_frame.grid(row=1, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True)
        left_weight, right_weight = 1, 2

        # 왼쪽 패널 (파일 목록)
        self.left_group = ttk.LabelFrame(self.paned_window, text="", padding=5)
        self.paned_window.add(self.left_group, weight=left_weight) 
        self.left_group.grid_rowconfigure(1, weight=1)
        self.left_group.grid_columnconfigure(0, weight=1)

        self.search_button = ttk.Button(self.left_group, text="", command=self.open_search_window, state="disabled") # 초기 상태 비활성화
        self.search_button.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        list_frame_inner = ttk.Frame(self.left_group)
        list_frame_inner.grid(row=1, column=0, sticky="nsew")
        list_frame_inner.grid_rowconfigure(0, weight=1)
        list_frame_inner.grid_columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame_inner, selectmode=tk.SINGLE)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        list_scrollbar = ttk.Scrollbar(list_frame_inner, orient=tk.VERTICAL, command=self.file_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=list_scrollbar.set)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        
        # 오른쪽 패널 (스토리 상세 정보)
        self.right_group = ttk.LabelFrame(self.paned_window, text="", padding=5)
        self.paned_window.add(self.right_group, weight=right_weight)
        self.right_group.grid_rowconfigure(0, weight=1)
        self.right_group.grid_columnconfigure(0, weight=1)
        
        text_frame_inner = ttk.Frame(self.right_group)
        text_frame_inner.grid(row=0, column=0, sticky="nsew")
        text_frame_inner.grid_rowconfigure(0, weight=1)
        text_frame_inner.grid_columnconfigure(0, weight=1)
        
        self.story_text = tk.Text(text_frame_inner, wrap=tk.WORD, state=tk.DISABLED, spacing1=2, padx=10, pady=10)
        self.story_text.grid(row=0, column=0, sticky="nsew")
        text_scrollbar = ttk.Scrollbar(text_frame_inner, orient=tk.VERTICAL, command=self.story_text.yview)
        text_scrollbar.grid(row=0, column=1, sticky="ns")
        self.story_text.config(yscrollcommand=text_scrollbar.set)

        # 상태 표시줄
        self.status_bar = ttk.Label(self.master, text="", anchor=tk.W, padding=5)
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        # PanedWindow 비율 유지를 위한 이벤트 바인딩
        def reapply_weights(event=None):
            try:
                total_width = self.paned_window.winfo_width()
                sash_position = int(total_width * left_weight / (left_weight + right_weight))
                self.paned_window.sashpos(0, sash_position)
                self.paned_window.unbind("<Configure>") # 한 번만 실행
            except tk.TclError: pass
        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self):
        """스토리 상세 정보 뷰어의 텍스트 스타일(태그)을 설정합니다."""
        default_font_family = font.nametofont("TkDefaultFont").cget("family")
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A')
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000')
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')
    
    def create_menu(self):
        """메인 메뉴 바를 생성하고 설정합니다."""
        self.menu_bar = tk.Menu(self.master)
        
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)
        
        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)
        self.menu_bar.add_command(label="", command=self._show_about_dialog)

        self.file_menu.add_command(label="", command=self.open_files)
        self.file_menu.add_command(label="", command=self.open_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="", command=self.open_export_window, state="disabled") # open_export_window로 변경
        self.file_menu.add_separator()
        self.file_menu.add_command(label="", command=self.master.quit)
        
        self.lang_menu.add_radiobutton(label=LANGUAGES['ko']['lang_ko'], variable=self.lang, value='ko')
        self.lang_menu.add_radiobutton(label=LANGUAGES['en']['lang_en'], variable=self.lang, value='en')
        self.lang_menu.add_radiobutton(label=LANGUAGES['ja']['lang_ja'], variable=self.lang, value='ja')
        
        self.master.config(menu=self.menu_bar)

    def _on_language_change(self, *args):
        """언어 변경 시 UI 텍스트 업데이트 및 표시 내용 재구성을 호출합니다."""
        self._update_ui_text()
        self._on_display_mode_change(force_update=True) # 파일 목록 다시 그리기
        self._on_view_mode_change(force_update=True) # 상세 정보 다시 그리기


    def _update_ui_text(self):
        """UI의 모든 텍스트 요소를 현재 선택된 언어로 갱신합니다."""
        lang_dict = LANGUAGES[self.lang.get()]

        self.master.title(lang_dict['window_title'])
        self.menu_bar.entryconfig(1, label=lang_dict['menu_file'])
        self.menu_bar.entryconfig(2, label=lang_dict['menu_lang'])
        self.menu_bar.entryconfig(3, label=lang_dict['menu_about'])

        self.file_menu.entryconfig(0, label=lang_dict['file_open'])
        self.file_menu.entryconfig(1, label=lang_dict['folder_open'])
        self.file_menu.entryconfig(3, label=lang_dict['export'])
        self.file_menu.entryconfig(5, label=lang_dict['exit'])

        self.options_group.config(text=lang_dict['options_group'])
        self.file_options_group.config(text=lang_dict['file_options_group'])
        self.detail_options_group.config(text=lang_dict['detail_options_group'])
        self.display_orig_radio.config(text=lang_dict['display_original_filename'])
        self.display_title_radio.config(text=lang_dict['display_title'])
        self.view_simple_radio.config(text=lang_dict['view_simple'])
        self.view_detailed_radio.config(text=lang_dict['view_detailed'])
        self.left_group.config(text=lang_dict['list_group_title'])
        self.right_group.config(text=lang_dict['detail_group_title'])
        self.search_button.config(text=lang_dict['search_button_text'])
        
        # 현재 목록이 있으면 언어 변경에 맞춰 다시 표시
        self.update_file_list(self.current_filenames_in_list)


    def _update_status_bar(self, key, **kwargs):
        """상태 표시줄의 메시지를 업데이트합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        message = lang_dict.get(key, "...")
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError:
                pass
        self.status_bar.config(text=message)
        
    def _show_about_dialog(self):
        """'정보' 대화상자를 표시합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        title = lang_dict['about_header']
        
        info_lines = []
        for key, value in ABOUT_INFO.items():
            label_key = f'about_label_{key}'
            label_text = lang_dict.get(label_key, key.capitalize())
            info_lines.append(f"{label_text}: {value}")
            
        message = "\n".join(info_lines)
        messagebox.showinfo(title, message, parent=self.master)

    def _process_queue(self):
        """주기적으로 태스크 큐를 확인하고, UI 관련 작업을 메인 스레드에서 실행합니다."""
        try:
            while True:
                task = self.task_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self._process_queue) # 다음 확인 예약

    def _clear_workspace(self):
        """새로운 파일을 로드하기 전에 모든 데이터와 UI 상태를 초기화합니다."""
        self.update_story_text([])
        self.all_files.clear()
        self.story_data_cache.clear()
        self.search_data.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.search_button.config(state="disabled")
        self.file_menu.entryconfig(3, state="disabled")
        self.db_status.clear()
        self.db_check_done = False
        self.db_warning_shown = False

    def _is_valid_storydata(self, file_path):
        """
        주어진 파일이 유효한 storydata JSON 형식인지 검사합니다.

        Returns:
            tuple: (is_valid, data, error_reason)
                   - is_valid (bool): 유효성 여부.
                   - data (dict | None): 유효한 경우 파싱된 JSON 데이터.
                   - error_reason (str | None): 유효하지 않은 경우 원인.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 데이터가 비어있거나 딕셔너리 형태가 아니면 유효하지 않음
            if not isinstance(data, dict) or not data:
                return False, None, "File content is empty or not in dictionary format"
            # 모든 키가 숫자이고 값이 딕셔너리인지 검사 (storydata 구조)
            # 첫 번째 키가 0이고 'title' 또는 'outline'이 있는지 확인 (선택적)
            if '0' in data and isinstance(data['0'], dict) and ('title' in data['0'] or 'outline' in data['0']):
                return True, data, None
            else:
                return False, None, "Does not seem to be a storydata file (missing '0' key or title/outline)"
        except json.JSONDecodeError as e:
            return False, None, f"JSON format error: {e}"
        except Exception as e:
            return False, None, f"File read/other error: {e}"

    def _start_loading_task(self, paths=None, folder_path=None):
        """파일 로딩 및 분석을 위한 백그라운드 스레드를 시작합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return
        self._clear_workspace()
        self.is_loading = True
        self._update_status_bar('status_bar_loading_start')
        # 로딩 중 메뉴 비활성화
        self.file_menu.entryconfig(0, state="disabled")
        self.file_menu.entryconfig(1, state="disabled")
        # 스레드 생성 및 시작
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path))
        thread.daemon = True
        thread.start()

    def open_files(self):
        """'파일 열기' 메뉴를 통해 storydata 파일들을 선택하고 로딩을 시작합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[(lang_dict.get('filetype_json', "JSON Files"), "*.json"), (lang_dict.get('filetype_all', "All Files"), "*.*")]
        )
        if file_paths:
            self._start_loading_task(paths=file_paths)

    def open_folder(self):
        """'폴더 열기' 메뉴를 통해 폴더 내의 storydata 파일들을 로딩합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        folder_path = filedialog.askdirectory(title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files"))
        if folder_path:
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths, folder_path):
        """백그라운드에서 파일 로드, 유효성 검사, 내용 분석을 수행하는 스레드 함수."""
        temp_all_files, temp_story_cache, invalid_files = {}, {}, []
        
        # 중복 파일명 처리 로직
        file_candidates = {} # {파일명: [경로1, 경로2, ...]} 형식으로 후보 수집
        pattern = re.compile(r'^storydata_\d{7}\.json$')

        # 1. '파일 열기'로 선택된 경로 수집 (단일 파일 선택도 중복 처리 로직에 포함)
        if paths:
            for path in paths:
                filename = os.path.basename(path)
                if pattern.match(filename):
                    if filename not in file_candidates:
                        file_candidates[filename] = []
                    file_candidates[filename].append(path)

        # 2. '폴더 열기'로 선택된 경로 수집
        if folder_path:
            for dirpath, _, filenames in os.walk(folder_path):
                for filename in filenames:
                    if pattern.match(filename):
                        full_path = os.path.join(dirpath, filename)
                        if filename not in file_candidates:
                            file_candidates[filename] = []
                        file_candidates[filename].append(full_path)
        
        # 3. 후보군 중에서 최종 처리할 파일 목록 선택 (중복 시 파일 크기가 큰 것으로)
        file_list_to_process = []
        for filename, path_list in file_candidates.items():
            if len(path_list) > 1:
                try:
                    # 파일 크기가 가장 큰 경로를 선택
                    winner_path = max(path_list, key=os.path.getsize)
                    file_list_to_process.append(winner_path)
                except FileNotFoundError:
                    # 파일 검색과 처리 사이에 파일이 삭제될 경우를 대비한 예외 처리
                    pass 
            elif path_list:
                file_list_to_process.append(path_list[0])
        
        file_list_to_process.sort() # 일관된 순서를 위해 정렬
        
        # 파일 유효성 검사 및 분석
        total_files = len(file_list_to_process)
        for i, path in enumerate(file_list_to_process):
            self.task_queue.put(lambda i=i, t=total_files: self._update_status_bar('status_bar_analyzing', i=i+1, t=t))
            is_valid, data, error_reason = self._is_valid_storydata(path)
            
            if is_valid:
                filename = os.path.basename(path)
                temp_all_files[filename] = path
                temp_story_cache[filename] = data
            else:
                invalid_files.append((path, error_reason))
        
        # 유효한 파일이 없는 경우 즉시 종료
        if not temp_all_files:
            self.task_queue.put(lambda: self._finish_loading(None, invalid_files))
            return

        # 검색 데이터(Combobox 목록) 추출
        unique_char_names, unique_bgms, unique_bgs, temp_file_titles = set(), set(), set(), {}
        def _extract_asset_name(value):
            if isinstance(value, str): return value
            if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
            return None

        for filename, data in temp_story_cache.items():
            # 파일 제목 추출
            title = data.get('0', {}).get('title', '').strip()
            temp_file_titles[filename] = title if title else filename
            # 캐릭터 이름, BGM, 배경 추출
            for scene in data.values():
                if 'print' in scene and 'name' in scene['print'] and (name := str(scene['print']['name']).strip()): unique_char_names.add(name)
                if 'bgm' in scene and (bgm_name := _extract_asset_name(scene['bgm'])): unique_bgms.add(bgm_name)
                if 'background' in scene and (bg_name := _extract_asset_name(scene['background'])): unique_bgs.add(bg_name)

        # 최종 결과 정리
        temp_search_data = {
            'filenames': sorted(list(temp_all_files.keys())), 
            'character_names': sorted(list(unique_char_names)), 
            'bgms': sorted(list(unique_bgms)), 
            'backgrounds': sorted(list(unique_bgs))
        }
        results = {"all_files": temp_all_files, "cache": temp_story_cache, "titles": temp_file_titles, "search_data": temp_search_data}
        # 결과를 UI 스레드로 전달
        self.task_queue.put(lambda: self._finish_loading(results, invalid_files))

    def _finish_loading(self, results, invalid_files):
        """파일 로딩 스레드 종료 후, UI에 결과를 반영하고 상태를 업데이트합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        self.is_loading = False
        self.file_menu.entryconfig(0, state="normal")
        self.file_menu.entryconfig(1, state="normal")
        if not results:
            self._update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'])
        else:
            # 로드된 데이터 저장
            self.all_files, self.story_data_cache, self.file_titles, self.search_data = results['all_files'], results['cache'], results['titles'], results['search_data']
            self.loaded_filenames = sorted(list(self.all_files.keys())) # 로드된 모든 파일명 저장
            self._update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))
            self.search_button.config(state="normal")
            self.file_menu.entryconfig(3, state="normal") # 내보내기 메뉴 활성화
            self.update_file_list(list(self.all_files.keys())) # 초기에는 모든 파일을 목록에 표시
        
        # 유효하지 않은 파일이 있었을 경우 로그 저장 여부 확인
        if invalid_files:
            msg = lang_dict['msgbox_load_fail_msg'].format(count=len(invalid_files))
            if messagebox.askyesno(lang_dict['msgbox_load_fail_title'], msg):
                log_filename = "invalid_storydata_log.txt"
                try:
                    with open(log_filename, 'w', encoding='utf-8') as f:
                        f.write(lang_dict['log_header'].format(timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                        f.write(lang_dict['log_total_failed'].format(count=len(invalid_files)))
                        f.write("-" * 50 + "\n\n")
                        for path, reason in invalid_files:
                            f.write(f"{lang_dict['log_file_label']}: {path}\n")
                            f.write(f"{lang_dict['log_reason_label']}: {reason}\n")
                            f.write("-" * 30 + "\n")
                    messagebox.showinfo(lang_dict['msgbox_log_saved_title'], lang_dict['msgbox_log_saved_msg'].format(filename=log_filename))
                except Exception as e:
                    messagebox.showerror(lang_dict['msgbox_log_save_error_title'], lang_dict['msgbox_log_save_error_msg'].format(e=e))

    def _check_and_cache_db_status(self):
        """DB 파일 존재 여부를 확인하고, 누락 시 경고를 한 번만 표시합니다."""
        if self.db_check_done: return
        
        lang_dict = LANGUAGES[self.lang.get()]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        missing_db_paths = []
        
        for server, info in self.server_db_info.items():
            db_path = os.path.join(script_dir, info['db_path'])
            exists = os.path.exists(db_path)
            self.db_status[server] = exists
            if not exists:
                missing_db_paths.append(info['db_path'])

        # DB 파일이 하나라도 없고, 아직 경고를 표시하지 않았다면
        if missing_db_paths and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_paths)
            messagebox.showwarning(
                lang_dict['db_not_found_title'], 
                lang_dict['db_not_found_msg'].format(paths=paths_str),
                parent=self.master
            )
            self.db_warning_shown = True # 경고 표시 완료 플래그 설정

        self.db_check_done = True


    def open_search_window(self):
        """'고급 검색' 버튼 클릭 시 검색 창을 엽니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_search_before_load_title'], lang_dict['msgbox_search_before_load_msg'])
            return
        
        self._check_and_cache_db_status() # DB 상태 확인 및 1회 경고
        
        SearchWindow(app=self, all_files_dict=self.all_files, story_data_cache=self.story_data_cache, search_callback=self.update_file_list, search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)

    def open_export_window(self):
        """'내보내기' 메뉴를 통해 ExportWindow를 엽니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_no_export_files_title'], lang_dict['msgbox_no_export_files_msg'])
            return
            
        self._check_and_cache_db_status() # DB 상태 확인 및 1회 경고
        
        ExportWindow(app=self, all_files_dict=self.all_files, story_data_cache=self.story_data_cache, 
                     search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)


    def update_file_list(self, filenames):
        """주어진 파일명 목록으로 파일 리스트 UI(Listbox)를 업데이트합니다."""
        self.update_story_text([])
        self.current_file_path = None
        self.current_filenames_in_list = sorted(filenames)
        self.display_name_to_filename.clear()
        self.file_listbox.delete(0, tk.END)
        total, chunk_size = len(self.current_filenames_in_list), 200 # 대용량 목록 성능을 위한 청크 처리
        
        def _populate_list(index=0):
            if index >= total:
                self._update_status_bar('status_bar_list_updated', count=total)
                if total > 0:
                    self.file_listbox.selection_set(0) # 첫 항목 자동 선택
                    self.file_listbox.event_generate("<<ListboxSelect>>") # 선택 이벤트 강제 발생
                else:
                    self._update_status_bar('status_bar_ready')
                return
            self._update_status_bar('status_bar_list_updating', i=index + 1, t=total)
            end_index = min(index + chunk_size, total)
            display_mode = self.display_mode_var.get()
            display_chunk = []
            for i in range(index, end_index):
                filename = self.current_filenames_in_list[i]
                display_name = filename
                if display_mode == 'title':
                    if title := self.file_titles.get(filename, filename):
                        display_name = f"{title}"
                display_chunk.append(display_name)
                self.display_name_to_filename[display_name] = filename
            self.file_listbox.insert(tk.END, *display_chunk)
            self.master.after(1, lambda: _populate_list(end_index)) # 다음 청크 처리 예약
        _populate_list()

    def on_file_select(self, event):
        """파일 리스트에서 항목을 선택했을 때 호출되어 상세 정보를 표시합니다."""
        if not self.file_listbox.curselection(): return
        try:
            display_name = self.file_listbox.get(self.file_listbox.curselection()[0])
        except tk.TclError: return
        if filename := self.display_name_to_filename.get(display_name):
            self.current_file_path = self.all_files.get(filename)
            if data := self.story_data_cache.get(filename):
                self.update_story_text(self.format_story_data(data))
                self._update_status_bar('status_bar_displaying', filename=filename)
            else:
                self._update_status_bar('status_bar_cache_error', filename=filename)

    def _on_display_mode_change(self, force_update=False):
        """파일 목록 표시 모드(파일명/제목) 변경 시 호출됩니다."""
        if not force_update and self.is_loading: return
        self.update_file_list(self.current_filenames_in_list)

    def _on_view_mode_change(self, force_update=False):
        """상세 정보 보기 모드(간단/상세) 변경 시 호출됩니다."""
        if not force_update and self.is_loading: return
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            if data := self.story_data_cache.get(filename):
                self.update_story_text(self.format_story_data(data))

    def format_story_data(self, data):
        """
        JSON 데이터를 UI에 표시하기 좋은 형태의 (텍스트, 태그) 튜플 리스트로 포맷팅합니다.

        Returns:
            list: [(text, tag), (text, tag), ...] 형태의 리스트.
        """
        content_list = []
        view_mode = self.view_mode_var.get()
        # 씬 키가 정수형이 되도록 하여 정렬
        scene_keys = sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf')) 
        
        for key in scene_keys:
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            if view_mode == 'simple':
                keys_to_display = [k for k in ['title', 'outline', 'vo', 'print'] if k in scene]
            else: # 상세 보기 시 정의된 순서대로 정렬
                # field_order에 없는 키는 목록 마지막에 알파벳 순으로 추가
                existing_keys = [k for k in self.field_order if k in scene]
                other_keys = sorted([k for k in scene.keys() if k not in self.field_order])
                keys_to_display = existing_keys + other_keys

            for field in keys_to_display:
                value = scene[field]
                content_list.append(("    " + f"{field}\n", 'key'))
                # 필드 이름에 따라 적절한 포맷터 호출
                formatter = getattr(self, f'_format_{field}', self._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append(("-"*60 + "\n\n", None))
        return content_list

    # --- 각 필드별 포맷터 함수들 ---
    def _format_print(self, value, content_list):
        indent = "        "
        name, text = str(value.get('name', '???')), value.get('text', '')
        formatted_text = text.replace('\n', '\n' + indent)
        content_list.extend([(indent + f"- name: {name}\n", 'print_sub_key'), (indent + f"- text: “{formatted_text}”\n", 'print_sub_key')])
    def _format_chara_full(self, v, c): self._format_generic_id_list(v, c)
    def _format_fadein(self, v, c): self._format_generic_id_list(v, c)
    def _format_fadeout(self, v, c): self._format_generic_id_list(v, c)
    def _format_face(self, v, c): self._format_generic_id_list(v, c)
    def _format_nod(self, v, c): self._format_simple_id_list(v, c)
    def _format_shake(self, v, c): self._format_simple_id_list(v, c)
    def _format_focus(self, v, c): self._format_simple_id_list(v, c)
    def _format_choice(self, value, content_list):
        indent = "        "
        for i, item in enumerate(value, 1):
            content_list.extend([(indent + f"{i}. {item['text']}", 'choice'), (f" (→ S# {item['tag']})\n", 'choice_tag')])
    def _format_default(self, value, content_list):
        content_list.append(("        " + f"{str(value)}\n", 'value'))
    def _format_generic_id_list(self, value, content_list):
        indent = "        "
        if not isinstance(value, list):
            self._format_default(value, content_list)
            return
        for item in value:
            if isinstance(item, list) and item:
                details = ", ".join(map(str, item[1:]))
                content_list.extend([(indent + f"- {str(item[0])}", 'value'), (f" ({details})\n" if details else "\n", 'value')])
            else:
                content_list.append((indent + f"- {str(item)}\n", 'value'))
    def _format_simple_id_list(self, value, content_list):
        indent = "        "
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {str(item)}\n", 'value'))

    def update_story_text(self, content_list):
        """포맷팅된 콘텐츠 리스트를 받아 텍스트 뷰어에 렌더링합니다."""
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)

    # --- 내보내기 기능 관련 메서드 ---
    def _get_all_filenames(self):
        return sorted(list(self.loaded_filenames))

    def _get_all_character_names(self):
        return sorted(self.search_data.get('character_names', []))

    def _get_all_bgm_names(self):
        return sorted(self.search_data.get('bgms', []))

    def _get_all_background_names(self):
        return sorted(self.search_data.get('backgrounds', []))

    def _get_event_list_from_db(self, server_key):
        lang_dict = LANGUAGES[self.lang.get()]
        db_info = self.server_db_info.get(server_key)
        
        # DB 파일이 없을 경우, 연결 시도 없이 즉시 빈 리스트 반환
        if not db_info or not self.db_status.get(server_key):
            return []

        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, db_info['db_path'])
        
        event_names = []
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                query = f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\""
                cursor.execute(query)
                event_names = [row[0].replace('\\n', ' ').strip() for row in cursor.fetchall() if row[0]]
            return sorted(event_names)
        except sqlite3.Error as e:
            # 람다에서 예외 객체를 안전하게 캡처 (exc=e)
            self.task_queue.put(lambda exc=e: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=exc), parent=self.master))
            return []
        except Exception as e:
            # 람다에서 예외 객체를 안전하게 캡처 (exc=e)
            self.task_queue.put(lambda exc=e: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=exc), parent=self.master))
            return []

    def _save_list_to_file(self, data_list, filename_suffix, output_folder, header_text):
        """범용적으로 리스트 데이터를 파일로 저장하는 헬퍼 함수."""
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    for item in data_list:
                        f.write(f"{item}\n")
                else:
                    f.write(f"(No data found for {filename_suffix})\n")
            return True, None
        except Exception as e:
            return False, e

    def _export_master_thread(self, selected_options, output_folder):
        """백그라운드에서 모든 선택된 내보내기 작업을 총괄하여 수행합니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []

        # 스토리 데이터 내보내기 로직 (범위 옵션에 따라 달라짐)
        if selected_options['story_data']:
            story_data_scope = selected_options['story_data_scope']
            filenames_to_export = []
            if story_data_scope == 'current_list':
                filenames_to_export = self.current_filenames_in_list
            elif story_data_scope == 'all_loaded':
                filenames_to_export = self.loaded_filenames # 모든 로드된 파일 사용
            
            # 파일이 없으면 내보내기 건너뛰기
            if not filenames_to_export:
                export_results['story_data'] = {'success': 0, 'failed': 0, 'details': ["No story data files selected for export."]}
                # 상태바 업데이트는 각 항목 완료 후에 총괄로 이루어지므로 이 부분은 생략
            else:
                type_name = lang_dict.get('export_type_story_data', 'Story Data')
                success_count = 0
                fail_count = 0
                current_failed_details = []

                for i, filename in enumerate(filenames_to_export):
                    self.task_queue.put(lambda tn=type_name, s=success_count, f=fail_count, i=i, tf=len(filenames_to_export): self._update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=i+1, t=tf))
                    data = self.story_data_cache.get(filename)
                    if not data:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Cache Miss)")
                        continue
                    output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".txt")
                    try:
                        text_to_write = "".join([text for text, _ in self.format_story_data(data)])
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(text_to_write)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Error: {e})")
                
                export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)


        # 기타 목록 내보내기 로직
        other_export_types = [
            {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': self._get_all_filenames, 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
            {'type': 'character_names', 'name_key': 'export_type_character_names', 'data_func': self._get_all_character_names, 'file_suffix': 'character_names', 'header_key': 'export_type_character_names'},
            {'type': 'bgm_names', 'name_key': 'export_type_bgm_names', 'data_func': self._get_all_bgm_names, 'file_suffix': 'bgm_names', 'header_key': 'export_type_bgm_names'},
            {'type': 'background_names', 'name_key': 'export_type_background_names', 'data_func': self._get_all_background_names, 'file_suffix': 'background_names', 'header_key': 'export_type_background_names'},
        ]
        
        for task in other_export_types:
            task_type = task['type']
            if not selected_options[task_type]: # ExportWindow에서 선택되지 않은 항목은 건너뛰기
                continue

            type_name = lang_dict.get(task['name_key'], task_type)
            success_count = 0
            fail_count = 0
            current_failed_details = []

            self.task_queue.put(lambda tn=type_name: self._update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0))
            try:
                data_list = task['data_func']()
                if not data_list: # 데이터가 없으면 성공 0, 실패 0으로 처리하고 다음으로
                    export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                    continue

                success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                if success:
                    success_count = 1
                else:
                    fail_count = 1
                    current_failed_details.append(f"{type_name} (Error: {error})")
            except Exception as e:
                fail_count += 1
                current_failed_details.append(f"{type_name} (Unexpected Error: {e})")

            export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
            total_exported_count += success_count
            total_failed_count += fail_count
            all_failed_details.extend(current_failed_details)

        # 이벤트 목록 로직 (마스터 체크박스 활성화 시에만 진입)
        if selected_options['event_list_master']:
            event_list_tasks = [
                {'type': 'event_list_jp', 'name_key': 'export_type_event_list_jp', 'data_func': lambda: self._get_event_list_from_db('JP'), 'file_suffix': 'event_list_jp', 'header_key': 'export_type_event_list_jp'},
                {'type': 'event_list_kr', 'name_key': 'export_type_event_list_kr', 'data_func': lambda: self._get_event_list_from_db('KR'), 'file_suffix': 'event_list_kr', 'header_key': 'export_type_event_list_kr'}
            ]
            for task in event_list_tasks:
                task_type = task['type']
                if not selected_options[task_type]: # ExportWindow에서 선택되지 않은 항목은 건너뛰기
                    continue

                type_name = lang_dict.get(task['name_key'], task_type)
                success_count = 0
                fail_count = 0
                current_failed_details = []

                self.task_queue.put(lambda tn=type_name: self._update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0))
                try:
                    data_list = task['data_func']()
                    if not data_list:
                        export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                        continue

                    success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                    if success:
                        success_count = 1
                    else:
                        fail_count = 1
                        current_failed_details.append(f"{type_name} (Error: {error})")
                except Exception as e:
                    fail_count += 1
                    current_failed_details.append(f"{type_name} (Unexpected Error: {e})")
                
                export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)


        # 최종 결과를 UI 스레드로 전달
        self.task_queue.put(lambda: self._finish_export(total_exported_count, total_failed_count, all_failed_details))

    def _finish_export(self, exported_count, failed_count, failed_list):
        """내보내기 작업 완료 후 결과를 메시지 박스로 알립니다."""
        lang_dict = LANGUAGES[self.lang.get()]
        self.file_menu.entryconfig(3, state="normal") # 내보내기 버튼 다시 활성화

        if exported_count > 0:
            messagebox.showinfo(lang_dict['msgbox_export_complete_title'], lang_dict['msgbox_export_complete_msg'].format(exported_count=exported_count), parent=self.master)
            self._update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        else:
            messagebox.showwarning(lang_dict['msgbox_export_failed_title'], lang_dict['msgbox_export_failed_msg'].format(failed_count=failed_count), parent=self.master)
            self._update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        
        # 실패한 파일이 있으면 상세 정보 표시
        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(lang_dict['msgbox_export_error_details_title'], lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg), parent=self.master)

# ToolTip 클래스 (ExportWindow에서 DB 미발견 시 툴팁을 위해 추가)
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = 0
        self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.x = self.widget.winfo_rootx() + 20
        self.y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.id = self.widget.after(500, self.show_tip) # 0.5초 후 툴팁 표시

    def leave(self, event=None):
        self.hide_tip()

    def show_tip(self):
        if self.tip_window or not self.text:
            return
        # 위젯이 비활성화 상태이면 툴팁을 표시하지 않음
        if str(self.widget.cget('state')) == 'disabled':
            return
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True) # 타이틀바, 테두리 없음
        self.tip_window.wm_geometry(f"+{self.x}+{self.y}")

        label = tk.Label(self.tip_window, text=self.text, background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self):
        # 툴팁을 숨기기 전에 after 작업을 취소
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None


# --- 프로그램 실행 진입점 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = StoryViewerApp(root)
    root.mainloop()