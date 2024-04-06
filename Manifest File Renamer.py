import os
import sqlite3
import hashlib
import concurrent.futures

# 변환된 파일의 총 수를 계산하기 위한 변수
total_processed = 0

print("""
         ___      _                        _____                       __  __      ___      _ ___  _         
        / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
       / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
      /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
      """)
print("""
                   __  ___          _ ___        __    _____ __      ___                             
                  /  |/  /__ ____  (_) _/__ ___ / /_  / __(_) /__   / _ \___ ___  ___ ___ _  ___ ____
                 / /|_/ / _ `/ _ \/ / _/ -_|_-</ __/ / _// / / -_) / , _/ -_) _ \/ _ `/  ' \/ -_) __/
                /_/  /_/\_,_/_//_/_/_/ \__/___/\__/ /_/ /_/_/\__/ /_/|_|\__/_//_/\_,_/_/_/_/\__/_/
                """)

print("\n\n [ 주의 ] 작업 진행 중 콘솔 창 내부를 클릭하면 진행이 멈출 수 있습니다.")
print("          ( * 임시 해결 방법: 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭 )\n")

print(" 작업을 진행하시겠습니까? (Y/N, 대소문자 구분 없음.)")

class RenameHashedFile:
    def __init__(self):
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        self.hash_list = {}
        self.processed_count_rename = 0
        self.processed_count_check = 0
        self.unprocessed_files = []
        self.results = []

    def start_processing(self):
        while True:
            user_input = input(" >>> ").strip().lower()
            if user_input == 'y':
                print("\n\n")
                self.process_files()
                break
            elif user_input == 'n':
                input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")
                sys.exit()
            else:
                print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")

    def process_files(self):
        files = self.get_all_files_in_folders(self.target_folders)
        if not files:
            print(" 대상 폴더에서 파일을 찾을 수 없습니다.")
            return

        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            input("\n\n\n [ 경고 ] manifest.db 파일이 존재하지 않습니다. Enter 키를 입력하여 창을 종료하십시오.")
            return

        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.process, file, index): (file, index) for index, file in enumerate(files, 1)}
            for future in concurrent.futures.as_completed(futures):
                file_path, file_index = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f" File processing failed for {file_path}: {exc}")
                else:
                    if result is not None:
                        if not result[0]:
                            self.unprocessed_files.append(result[1])
                        else:
                            self.results.append((file_index, result[1], result[2]))

        for file_index, original_file, new_file_info in sorted(self.results, key=lambda x: x[0]):
            print(new_file_info)
            self.processed_count_rename += 1


        print("\n\n [ 안내 ] manifest.db에서 인식하지 못한 파일은 아래 내용을 참고하십시오.")
        print("          (* 아래 파일들은 예외 처리되었습니다.)")
        for file_path in self.unprocessed_files:
            with open(file_path, 'r', encoding='utf-8') as file:
                first_line = file.readline().strip()

            print()
            
            if 'a/bdl' in first_line:
                new_filename = os.path.join("manifest", "bdl_assetmanifest")
                self.processed_count_check += 1
                print(f" 특정 문자열 'a/bdl'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'manifest/' in first_line:
                new_filename = os.path.join("manifest", "manifest_assetmanifest")
                self.processed_count_check += 1
                print(f" 특정 문자열 'manifest/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'm/' in first_line:
                new_filename = os.path.join("manifest", "movie2manifest")
                self.processed_count_check += 1
                print(f" 특정 문자열 'm/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'b/' in first_line:
                new_filename = os.path.join("manifest", "soundmanifest")
                self.processed_count_check += 1
                print(f" 특정 문자열 'b/'이(가) {file_path[len(os.getcwd()):]}파일 내용에 포함되어 있습니다.")

            try:
                os.rename(file_path, new_filename)
                print(f" 파일 이름이 \\{new_filename.replace(os.sep, '/')}으로 변경되었습니다.")
            except FileNotFoundError:
                print(f"{file_path}을(를) 찾을 수 없습니다.")

        total_processed = self.processed_count_rename + self.processed_count_check
        input(f"\n\n\n 총 {self.processed_count_rename + self.processed_count_check}개의 파일이 처리되었습니다. Enter 키를 입력하여 창을 종료하십시오.")

    def process(self, file_path, file_index):
        hash_md5 = self.calculate_md5(file_path)
        hash_value = hash_md5.hexdigest()

        if hash_value in self.hash_list:
            new_filename = self.hash_list[hash_value]
            try:
                os.rename(file_path, os.path.join(os.getcwd(), new_filename))
                relative_file_path = os.path.relpath(file_path, os.getcwd())
                return True, None, f" 파일 처리 순번 : {file_index}\n 원본 파일 명 : \\{relative_file_path}\n 변경된 파일 명 : \\{new_filename.replace(os.sep, '/')}\n"
            except FileNotFoundError:
                print(f" {file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None
        return False, file_path, None

    def calculate_md5(self, file_path):
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash

    def get_all_files_in_folders(self, target_folders):
        all_files = []
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        all_files.append(os.path.join(root, file_name))
        return all_files


rename_hashed_file = RenameHashedFile()
rename_hashed_file.start_processing()
