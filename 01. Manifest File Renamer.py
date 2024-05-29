# 필요한 라이브러리 임포트
import os  # 파일 시스템 작업을 위한 라이브러리
import sqlite3  # SQLite 데이터베이스를 사용하기 위한 라이브러리
import hashlib  # 해시 함수를 사용하기 위한 라이브러리
import concurrent.futures  # 병렬 처리를 위한 라이브러리
from tqdm import tqdm  # 진행 상황을 시각적으로 표시하기 위한 라이브러리
import xxhash  # xxhash64 해시 함수를 사용하기 위한 라이브러리



# 변환된 파일의 총 수를 계산하기 위한 변수
total_processed = 0



# 프로그램 시작 시 화면에 출력되는 ASCII Art
print("""
           ___      _                        _____                       __  __      ___      _ ___  _         
          / _ \\____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \\___ (_) _ \\(_)  _____ 
         / ___/ __/ / _ \\/ __/ -_|_-<(_-<  / /__/ _ \\/ _ \\/ _ \\/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
        /_/  /_/ /_/_//_/\\__/\__/___/___/  \\___/\\___/_//_/_//_/\\__/\\__/\__(_)     /_/|_|\\__(_)____/_/|___/\\__/
    """)
print("""
                   __  ___          _ ___        __    _____ __      ___                             
                  /  |/  /__ ____  (_) _/__ ___ / /_  / __(_) /__   / _ \\___ ___  ___ ___ _  ___ ____
                 / /|_/ / _ `/ _ \\/ / _/ -_|_-</ __/ / _// / / -_) / , _/ -_) _ \\/ _ `/  ' \\/ -_) __/
                /_/  /_/\\_,_/_//_/_/_/ \\__/___/\\__/ /_/ /_/_/\\__/ /_/|_|\\__/_//_/\\_,_/_/_/_/\\__/_/
    """)



# 작업 진행여부 확인 안내 문구
print("\n\n [ 주의 ] 현재 디렉터리에 'manifest.db'파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")

print("\n\n 작업을 진행하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.)")



# 파일 이름 변경 및 파일 내용 확인 클래스 정의
class RenameHashedFile:
    def __init__(self):
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']  # 대상 폴더들을 지정
        self.hash_list = {}  # 해시 값과 파일 이름을 매핑할 딕셔너리
        self.processed_count_rename = 0  # 파일 이름 변경된 개수
        self.processed_count_check = 0  # 파일 내용 확인된 개수
        self.unprocessed_files = []  # 처리되지 않은 파일 목록
        self.results = []  # 처리된 결과



    def start_processing(self):
        # 사용자 입력 받기
        while True:
            user_input = input(" >>> ").strip().lower()
            if user_input == 'y':
                print("\n\n")
                self.process_files()  # 파일 처리 시작
                break
            elif user_input == 'n':
                input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
                sys.exit()
            else:
                print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")



    def process_files(self):
        print(" [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
        print("          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n")
        
        files = self.get_all_files_in_folders(self.target_folders)  # 대상 폴더 내 모든 파일 가져오기
        total_files = len(files)  # 전체 파일 수 계산
        
        if not files:
            input("\n\n 대상 폴더에서 파일을 찾을 수 없습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
            return

        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")  # manifest.db 파일 경로
        if not os.path.exists(manifest_db_path):
            input("\n\n [ 경고 ] 'manifest.db'파일이 존재하지 않습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
            return

        # manifest.db에서 해시 값과 파일 이름 가져오기
        with sqlite3.connect(manifest_db_path) as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM t")
            rows = cursor.fetchall()
            for row in rows:
                filename, hash_value = row
                self.hash_list[hash_value] = filename

        # 스레드 풀을 사용하여 파일 처리
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 파일 처리를 위한 각 파일에 대한 Future 객체 생성
            futures = {executor.submit(self.process, file, index, total_files): (file, index) for index, file in enumerate(files, 1)}
            # tqdm을 사용하여 진행 상황 표시
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=" 파일을 불러오는 중..."):
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

        print("\n")

        # 결과 출력
        for file_index, original_file, new_file_info in sorted(self.results, key=lambda x: x[0]):
            print(new_file_info)
            self.processed_count_rename += 1

        # 처리되지 않은 파일 및 manifest.db에서 인식하지 못한 파일 확인
        print("\n\n\n [ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략 되었습니다.")
        for file_path in self.unprocessed_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:  # errors='ignore'를 추가하여 오류 발생 시 무시
                    first_line = file.readline().strip()
            except Exception as e:
                print(f" 오류 발생: 알 수 없는 오류가 발생했습니다. 무시하고 다음 작업을 진행합니다.")
                print(f" 오류 메시지: {e}")
                continue
            
            new_filename = None  # 새 파일 이름 초기화
            
            # 파일 내용에 따라 새 파일 이름 결정
            if 'a/bdl' in first_line:
                new_filename = os.path.join("manifest", "bdl_assetmanifest")
                self.processed_count_check += 1
                print(f"\n 특정 문자열 'a/bdl'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'manifest/' in first_line:
                new_filename = os.path.join("manifest", "manifest_assetmanifest")
                self.processed_count_check += 1
                print(f"\n 특정 문자열 'manifest/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'm/' in first_line:
                new_filename = os.path.join("manifest", "movie2manifest")
                self.processed_count_check += 1
                print(f"\n 특정 문자열 'm/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            elif 'b/' in first_line:
                new_filename = os.path.join("manifest", "soundmanifest")
                self.processed_count_check += 1
                print(f"\n 특정 문자열 'b/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")

            if new_filename is not None:
                try:
                    os.rename(file_path, new_filename)
                    print(f" 파일 이름이 \\{new_filename.replace(os.sep, '/')}으로 변경되었습니다.")
                except FileNotFoundError:
                    print(f"{file_path}을(를) 찾을 수 없습니다.")

        total_processed = self.processed_count_rename + self.processed_count_check

        # 작업 완료 후 종료 여부 확인
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")



    def process(self, file_path, file_index, total_files):
        hash_md5 = self.calculate_md5(file_path)
        hash_md5_value = hash_md5.hexdigest()

        # 백분율 계산
        file_index_int = int(file_index)
        total_files_int = int(total_files)
        percent_complete = (file_index_int / total_files_int) * 100
        
        # MD5 해시로 파일 이름 변경 시도
        if hash_md5_value in self.hash_list:
            new_filename = self.hash_list[hash_md5_value]
            try:
                os.rename(file_path, os.path.join(os.getcwd(), new_filename))
                relative_file_path = os.path.relpath(file_path, os.getcwd())
                return True, None, f"\n 작업 진행 상태: {file_index}/{total_files} ({percent_complete:.4f}%)\n 원본 파일 명 : \\{relative_file_path}\n 변경된 파일 명 : \\{new_filename.replace(os.sep, '/')}"
            except FileNotFoundError:
                print(f" {file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None

        # xxhash64로 해시 계산 후 파일 이름 변경 시도
        hash_xxhash64 = self.calculate_xxhash64(file_path)
        hash_xxhash64_value = hash_xxhash64.hexdigest()
        if hash_xxhash64_value in self.hash_list:
            new_filename = self.hash_list[hash_xxhash64_value]
            try:
                os.rename(file_path, os.path.join(os.getcwd(), new_filename))
                relative_file_path = os.path.relpath(file_path, os.getcwd())
                return True, None, f"\n 작업 진행 상태: {file_index}/{total_files} ({percent_complete:.4f}%)\n 원본 파일 명 : \\{relative_file_path}\n 변경된 파일 명 : \\{new_filename.replace(os.sep, '/')}"
            except FileNotFoundError:
                print(f" {file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None

        # 어느 해시 값으로도 일치하지 않을 경우
        return False, file_path, None



    def calculate_md5(self, file_path):
        # 파일의 MD5 해시 값 계산
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash



    def calculate_xxhash64(self, file_path):
        # 파일의 xxhash64 해시 값 계산
        xxhash64_hash = xxhash.xxh64()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                xxhash64_hash.update(chunk)
        return xxhash64_hash



    def get_all_files_in_folders(self, target_folders):
        # 대상 폴더 내의 모든 파일 가져오기
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
        # 문자열이 SHA1 해시 값 형식인지 확인
        return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)



rename_hashed_file = RenameHashedFile()
rename_hashed_file.start_processing()
