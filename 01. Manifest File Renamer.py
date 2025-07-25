# --- 필수 모듈 임포트 ---
# 시스템 및 운영체제 관련 모듈
import os                     # OS 기능 (경로, 파일 확인)

# 데이터 처리 및 암호화 관련 모듈
from datetime import datetime # 현재 시간 (로그 타임스탬프용)
import sqlite3                # SQLite3 DB 접근
import hashlib                # MD5 해시 계산

# 동시성 및 병렬 처리 관련 모듈
import threading              # 스레드 생성/관리
import queue                  # 스레드 간 데이터 통신
import concurrent.futures     # 병렬 처리 (스레드 풀)

# 그래픽 사용자 인터페이스(GUI) 관련 모듈
import tkinter as tk                                  # GUI 라이브러리
from tkinter import scrolledtext, messagebox, ttk     # GUI 확장 위젯 (스크롤 텍스트, 메시지 박스, 테마 위젯)

# 서드파티(Third-Party) 라이브러리: 별도 설치 필요 모듈
import xxhash                 # xxHash64 해시 계산

# --- 다국어 리소스 ---
LANGUAGES = {
    'ko': {
        'window_title': "Manifest File Renamer", 'menu_language': "언어(Language)", 'menu_about': "정보(About)",
        'start_button': "작업 시작", 'status_waiting': "상태: 대기 중", 'status_searching': "파일 검색 중...",
        'status_processing': "처리: {current} / {total}", 'status_complete': "상태: 완료",
        'status_complete_count': "완료: {count} / {count}",
        'program_started': "프로그램이 시작되었습니다.\n",
        'initial_info_db': "[ 주의 ] 현재 디렉터리에 'manifest.db' 파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n\n"
                           "         [ 예시 ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 실행 파일)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 안내 ] '작업 시작' 버튼을 눌러주세요.\n",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 작업 대상 폴더)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 작업 대상 폴더)\n",
        'error_title': "오류", 'error_db_not_found': "'manifest.db' 파일을 찾을 수 없습니다。",
        'job_start_log': "[ 작업 시작 ] 새로운 작업을 시작합니다.\n\n",
        'backend_warning_db_not_found': "[ 경고 ] 현재 디렉터리에 'manifest.db'파일이 존재하지 않습니다.\n\n",
        'backend_info_long_time': " [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.\n",
        'backend_info_auto_rename': "          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n\n",
        'backend_searching_files': "[ 진행 ] 대상 폴더에서 파일 목록을 검색 중입니다...\n\n",
        'backend_no_files_found': "대상 폴더에서 처리 할 파일을 찾을 수 없습니다.\n\n",
        'backend_found_files': "[ 완료 ] 총 {count}개의 처리 대상 파일을 찾았습니다. 이름 변경을 시작합니다.\n\n\n",
        'backend_unprocessed_header': "[ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략되었습니다.\n\n",
        'backend_unprocessed_error': " 오류 발생: 알 수 없는 오류가 발생했습니다. ({error})\n\n",
        'backend_file_process_fail': "파일 처리 실패 {path}: {exc}\n\n",
        'backend_job_summary': "총 {total_processed}개의 파일이 처리되었습니다.\n\n",
        'backend_unprocessed_summary': "{count}개의 파일은 처리되지 않았습니다.\n\n",
        'backend_rename_error': "오류: {error}\n\n",
        'backend_rename_block': " - 작업 상태: 파일 이름 변경 완료\n"
                                "   - 원본: \\{original}\n"
                                "   - 변경: \\{new}\n\n",
        'backend_rename_exception_block': " - 작업 상태: 예외 처리된 파일 이름 변경 완료\n"
                                          "   - 원본: \\{original}\n"
                                          "   - 변경: \\{new}\n\n",
        'about_header': "[ 프로그램 정보 ]",
        'about_label_program': "프로그램 이름", 'about_label_version': "버전", 'about_label_updated': "최종 업데이트",
        'about_label_license': "라이선스", 'about_label_developer': "개발자", 'about_label_website': "웹 사이트",
    },
    'en': {
        'window_title': "Manifest File Renamer", 'menu_language': "Language", 'menu_about': "About",
        'start_button': "Start Process", 'status_waiting': "Status: Waiting", 'status_searching': "Searching files...",
        'status_processing': "Processing: {current} / {total}", 'status_complete': "Status: Complete",
        'status_complete_count': "Complete: {count} / {count}",
        'program_started': "Program started.\n",
        'initial_info_db': "[ WARNING ] 'manifest.db' and the target files must be in the current directory with their original structure.\n\n"
                           "         [ Example ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← Executable)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ INFO ] Please press the 'Start Process' button.\n",
        'folder_item_branch': "            ├─ {folder_name}\\ (← Target folder)",
        'folder_item_last':   "            └─ {folder_name}\\ (← Target folder)\n",
        'error_title': "Error", 'error_db_not_found': "'manifest.db' file not found.",
        'job_start_log': "[ START PROCESS ] Starting a new job.\n\n",
        'backend_warning_db_not_found': "[ WARNING ] 'manifest.db' does not exist in the current directory.\n\n",
        'backend_info_long_time': " [ INFO ] This may take a long time if there are many files or the storage device is slow.\n",
        'backend_info_auto_rename': "          All files will be renamed automatically after being loaded.\n\n",
        'backend_searching_files': "[ PROGRESS ] Searching for files in target folders...\n\n",
        'backend_no_files_found': "No files to process were found in the target folders.\n\n",
        'backend_found_files': "[ COMPLETE ] Found a total of {count} files to process. Starting rename.\n\n\n",
        'backend_unprocessed_header': "\n[ INFO ] Files not recognized by manifest.db were handled or skipped as follows.\n\n",
        'backend_unprocessed_error': " An unknown error occurred. ({error})\n\n",
        'backend_file_process_fail': "Failed to process file {path}: {exc}\n\n",
        'backend_job_summary': "A total of {total_processed} files have been processed.\n\n",
        'backend_unprocessed_summary': "{count} files were not processed.\n\n",
        'backend_rename_error': "Error: {error}\n\n",
        'backend_rename_block': " - Status: File renamed successfully\n"
                                "   - Original: \\{original}\n"
                                "   - New: \\{new}\n\n",
        'backend_rename_exception_block': " - Status: Renamed file via exception handling\n"
                                          "   - Original: \\{original}\n"
                                          "   - New: \\{new}\n\n",
        'about_header': "[ Program Information ]",
        'about_label_program': "Program", 'about_label_version': "Version", 'about_label_updated': "Updated",
        'about_label_license': "License", 'about_label_developer': "Developer", 'about_label_website': "Website",
    },
    'ja': {
        'window_title': "Manifest File Renamer", 'menu_language': "言語(Language)", 'menu_about': "情報(About)",
        'start_button': "作業開始", 'status_waiting': "状態: 待機中", 'status_searching': "ファイルを検索中...",
        'status_processing': "処理中: {current} / {total}", 'status_complete': "状態: 完了",
        'status_complete_count': "完了: {count} / {count}",
        'program_started': "プログラムが起動しました。\n",
        'initial_info_db': "[ 注意 ] 現在のディレクトリに 'manifest.db' ファイルと対象ファイルを元の構造のまま配置してください。\n\n"
                           "         [ 例 ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 実行ファイル)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 案内 ] 「作業開始」ボタンを押してください。\n",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 対象フォルダ)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 対象フォルダ)\n",
        'error_title': "エラー", 'error_db_not_found': "'manifest.db' ファイルが見つかりません。",
        'job_start_log': "[ 作業開始 ] 新しい作業を開始します。\n\n",
        'backend_warning_db_not_found': "[ 警告 ] 現在のディレクトリに 'manifest.db' が存在しません。\n\n",
        'backend_info_long_time': "[ 案内 ] ファイル数が多い、またはストレージの速度が遅い場合、時間がかかることがあります。\n",
        'backend_info_auto_rename': "          すべてのファイルが読み込まれた後、自動的にリネームされます。\n\n",
        'backend_searching_files': "[ 進行 ] 対象フォルダ内のファイルを検索しています...\n\n",
        'backend_no_files_found': "対象フォルダに処理するファイルが見つかりませんでした。\n\n",
        'backend_found_files': "[ 完了 ] 合計{count}個の処理対象ファイルを見つけました。名前の変更を開始します。\n\n\n",
        'backend_unprocessed_header': "\n[ 案内 ] manifest.dbで認識できなかったファイルは、次のように例外処理またはスキップされました。\n\n",
        'backend_unprocessed_error': " 不明なエラーが発生しました。({error})\n\n",
        'backend_file_process_fail': "ファイル処理失敗 {path}: {exc}\n\n",
        'backend_job_summary': "合計{total_processed}個のファイルが処理されました。\n\n",
        'backend_unprocessed_summary': "{count}個のファイルは処理されませんでした。\n\n",
        'backend_rename_error': "エラー: {error}\n\n",
        'backend_rename_block': " - 状態: ファイル名の変更が完了しました\n"
                                "   - 元の名前: \\{original}\n"
                                "   - 新しい名前: \\{new}\n\n",
        'backend_rename_exception_block': " - 状態: 例外処理によりファイル名を変更しました\n"
                                          "   - 元の名前: \\{original}\n"
                                          "   - 新しい名前: \\{new}\n\n",
        'about_header': "[ プログラム情報 ]",
        'about_label_program': "プログラム名", 'about_label_version': "バージョン", 'about_label_updated': "最終更新",
        'about_label_license': "ライセンス", 'about_label_developer': "開発者", 'about_label_website': "ウェブサイト",
    }
}

# --- 상수 정의 ---
# 로그 영역에서 내용 구분을 위해 사용되는 수평선 문자열.
SEPARATOR = "-" * 100

# ##################################################################
# Class: FileRenamerGUI
#
# 목적: 어플리케이션의 메인 GUI 창 및 사용자 상호작용을 관리.
#
# 주요 기능:
# 1. 메인 윈도우, 메뉴, 버튼, 진행률 표시줄, 로그 영역 등 위젯 생성 및 배치.
# 2. 다국어 지원 기능 (한국어, 영어, 일본어) 및 언어 변경 처리.
# 3. '작업 시작' 버튼 이벤트에 대한 응답으로 백엔드 파일 처리 스레드 시작.
# 4. 백엔드 스레드와의 통신(Queue 사용)을 통해 로그 및 진행 상황을 실시간으로 UI에 업데이트.
# 5. 프로그램 정보(About) 표시.
# ##################################################################
class FileRenamerGUI:
    # --- 프로그램 정보 상수 ---
    # '정보(About)' 메뉴에 표시될 정적 데이터.
    ABOUT_INFO = {
        'program': "Manifest File Renamer",
        'version': "2.0.0",
        'updated': "2025-07-26",
        'license': "GNU General Public License v3.0",
        'developer': "(Github) IZH318",
        'website': "https://github.com/IZH318",
    }

    # --- GUI 클래스 초기화 메서드 ---
    def __init__(self, master):
        """
        FileRenamerGUI 클래스의 인스턴스를 초기화합니다.
        
        Args:
            master (tk.Tk): 이 GUI를 담을 최상위 Tkinter 윈도우 객체.
        """
        # 1. 기본 멤버 변수 설정
        self.master = master  # Tkinter 루트 윈도우 참조 저장
        self.current_lang = 'ko'  # 어플리케이션의 기본 언어를 '한국어'로 설정
        self.lang_var = tk.StringVar(value=self.current_lang)  # 언어 변경을 감지하기 위한 Tkinter 문자열 변수
        self.lang_var.trace_add("write", self.on_language_change)  # lang_var의 값이 변경될 때마다 on_language_change 콜백 함수 호출
        
        self.log_data = []  # 로그 메시지를 (타임스탬프, 키, 포맷인자) 튜플 형태로 저장할 리스트
        
        # 2. 상태 관련 변수 설정
        self.last_progress_info = {'current': 0, 'total': 0}  # 마지막으로 업데이트된 진행률 정보 (현재 파일 수 / 전체 파일 수)
        self.is_processing = False  # 현재 파일 처리 작업이 진행 중인지 여부를 나타내는 플래그

        # 3. 윈도우 크기 및 위치 설정
        window_width = 800  # 윈도우 너비
        window_height = 600  # 윈도우 높이
        screen_width = self.master.winfo_screenwidth()  # 사용자 모니터의 전체 너비
        screen_height = self.master.winfo_screenheight()  # 사용자 모니터의 전체 높이
        center_x = int(screen_width / 2 - window_width / 2)  # 윈도우를 화면 수평 중앙에 위치시키기 위한 x 좌표
        center_y = int(screen_height / 2 - window_height / 2)  # 윈도우를 화면 수직 중앙에 위치시키기 위한 y 좌표
        self.master.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')  # 윈도우 크기와 위치 적용

        # 4. 스레드 간 통신을 위한 Queue 객체 생성
        self.log_queue = queue.Queue()  # 백엔드 스레드에서 GUI 스레드로 로그 메시지를 전달하기 위한 큐
        self.progress_queue = queue.Queue()  # 백엔드 스레드에서 GUI 스레드로 진행률 정보를 전달하기 위한 큐
        
        # 5. 백엔드 로직 클래스 인스턴스 생성
        # GUI와 백엔드 로직을 분리하여 코드의 유지보수성을 높임.
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue, self.get_string)
        
        # 6. GUI 업데이트 설정
        self.GUI_UPDATE_INTERVAL_MS = 10  # 큐를 확인하고 GUI를 업데이트하는 주기 (10밀리초)
        
        # 7. 위젯에서 사용할 변수
        self.progress_label_var = tk.StringVar()  # 진행률 상태 텍스트를 표시하기 위한 Tkinter 문자열 변수
        self.total_files_count = 0  # 처리할 전체 파일의 수

        # 8. GUI 구성 요소 초기화 및 생성
        self.menubar = None  # 메뉴바 객체 (초기에는 없음)
        self.language_menu = None  # 언어 메뉴 객체
        self.create_widgets()  # 모든 GUI 위젯 생성
        self.update_ui_language(is_initial_setup=True)  # UI를 현재 설정된 언어로 초기화

    # --- 다국어 문자열 관리 ---
    def get_string(self, key, **kwargs):
        """현재 선택된 언어에 해당하는 문자열을 반환합니다. 키워드 인자를 사용하여 문자열 포맷팅을 지원합니다."""
        return LANGUAGES[self.current_lang].get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    # --- 언어 변경 처리 ---
    def set_language(self, lang_code):
        """어플리케이션의 언어를 변경하고, 관련된 모든 UI 텍스트를 즉시 갱신합니다."""
        if self.current_lang != lang_code:  # 현재 언어와 다른 언어가 선택되었을 경우에만 실행
            self.current_lang = lang_code  # 현재 언어 코드 업데이트
            self.file_processor.set_get_string_func(self.get_string)  # 백엔드 클래스에도 변경된 언어 함수 전달
            self.update_ui_language()  # 전체 UI 텍스트 업데이트

    def on_language_change(self, *args):
        """언어 선택 라디오 버튼의 값이 변경될 때 호출되는 콜백 함수입니다."""
        new_lang = self.lang_var.get()  # 새로 선택된 언어 코드를 가져옴
        self.set_language(new_lang)  # 언어 변경 함수 호출

    # --- UI 업데이트 ---
    def update_ui_language(self, is_initial_setup=False):
        """
        창 제목, 메뉴, 버튼 등 UI의 모든 텍스트 요소를 현재 설정된 언어로 업데이트합니다.
        
        Args:
            is_initial_setup (bool): 프로그램 최초 실행 시 호출 여부. True이면 초기 메시지를 표시합니다.
        """
        # 1. 기본 UI 요소 텍스트 변경
        self.master.title(self.get_string('window_title'))
        self.create_menubar()  # 메뉴바의 텍스트도 갱신해야 하므로 재생성
        self.start_button.config(text=self.get_string('start_button'))
        
        # 2. 현재 상태(대기, 처리 중, 완료)에 따라 진행률 레이블 텍스트 동적 변경
        if not self.is_processing:  # 작업 대기 또는 완료 상태
            if self.total_files_count > 0 and self.progress_bar['value'] >= 100:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                 self.progress_label_var.set(self.get_string('status_waiting'))
        else:  # 작업 진행 중 상태
            if self.last_progress_info['total'] == 0:  # 아직 파일 개수 파악 전
                 self.progress_label_var.set(self.get_string('status_searching'))
            else:  # 파일 개수 파악 후 처리 중
                self.progress_label_var.set(self.get_string('status_processing', **self.last_progress_info))
        
        # 3. 프로그램 시작 시 초기 안내 메시지 표시
        if is_initial_setup:
            self.log_data.clear()
            self.show_initial_message()
        
        # 4. 언어가 변경되었으므로, 기존 로그도 새로운 언어로 다시 표시
        self.re_render_logs()
        
    # --- 위젯 생성 (메뉴바) ---
    def create_menubar(self):
        """메뉴바를 생성하거나, 언어 변경 시 기존 메뉴바를 삭제하고 새로운 언어로 다시 생성합니다."""
        if self.menubar is None:  # 최초 생성
            self.menubar = tk.Menu(self.master)
            self.master.config(menu=self.menubar)
        else:
            self.menubar.delete(0, tk.END)  # 기존 메뉴 항목 모두 삭제

        # '언어' 메뉴 생성 및 하위 라디오 버튼 추가
        self.language_menu = tk.Menu(self.menubar, tearoff=0)
        self.language_menu.add_radiobutton(label="한국어", variable=self.lang_var, value='ko')
        self.language_menu.add_radiobutton(label="English", variable=self.lang_var, value='en')
        self.language_menu.add_radiobutton(label="日本語", variable=self.lang_var, value='ja')
        
        # 메뉴바에 '언어'와 '정보' 메뉴 추가
        self.menubar.add_cascade(label=self.get_string('menu_language'), menu=self.language_menu)
        self.menubar.add_command(label=self.get_string('menu_about'), command=self.show_about_info)

    # --- 기능 (정보 표시) ---
    def show_about_info(self):
        """'정보(About)' 메뉴를 클릭했을 때 로그 영역에 프로그램 정보를 출력합니다."""
        self._add_raw_text(SEPARATOR)
        self._add_log_event('SHOW_ABOUT_INFO')  # 정보 표시 '이벤트'를 로그 데이터에 추가
        self._add_raw_text(SEPARATOR)
        self.re_render_logs()  # 로그를 다시 렌더링하여 화면에 표시

    # --- 위젯 생성 (메인 화면) ---
    def create_widgets(self):
        """메인 윈도우에 표시될 버튼, 레이블, 진행률 표시줄, 로그 영역 등의 위젯을 생성하고 배치합니다."""
        # 상단 컨트롤 프레임 (진행률 표시줄, 상태 레이블, 시작 버튼 포함)
        top_frame = tk.Frame(self.master)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)

        self.start_button = tk.Button(control_frame, command=self.start_processing_thread)
        self.start_button.pack(side=tk.RIGHT, padx=(10, 0))  # 오른쪽에 배치
        self.progress_label = tk.Label(control_frame, textvariable=self.progress_label_var, width=25)
        self.progress_label.pack(side=tk.LEFT, padx=(0, 5))  # 왼쪽에 배치
        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X)  # 남은 공간 채우기
        
        # 하단 로그 영역 (스크롤 가능)
        # 폰트는 가독성이 좋은 고정폭 글꼴(Consolas) 사용, 초기 상태는 'disabled'로 읽기 전용.
        self.log_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD, font=("Consolas", 9), state='disabled')
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    # --- 로그 관리 ---
    def show_initial_message(self):
        """프로그램 시작 시 사용자에게 사용법을 안내하는 초기 메시지를 로그 데이터에 추가합니다."""
        self._add_raw_text(SEPARATOR)
        self._add_log_event('program_started')
        self._add_raw_text(SEPARATOR)
        
        # 처리 대상 폴더 목록을 동적으로 생성하여 안내 메시지에 포함
        folder_lines = []
        folders = self.file_processor.target_folders
        for i, folder in enumerate(folders):
            prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
            folder_lines.append(self.get_string(prefix_key, folder_name=folder))
        
        self._add_log_event('initial_info_db', {'folder_structure': "\n".join(folder_lines)})
        self._add_log_event('initial_info_start')
        self._add_raw_text(SEPARATOR)
        
    def re_render_logs(self):
        """
        `self.log_data`에 저장된 모든 로그 기록을 현재 언어로 변환하여 로그 영역에 다시 씁니다.
        언어 변경 시 이전 로그들도 새 언어로 번역되어 보이게 하는 핵심 기능입니다.
        """
        self.log_area.configure(state='normal')  # 내용을 수정하기 위해 일시적으로 편집 가능 상태로 변경
        self.log_area.delete('1.0', tk.END)  # 기존 로그 내용 모두 삭제

        output_buffer = []  # 화면에 출력할 문자열들을 임시로 저장할 리스트 (성능 향상 목적)

        # self.log_data 리스트를 순회하며 각 로그 항목을 문자열로 변환
        for i, (timestamp, key, kwargs) in enumerate(self.log_data):
            if timestamp is None:  # 타임스탬프가 없는 데이터는 구분선과 같은 원시 텍스트.
                output_buffer.append(key + "\n")
                continue

            message = self.get_string(key, **kwargs)  # 로그 키에 해당하는 메시지를 현재 언어로 가져옴
            if not message:
                continue

            # 동일한 밀리초에 발생한 여러 로그는 타임스탬프를 한 번만 표시하여 가독성 향상
            is_same_group = i > 0 and self.log_data[i-1][0] == timestamp
            line_prefix = f"[{timestamp}] " if not is_same_group else ' ' * 13

            # 로그 키에 따라 특별한 포맷팅 적용
            if key == 'SHOW_ABOUT_INFO':  # '정보' 표시는 여러 줄로 구성
                about_lines = [self.get_string('about_header')]
                for info_key, value in self.ABOUT_INFO.items():
                    label_key = f'about_label_{info_key}'
                    label_text = self.get_string(label_key)
                    about_lines.append(f"  - {label_text}\t: {value}")
                output_buffer.append("\n".join(about_lines) + "\n")
            elif key == 'backend_job_summary':  # 작업 요약은 가독성을 위해 앞에 한 줄 띄움
                output_buffer.append(f"\n[{timestamp}] {message}")
            else:  # 일반 로그
                output_buffer.append(f"{line_prefix}{message}")

        final_text = "".join(output_buffer)  # 버퍼의 모든 문자열을 하나로 합침
        self.log_area.insert('1.0', final_text)  # 합쳐진 텍스트를 로그 영역에 한 번에 삽입 (효율적)
        self.log_area.configure(state='disabled')  # 다시 읽기 전용 상태로 변경
        self.log_area.see(tk.END)  # 스크롤을 항상 맨 아래로 이동시켜 최신 로그가 보이게 함

    def _add_raw_text(self, text):
        """구분선과 같이 번역이 필요 없는 순수 텍스트를 로그 데이터에 추가합니다."""
        self.log_data.append((None, text, None)) # (타임스탬프 없음, 텍스트, 인자 없음)

    def _add_log_event(self, key, kwargs=None):
        """번역이 필요한 로그 '이벤트'를 현재 타임스탬프와 함께 로그 데이터에 추가합니다."""
        if kwargs is None:
            kwargs = {}
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # 시:분:초.밀리초 형식
        self.log_data.append((timestamp, key, kwargs))

    # --- 스레드 관리 및 이벤트 처리 ---
    def start_processing_thread(self):
        """
        '작업 시작' 버튼을 클릭했을 때 호출됩니다.
        UI를 '작업 중' 상태로 바꾸고, 실제 파일 처리를 담당할 백그라운드 스레드를 시작합니다.
        """
        # 1. 필수 파일(manifest.db) 존재 여부 사전 확인
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        # 2. 새 작업 시작을 위해 기존 로그 초기화
        self.log_data.clear()
        self.show_initial_message()
        self.re_render_logs()
        
        # 3. UI를 '작업 중' 상태로 전환
        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)  # 중복 실행 방지를 위해 버튼 비활성화
        self.progress_bar['value'] = 0
        self.last_progress_info = {'current': 0, 'total': 0}
        self.progress_label_var.set(self.get_string('status_searching'))
        
        # 4. 백엔드 클래스에 현재 UI의 언어 설정 전달
        self.file_processor.set_get_string_func(self.get_string)
        
        # 5. 파일 처리 함수(process_files)를 실행할 별도의 스레드 생성
        # daemon=True로 설정하여 메인 프로그램 종료 시 스레드도 함께 종료되도록 함.
        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()  # 스레드 시작
        
        # 6. 백엔드 스레드에서 오는 데이터를 감시하는 큐 모니터링 루프 시작
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread):
        """
        백그라운드 스레드가 살아있는 동안 주기적으로 큐를 확인하여
        로그와 진행률 정보를 가져와 UI에 반영합니다. 비동기 작업의 핵심입니다.
        
        Args:
            thread (threading.Thread): 모니터링할 백그라운드 스레드 객체.
        """
        log_items_batch = []
        progress_updates = []
        
        # 1. 큐에 쌓인 데이터를 일괄적으로 가져옴 (UI 업데이트 부하 감소)
        try:
            while not self.log_queue.empty():
                log_items_batch.append(self.log_queue.get_nowait())
            while not self.progress_queue.empty():
                progress_updates.append(self.progress_queue.get_nowait())
        except queue.Empty:
            pass  # 큐가 비어있는 것은 정상적인 상황

        # 2. 가져온 로그 데이터 처리
        if log_items_batch:
            # 작업 시작 로그 바로 뒤에 강조용 구분선 추가
            is_first_job_log = self.log_data[-1][1] == SEPARATOR
            if is_first_job_log:
                self._add_raw_text("")
                self._add_raw_text("="*100)

            for key, kwargs in log_items_batch:
                self._add_log_event(key, kwargs)
            self.re_render_logs()  # 로그 영역 업데이트

        # 3. 가져온 진행률 데이터 처리
        if progress_updates:
            for progress_val, current, total in progress_updates:
                self.progress_bar['value'] = progress_val
                self.last_progress_info = {'current': current, 'total': total}
                self.progress_label_var.set(self.get_string('status_processing', current=current, total=total))
                self.total_files_count = total

        # 4. 스레드 상태 확인 및 재귀 호출
        if thread.is_alive():  # 스레드가 아직 실행 중이면,
            # 지정된 시간(GUI_UPDATE_INTERVAL_MS) 후에 다시 이 함수를 호출하여 큐를 계속 감시.
            self.master.after(self.GUI_UPDATE_INTERVAL_MS, lambda: self.monitor_queue(thread))
        else:  # 스레드 작업이 완료되었으면,
            # 큐에 남아있을 수 있는 마지막 데이터를 모두 처리
            final_log_items = []
            try:
                while True: 
                    final_log_items.append(self.log_queue.get_nowait())
            except queue.Empty: pass
            
            if final_log_items:
                for key, kwargs in final_log_items:
                    self._add_log_event(key, kwargs)
            
            self.re_render_logs()

            # 5. UI를 '완료' 상태로 전환
            self.is_processing = False
            self.progress_bar['value'] = 100
            if self.total_files_count > 0:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                self.progress_label_var.set(self.get_string('status_complete'))
            self.start_button.config(state=tk.NORMAL)  # 버튼 다시 활성화

# ##################################################################
# Class: RenameHashedFile
#
# 목적: 파일 시스템과 직접 상호작용하는 모든 백엔드 로직을 담당.
#       GUI 클래스로부터 완전히 분리되어 독립적으로 작동 가능.
#
# 주요 기능:
# 1. 지정된 폴더 내에서 처리 대상 파일(SHA1 형식 이름) 검색.
# 2. 'manifest.db'에서 해시-파일이름 매핑 데이터를 메모리로 로드.
# 3. ThreadPoolExecutor를 사용해 다수의 파일을 병렬로 처리.
#    - 각 파일의 MD5, xxHash64 해시 계산.
#    - 계산된 해시를 DB 데이터와 비교하여 원본 파일명 조회.
#    - 일치하는 파일 이름 변경.
# 4. 해시가 일치하지 않는 파일들에 대한 예외 처리 로직 수행(파일 내용 기반 추측).
# 5. 처리 과정 및 결과를 Queue를 통해 GUI 스레드로 전달.
# ##################################################################
class RenameHashedFile:
    # --- 백엔드 클래스 초기화 메서드 ---
    def __init__(self, log_queue, progress_queue, get_string_func):
        """
        RenameHashedFile 클래스의 인스턴스를 초기화합니다.
        
        Args:
            log_queue (queue.Queue): 로그 메시지를 GUI로 보내기 위한 큐.
            progress_queue (queue.Queue): 진행률 정보를 GUI로 보내기 위한 큐.
            get_string_func (function): 다국어 문자열을 반환하는 GUI의 함수.
        """
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']  # 파일 이름 변경 작업을 수행할 대상 폴더 목록
        self.hash_list = {}  # DB에서 불러온 {해시: 파일명} 데이터를 저장할 딕셔너리
        self.unprocessed_files = []  # 1차 해시 대조에서 실패한 파일들의 경로를 저장할 리스트
        self.log_queue = log_queue  # GUI와의 통신을 위한 큐 참조
        self.progress_queue = progress_queue
        self.get_string = get_string_func

    def set_get_string_func(self, get_string_func):
        """GUI에서 언어가 변경되었을 때, 이 클래스가 사용하는 번역 함수를 업데이트합니다."""
        self.get_string = get_string_func

    # --- GUI로의 정보 전달 메서드 ---
    def log(self, key, **kwargs):
        """로그 메시지를 생성하여 로그 큐에 넣습니다. GUI 스레드가 이를 가져가 화면에 표시합니다."""
        self.log_queue.put((key, kwargs))

    def update_progress(self, value, current, total):
        """진행률 정보를 생성하여 진행률 큐에 넣습니다."""
        self.progress_queue.put((value, current, total))

    # --- 메인 파일 처리 로직 ---
    def process_files(self):
        """파일 이름 변경 작업의 전체 과정을 순차적으로 실행합니다."""
        # 1. manifest.db 파일 존재 확인
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            self.log('backend_warning_db_not_found')
            return
            
        # 2. 작업 시작 안내 로그 전송
        self.log('backend_info_long_time')
        self.log('backend_info_auto_rename')
        self.log('backend_searching_files')
        
        # 3. 대상 폴더에서 모든 처리 대상 파일 검색
        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        
        self.update_progress(0, 0, total_files)  # 진행률 0%로 초기화

        if not files:  # 처리할 파일이 없으면 작업 종료
            self.log('backend_no_files_found')
            return
            
        self.log('backend_found_files', count=total_files)

        # 4. SQLite DB에 연결하여 해시 데이터를 메모리(self.hash_list)로 로드
        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename
        
        # 5. 처리 결과 카운트 변수 초기화
        processed_count_rename = 0  # 해시 대조로 이름 변경 성공 카운트
        processed_count_check = 0   # 예외 처리로 이름 변경 성공 카운트
        final_unprocessed_files = [] # 최종적으로 처리 실패한 파일 목록
        self.unprocessed_files.clear()

        # 6. ThreadPoolExecutor를 사용한 병렬 파일 처리
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 각 파일에 대해 process 함수를 실행하는 작업을 스레드 풀에 제출
            futures = {executor.submit(self.process, file): file for file in files}
            
            processed_futures = 0
            # as_completed: 작업이 완료되는 순서대로 결과를 반환받음
            for future in concurrent.futures.as_completed(futures):
                processed_futures += 1
                progress = (processed_futures / total_files) * 100.0
                self.update_progress(progress, processed_futures, total_files) # 진행률 업데이트
                
                try:
                    was_successful, data = future.result()  # 스레드 작업 결과 가져오기
                    if was_successful:
                        processed_count_rename += 1
                    else:  # 해시 불일치 파일
                        self.unprocessed_files.append(data)
                except Exception as exc:  # 스레드 내에서 예외 발생 시
                    file_path = futures[future]
                    self.log('backend_file_process_fail', path=file_path, exc=str(exc))

        # 7. 1차 처리에서 실패한 파일들에 대한 예외 처리 로직
        self.log('backend_unprocessed_header')
        if self.unprocessed_files:
            for file_path in self.unprocessed_files:
                renamed_by_content = False
                try:
                    # 파일의 첫 줄을 읽어 파일 유형을 추측 (매니페스트 파일 대상)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                        first_line = file.readline().strip()
                    
                    # 특정 경로 문자열이 포함되어 있으면 해당 매니페스트 파일로 간주
                    new_filename = None
                    if 'a/bdl' in first_line: new_filename = os.path.join("manifest", "bdl_assetmanifest")
                    elif 'manifest/' in first_line: new_filename = os.path.join("manifest", "manifest_assetmanifest")
                    elif 'm/' in first_line: new_filename = os.path.join("manifest", "movie2manifest")
                    elif 'b/' in first_line: new_filename = os.path.join("manifest", "soundmanifest")
                    
                    if new_filename:
                        new_filepath = self.get_unique_filename(new_filename)
                        os.rename(file_path, new_filepath)
                        processed_count_check += 1
                        relative_file_path = os.path.relpath(file_path, os.getcwd())
                        
                        self.log('backend_rename_exception_block', original=relative_file_path, new=new_filename.replace(os.sep, '\\'))
                        renamed_by_content = True
                except Exception as e:
                    self.log('backend_unprocessed_error', error=str(e))
                
                # 예외 처리 로직으로도 이름 변경에 실패한 경우, 최종 미처리 파일 목록에 추가
                if not renamed_by_content:
                    final_unprocessed_files.append(file_path)

        # 8. 최종 작업 결과 요약 로그 전송
        total_processed = processed_count_rename + processed_count_check
        self.log('backend_job_summary', total_processed=total_processed)
        if final_unprocessed_files:
            self.log('backend_unprocessed_summary', count=len(final_unprocessed_files))

    # --- 개별 파일 처리 ---
    def process(self, file_path):
        """
        단일 파일에 대해 해시를 계산하고, self.hash_list와 비교하여 이름 변경을 시도합니다.
        
        Returns:
            (bool, str): (성공 여부, 파일 경로) 튜플을 반환.
        """
        # 1. MD5 해시로 먼저 시도
        hash_md5_value = self.calculate_md5(file_path).hexdigest()
        if hash_md5_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_md5_value])

        # 2. MD5 실패 시, 더 빠른 xxHash64로 시도
        hash_xxhash64_value = self.calculate_xxhash64(file_path).hexdigest()
        if hash_xxhash64_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_xxhash64_value])

        # 두 해시 모두 불일치 시, 처리 실패로 간주하고 원본 파일 경로 반환
        return False, file_path

    def rename_file(self, file_path, new_filename):
        """실제로 파일의 이름을 변경하고, 성공 또는 실패 결과를 로그로 남깁니다."""
        new_filepath = os.path.join(os.getcwd(), new_filename)
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)  # 대상 폴더가 없으면 생성

        # 이름 변경하려는 파일이 이미 존재할 경우, 중복을 피하기 위해 새 이름 생성
        if os.path.exists(new_filepath):
            new_filepath = self.get_unique_filename(new_filepath)
            
        try:
            os.rename(file_path, new_filepath)
            relative_file_path = os.path.relpath(file_path, os.getcwd())  # 로그에 표시할 상대 경로
            
            self.log('backend_rename_block', original=relative_file_path, new=new_filename.replace(os.sep, '\\').replace('/', '\\'))
            return True, new_filepath
        except Exception as e:
            self.log('backend_rename_error', error=str(e))
            return False, file_path

    # --- 유틸리티 메서드 ---
    def calculate_md5(self, file_path):
        """파일을 4KB 청크 단위로 읽어 메모리 효율적으로 MD5 해시를 계산합니다."""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash

    def calculate_xxhash64(self, file_path):
        """파일을 4KB 청크 단위로 읽어 메모리 효율적으로 xxHash64 해시를 계산합니다."""
        xxhash64_hash = xxhash.xxh64()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                xxhash64_hash.update(chunk)
        return xxhash64_hash

    def get_all_files_in_folders(self, target_folders):
        """지정된 모든 폴더와 그 하위 폴더를 재귀적으로 탐색하여 SHA1 형식의 파일 목록을 반환합니다."""
        all_files = []
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        if self.is_sha1(file_name):  # 파일명이 SHA1 형식인지 확인
                            all_files.append(os.path.join(root, file_name))
        return all_files

    def is_sha1(self, s):
        """주어진 문자열이 SHA1 해시 형식(길이 40의 16진수 문자열)인지 확인합니다."""
        return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)

    def get_unique_filename(self, file_path):
        """
        주어진 파일 경로가 이미 존재할 경우, 중복되지 않는 새 파일 경로를 생성하여 반환합니다.
        예: 'file.txt' -> 'file_(Duplicate_1).txt'
        """
        base, extension = os.path.splitext(file_path)
        counter = 1
        new_file_path = f"{base}{extension}"
        while os.path.exists(new_file_path):
            new_file_path = f"{base}_(Duplicate_{counter}){extension}"
            counter += 1
        return new_file_path


# ===================================================================
# 프로그램 실행 진입점 (Entry Point)
# ===================================================================
if __name__ == '__main__':
    # 이 스크립트가 직접 실행되었을 때만 아래 코드가 실행됩니다.
    
    root = tk.Tk()  # 메인 Tkinter 윈도우 객체 생성
    app = FileRenamerGUI(root)  # 우리가 정의한 GUI 어플리케이션 클래스의 인스턴스 생성
    root.mainloop()  # GUI 이벤트 루프를 시작하여 사용자의 입력을 기다리고 창을 화면에 유지