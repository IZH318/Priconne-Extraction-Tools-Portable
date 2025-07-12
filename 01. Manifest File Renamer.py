# --- 필요한 라이브러리 임포트 ---
# GUI 구현을 위한 tkinter 라이브러리
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk

# 파일 시스템, 시스템 제어, DB, 해시, 병렬 처리 라이브러리
import os
import sys
import sqlite3
import hashlib
import concurrent.futures
import xxhash

# GUI와 백그라운드 작업 간의 안전한 통신을 위한 스레딩 및 큐 라이브러리
import threading
import queue

# --- GUI 애플리케이션 클래스 정의 ---
class FileRenamerGUI:
    """
    파일 리네임 프로그램의 메인 GUI 창을 생성하고 관리하는 클래스
    """
    def __init__(self, master):
        """
        GUI 애플리케이션의 창과 위젯을 초기화합니다.
        """
        # 메인 윈도우(창) 설정
        self.master = master
        self.master.title("Manifest File Renamer")

        # --- 창 크기 및 화면 중앙 배치 설정 ---
        window_width = 800
        window_height = 600

        # 스크린의 너비와 높이를 구합니다.
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()

        # 창이 화면 중앙에 위치하도록 x, y 좌표를 계산합니다.
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)

        # 창의 크기와 위치를 설정합니다.
        self.master.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        # GUI 화면에 표시될 위젯들(버튼, 텍스트 상자 등)을 생성합니다.
        self.create_widgets()

        # 백그라운드에서 파일 처리를 담당할 클래스의 인스턴스를 생성합니다.
        self.file_processor = RenameHashedFile(self.log_queue, self.progress_queue)

    def create_widgets(self):
        """
        GUI를 구성하는 위젯들을 생성하고 화면에 배치합니다.
        모든 위젯은 기본 스타일(배경색, 폰트 등)을 사용합니다.
        """
        # 최상위 프레임: 위젯 간 간격을 위해 사용
        top_frame = tk.Frame(self.master)
        top_frame.pack(padx=10, pady=10, fill=tk.X)

        # 컨트롤(버튼, 진행 막대)들을 담을 프레임 위젯
        control_frame = tk.Frame(top_frame)
        control_frame.pack(fill=tk.X)

        # 작업 시작 버튼
        self.start_button = tk.Button(control_frame, text="작업 시작", command=self.start_processing_thread)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 프로그램 종료 버튼
        self.close_button = tk.Button(control_frame, text="종료", command=self.master.quit)
        self.close_button.pack(side=tk.LEFT, padx=5)

        # 작업 진행률을 시각적으로 보여줄 프로그레스 바
        self.progress_bar = ttk.Progressbar(control_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        # 작업 로그를 출력할 스크롤 가능한 텍스트 영역
        self.log_area = scrolledtext.ScrolledText(self.master, wrap=tk.WORD)
        self.log_area.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)
        
        # --- 초기 메시지 및 ASCII 아트를 로그 창에 표시 ---
        # ASCII 아트 텍스트
        ascii_art_text = """
      ___      _                        _____                       __  __      ___      _ ___  _         
     / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
    / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
   /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
              __  ___          _ ___        __    _____ __      ___                             
             /  |/  /__ ____  (_) _/__ ___ / /_  / __(_) /__   / _ \___ ___  ___ ___ _  ___ ____
            / /|_/ / _ `/ _ \/ / _/ -_|_-</ __/ / _// / / -_) / , _/ -_) _ \/ _ `/  ' \/ -_) __/
           /_/  /_/\_,_/_//_/_/_/ \__/___/\__/ /_/ /_/_/\__/ /_/|_|\__/_//_/\_,_/_/_/_/\__/_/
        """

        self.log_area.insert(tk.END, ascii_art_text + '\n')
        self.log_area.insert(tk.END, "--------------------------------------------------------------------------------------------------\n")
        self.log_area.insert(tk.END, "[ 주의 ] 현재 디렉터리에 'manifest.db'파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n")
        self.log_area.insert(tk.END, "--------------------------------------------------------------------------------------------------\n")
        self.log_area.insert(tk.END, "'작업 시작' 버튼을 눌러주세요.\n")
        self.log_area.configure(state='disabled') # 초기 메시지 출력 후 비활성화

        # 스레드 간의 안전한 데이터 교환을 위한 큐(Queue) 객체 생성
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()

    def add_log(self, message):
        """
        로그 영역에 새로운 메시지를 추가하고, 항상 최신 로그가 보이도록 스크롤을 내립니다.
        """
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def start_processing_thread(self):
        """
        '작업 시작' 버튼을 누르면 호출됩니다.
        파일 처리 작업은 시간이 오래 걸릴 수 있으므로, GUI가 멈추지 않도록 별도의 스레드에서 실행합니다.
        """
        if not os.path.exists(os.path.join(os.getcwd(), "manifest.db")):
            messagebox.showerror("오류", "현재 디렉터리에 'manifest.db' 파일이 존재하지 않습니다.")
            return

        self.start_button.config(state=tk.DISABLED)
        
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.config(state='disabled')
        self.progress_bar['value'] = 0

        self.processing_thread = threading.Thread(target=self.file_processor.process_files, daemon=True)
        self.processing_thread.start()

        self.master.after(100, self.monitor_queue)

    def monitor_queue(self):
        """
        주기적으로(100ms마다) 큐를 확인하여 작업 스레드로부터 온 데이터로 GUI를 업데이트합니다.
        """
        try:
            while True:
                log_msg = self.log_queue.get_nowait()
                self.add_log(log_msg)
        except queue.Empty:
            pass

        try:
            while True:
                progress_val = self.progress_queue.get_nowait()
                self.progress_bar['value'] = progress_val
        except queue.Empty:
            pass

        if self.processing_thread.is_alive():
            self.master.after(100, self.monitor_queue)
        else:
            self.start_button.config(state=tk.NORMAL)


# --- 파일 처리 로직 클래스 정의 ---
class RenameHashedFile:
    def __init__(self, log_queue, progress_queue):
        """
        FileProcessor 클래스의 초기화 메서드.
        """
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        self.hash_list = {}
        self.processed_count_rename = 0
        self.processed_count_check = 0
        self.unprocessed_files = []
        self.results = []
        self.log_queue = log_queue
        self.progress_queue = progress_queue

    def log(self, message):
        """GUI의 로그 창에 메시지를 보내기 위해 큐에 데이터를 추가합니다."""
        self.log_queue.put(message)

    def update_progress(self, value):
        """GUI의 진행 막대를 업데이트하기 위해 큐에 데이터를 추가합니다."""
        self.progress_queue.put(value)
        
    def process_files(self):
        """
        대상 폴더 내의 파일을 처리하는 메인 메서드입니다.
        """
        self.hash_list.clear()
        self.unprocessed_files.clear()
        self.results.clear()
        self.processed_count_rename = 0
        self.processed_count_check = 0

        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        
        self.log("[ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기/쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
        self.log("[ 안내 ] 모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n")
        
        files = self.get_all_files_in_folders(self.target_folders)
        total_files = len(files)
        
        if not files:
            self.log("[ 경고 ] 대상 폴더에서 처리할 파일을 찾을 수 없습니다.")
            return

        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.process, file, index, total_files): (file, index) for index, file in enumerate(files, 1)}
            for future in concurrent.futures.as_completed(futures):
                file_path, file_index = futures[future]
                try:
                    result = future.result()
                    if result is not None:
                        if not result[0]:
                            self.unprocessed_files.append(result[1])
                        else:
                            self.results.append((file_index, result[1], result[2]))
                except Exception as exc:
                    self.log(f"파일 처리 중 심각한 오류 발생: {file_path}: {exc}")

        self.log("\n--- 파일 이름 변경 결과 ---\n")
        for file_index, original_file, new_file_info in sorted(self.results, key=lambda x: x[0]):
            self.log(new_file_info)
            self.processed_count_rename += 1

        self.log("\n\n--- 예외 처리 결과 ---")
        self.log("[ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 파일 내용을 기반으로 예외 처리됩니다.")
        for file_path in self.unprocessed_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    first_line = file.readline().strip()
            except Exception as e:
                self.log(f"파일 읽기 오류: {e}. 다음 파일로 넘어갑니다.")
                continue
            
            new_filename = None
            
            if 'a/bdl' in first_line:
                new_filename = os.path.join("manifest", "bdl_assetmanifest")
                self.processed_count_check += 1
                self.log(f"\n파일 내용('a/bdl') 확인: {file_path[len(os.getcwd()):]}")
            elif 'manifest/' in first_line:
                new_filename = os.path.join("manifest", "manifest_assetmanifest")
                self.processed_count_check += 1
                self.log(f"\n파일 내용('manifest/') 확인: {file_path[len(os.getcwd()):]}")
            elif 'm/' in first_line:
                new_filename = os.path.join("manifest", "movie2manifest")
                self.processed_count_check += 1
                self.log(f"\n파일 내용('m/') 확인: {file_path[len(os.getcwd()):]}")
            elif 'b/' in first_line:
                new_filename = os.path.join("manifest", "soundmanifest")
                self.processed_count_check += 1
                self.log(f"\n파일 내용('b/') 확인: {file_path[len(os.getcwd()):]}")
            
            if new_filename:
                new_filepath = self.get_unique_filename(new_filename)
                try:
                    os.rename(file_path, new_filepath)
                    relative_file_path = os.path.relpath(file_path, os.getcwd())
                    log_msg = (
                        f"  - 작업 상태: 예외 처리된 파일 이름 변경 완료\n"
                        f"  - 원본: \\{relative_file_path}\n"
                        f"  - 변경: \\{new_filepath.replace(os.sep, '/')}"
                    )
                    self.log(log_msg)
                except (FileNotFoundError, FileExistsError) as e:
                    self.log(f"예외 처리 중 파일 이름 변경 오류: {e}")

        total_processed = self.processed_count_rename + self.processed_count_check
        self.log(f"\n\n--- 작업 완료 ---")
        self.log(f"총 {total_processed}개의 파일이 성공적으로 처리되었습니다.")

    def process(self, file_path, file_index, total_files):
        percent_complete = (file_index / total_files) * 100
        self.update_progress(percent_complete)
        
        hash_md5_value = self.calculate_md5(file_path).hexdigest()
        if hash_md5_value in self.hash_list:
            return self.rename_file(file_path, hash_md5_value, file_index, total_files, percent_complete)

        hash_xxhash64_value = self.calculate_xxhash64(file_path).hexdigest()
        if hash_xxhash64_value in self.hash_list:
            return self.rename_file(file_path, hash_xxhash64_value, file_index, total_files, percent_complete)

        return False, file_path, None

    def rename_file(self, file_path, hash_value, file_index, total_files, percent_complete):
        new_filename = self.hash_list[hash_value]
        new_filepath = os.path.join(os.getcwd(), new_filename)
        
        os.makedirs(os.path.dirname(new_filepath), exist_ok=True)
        
        if os.path.exists(new_filepath):
            new_filepath = self.get_unique_filename(new_filepath)
            
        try:
            os.rename(file_path, new_filepath)
            relative_file_path = os.path.relpath(file_path, os.getcwd())
            log_message = (
                f"작업 진행 상태: {file_index}/{total_files} ({percent_complete:.2f}%)\n"
                f"  - 원본 파일 명 : \\{relative_file_path}\n"
                f"  - 변경된 파일 명 : \\{new_filepath.replace(os.sep, '/')}"
            )
            return True, None, log_message
        except (FileNotFoundError, FileExistsError) as e:
            self.log(f"파일 이름 변경 오류: {e}")
            return False, file_path, None

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
        new_file_path = file_path
        while os.path.exists(new_file_path):
            new_file_path = f"{base}_(Duplicate_{counter}){extension}"
            counter += 1
        return new_file_path


# --- 프로그램 실행 부분 ---
if __name__ == '__main__':
    root = tk.Tk()
    app = FileRenamerGUI(root)
    root.mainloop()