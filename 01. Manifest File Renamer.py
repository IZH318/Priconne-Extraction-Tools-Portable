# 필요한 라이브러리 임포트
import os
import sys
import sqlite3
import hashlib
import concurrent.futures
import xxhash
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import threading
import queue

# 중앙 언어 관리 시스템
LANGUAGES = {
    'ko': {
        'window_title': "Manifest File Renamer", 'menu_language': "언어(Language)", 'menu_about': "정보(About)",
        'start_button': "작업 시작", 'status_waiting': "상태: 대기 중", 'status_searching': "파일 검색 중...",
        'status_processing': "처리: {current} / {total}", 'status_complete': "상태: 완료",
        'status_complete_count': "완료: {count} / {count}",
        'initial_info_db': "[ 주의 ] 현재 디렉터리에 'manifest.db' 파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n\n"
                           "         [ 예시 ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 실행 파일)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 안내 ] '작업 시작' 버튼을 눌러주세요.",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 작업 대상 폴더)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 작업 대상 폴더)",
        'error_title': "오류", 'error_db_not_found': "'manifest.db' 파일을 찾을 수 없습니다。",
        'job_start_log': "\n" + "="*100 + "\n[ 작업 시작 ] 새로운 작업을 시작합니다.\n",
        'job_complete_log': "\n작업이 모두 완료되었습니다.",
        'backend_warning_db_not_found': "[ 경고 ] 현재 디렉터리에 'manifest.db'파일이 존재하지 않습니다.",
        'backend_info_long_time': " [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.",
        'backend_info_auto_rename': "          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n",
        'backend_searching_files': "[ 진행 ] 대상 폴더에서 파일 목록을 검색 중입니다...",
        'backend_no_files_found': "대상 폴더에서 처리 할 파일을 찾을 수 없습니다.",
        'backend_found_files': "[ 완료 ] 총 {count}개의 처리 대상 파일을 찾았습니다. 이름 변경을 시작합니다.",
        'backend_unprocessed_header': "\n\n\n [ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략되었습니다.",
        'backend_unprocessed_error': " 오류 발생: 알 수 없는 오류가 발생했습니다. ({error})",
        'backend_file_process_fail': "파일 처리 실패 {path}: {exc}",
        'backend_job_summary': "\n\n\n--- 작업 완료 ---\n총 {total_processed}개의 파일이 처리되었습니다.",
        'backend_unprocessed_summary': "{count}개의 파일은 처리되지 않았습니다.",
        'backend_rename_exception_success': "\n  - 작업 상태: 예외 처리된 파일 이름 변경 완료",
        'backend_rename_success': "\n  - 작업 상태: 파일 이름 변경 완료",
        'backend_rename_original': "    - 원본: \\{path}",
        'backend_rename_changed': "    - 변경: \\{path}",
        'backend_rename_error': "오류: {error}",
        'about_header': "[ 프로그램 정보 ]",
        'about_label_program': "프로그램 이름",
        'about_label_version': "버전",
        'about_label_updated': "최종 업데이트",
        'about_label_license': "라이선스",
        'about_label_developer': "개발자",
        'about_label_website': "웹 사이트",
    },
    'en': {
        'window_title': "Manifest File Renamer", 'menu_language': "Language", 'menu_about': "About",
        'start_button': "Start Job", 'status_waiting': "Status: Waiting", 'status_searching': "Searching files...",
        'status_processing': "Processing: {current} / {total}", 'status_complete': "Status: Complete",
        'status_complete_count': "Complete: {count} / {count}",
        'initial_info_db': "[ WARNING ] 'manifest.db' and the target files must be in the current directory with their original structure.\n\n"
                           "         [ Example ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← Executable)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ INFO ] Please press the 'Start Job' button.",
        'folder_item_branch': "            ├─ {folder_name}\\ (← Target folder)",
        'folder_item_last':   "            └─ {folder_name}\\ (← Target folder)",
        'error_title': "Error", 'error_db_not_found': "'manifest.db' file not found.",
        'job_start_log': "\n" + "="*100 + "\n[ JOB START ] Starting a new job.\n",
        'job_complete_log': "\nThe job has been completed.",
        'backend_warning_db_not_found': "[ WARNING ] 'manifest.db' does not exist in the current directory.",
        'backend_info_long_time': " [ INFO ] This may take a long time if there are many files or the storage device is slow.",
        'backend_info_auto_rename': "          All files will be renamed automatically after being loaded.\n",
        'backend_searching_files': "[ PROGRESS ] Searching for files in target folders...",
        'backend_no_files_found': "No files to process were found in the target folders.",
        'backend_found_files': "[ COMPLETE ] Found a total of {count} files to process. Starting rename.",
        'backend_unprocessed_header': "\n\n\n [ INFO ] Files not recognized by manifest.db were handled or skipped as follows.",
        'backend_unprocessed_error': " An unknown error occurred. ({error})",
        'backend_file_process_fail': "Failed to process file {path}: {exc}",
        'backend_job_summary': "\n\n\n--- JOB COMPLETE ---\nA total of {total_processed} files have been processed.",
        'backend_unprocessed_summary': "{count} files were not processed.",
        'backend_rename_exception_success': "\n  - Status: Renamed file via exception handling",
        'backend_rename_success': "\n  - Status: File renamed successfully",
        'backend_rename_original': "    - Original: \\{path}",
        'backend_rename_changed': "    - New: \\{path}",
        'backend_rename_error': "Error: {error}",
        'about_header': "[ Program Information ]",
        'about_label_program': "Program",
        'about_label_version': "Version",
        'about_label_updated': "Updated",
        'about_label_license': "License",
        'about_label_developer': "Developer",
        'about_label_website': "Website",
    },
    'ja': {
        'window_title': "Manifest File Renamer", 'menu_language': "言語(Language)", 'menu_about': "情報(About)",
        'start_button': "作業開始", 'status_waiting': "状態: 待機中", 'status_searching': "ファイルを検索中...",
        'status_processing': "処理中: {current} / {total}", 'status_complete': "状態: 完了",
        'status_complete_count': "完了: {count} / {count}",
        'initial_info_db': "[ 注意 ] 現在のディレクトリに 'manifest.db' ファイルと対象ファイルを元の構造のまま配置してください。\n\n"
                           "         [ 例 ]\n"
                           "         C:\\MyRenamer\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 実行ファイル)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 案内 ] 「作業開始」ボタンを押してください。",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 対象フォルダ)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 対象フォルダ)",
        'error_title': "エラー", 'error_db_not_found': "'manifest.db' ファイルが見つかりません。",
        'job_start_log': "\n" + "="*100 + "\n[ 作業開始 ] 新しい作業を開始します。\n",
        'job_complete_log': "\nすべての作業が完了しました。",
        'backend_warning_db_not_found': "[ 警告 ] 現在のディレクトリに 'manifest.db' が存在しません。",
        'backend_info_long_time': "[ 案内 ] ファイル数が多い、またはストレージの速度が遅い場合、時間がかかることがあります。",
        'backend_info_auto_rename': "          すべてのファイルが読み込まれた後、自動的にリネームされます。\n",
        'backend_searching_files': "[ 進行 ] 対象フォルダ内のファイルを検索しています...",
        'backend_no_files_found': "対象フォルダに処理するファイルが見つかりませんでした。",
        'backend_found_files': "[ 完了 ] 合計{count}個の処理対象ファイルを見つけました。名前の変更を開始します。",
        'backend_unprocessed_header': "\n\n\n [ 案内 ] manifest.dbで認識できなかったファイルは、次のように例外処理またはスキップされました。",
        'backend_unprocessed_error': " 不明なエラーが発生しました。({error})",
        'backend_file_process_fail': "ファイル処理失敗 {path}: {exc}",
        'backend_job_summary': "\n\n\n--- 作業完了 ---\n合計{total_processed}個のファイルが処理されました。",
        'backend_unprocessed_summary': "{count}個のファイルは処理されませんでした。",
        'backend_rename_exception_success': "\n  - 状態: 例外処理によりファイル名を変更しました",
        'backend_rename_success': "\n  - 状態: ファイル名の変更が完了しました",
        'backend_rename_original': "    - 元の名前: \\{path}",
        'backend_rename_changed': "    - 新しい名前: \\{path}",
        'backend_rename_error': "エラー: {error}",
        'about_header': "[ プログラム情報 ]",
        'about_label_program': "プログラム名",
        'about_label_version': "バージョン",
        'about_label_updated': "最終更新",
        'about_label_license': "ライセンス",
        'about_label_developer': "開発者",
        'about_label_website': "ウェブサイト",
    }
}

SEPARATOR = "-" * 100

class FileRenamerGUI:
    ABOUT_INFO = {
        'program': "Manifest File Renamer",
        'version': "2.0.0",
        'updated': "2025-07-15",
        'license': "MIT License",
        'developer': "(Github) IZH318",
        'website': "https://github.com/IZH318",
    }

    def __init__(self, master):
        self.master = master
        self.current_lang = 'ko'
        self.lang_var = tk.StringVar(value=self.current_lang)
        self.lang_var.trace_add("write", self.on_language_change)
        
        self.log_data = []
        
        self.last_progress_info = {'current': 0, 'total': 0}
        self.is_processing = False
        window_width = 800
        window_height = 600
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        self.master.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue, self.get_string)
        
        self.MAX_LOGS_PER_CYCLE = 1000
        self.GUI_UPDATE_INTERVAL_MS = 100
        
        self.progress_label_var = tk.StringVar()
        self.total_files_count = 0

        self.menubar = None
        self.language_menu = None

        self.create_widgets()
        self.update_ui_language(is_initial_setup=True)

    def get_string(self, key, **kwargs):
        return LANGUAGES[self.current_lang].get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    def set_language(self, lang_code):
        if self.current_lang != lang_code:
            self.current_lang = lang_code
            self.file_processor.set_get_string_func(self.get_string)
            self.update_ui_language()

    def on_language_change(self, *args):
        new_lang = self.lang_var.get()
        self.set_language(new_lang)

    def update_ui_language(self, is_initial_setup=False):
        self.master.title(self.get_string('window_title'))
        
        # 메뉴바를 현재 언어로 다시 그림
        self.create_menubar()
        
        self.start_button.config(text=self.get_string('start_button'))
        
        if not self.is_processing:
            if self.total_files_count > 0 and self.progress_bar['value'] == 100:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                 self.progress_label_var.set(self.get_string('status_waiting'))
        else:
            if self.last_progress_info['total'] == 0:
                 self.progress_label_var.set(self.get_string('status_searching'))
            else:
                self.progress_label_var.set(self.get_string('status_processing', **self.last_progress_info))
        
        if is_initial_setup:
            self.show_initial_message()
        
        self.re_render_logs()
        
    def create_menubar(self):
        """
        메뉴바를 생성하거나, 이미 있다면 내용을 모두 지우고 현재 언어로 다시 만듭니다.
        이것이 가장 안정적인 방법입니다.
        """
        if self.menubar is None:
            # 프로그램 시작 시 한 번만 메뉴바 객체를 생성
            self.menubar = tk.Menu(self.master)
            self.master.config(menu=self.menubar)
        else:
            # 언어 변경 시, 기존 메뉴 항목들을 모두 삭제
            self.menubar.delete(0, tk.END)

        # 언어 메뉴 (드롭다운) 생성
        self.language_menu = tk.Menu(self.menubar, tearoff=0)
        self.language_menu.add_radiobutton(label="한국어", variable=self.lang_var, value='ko')
        self.language_menu.add_radiobutton(label="English", variable=self.lang_var, value='en')
        self.language_menu.add_radiobutton(label="日本語", variable=self.lang_var, value='ja')
        
        # 현재 언어에 맞는 텍스트로 메뉴바에 항목들을 다시 추가
        self.menubar.add_cascade(label=self.get_string('menu_language'), menu=self.language_menu)
        self.menubar.add_command(label=self.get_string('menu_about'), command=self.show_about_info)

    def show_about_info(self):
        self.log_data.append(SEPARATOR)
        self.log_data.append('SHOW_ABOUT_INFO')
        self.log_data.append(SEPARATOR)
        self.re_render_logs()

    def create_widgets(self):
        # 메뉴바 생성은 update_ui_language에서 처리하므로 여기서 호출하지 않음
        top_frame = tk.Frame(self.master)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        
        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)

        # 1. 시작 버튼을 생성하고 오른쪽에 배치합니다. (side=tk.RIGHT)
        self.start_button = tk.Button(control_frame, command=self.start_processing_thread)
        self.start_button.pack(side=tk.RIGHT, padx=(10, 0))

        # 2. 상태 레이블을 왼쪽에 배치합니다.
        self.progress_label = tk.Label(control_frame, textvariable=self.progress_label_var, width=25)
        self.progress_label.pack(side=tk.LEFT, padx=(0, 5))

        # 3. 프로그레스 바를 레이블 옆, 남은 공간을 모두 채우도록 왼쪽에 배치합니다.
        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        # 로그 영역은 변경 없이 그대로 둡니다.
        self.log_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD, font=("Consolas", 9))
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    def show_initial_message(self):
        self.log_data.clear()
        
        folder_lines = []
        folders = self.file_processor.target_folders
        for i, folder in enumerate(folders):
            prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
            folder_lines.append((prefix_key, {'folder_name': folder}))

        initial_log_structure = [
            SEPARATOR,
            ('initial_info_db', {'folder_structure': "\n".join([self.get_string(k, **v) for k,v in folder_lines])}),
            ('initial_info_start', {}),
            SEPARATOR,
        ]
        self.log_data = initial_log_structure
        self.re_render_logs()
        
    def re_render_logs(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        
        rendered_logs = []
        for item in self.log_data:
            if isinstance(item, str):
                if item == 'SHOW_ABOUT_INFO':
                    about_lines = [self.get_string('about_header')]
                    for key, value in self.ABOUT_INFO.items():
                        label_key = f'about_label_{key}'
                        label_text = self.get_string(label_key)
                        about_lines.append(f"  - {label_text}\t: {value}")
                    rendered_logs.append("\n".join(about_lines))
                else:
                    rendered_logs.append(item)
            elif isinstance(item, tuple):
                key, original_kwargs = item
                kwargs = original_kwargs.copy()
                
                if key == 'initial_info_db':
                    folder_lines = []
                    folders = self.file_processor.target_folders
                    for i, folder in enumerate(folders):
                         prefix_key = 'folder_item_last' if i == len(folders) - 1 else 'folder_item_branch'
                         folder_lines.append(self.get_string(prefix_key, folder_name=folder))
                    kwargs['folder_structure'] = "\n".join(folder_lines)

                rendered_logs.append(self.get_string(key, **kwargs))

        self.log_area.insert('1.0', "\n".join(rendered_logs))
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def add_log_data(self, log_item):
        self.log_data.append(log_item)
        self.re_render_logs()

    def start_processing_thread(self):
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        self.show_initial_message()
        self.add_log_data(('job_start_log', {}))
        
        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.last_progress_info = {'current': 0, 'total': 0}
        self.progress_label_var.set(self.get_string('status_searching'))
        
        self.file_processor.set_get_string_func(self.get_string)
        
        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread):
        new_log_data = []
        try:
            for _ in range(self.MAX_LOGS_PER_CYCLE):
                new_log_data.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        
        if new_log_data:
            self.log_data.extend(new_log_data)
            self.re_render_logs()

        try:
            while not self.progress_queue.empty():
                progress_val, current, total = self.progress_queue.get_nowait()
                self.progress_bar['value'] = progress_val
                self.last_progress_info = {'current': current, 'total': total}
                self.progress_label_var.set(self.get_string('status_processing', current=current, total=total))
                self.total_files_count = total
        except queue.Empty:
            pass

        if thread.is_alive():
            self.master.after(self.GUI_UPDATE_INTERVAL_MS, lambda: self.monitor_queue(thread))
        else:
            final_logs = []
            try:
                while True: 
                    final_logs.append(self.log_queue.get_nowait())
            except queue.Empty: pass
            
            if final_logs:
                self.log_data.extend(final_logs)
            
            self.add_log_data(('job_complete_log', {}))
            self.re_render_logs()

            self.is_processing = False
            self.progress_bar['value'] = 100
            if self.total_files_count > 0:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                self.progress_label_var.set(self.get_string('status_complete'))
            self.start_button.config(state=tk.NORMAL)


class RenameHashedFile:
    def __init__(self, log_queue, progress_queue, get_string_func):
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        self.hash_list = {}
        self.unprocessed_files = []
        self.log_queue = log_queue
        self.progress_queue = progress_queue
        self.get_string = get_string_func

    def set_get_string_func(self, get_string_func):
        self.get_string = get_string_func

    def log(self, key, **kwargs):
        self.log_queue.put((key, kwargs))

    def update_progress(self, value, current, total):
        self.progress_queue.put((value, current, total))

    def process_files(self):
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            self.log('backend_warning_db_not_found')
            return
            
        self.log('backend_info_long_time')
        self.log('backend_info_auto_rename')
        self.log('backend_searching_files')
        
        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        
        self.update_progress(0, 0, total_files)

        if not files:
            self.log('backend_no_files_found')
            return
            
        self.log('backend_found_files', count=total_files)

        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename
        
        processed_count_rename = 0
        processed_count_check = 0
        final_unprocessed_files = []
        self.unprocessed_files.clear()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.process, file): file for file in files}
            
            processed_futures = 0
            for future in concurrent.futures.as_completed(futures):
                processed_futures += 1
                progress = (processed_futures / total_files) * 100.0
                self.update_progress(progress, processed_futures, total_files)
                
                try:
                    was_successful, data = future.result()
                    if was_successful:
                        processed_count_rename += 1
                    else:
                        self.unprocessed_files.append(data)
                except Exception as exc:
                    file_path = futures[future]
                    self.log('backend_file_process_fail', path=file_path, exc=str(exc))

        self.log('backend_unprocessed_header')
        
        if self.unprocessed_files:
            for file_path in self.unprocessed_files:
                renamed_by_content = False
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                        first_line = file.readline().strip()
                    
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
                        
                        self.log('backend_rename_exception_success')
                        self.log('backend_rename_original', path=relative_file_path)
                        self.log('backend_rename_changed', path=new_filename.replace(os.sep, '\\'))
                        renamed_by_content = True
                except Exception as e:
                    self.log('backend_unprocessed_error', error=str(e))
                
                if not renamed_by_content:
                    final_unprocessed_files.append(file_path)

        total_processed = processed_count_rename + processed_count_check
        self.log('backend_job_summary', total_processed=total_processed)
        if final_unprocessed_files:
            self.log('backend_unprocessed_summary', count=len(final_unprocessed_files))

    def process(self, file_path):
        hash_md5_value = self.calculate_md5(file_path).hexdigest()
        if hash_md5_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_md5_value])

        hash_xxhash64_value = self.calculate_xxhash64(file_path).hexdigest()
        if hash_xxhash64_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_xxhash64_value])

        return False, file_path

    def rename_file(self, file_path, new_filename):
        new_filepath = os.path.join(os.getcwd(), new_filename)
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)
        if os.path.exists(new_filepath):
            new_filepath = self.get_unique_filename(new_filepath)
        try:
            os.rename(file_path, new_filepath)
            relative_file_path = os.path.relpath(file_path, os.getcwd())
            
            self.log('backend_rename_success')
            self.log('backend_rename_original', path=relative_file_path)
            self.log('backend_rename_changed', path=new_filename.replace(os.sep, '\\').replace('/', '\\'))
            
            return True, new_filepath
        except Exception as e:
            self.log('backend_rename_error', error=str(e))
            return False, file_path

    def calculate_md5(self, file_path):
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash

    def calculate_xxhash64(self, file_path):
        xxhash64_hash = xxhash.xxh64()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                xxhash64_hash.update(chunk)
        return xxhash64_hash

    def get_all_files_in_folders(self, target_folders):
        all_files = []
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        if self.is_sha1(file_name):
                            all_files.append(os.path.join(root, file_name))
        return all_files

    def is_sha1(self, s):
        return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)

    def get_unique_filename(self, file_path):
        base, extension = os.path.splitext(file_path)
        counter = 1
        new_file_path = f"{base}{extension}"
        while os.path.exists(new_file_path):
            new_file_path = f"{base}_(Duplicate_{counter}){extension}"
            counter += 1
        return new_file_path


if __name__ == '__main__':
    root = tk.Tk()
    app = FileRenamerGUI(root)
    root.mainloop()