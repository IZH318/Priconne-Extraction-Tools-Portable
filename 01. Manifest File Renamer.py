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

class FileRenamerGUI:
    """
    파일 리네임 프로그램의 메인 GUI 창을 생성하고 관리하는 클래스
    """
    def __init__(self, master):
        self.master = master
        self.master.title("Manifest File Renamer (GUI Version)")

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

    def create_widgets(self):
        top_frame = tk.Frame(self.master)
        top_frame.pack(padx=10, pady=10, fill=tk.X)

        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)

        self.start_button = tk.Button(control_frame, text="작업 시작", command=self.start_processing_thread)
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.progress_label = tk.Label(control_frame, textvariable=self.progress_label_var, width=25)
        self.progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.progress_label_var.set("상태: 대기 중")

        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.log_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD, font=("Consolas", 9))
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)
        
        self.show_initial_message()

    def show_initial_message(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        ascii_art = r"""
      ___      _                        _____                       __  __      ___      _ ___  _         
     / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
    / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
   /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
        """
        self.log_area.insert(tk.END, ascii_art + '\n')
        self.log_area.insert(tk.END, "-"*100 + "\n")
        self.log_area.insert(tk.END, "[ 주의 ] 현재 디렉터리에 'manifest.db' 파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n")
        self.log_area.insert(tk.END, "[ 안내 ] '작업 시작' 버튼을 눌러주세요.\n")
        self.log_area.insert(tk.END, "-"*100 + "\n")
        self.log_area.configure(state='disabled')

    def add_log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, str(message) + '\n')
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def start_processing_thread(self):
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror("오류", "'manifest.db' 파일을 찾을 수 없습니다.")
            return

        self.start_button.config(state=tk.DISABLED)
        self.add_log("\n" + "="*100 + "\n[ 작업 시작 ] 새로운 작업을 시작합니다.\n")
        self.progress_bar['value'] = 0
        self.progress_label_var.set("파일 검색 중...")

        processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        processing_thread.start()
        self.monitor_queue(processing_thread)

    def monitor_queue(self, thread):
        try:
            for _ in range(self.MAX_LOGS_PER_CYCLE):
                self.add_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass

        try:
            while not self.progress_queue.empty():
                progress_val, current, total = self.progress_queue.get_nowait()
                self.progress_bar['value'] = progress_val
                self.progress_label_var.set(f"처리: {current} / {total}")
                self.total_files_count = total
        except queue.Empty:
            pass

        if thread.is_alive():
            self.master.after(self.GUI_UPDATE_INTERVAL_MS, lambda: self.monitor_queue(thread))
        else:
            try:
                while True: self.add_log(self.log_queue.get_nowait())
            except queue.Empty: pass
            
            self.progress_bar['value'] = 100
            if self.total_files_count > 0:
                self.progress_label_var.set(f"완료: {self.total_files_count} / {self.total_files_count}")
            else:
                self.progress_label_var.set("상태: 완료")
            self.start_button.config(state=tk.NORMAL)
            self.add_log(f"\n작업이 모두 완료되었습니다.")


class RenameHashedFile:
    def __init__(self, log_queue, progress_queue):
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        self.hash_list = {}
        self.unprocessed_files = []
        self.log_queue = log_queue
        self.progress_queue = progress_queue

    def log(self, message):
        self.log_queue.put(message)

    def update_progress(self, value, current, total):
        self.progress_queue.put((value, current, total))

    def process_files(self):
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            self.log("[ 경고 ] 현재 디렉터리에 'manifest.db'파일이 존재하지 않습니다.")
            return
            
        self.log(" [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
        self.log("          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n")
        self.log("[ 진행 ] 대상 폴더에서 파일 목록을 검색 중입니다...")
        
        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        
        self.update_progress(0, 0, total_files)

        if not files:
            self.log("대상 폴더에서 처리 할 파일을 찾을 수 없습니다.")
            return
            
        self.log(f"[ 완료 ] 총 {total_files}개의 처리 대상 파일을 찾았습니다. 이름 변경을 시작합니다.")

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
                    was_successful, data, log_msg = future.result()
                    if was_successful:
                        if log_msg: self.log(log_msg)
                        processed_count_rename += 1
                    else:
                        self.unprocessed_files.append(data)
                except Exception as exc:
                    file_path = futures[future]
                    self.log(f"파일 처리 실패 {file_path}: {exc}")

        self.log("\n\n\n [ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략되었습니다.")
        
        num_exception_files = len(self.unprocessed_files)
        if num_exception_files > 0:
            for idx, file_path in enumerate(self.unprocessed_files):
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

                        # --- [수정 1] 경로 구분자 통일 ---
                        consistent_new_filename = new_filename.replace(os.sep, '\\').replace('/', '\\')
                        
                        log_msg = (
                            f"\n  - 작업 상태: 예외 처리된 파일 이름 변경 완료\n"
                            f"  - 원본: \\{relative_file_path}\n"
                            f"  - 변경: \\{consistent_new_filename}"
                        )
                        self.log(log_msg)
                        renamed_by_content = True
                except Exception as e:
                    self.log(f" 오류 발생: 알 수 없는 오류가 발생했습니다. ({e})")
                
                if not renamed_by_content:
                    final_unprocessed_files.append(file_path)

        total_processed = processed_count_rename + processed_count_check
        self.log(f"\n\n\n--- 작업 완료 ---\n총 {total_processed}개의 파일이 처리되었습니다.")
        if final_unprocessed_files:
            self.log(f"{len(final_unprocessed_files)}개의 파일은 처리되지 않았습니다.")

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
            
            # --- [수정 2] 경로 구분자 통일 ---
            # DB에 / 또는 \ 어떤 형식으로 저장되어 있든 \로 통일하여 표시
            consistent_new_filename = new_filename.replace('/', '\\').replace(os.sep, '\\')
            
            log_msg = (
                f"\n  - 작업 상태: 파일 이름 변경 완료\n"
                f"  - 원본: \\{relative_file_path}\n"
                f"  - 변경: \\{consistent_new_filename}"
            )
            return True, new_filepath, log_msg
        except Exception as e:
            return False, file_path, f"오류: {e}"

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