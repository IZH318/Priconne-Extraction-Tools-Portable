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

# 언어 딕셔너리 (변경 없음)
LANGUAGES = {
    'ko': {
        'window_title': "Manifest File Renamer (GUI Version)", 'menu_language': "언어", 'start_button': "작업 시작",
        'status_waiting': "상태: 대기 중", 'status_searching': "파일 검색 중...", 'status_processing': "처리: {current} / {total}",
        'status_complete': "상태: 완료", 'status_complete_count': "완료: {count} / {count}",
        'initial_info_db': "[ 주의 ] 현재 디렉터리에 'manifest.db' 파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n\n"
                           "         [ 예시 ]\n"
                           "         C:\\PriconneClient\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 실행 파일)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 안내 ] '작업 시작' 버튼을 눌러주세요.",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 작업 대상 폴더)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 작업 대상 폴더)",
        'error_title': "오류", 'error_db_not_found': "'manifest.db' 파일을 찾을 수 없습니다。",
        'log_new_job_start': "[ 작업 시작 ] 새로운 작업을 시작합니다.", 'log_warning_db_not_found': "[ 경고 ] 현재 디렉터리에 'manifest.db'파일이 존재하지 않습니다.",
        'log_info_long_time': "[ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.",
        'log_info_auto_rename': "          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.",
        'log_searching_files': "[ 진행 ] 대상 폴더에서 파일 목록을 검색 중입니다...", 'log_no_files_found': "대상 폴더에서 처리 할 파일을 찾을 수 없습니다.",
        'log_found_files': "[ 완료 ] 총 {count}개의 처리 대상 파일을 찾았습니다. 이름 변경을 시작합니다.", 'log_rename_success': "  - 작업 상태: 파일 이름 변경 완료",
        'log_rename_exception': "  - 작업 상태: 예외 처리된 파일 이름 변경 완료", 'log_rename_original': "  - 원본: \\{path}",
        'log_rename_changed': "  - 변경: \\{path}", 'log_rename_error': "오류: {error}",
        'log_unprocessed_header': "[ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략되었습니다.",
        'log_unprocessed_error': " 오류 발생: 알 수 없는 오류가 발생했습니다. ({error})", 'log_file_process_fail': "파일 처리 실패 {path}: {error}",
        'log_job_summary': "--- 작업 완료 ---\n총 {count}개의 파일이 처리되었습니다.", 'log_unprocessed_summary': "{count}개의 파일은 처리되지 않았습니다.",
        'log_job_complete': "작업이 모두 완료되었습니다。",
    },
    'en': {
        'window_title': "Manifest File Renamer (GUI Version)", 'menu_language': "Language", 'start_button': "Start Job",
        'status_waiting': "Status: Waiting", 'status_searching': "Searching files...", 'status_processing': "Processing: {current} / {total}",
        'status_complete': "Status: Complete", 'status_complete_count': "Complete: {count} / {count}",
        'initial_info_db': "[ WARNING ] 'manifest.db' and the target files must be in the current directory with their original structure.\n\n"
                           "         [ Example ]\n"
                           "         C:\\PriconneClient\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← Executable)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ INFO ] Please press the 'Start Job' button.",
        'folder_item_branch': "            ├─ {folder_name}\\ (← Target folder)",
        'folder_item_last':   "            └─ {folder_name}\\ (← Target folder)",
        'error_title': "Error", 'error_db_not_found': "'manifest.db' file not found.",
        'log_new_job_start': "[ JOB START ] Starting a new job.", 'log_warning_db_not_found': "[ WARNING ] 'manifest.db' does not exist in the current directory.",
        'log_info_long_time': "[ INFO ] This may take a long time if there are many files or the storage device is slow.",
        'log_info_auto_rename': "          All files will be renamed automatically after being loaded.",
        'log_searching_files': "[ PROGRESS ] Searching for files in target folders...", 'log_no_files_found': "No files to process were found in the target folders.",
        'log_found_files': "[ COMPLETE ] Found a total of {count} files to process. Starting rename.", 'log_rename_success': "  - Status: File renamed successfully",
        'log_rename_exception': "  - Status: Renamed file via exception handling", 'log_rename_original': "  - Original: \\{path}",
        'log_rename_changed': "  - New: \\{path}", 'log_rename_error': "Error: {error}",
        'log_unprocessed_header': "[ INFO ] Files not recognized by manifest.db were handled or skipped as follows.",
        'log_unprocessed_error': " An unknown error occurred. ({error})", 'log_file_process_fail': "Failed to process file {path}: {error}",
        'log_job_summary': "--- JOB COMPLETE ---\nA total of {count} files have been processed.", 'log_unprocessed_summary': "{count} files were not processed.",
        'log_job_complete': "The job has been completed.",
    },
    'ja': {
        'window_title': "Manifest File Renamer (GUI Version)", 'menu_language': "言語", 'start_button': "作業開始",
        'status_waiting': "状態: 待機中", 'status_searching': "ファイルを検索中...", 'status_processing': "処理中: {current} / {total}",
        'status_complete': "状態: 完了", 'status_complete_count': "完了: {count} / {count}",
        'initial_info_db': "[ 注意 ] 現在のディレクトリに 'manifest.db' ファイルと対象ファイルを元の構造のまま配置してください。\n\n"
                           "         [ 例 ]\n"
                           "         C:\\PriconneClient\\\n"
                           "            ├─ 01. Manifest File Renamer.py  (← 実行ファイル)\n"
                           "            ├─ manifest.db\n"
                           "{folder_structure}\n",
        'initial_info_start': "[ 案内 ] 「作業開始」ボタンを押してください。",
        'folder_item_branch': "            ├─ {folder_name}\\ (← 対象フォルダ)",
        'folder_item_last':   "            └─ {folder_name}\\ (← 対象フォルダ)",
        'error_title': "エラー", 'error_db_not_found': "'manifest.db' ファイルが見つかりません。",
        'log_new_job_start': "[ 作業開始 ] 新しい作業を開始します。", 'log_warning_db_not_found': "[ 警告 ] 現在のディレクトリに 'manifest.db' が存在しません。",
        'log_info_long_time': "[ 案内 ] ファイル数が多い、またはストレージの速度が遅い場合、時間がかかることがあります。",
        'log_info_auto_rename': "          すべてのファイルが読み込まれた後、自動的にリネームされます。",
        'log_searching_files': "[ 進行 ] 対象フォルダ内のファイルを検索しています...", 'log_no_files_found': "対象フォルダに処理するファイルが見つかりませんでした。",
        'log_found_files': "[ 完了 ] 合計{count}個の処理対象ファイルを見つけました。名前の変更を開始します。", 'log_rename_success': "  - 状態: ファイル名の変更が完了しました",
        'log_rename_exception': "\n  - 状態: 例外処理によりファイル名を変更しました", 'log_rename_original': "  - 元の名前: \\{path}",
        'log_rename_changed': "  - 新しい名前: \\{path}", 'log_rename_error': "エラー: {error}",
        'log_unprocessed_header': "[ 案内 ] manifest.dbで認識できなかったファイルは、次のように例外処理またはスキップされました。",
        'log_unprocessed_error': " 不明なエラーが発生しました。({error})", 'log_file_process_fail': "ファイル処理失敗 {path}: {error}",
        'log_job_summary': "--- 作業完了 ---\n合計{count}個のファイルが処理されました。", 'log_unprocessed_summary': "{count}個のファイルは処理されませんでした。",
        'log_job_complete': "すべての作業が完了しました。",
    }
}
ASCII_ART = r"""
      ___      _                        _____                       __  __      ___      _ ___  _         
     / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
    / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
   /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
              __  ___          _ ___        __    _____ __      ___                             
             /  |/  /__ ____  (_) _/__ ___ / /_  / __(_) /__   / _ \___ ___  ___ ___ _  ___ ____
            / /|_/ / _ `/ _ \/ / _/ -_|_-</ __/ / _// / / -_) / , _/ -_) _ \/ _ `/  ' \/ -_) __/
           /_/  /_/\_,_/_//_/_/_/ \__/___/\__/ /_/ /_/_/\__/ /_/|_|\__/_//_/\_,_/_/_/_/\__/_/
        """
SEPARATOR = "-" * 100

class FileRenamerGUI:
    def __init__(self, master):
        self.master = master
        self.current_lang = 'ko'
        self.lang_var = tk.StringVar(value=self.current_lang)
        self.lang_var.trace_add("write", self.on_language_change)
        self.log_history = []
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
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue)
        self.MAX_LOGS_PER_CYCLE = 1
        self.GUI_UPDATE_INTERVAL_MS = 1
        self.progress_label_var = tk.StringVar()
        self.total_files_count = 0
        self.create_widgets()
        self.update_ui_language(is_initial_setup=True)

    def get_string(self, key, **kwargs):
        return LANGUAGES[self.current_lang].get(key, f"NO_TRANSLATION_FOR_{key}").format(**kwargs)

    def set_language(self, lang_code):
        if self.current_lang != lang_code:
            self.current_lang = lang_code
            self.update_ui_language()

    def on_language_change(self, *args):
        new_lang = self.lang_var.get()
        self.set_language(new_lang)

    def update_ui_language(self, is_initial_setup=False):
        self.master.title(self.get_string('window_title'))
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
            self.log_history = [
                ('raw', {'text': ASCII_ART}),
                ('raw', {'text': SEPARATOR}),
                ('initial_info_db', {}),
                ('initial_info_start', {}),
                ('raw', {'text': SEPARATOR}),
            ]
        self.re_render_logs()
        
    def create_menubar(self):
        menubar = tk.Menu(self.master)
        language_menu = tk.Menu(menubar, tearoff=0)
        language_menu.add_radiobutton(label="한국어", variable=self.lang_var, value='ko')
        language_menu.add_radiobutton(label="English", variable=self.lang_var, value='en')
        language_menu.add_radiobutton(label="日本語", variable=self.lang_var, value='ja')
        menubar.add_cascade(label=self.get_string('menu_language'), menu=language_menu)
        self.master.config(menu=menubar)

    def create_widgets(self):
        self.create_menubar()
        top_frame = tk.Frame(self.master)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)
        self.start_button = tk.Button(control_frame, command=self.start_processing_thread)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        self.progress_label = tk.Label(control_frame, textvariable=self.progress_label_var, width=25)
        self.progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.log_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD, font=("Consolas", 9))
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

    # --- [결정적인 수정] re_render_logs 메서드 ---
    def re_render_logs(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        
        full_log_text = []
        for key, kwargs in self.log_history:
            if key == 'raw':
                message = kwargs.get('text', '')
            elif key == 'initial_info_db':
                # --- 폴더 구조를 리스트에 담아 안전하게 생성 ---
                folder_lines = []
                folders = self.file_processor.target_folders
                for i, folder in enumerate(folders):
                    if i == len(folders) - 1:
                        prefix_key = 'folder_item_last'
                    else:
                        prefix_key = 'folder_item_branch'
                    folder_lines.append(self.get_string(prefix_key, folder_name=folder))
                
                # .strip() 없이 join하여 들여쓰기 보존
                folder_structure_str = "\n".join(folder_lines)
                
                message = self.get_string(key, folder_structure=folder_structure_str)
            else:
                message = self.get_string(key, **kwargs)
            full_log_text.append(message)
        
        self.log_area.insert('1.0', "\n".join(full_log_text))
        
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def add_log(self, key, **kwargs):
        self.log_history.append((key, kwargs))
        self.re_render_logs()

    def start_processing_thread(self):
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror(self.get_string('error_title'), self.get_string('error_db_not_found'))
            return
        
        self.log_history = [
            ('raw', {'text': "="*100}),
            ('log_new_job_start', {}),
            ('raw', {'text': ""}),
        ]
        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.progress_label_var.set(self.get_string('status_searching'))
        self.last_progress_info = {'current': 0, 'total': 0}
        self.re_render_logs()
        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread):
        logs_to_add = []
        try:
            while not self.log_queue.empty():
                logs_to_add.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass

        if logs_to_add:
            self.log_history.extend(logs_to_add)
            self.re_render_logs()

        try:
            while not self.progress_queue.empty():
                progress_val, current, total = self.progress_queue.get_nowait()
                self.progress_bar['value'] = progress_val
                self.last_progress_info = {'current': current, 'total': total}
                self.progress_label_var.set(self.get_string('status_processing', **self.last_progress_info))
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
                self.log_history.extend(final_logs)
            
            self.is_processing = False
            self.progress_bar['value'] = 100
            if self.total_files_count > 0:
                self.progress_label_var.set(self.get_string('status_complete_count', count=self.total_files_count))
            else:
                self.progress_label_var.set(self.get_string('status_complete'))
            self.start_button.config(state=tk.NORMAL)
            
            self.log_history.append(('raw', {'text': ""}))
            self.log_history.append(('log_job_complete', {}))
            self.re_render_logs()


class RenameHashedFile:
    def __init__(self, log_queue, progress_queue):
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        self.hash_list = {}
        self.unprocessed_files = []
        self.log_queue = log_queue
        self.progress_queue = progress_queue

    def log(self, key, **kwargs):
        self.log_queue.put((key, kwargs))

    def update_progress(self, value, current, total):
        self.progress_queue.put((value, current, total))

    def process_files(self):
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            self.log('log_warning_db_not_found')
            return
        
        self.log('log_info_long_time')
        self.log('log_info_auto_rename')
        self.log('raw', text="")
        self.log('log_searching_files')

        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        self.update_progress(0, 0, total_files)

        if not files:
            self.log('log_no_files_found')
            return
            
        self.log('log_found_files', count=total_files)

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
                    was_successful, data, log_id_list = future.result()
                    if was_successful:
                        if log_id_list:
                            for log_id, log_kwargs in log_id_list:
                                self.log(log_id, **log_kwargs)
                        processed_count_rename += 1
                    else:
                        self.unprocessed_files.append(data)
                except Exception as exc:
                    file_path = futures[future]
                    self.log('log_file_process_fail', path=file_path, error=exc)
        
        if processed_count_rename > 0 or self.unprocessed_files:
            self.log('raw', text='\n')

        self.log('log_unprocessed_header')
        
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
                        consistent_new_filename = new_filename.replace(os.sep, '\\').replace('/', '\\')
                        self.log('raw', {'text': ''})
                        self.log('log_rename_exception')
                        self.log('log_rename_original', path=relative_file_path)
                        self.log('log_rename_changed', path=consistent_new_filename)
                        renamed_by_content = True
                except Exception as e:
                    self.log('log_unprocessed_error', error=e)
                if not renamed_by_content:
                    final_unprocessed_files.append(file_path)
        
        total_processed = processed_count_rename + processed_count_check
        self.log('raw', text='\n')
        self.log('log_job_summary', count=total_processed)
        if final_unprocessed_files:
            self.log('log_unprocessed_summary', count=len(final_unprocessed_files))

    def process(self, file_path):
        hash_md5_value = self.calculate_md5(file_path).hexdigest()
        if hash_md5_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_md5_value])
        hash_xxhash64_value = self.calculate_xxhash64(file_path).hexdigest()
        if hash_xxhash64_value in self.hash_list:
            return self.rename_file(file_path, self.hash_list[hash_xxhash64_value])
        return False, file_path, None

    def rename_file(self, file_path, new_filename):
        new_filepath = os.path.join(os.getcwd(), new_filename)
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)
        if os.path.exists(new_filepath):
            new_filepath = self.get_unique_filename(new_filepath)
        try:
            os.rename(file_path, new_filepath)
            relative_file_path = os.path.relpath(file_path, os.getcwd())
            consistent_new_filename = new_filename.replace('/', '\\').replace(os.sep, '\\')
            
            log_tuples = [
                ('raw', {'text': ''}),
                ('log_rename_success', {}),
                ('log_rename_original', {'path': relative_file_path}),
                ('log_rename_changed', {'path': consistent_new_filename})
            ]
            return True, new_filepath, log_tuples
        except Exception as e:
            log_tuples = [('log_rename_error', {'error': e})]
            return False, file_path, log_tuples

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