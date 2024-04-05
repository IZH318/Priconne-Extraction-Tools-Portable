import os
import sqlite3
import hashlib
import concurrent.futures

class RenameHashedFile:
    def __init__(self):
        # 대상 폴더 목록 정의
        target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']
        # 대상 폴더의 모든 파일을 가져옴
        files = self.get_all_files_in_folders(target_folders)
        files_amount = len(files)

        # manifest.db 파일이 존재하는지 확인하고, 해시-파일명 쌍을 저장할 딕셔너리를 생성
        self.hash_list = {}
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")
        if not os.path.exists(manifest_db_path):
            return

        # manifest.db에 연결하여 해시-파일명 쌍을 읽어옴
        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename

        # 파일을 하나씩 처리하며 해시 값에 따라 이름을 변경
        self.processed_count_rename = 0  # 변경된 파일 개수를 저장하는 변수
        self.processed_count_check = 0   # 확인된 파일 개수를 저장하는 변수
        self.unprocessed_files = []  # 처리되지 않은 파일 이름을 저장할 리스트
        self.results = []  # 각 스레드의 결과를 저장할 리스트
        self.process_files(files)

        print("\n\n※ manifest.db에서 인식하지 못한 파일 목록은 예외적으로 처리되었습니다.")
        for unprocessed_file in self.unprocessed_files:
            # 작업 대상 폴더의 부분만 출력
            relative_path = os.path.relpath(unprocessed_file, os.getcwd())
            print("\\" + relative_path)

    def process_files(self, files):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(self.process, file, index): (file, index) for index, file in enumerate(files, 1)}
            for future in concurrent.futures.as_completed(futures):
                file_path, file_index = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"File processing failed for {file_path}: {exc}")
                else:
                    if result is not None:
                        if not result[0]:
                            self.unprocessed_files.append(result[1])
                        else:
                            self.results.append((file_index, result[1], result[2]))

        # 결과를 출력
        for file_index, original_file, new_file_info in sorted(self.results, key=lambda x: x[0]):
            print(new_file_info)
            self.processed_count_rename += 1

    def process(self, file_path, file_index):
        # 파일의 MD5 해시 값 계산
        hash_md5 = self.calculate_md5(file_path)
        hash_value = hash_md5.hexdigest()

        # 해시 값이 해시 리스트에 있는지 확인하고, 있다면 파일 이름을 변경
        if hash_value in self.hash_list:
            new_filename = self.hash_list[hash_value]
            try:
                os.rename(file_path, os.path.join(os.getcwd(), new_filename))
                # 파일 처리 결과 반환
                relative_file_path = os.path.relpath(file_path, os.getcwd())
                return True, None, f"파일 처리 순번 : {file_index}\n원본 파일 명 : {relative_file_path}\n변경된 파일 명 : {new_filename.replace(os.sep, '/')}\n"
            except FileNotFoundError:
                print(f"{file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None
        return False, file_path, None

    def calculate_md5(self, file_path):
        # 파일의 MD5 해시 값 계산
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash

    def get_all_files_in_folders(self, target_folders):
        # 대상 폴더의 모든 파일을 가져옴
        all_files = []
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder)
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for root, _, files in os.walk(folder_path):
                    for file_name in files:
                        all_files.append(os.path.join(root, file_name))
        return all_files

    def check_and_rename_files(self):
        for file_path in self.unprocessed_files:
            # 파일 내용에서 가장 첫 번째 줄을 가져옴
            with open(file_path, 'r', encoding='utf-8') as file:
                first_line = file.readline().strip()

            # 특정 문자열이 파일 내용에 포함되어 있는지 확인하고, 포함되어 있다면 파일 이름 변경
            print()
            if 'a/bdl' in first_line:
                new_filename = os.path.join("manifest", "bdl_assetmanifest")
                self.processed_count_check += 1  # 처리된 파일 개수 증가
                print(f"특정 문자열 'a/bdl'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'manifest/' in first_line:
                new_filename = os.path.join("manifest", "manifest_assetmanifest")
                self.processed_count_check += 1  # 처리된 파일 개수 증가
                print(f"특정 문자열 'manifest/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'm/' in first_line:
                new_filename = os.path.join("manifest", "movie2manifest")
                self.processed_count_check += 1  # 처리된 파일 개수 증가
                print(f"특정 문자열 'm/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'b/' in first_line:
                new_filename = os.path.join("manifest", "soundmanifest")
                self.processed_count_check += 1  # 처리된 파일 개수 증가
                print(f"특정 문자열 'b/'이(가) {file_path[len(os.getcwd()):]}파일 내용에 포함되어 있습니다.")
            else:
                # 특정 문자열이 없는 경우에는 파일 이름 변경하지 않고 다음 파일로 넘어감
                continue

            # 파일 이름 변경
            try:
                os.rename(file_path, new_filename)
                print(f"파일 이름이 \\{new_filename.replace(os.sep, '/')}으로 변경되었습니다.")
            except FileNotFoundError:
                print(f"{file_path}을(를) 찾을 수 없습니다.")

        input(f"\n\n\n총 {self.processed_count_rename + self.processed_count_check}개의 파일이 정상적으로 처리되었습니다. Enter 키를 입력하여 창을 종료하십시오.")
        


# RenameHashedFile 클래스의 인스턴스를 생성하여 실행
rename_hashed_file = RenameHashedFile()

# 파일 이름 변경 및 특정 문자열 포함 여부 확인
rename_hashed_file.check_and_rename_files()
