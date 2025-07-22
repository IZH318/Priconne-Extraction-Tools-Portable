import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import os
import json
import re
import sqlite3
import threading
import queue
from datetime import datetime

# --- 프로그램 정보 ---
ABOUT_INFO = {
    'program': "storydata Viewer",
    'version': "1.0.0",
    'updated': "2025-07-22",
    'license': "MIT License",
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
        'status_bar_initial': "폴더를 열어주세요.",
        'status_bar_loading_start': "파일 로딩 및 분석 시작...",
        'status_bar_analyzing': "파일 분석 중... ({i}/{t})",
        'status_bar_loading_done': "로드 완료: {loaded}개 성공, {failed}개 실패.",
        'status_bar_ready': "준비",
        'status_bar_displaying': "'{filename}' 표시 완료.",
        'status_bar_cache_error': "오류: '{filename}' 캐시 데이터 없음.",
        'status_bar_list_updated': "{count}개의 파일이 목록에 표시됩니다.",
        'status_bar_export_prep': "내보내기 준비 중...",
        'status_bar_exporting': "내보내기 중... ({i}/{t})",
        'status_bar_export_done': "{exported}개 파일 내보내기 완료. ({failed}개 실패)",
        'status_bar_export_all_failed': "모든 파일 내보내기 실패. ({failed}개 실패)",
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
        'msgbox_export_options_msg': "현재 목록에 있는 파일만 저장하시겠습니까?\n\n- 예(Y): 현재 목록의 파일만 저장\n- 아니요(N): 불러온 모든 파일 저장",
        'msgbox_no_export_files_title': "알림",
        'msgbox_no_export_files_msg': "내보낼 파일이 없습니다.",
        'msgbox_export_folder_title': "스토리 파일을 저장할 폴더를 선택하세요",
        'msgbox_export_complete_title': "내보내기 완료",
        'msgbox_export_complete_msg': "{count}개의 파일을 성공적으로 내보냈습니다.",
        'msgbox_export_failed_title': "내보내기 실패",
        'msgbox_export_failed_msg': "내보낸 파일이 없습니다. {count}개의 파일에서 오류가 발생했습니다.",
        'msgbox_export_error_details_title': "내보내기 오류 상세",
        'msgbox_export_error_details_msg': "다음 파일 내보내기 중 오류 발생:\n{errors}",
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
        'db_not_found_title': "데이터베이스 오류", 'db_not_found_msg': "{path} 파일을 찾을 수 없습니다.\n\n해당 서버의 이벤트 목록을 로드할 수 없습니다.",
        'db_error_title': "데이터베이스 오류", 'db_error_msg': "데이터베이스 처리 중 오류 발생:\n{e}",
        'status_searching': "고급 검색 중...",
        'search_error_title': "검색 오류", 'search_error_msg': "검색 중 오류가 발생했습니다:\n{e}",
    },
    'en': {
        'window_title': "storydata Viewer",
        'menu_file': "Menu", 'menu_lang': "Language", 'menu_about': "About",
        'file_open': "Open File(s)", 'folder_open': "Open Folder", 'export': "Export", 'exit': "Exit",
        'lang_ko': "한국어", 'lang_en': "English", 'lang_ja': "日本語",
        'options_group': "Options",
        'file_options_group': "Story File List Options",
        'display_original_filename': "Display by original filename", 'display_title': "Display by title info",
        'detail_options_group': "Story Detail Options",
        'view_simple': "Simple View (title, outline, vo, print)", 'view_detailed': "Detailed View",
        'list_group_title': "Story File List", 'detail_group_title': "Story Details",
        'search_button_text': "Advanced storydata Search",
        'status_bar_initial': "Please open a folder.",
        'status_bar_loading_start': "Starting to load and analyze files...",
        'status_bar_analyzing': "Analyzing files... ({i}/{t})",
        'status_bar_loading_done': "Loading complete: {loaded} succeeded, {failed} failed.",
        'status_bar_ready': "Ready",
        'status_bar_displaying': "Displaying '{filename}' done.",
        'status_bar_cache_error': "Error: Cached data for '{filename}' not found.",
        'status_bar_list_updated': "{count} files are displayed in the list.",
        'status_bar_export_prep': "Preparing for export...",
        'status_bar_exporting': "Exporting... ({i}/{t})",
        'status_bar_export_done': "Export complete: {exported} files. ({failed} failed)",
        'status_bar_export_all_failed': "Export failed for all files. ({failed} failed)",
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
        'msgbox_export_options_msg': "Do you want to save only the files in the current list?\n\n- Yes: Save files from the current list only\n- No: Save all loaded files",
        'msgbox_no_export_files_title': "Notice",
        'msgbox_no_export_files_msg': "There are no files to export.",
        'msgbox_export_folder_title': "Select a folder to save the story files",
        'msgbox_export_complete_title': "Export Complete",
        'msgbox_export_complete_msg': "Successfully exported {count} files.",
        'msgbox_export_failed_title': "Export Failed",
        'msgbox_export_failed_msg': "No files were exported. An error occurred in {count} files.",
        'msgbox_export_error_details_title': "Export Error Details",
        'msgbox_export_error_details_msg': "Error occurred while exporting the following files:\n{errors}",
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
        'db_not_found_title': "Database Error", 'db_not_found_msg': "File not found: {path}.\n\nCannot load event list for the selected server.",
        'db_error_title': "Database Error", 'db_error_msg': "An error occurred during database processing:\n{e}",
        'status_searching': "Advanced searching...",
        'search_error_title': "Search Error", 'search_error_msg': "An error occurred during search:\n{e}",
    },
    'ja': {
        'window_title': "storydata Viewer",
        'menu_file': "メニュー(Menu)", 'menu_lang': "言語(Language)", 'menu_about': "情報(About)",
        'file_open': "ファイルを開く", 'folder_open': "フォルダーを開く", 'export': "エクスポート", 'exit': "終了",
        'lang_ko': "한국어", 'lang_en': "English", 'lang_ja': "日本語",
        'options_group': "オプション",
        'file_options_group': "ストーリーファイルリストのオプション",
        'display_original_filename': "元のファイル名で表示", 'display_title': "title情報で表示",
        'detail_options_group': "ストーリー詳細情報のオプション",
        'view_simple': "簡易表示 (title, outline, vo, print)", 'view_detailed': "詳細表示",
        'list_group_title': "ストーリーファイルリスト", 'detail_group_title': "ストーリー詳細",
        'search_button_text': "storydata 高度な検索",
        'status_bar_initial': "フォルダーを開いてください。",
        'status_bar_loading_start': "ファイルの読み込みと分析を開始...",
        'status_bar_analyzing': "ファイルを分析中... ({i}/{t})",
        'status_bar_loading_done': "読み込み完了: {loaded}件成功, {failed}件失敗。",
        'status_bar_ready': "準備完了",
        'status_bar_displaying': "'{filename}' の表示完了。",
        'status_bar_cache_error': "エラー: '{filename}' のキャッシュデータがありません。",
        'status_bar_list_updated': "リストに{count}個のファイルが表示されています。",
        'status_bar_export_prep': "エクスポートの準備中...",
        'status_bar_exporting': "エクスポート中... ({i}/{t})",
        'status_bar_export_done': "{exported}件のエクスポート完了。({failed}件失敗)",
        'status_bar_export_all_failed': "すべてのファイルのエクスポートに失敗しました。({failed}件失敗)",
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
        'msgbox_export_options_msg': "現在のリストにあるファイルのみを保存しますか？\n\n- はい(Y): 現在のリストのファイルのみ保存\n- いいえ(N): 読み込まれたすべてのファイルを保存",
        'msgbox_no_export_files_title': "通知",
        'msgbox_no_export_files_msg': "エクスポートするファイルがありません。",
        'msgbox_export_folder_title': "ストーリーファイルを保存するフォルダーを選択してください",
        'msgbox_export_complete_title': "エクスポート完了",
        'msgbox_export_complete_msg': "{count}個のファイルを正常にエクスポートしました。",
        'msgbox_export_failed_title': "エクスポート失敗",
        'msgbox_export_failed_msg': "エクスポートされたファイルはありません。{count}個のファイルでエラーが発生しました。",
        'msgbox_export_error_details_title': "エクスポートエラー詳細",
        'msgbox_export_error_details_msg': "以下のファイルのエクスポート中にエラーが発生しました:\n{errors}",
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
        'db_not_found_title': "データベースエラー", 'db_not_found_msg': "ファイルが見つかりません: {path}。\n\n選択したサーバーのイベントリストを読み込めません。",
        'db_error_title': "データベースエラー", 'db_error_msg': "データベース処理中にエラーが発生しました:\n{e}",
        'status_searching': "高度な検索を実行中...",
        'search_error_title': "検索エラー", 'search_error_msg': "検索中にエラーが発生しました:\n{e}",
    }
}

class SearchWindow(tk.Toplevel):
    def __init__(self, app, all_files_dict, story_data_cache, search_callback, search_data):
        super().__init__(app.master)
        
        self.app = app
        self.all_files_dict = all_files_dict
        self.story_data_cache = story_data_cache
        self.search_callback = search_callback
        self.search_data = search_data

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
        self.server_var = tk.StringVar(value='JP')

        # 각 서버별 DB 파일 경로 및 테이블/컬럼 정보 정의
        self.server_db_info = {
            'JP': {
                'db_path': 'master_jp.db',
                'event_list_table': 'v1_8931e2893a2d2290dbf498046bc66faafeebc40b6764dd69334ad51f5aca2e9f',
                'event_name_col_list': 'e3f0f79d746654f52125f3c28eb487d9e102f02077fe104d1423f08e80e056e3', # 이벤트 목록 테이블의 이벤트 이름 컬럼 (2번째)
                'event_details_table': 'v1_04d08b8c6bf704241326eca45b6d63cc1a6dd38d03ff256df15b8ec8d4cd2649',
                'event_info_col_details': '20d0bf56a9ca7d14b3172ac4dd383fee10c010d4ecd30c9854302d10390d774e', # 이벤트 상세 테이블의 이벤트 이름+정보 컬럼 (11번째)
                'event_id_col_details': '69d3bbead1844607ef41ecb520a4d5385cae02eddca377aa13721ec7fd01e0ec' # 이벤트 상세 테이블의 이벤트 고유 ID 컬럼 (12번째)
            },
            'KR': {
                'db_path': 'master_kr.db',
                'event_list_table': 'v1_4e380b72af2e31867844884ba838095ad9ea8f02bf83037a3c8ed47b8943f164',
                'event_name_col_list': 'abb720eaefdc23b376dc5b817b683e633eb66fe9a3941025ae27413c56d56fad', # 이벤트 목록 테이블의 이벤트 이름 컬럼 (4번째)
                'event_details_table': 'v1_ebabad5e41c1f71b3e5d705a8fe81411012e124827b4cbde3dfb2469674f598f',
                'event_info_col_details': '45d39837db60a2b9aca5a03c3c17a9999201e08e97c3cff92bb95786dd344355', # 이벤트 상세 테이블의 이벤트 이름+정보 컬럼 (3번째)
                'event_id_col_details': '6db6c11bbfa308b726f5f24bdee2bc75a2f805e2ae94ed4908aaa7444ce3e2eb' # 이벤트 상세 테이블의 이벤트 고유 ID 컬럼 (7번째)
            }
        }
        
        self.transient(app.master)
        self.grab_set()
        
        self._setup_ui()
        self._on_server_selection_change()
        
        self.focus_set()
        self._center_window(420, 420)

    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.criteria_frame = ttk.LabelFrame(main_frame, text="", padding=5)
        self.criteria_frame.pack(fill="x", expand=False, anchor="n", pady=(0, 10))
        self.criteria_frame.columnconfigure(1, weight=1)

        pady_value = 4
        
        self.filename_label = ttk.Label(self.criteria_frame, text="")
        self.filename_label.grid(row=0, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['filename'], values=self.search_data.get('filenames', [])).grid(row=0, column=1, columnspan=2, sticky="ew")

        self.title_label = ttk.Label(self.criteria_frame, text="")
        self.title_label.grid(row=1, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['title']).grid(row=1, column=1, columnspan=2, sticky="ew")

        self.outline_label = ttk.Label(self.criteria_frame, text="")
        self.outline_label.grid(row=2, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['outline']).grid(row=2, column=1, columnspan=2, sticky="ew")

        self.char_name_label = ttk.Label(self.criteria_frame, text="")
        self.char_name_label.grid(row=3, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_name'], values=self.search_data.get('character_names', [])).grid(row=3, column=1, sticky="ew")
        self.char_type_combobox = ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['char_type'], width=12, state='readonly')
        self.char_type_combobox.grid(row=3, column=2, sticky="e", padx=(5,0))

        self.content_label = ttk.Label(self.criteria_frame, text="")
        self.content_label.grid(row=4, column=0, sticky="w", pady=pady_value)
        ttk.Entry(self.criteria_frame, textvariable=self.search_vars['content']).grid(row=4, column=1, columnspan=2, sticky="ew")

        self.bgm_label = ttk.Label(self.criteria_frame, text="")
        self.bgm_label.grid(row=5, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['bgm'], values=self.search_data.get('bgms', [])).grid(row=5, column=1, columnspan=2, sticky="ew")

        self.background_label = ttk.Label(self.criteria_frame, text="")
        self.background_label.grid(row=6, column=0, sticky="w", pady=pady_value)
        ttk.Combobox(self.criteria_frame, textvariable=self.search_vars['background'], values=self.search_data.get('backgrounds', [])).grid(row=6, column=1, columnspan=2, sticky="ew")

        self.event_search_frame = ttk.LabelFrame(main_frame, text="", padding="5")
        self.event_search_frame.pack(fill="x", expand=True, anchor="n")
        self.event_search_frame.columnconfigure(1, weight=1)

        server_frame = ttk.Frame(self.event_search_frame, padding="5")
        server_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,5))
        server_frame.columnconfigure(0, weight=1)
        server_frame.columnconfigure(1, weight=1)
        self.jp_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="JP", command=self._on_server_selection_change)
        self.jp_radio.grid(row=0, column=0, padx=5, sticky="w")
        self.kr_radio = ttk.Radiobutton(server_frame, text="", variable=self.server_var, value="KR", command=self._on_server_selection_change)
        self.kr_radio.grid(row=0, column=1, padx=5, sticky="w")

        self.event_list_label = ttk.Label(self.event_search_frame, text="")
        self.event_list_label.grid(row=1, column=0, sticky="w", pady=3)
        self.event_combobox = ttk.Combobox(self.event_search_frame, textvariable=self.search_vars['event_name'])
        self.event_combobox.grid(row=1, column=1, columnspan=2, sticky="ew")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        self.search_button = ttk.Button(button_frame, text="", command=self.start_search)
        self.search_button.pack(side="right")
        self.reset_button = ttk.Button(button_frame, text="", command=self._reset)
        self.reset_button.pack(side="right", padx=(0, 5))
        
        self._update_ui_text()

    def _update_ui_text(self):
        lang_dict = LANGUAGES[self.app.lang.get()]
        
        self.title(lang_dict['search_window_title'])
        self.criteria_frame.config(text=lang_dict['basic_search_criteria_frame'])
        self.filename_label.config(text=lang_dict['filename_label'])
        self.title_label.config(text=lang_dict['title_label'])
        self.outline_label.config(text=lang_dict['outline_label'])
        self.char_name_label.config(text=lang_dict['char_name_label'])
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
        selected_server = self.server_var.get()
        db_info = self.server_db_info.get(selected_server)
        lang_dict = LANGUAGES[self.app.lang.get()]

        if not db_info:
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, db_info['db_path'])
        
        if not os.path.exists(db_path):
            messagebox.showwarning(lang_dict['db_not_found_title'], lang_dict['db_not_found_msg'].format(path=db_path), parent=self)
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            return

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                query_event_list = f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\""
                cursor.execute(query_event_list)
                event_names = [row[0].replace('\\n', '') for row in cursor.fetchall() if row[0]]
            self.event_combobox['values'] = sorted(event_names)
            self.search_vars['event_name'].set('')
        except sqlite3.Error as e:
            messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=e), parent=self)
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')

    def start_search(self):
        self.search_button.config(state="disabled")
        self.reset_button.config(state="disabled")
        self.app._update_status_bar('status_searching')
        
        criteria = {key: var.get().lower() for key, var in self.search_vars.items() if var.get()}
        server = self.server_var.get()
        
        thread = threading.Thread(target=self._search_thread, args=(criteria, server))
        thread.daemon = True
        thread.start()

    def _search_thread(self, criteria, server):
        lang_dict = LANGUAGES[self.app.lang.get()]
        try:
            event_name_for_db_query = ""
            if 'event_name' in criteria:
                event_name_for_db_query = criteria.pop('event_name').replace(' ', '\\n')

            initial_matched_files = set(self.all_files_dict.keys())

            if event_name_for_db_query:
                db_info = self.server_db_info.get(server)
                if db_info:
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    db_path = os.path.join(script_dir, db_info['db_path'])
                    if os.path.exists(db_path):
                        try:
                            with sqlite3.connect(db_path) as conn:
                                cursor = conn.cursor()
                                query = f"SELECT \"{db_info['event_id_col_details']}\" FROM \"{db_info['event_details_table']}\" WHERE \"{db_info['event_info_col_details']}\" LIKE ?"
                                cursor.execute(query, (f"{event_name_for_db_query}%",))
                                event_story_ids = {f"storydata_{row[0]}.json" for row in cursor.fetchall()}
                                initial_matched_files.intersection_update(event_story_ids)
                        except sqlite3.Error as e:
                            self.app.task_queue.put(lambda: messagebox.showerror(lang_dict['db_error_title'], lang_dict['db_error_msg'].format(e=e), parent=self))
            
            final_matched_files = []
            if not criteria and not event_name_for_db_query:
                 final_matched_files = list(self.all_files_dict.keys())
            else:
                for filename in initial_matched_files:
                    if 'filename' in criteria and criteria['filename'] not in filename.lower():
                        continue
                    
                    data = self.story_data_cache.get(filename)
                    if not data: continue

                    content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
                    if not content_criteria or self._check_file_content(data, content_criteria):
                        final_matched_files.append(filename)
            
            self.app.task_queue.put(lambda: self._finish_search(sorted(list(set(final_matched_files)))))

        except Exception as e:
            self.app.task_queue.put(lambda: self._finish_search_error(e))

    def _finish_search(self, matched_files):
        self.search_callback(matched_files)
        self.destroy()

    def _finish_search_error(self, error):
        lang_dict = LANGUAGES[self.app.lang.get()]
        messagebox.showerror(lang_dict['search_error_title'], lang_dict['search_error_msg'].format(e=error), parent=self.app.master)
        self.search_button.config(state="normal")
        self.reset_button.config(state="normal")

    def _check_file_content(self, data, criteria):
        scene_0 = data.get('0', {})
        if 'title' in criteria and criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in criteria and criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        has_scene_level_criteria = any(k in criteria for k in ['char_name', 'content', 'bgm', 'background'])
        if not has_scene_level_criteria:
            return True

        for scene in data.values():
            if self._check_scene(scene, criteria):
                return True
        return False

    def _check_scene(self, scene, criteria):
        lang_dict = LANGUAGES[self.app.lang.get()]
        if 'content' in criteria and not ('print' in scene and criteria['content'] in scene['print'].get('text', '').lower()):
            return False
        if 'bgm' in criteria and not ('bgm' in scene and criteria['bgm'] in str(scene.get('bgm', '')).lower()):
            return False
        if 'background' in criteria and not ('background' in scene and criteria['background'] in str(scene.get('background', '')).lower()):
            return False
        if 'char_name' in criteria:
            char_name_crit = criteria['char_name']
            char_type_search = self.search_vars['char_type'].get()
            char_type_speaker = lang_dict['char_type_speaker']
            
            char_found = False
            if 'print' in scene:
                if char_type_search == char_type_speaker and char_name_crit in str(scene['print'].get('name', '')).lower():
                    char_found = True
                elif char_type_search != char_type_speaker and char_name_crit in scene['print'].get('text', '').lower():
                    char_found = True
            if not char_found:
                return False
        return True

    def _reset(self):
        for var in self.search_vars.values(): var.set('')
        self.server_var.set('JP')
        self._on_server_selection_change()
        self.search_callback(list(self.all_files_dict.keys()))
        self.destroy()

class StoryViewerApp:
    def __init__(self, master):
        self.master = master
        self.all_files = {}
        self.story_data_cache = {}
        self.search_data = {}
        self.file_titles = {}
        self.display_name_to_filename = {}
        self.current_filenames_in_list = []
        self.current_file_path = None
        self.is_loading = False
        self.task_queue = queue.Queue()

        self.lang = tk.StringVar(value='ko')
        self.lang.trace_add('write', self._on_language_change)
        
        self.display_mode_var = tk.StringVar(value="original")
        self.view_mode_var = tk.StringVar(value="simple")
        
        self.field_order = [
            # 20250722 storydata 기준
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
        self.setup_ui()
        self.setup_text_tags()
        self._center_window(800, 600)
        self.master.after(100, self._process_queue)
        self._update_ui_text()
        self._update_status_bar('status_bar_initial')

    def _center_window(self, width, height):
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def setup_ui(self):
        self.master.geometry("800x600")
        self.create_menu()
        self.master.grid_rowconfigure(1, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        
        self.options_group = ttk.LabelFrame(self.master, text="")
        self.options_group.grid(row=0, column=0, sticky="ew", padx=10, pady=(5,0))
        self.options_group.columnconfigure(0, weight=1)
        self.options_group.columnconfigure(1, weight=1)

        self.file_options_group = ttk.LabelFrame(self.options_group, text="", padding=5)
        self.file_options_group.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        self.display_orig_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="original", command=self._on_display_mode_change)
        self.display_orig_radio.grid(row=0, column=0, padx=5)
        self.display_title_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="title", command=self._on_display_mode_change)
        self.display_title_radio.grid(row=0, column=1, padx=5)

        self.detail_options_group = ttk.LabelFrame(self.options_group, text="", padding=5)
        self.detail_options_group.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.view_simple_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="simple", command=self._on_view_mode_change)
        self.view_simple_radio.grid(row=0, column=0, padx=5)
        self.view_detailed_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="detailed", command=self._on_view_mode_change)
        self.view_detailed_radio.grid(row=0, column=1, padx=5)

        main_frame = ttk.Frame(self.master, padding=(10, 5, 10, 0)) 
        main_frame.grid(row=1, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True)
        left_weight, right_weight = 1, 2

        self.left_group = ttk.LabelFrame(self.paned_window, text="", padding=5)
        self.paned_window.add(self.left_group, weight=left_weight) 
        self.left_group.grid_rowconfigure(1, weight=1)
        self.left_group.grid_columnconfigure(0, weight=1)

        self.search_button = ttk.Button(self.left_group, text="", command=self.open_search_window)
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

        self.status_bar = ttk.Label(self.master, text="", anchor=tk.W, padding=5)
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        def reapply_weights(event=None):
            try:
                total_width = self.paned_window.winfo_width()
                sash_position = int(total_width * left_weight / (left_weight + right_weight))
                self.paned_window.sashpos(0, sash_position)
                self.paned_window.unbind("<Configure>")
            except tk.TclError: pass
        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self):
        default_font_family = font.nametofont("TkDefaultFont").cget("family")
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A')
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000')
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')
    
    def create_menu(self):
        self.menu_bar = tk.Menu(self.master)
        
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)
        
        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)
        self.menu_bar.add_command(label="", command=self._show_about_dialog)

        self.file_menu.add_command(label="", command=self.open_files)
        self.file_menu.add_command(label="", command=self.open_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="", command=self.export_stories, state="disabled")
        self.file_menu.add_separator()
        self.file_menu.add_command(label="", command=self.master.quit)
        
        self.lang_menu.add_radiobutton(label=LANGUAGES['ko']['lang_ko'], variable=self.lang, value='ko')
        self.lang_menu.add_radiobutton(label=LANGUAGES['en']['lang_en'], variable=self.lang, value='en')
        self.lang_menu.add_radiobutton(label=LANGUAGES['ja']['lang_ja'], variable=self.lang, value='ja')
        
        self.master.config(menu=self.menu_bar)

    def _on_language_change(self, *args):
        self._update_ui_text()
        self._on_display_mode_change(force_update=True)
        self._on_view_mode_change(force_update=True)


    def _update_ui_text(self):
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
        
        self.update_file_list(self.current_filenames_in_list)


    def _update_status_bar(self, key, **kwargs):
        lang_dict = LANGUAGES[self.lang.get()]
        message = lang_dict.get(key, "...")
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError:
                pass
        self.status_bar.config(text=message)
        
    def _show_about_dialog(self):
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
        try:
            while True:
                task = self.task_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self._process_queue)

    def _clear_workspace(self):
        self.update_story_text([])
        self.all_files.clear()
        self.story_data_cache.clear()
        self.search_data.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.current_file_path = None
        self.search_button.config(state="disabled")
        self.file_menu.entryconfig(3, state="disabled")

    def _is_valid_storydata(self, file_path):
        """파일 유효성을 검사하고, 성공 시 (True, 데이터, None), 실패 시 (False, None, 실패 이유)를 반환합니다."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, dict) or not data:
                return False, None, "파일 내용이 비어있거나 딕셔너리 형식이 아님"
                
            if not all(k.isdigit() and isinstance(v, dict) for k, v in data.items()):
                return False, None, "데이터 구조 오류 (키는 숫자, 값은 딕셔너리여야 함)"
                
            return True, data, None
        except json.JSONDecodeError as e:
            return False, None, f"JSON 형식 오류: {e}"
        except Exception as e:
            return False, None, f"파일 읽기/기타 오류: {e}"

    def _start_loading_task(self, paths=None, folder_path=None):
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return

        self._clear_workspace()
        self.is_loading = True
        self._update_status_bar('status_bar_loading_start')
        self.file_menu.entryconfig(0, state="disabled")
        self.file_menu.entryconfig(1, state="disabled")

        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path))
        thread.daemon = True
        thread.start()

    def open_files(self):
        lang_dict = LANGUAGES[self.lang.get()]
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[
                (lang_dict.get('filetype_json', "JSON Files"), "*.json"),
                (lang_dict.get('filetype_all', "All Files"), "*.*")
            ]
        )
        if file_paths:
            self._start_loading_task(paths=file_paths)

    def open_folder(self):
        lang_dict = LANGUAGES[self.lang.get()]
        folder_path = filedialog.askdirectory(
            title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files")
        )
        if folder_path:
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths, folder_path):
        temp_all_files = {}
        temp_story_cache = {}
        invalid_files = []

        file_list_to_process = []
        if paths:
            file_list_to_process = paths
        elif folder_path:
            pattern = re.compile(r'^storydata_\d+\.json$')
            for dirpath, _, filenames in os.walk(folder_path):
                for filename in sorted(filenames):
                    if pattern.match(filename):
                        file_list_to_process.append(os.path.join(dirpath, filename))
        
        total_files = len(file_list_to_process)
        for i, path in enumerate(file_list_to_process):
            self.task_queue.put(lambda i=i, t=total_files: self._update_status_bar('status_bar_analyzing', i=i+1, t=t))

            is_valid, data, error_reason = self._is_valid_storydata(path)
            filename = os.path.basename(path)
            if is_valid:
                temp_all_files[filename] = path
                temp_story_cache[filename] = data
            else:
                invalid_files.append((filename, error_reason))
        
        if not temp_all_files:
            self.task_queue.put(lambda: self._finish_loading(None, invalid_files))
            return

        unique_char_names, unique_bgms, unique_bgs = set(), set(), set()
        temp_file_titles = {}
        
        def _extract_asset_name(value):
            if isinstance(value, str): return value
            if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
            return None

        for filename, data in temp_story_cache.items():
            title = data.get('0', {}).get('title', '').strip()
            temp_file_titles[filename] = title if title else filename
            for scene in data.values():
                if 'print' in scene and 'name' in scene['print']:
                    if name := str(scene['print']['name']).strip(): unique_char_names.add(name)
                if 'bgm' in scene and (bgm_name := _extract_asset_name(scene['bgm'])): unique_bgms.add(bgm_name)
                if 'background' in scene and (bg_name := _extract_asset_name(scene['background'])): unique_bgs.add(bg_name)

        temp_search_data = {
            'filenames': sorted(list(temp_all_files.keys())),
            'character_names': sorted(list(unique_char_names)),
            'bgms': sorted(list(unique_bgms)),
            'backgrounds': sorted(list(unique_bgs)),
        }
        
        results = {
            "all_files": temp_all_files,
            "cache": temp_story_cache,
            "titles": temp_file_titles,
            "search_data": temp_search_data,
        }
        self.task_queue.put(lambda: self._finish_loading(results, invalid_files))

    def _finish_loading(self, results, invalid_files):
        lang_dict = LANGUAGES[self.lang.get()]
        self.is_loading = False
        self.file_menu.entryconfig(0, state="normal")
        self.file_menu.entryconfig(1, state="normal")

        if not results:
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'])
            self._update_status_bar('status_bar_ready')
        else:
            self.all_files = results['all_files']
            self.story_data_cache = results['cache']
            self.file_titles = results['titles']
            self.search_data = results['search_data']
            
            self.search_button.config(state="normal")
            self.file_menu.entryconfig(3, state="normal")

            self.update_file_list(list(self.all_files.keys()))
            self._update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))
        
        if invalid_files:
            msg = lang_dict['msgbox_load_fail_msg'].format(count=len(invalid_files))
            if messagebox.askyesno(lang_dict['msgbox_load_fail_title'], msg):
                log_filename = "invalid_storydata_log.txt"
                try:
                    with open(log_filename, 'w', encoding='utf-8') as f:
                        f.write(f"--- 로드 실패 로그 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
                        f.write(f"총 {len(invalid_files)}개 파일 로드 실패\n")
                        f.write("-" * 50 + "\n\n")
                        for filename, reason in invalid_files:
                            f.write(f"파일: {filename}\n")
                            f.write(f"원인: {reason}\n")
                            f.write("-" * 30 + "\n")
                    messagebox.showinfo(lang_dict['msgbox_log_saved_title'], lang_dict['msgbox_log_saved_msg'].format(filename=log_filename))
                except Exception as e:
                    messagebox.showerror(lang_dict['msgbox_log_save_error_title'], lang_dict['msgbox_log_save_error_msg'].format(e=e))

    def open_search_window(self):
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_search_before_load_title'], lang_dict['msgbox_search_before_load_msg'])
            return
        SearchWindow(self, self.all_files, self.story_data_cache, self.update_file_list, self.search_data)

    def update_file_list(self, filenames):
        self.update_story_text([])
        self.current_file_path = None
        self.current_filenames_in_list = sorted(filenames)
        self.file_listbox.delete(0, tk.END)
        self.display_name_to_filename.clear()
        
        display_mode = self.display_mode_var.get()

        for filename in self.current_filenames_in_list:
            display_name = filename
            if display_mode == 'title':
                title = self.file_titles.get(filename, filename)
                if title and title != filename:
                    display_name = f"{title}"
            self.file_listbox.insert(tk.END, display_name)
            self.display_name_to_filename[display_name] = filename
            
        if not self.is_loading:
            self._update_status_bar('status_bar_list_updated', count=len(filenames))
        if filenames:
            self.file_listbox.selection_set(0)
            self.file_listbox.event_generate("<<ListboxSelect>>")

    def on_file_select(self, event):
        if not self.file_listbox.curselection(): return
        display_name = self.file_listbox.get(self.file_listbox.curselection()[0])
        filename = self.display_name_to_filename.get(display_name)
        if filename:
            self.current_file_path = self.all_files.get(filename)
            data = self.story_data_cache.get(filename)
            if data:
                content_list = self.format_story_data(data)
                self.update_story_text(content_list)
                self._update_status_bar('status_bar_displaying', filename=filename)
            else:
                self._update_status_bar('status_bar_cache_error', filename=filename)

    def _on_display_mode_change(self, force_update=False):
        if not force_update and self.is_loading: return
        self.update_file_list(self.current_filenames_in_list)


    def _on_view_mode_change(self, force_update=False):
        if not force_update and self.is_loading: return
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            data = self.story_data_cache.get(filename)
            if data:
                content_list = self.format_story_data(data)
                self.update_story_text(content_list)

    def format_story_data(self, data):
        content_list = []
        view_mode = self.view_mode_var.get()

        for key in sorted(data.keys(), key=int):
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            keys_to_display = []
            if view_mode == 'simple':
                keys_to_display = [k for k in ['title', 'outline', 'vo', 'print'] if k in scene]
            else:
                keys_to_display = sorted(scene.keys(), key=lambda k: (self.field_order.index(k) if k in self.field_order else len(self.field_order), k))
            for field in keys_to_display:
                value = scene[field]
                content_list.append(("    " + f"{field}\n", 'key'))
                formatter = getattr(self, f'_format_{field}', self._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append(("-"*60 + "\n\n", None))
        return content_list

    def _format_print(self, value, content_list):
        indent = "        "
        name = str(value.get('name', '???')) 
        text = value.get('text', '')
        formatted_text = text.replace('\n', '\n' + indent)
        content_list.append((indent + f"- name: {name}\n", 'print_sub_key'))
        content_list.append((indent + f"- text: “{formatted_text}”\n", 'print_sub_key'))
    def _format_chara_full(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_fadein(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_fadeout(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_face(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_nod(self, value, content_list): self._format_simple_id_list(value, content_list)
    def _format_shake(self, value, content_list): self._format_simple_id_list(value, content_list)
    def _format_focus(self, value, content_list): self._format_simple_id_list(value, content_list)
    def _format_choice(self, value, content_list):
        indent = "        "
        for i, choice_item in enumerate(value, 1):
            content_list.append((indent + f"{i}. {choice_item['text']}", 'choice'))
            content_list.append((f" (→ S# {choice_item['tag']})\n", 'choice_tag'))
    def _format_default(self, value, content_list):
        content_list.append(("        " + f"{str(value)}\n", 'value'))
    def _format_generic_id_list(self, value, content_list):
        indent = "        "
        if not isinstance(value, list):
            self._format_default(value, content_list)
            return
        for item in value:
            if isinstance(item, list) and item:
                char_id = str(item[0])
                details = ", ".join(map(str, item[1:]))
                content_list.append((indent + f"- {char_id}", 'value'))
                content_list.append((f" ({details})\n" if details else "\n", 'value'))
            else:
                content_list.append((indent + f"- {str(item)}\n", 'value'))
    def _format_simple_id_list(self, value, content_list):
        indent = "        "
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {str(item)}\n", 'value'))

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)

    def export_stories(self):
        lang_dict = LANGUAGES[self.lang.get()]
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'])
            return

        response = messagebox.askyesnocancel(lang_dict['msgbox_export_options_title'], lang_dict['msgbox_export_options_msg'])
        if response is None: return

        filenames_to_export = self.current_filenames_in_list if response else sorted(list(self.all_files.keys()))
        if not filenames_to_export:
            messagebox.showinfo(lang_dict['msgbox_no_export_files_title'], lang_dict['msgbox_no_export_files_msg'])
            return

        output_folder = filedialog.askdirectory(title=lang_dict['msgbox_export_folder_title'])
        if not output_folder: return

        self._update_status_bar('status_bar_export_prep')
        self.file_menu.entryconfig(3, state="disabled")
        
        thread = threading.Thread(target=self._export_thread, args=(filenames_to_export, output_folder))
        thread.daemon = True
        thread.start()

    def _export_thread(self, filenames, output_folder):
        exported_count, failed_count = 0, 0
        failed_files = []
        total = len(filenames)

        for i, filename in enumerate(filenames):
            self.task_queue.put(lambda i=i, t=total: self._update_status_bar('status_bar_exporting', i=i+1, t=t))
            data = self.story_data_cache.get(filename)
            if not data:
                failed_count += 1
                failed_files.append(filename)
                continue
            
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_path = os.path.join(output_folder, output_filename)

            try:
                formatted_content_list = self.format_story_data(data)
                text_to_write = "".join([text for text, _ in formatted_content_list])
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(text_to_write)
                exported_count += 1
            except Exception as e:
                failed_count += 1
                failed_files.append(f"{filename} (Error: {e})")

        self.task_queue.put(lambda: self._finish_export(exported_count, failed_count, failed_files))

    def _finish_export(self, exported, failed, failed_list):
        lang_dict = LANGUAGES[self.lang.get()]
        self.file_menu.entryconfig(3, state="normal")
        
        if exported > 0:
            messagebox.showinfo(lang_dict['msgbox_export_complete_title'], lang_dict['msgbox_export_complete_msg'].format(count=exported))
            self._update_status_bar('status_bar_export_done', exported=exported, failed=failed)
        else:
            messagebox.showwarning(lang_dict['msgbox_export_failed_title'], lang_dict['msgbox_export_failed_msg'].format(count=failed))
            self._update_status_bar('status_bar_export_all_failed', failed=failed)
        
        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(lang_dict['msgbox_export_error_details_title'], lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg))

if __name__ == "__main__":
    root = tk.Tk()
    app = StoryViewerApp(root)
    root.mainloop()