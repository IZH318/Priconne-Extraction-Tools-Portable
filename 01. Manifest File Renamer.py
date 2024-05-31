# 필요한 라이브러리 임포트
import os  # 파일 시스템 작업을 위한 라이브러리
import sys  # 파이썬 시스템과 관련된 기능을 제공하는 sys 모듈
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



# 작업 진행여부 확인 안내 문구 출력
print("\n\n [ 주의 ] 현재 디렉터리에 'manifest.db'파일과 작업을 진행할 파일이 원본 구조 그대로 있어야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")



# 사용자에게 작업을 진행할지 여부를 묻는 메시지 출력
print("\n\n 작업을 진행하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.)")



# 파일 이름 변경 및 파일 내용 확인 클래스 정의
class RenameHashedFile:
    def __init__(self):
        """
        FileProcessor 클래스의 초기화 메서드

        Attributes:
            - target_folders (list): 파일 처리 대상 폴더들을 포함하는 리스트.
            - hash_list (dict): 해시 값과 파일 이름을 매핑하는 딕셔너리.
            - processed_count_rename (int): 파일 이름이 변경된 횟수.
            - processed_count_check (int): 파일 내용이 확인된 횟수.
            - unprocessed_files (list): 처리되지 않은 파일 목록.
            - results (list): 처리된 결과를 담는 리스트.
            
        Parameters:
            None

        Returns:
            None
        """
        # 클래스 초기화
        self.target_folders = ['a', 'b', 'm', 'manifest', 's', 'v']  # 대상 폴더들을 지정
        self.hash_list = {}  # 해시 값과 파일 이름을 매핑할 딕셔너리
        self.processed_count_rename = 0  # 파일 이름 변경된 개수
        self.processed_count_check = 0  # 파일 내용 확인된 개수
        self.unprocessed_files = []  # 처리되지 않은 파일 목록
        self.results = []  # 처리된 결과



    # 사용자 입력을 받아서 작업을 시작하거나 종료
    def start_processing(self):
        """
        파일 처리를 시작하는 메서드

        사용자로부터 확인을 받은 후, 파일 처리를 시작하거나 프로그램을 종료

        Parameters:
            None

        Returns:
            None
        """
        while True:
            user_input = input(" >>> ").strip().lower()  # 사용자 입력을 받음
            if user_input == 'y':
                print("\n\n")
                self.process_files()  # 파일 처리 시작
                break
            elif user_input == 'n':
                input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
                sys.exit()  # 프로그램 종료
            else:
                print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")



    # 파일을 처리하는 메인 함수
    def process_files(self):
        """
        대상 폴더 내의 파일을 처리하는 메서드

        01. 'manifest.db' 파일의 존재 여부를 확인하고, 없으면 경고 메시지를 출력하고 종료
        02. 대상 폴더 내의 모든 파일을 가져옴
        03. 'manifest.db' 파일에서 해시 값과 파일 이름을 가져와 딕셔너리에 저장
        04. 스레드 풀을 사용하여 파일을 처리, 처리 중 실패한 파일은 목록에 추가
        05. 처리된 파일의 정보 출력, 처리되지 않은 파일과 인식하지 못한 파일에 대한 예외 처리를 수행
        06. 처리된 파일의 수를 요약하여 출력

        Parameters:
            None

        Returns:
            None
        """
        manifest_db_path = os.path.join(os.getcwd(), "manifest.db")  # manifest.db 파일 경로 설정
        
        # manifest.db 파일이 현재 디렉토리에 없을 경우 경고 메시지 출력 후 종료
        if not os.path.exists(manifest_db_path):
            input(f" [ 경고 ] 현재 디렉터리에 'manifest.db'파일이 존재하지 않습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
            sys.exit()
            
        print(" [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
        print("          모든 파일이 불러와지면 파일 이름이 모두 자동으로 변환됩니다.\n")
        
        files = self.get_all_files_in_folders(self.target_folders)  # 대상 폴더 내 모든 파일 가져오기
        total_files = len(files)  # 전체 파일 수 계산
        
        # 대상 폴더에서 처리할 파일이 없을 경우 경고 메시지 출력 후 종료
        if not files:
            input(f"\n\n 대상 폴더에서 처리 할 파일을 찾을 수 없습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
            sys.exit()

        # manifest.db에서 해시 값과 파일 이름 가져오기
        with sqlite3.connect(manifest_db_path) as connection:  # manifest.db 파일과 연결
            cursor = connection.cursor()  # 커서 생성
            cursor.execute("SELECT * FROM t")  # 테이블 t에서 모든 데이터 선택
            rows = cursor.fetchall()  # 모든 행 가져오기
            for row in rows:  # 각 행에 대해
                filename, hash_value = row  # 파일 이름과 해시 값을 가져옴
                self.hash_list[hash_value] = filename  # 해시 값을 키로 파일 이름을 딕셔너리에 저장

        # 스레드 풀을 사용하여 파일 처리
        with concurrent.futures.ThreadPoolExecutor() as executor:  # 스레드 풀 생성
            # 파일 처리를 위한 각 파일에 대한 Future 객체 생성
            futures = {executor.submit(self.process, file, index, total_files): (file, index) for index, file in enumerate(files, 1)}
            # tqdm을 사용하여 진행 상황 표시
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=" 파일을 불러오는 중..."):
                file_path, file_index = futures[future]  # 파일 경로와 파일 인덱스를 가져옴
                try:
                    result = future.result()  # 처리 결과를 가져옴
                except Exception as exc:  # 예외 발생 시
                    print(f" File processing failed for {file_path}: {exc}")  # 오류 메시지 출력
                else:
                    if result is not None:
                        if not result[0]:  # 처리 실패 시
                            self.unprocessed_files.append(result[1])  # 처리되지 않은 파일 목록에 추가
                        else:  # 처리 성공 시
                            self.results.append((file_index, result[1], result[2]))  # 결과 목록에 추가

        print("\n")

        # 결과 출력
        for file_index, original_file, new_file_info in sorted(self.results, key=lambda x: x[0]):
            print(new_file_info)
            self.processed_count_rename += 1

        # 처리되지 않은 파일 및 manifest.db에서 인식하지 못한 파일 확인
        print("\n\n\n [ 안내 ] manifest.db에서 인식하지 못한 파일은 다음과 같이 예외 처리 또는 생략되었습니다.")
        for file_path in self.unprocessed_files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:  # errors='ignore'를 추가하여 오류 발생 시 무시
                    first_line = file.readline().strip()  # 첫 번째 줄 읽기
            except Exception as e:  # 예외 발생 시
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
                new_filename = os.path.join("manifest", "assetmanifest")
                self.processed_count_check += 1
                print(f"\n 특정 문자열 'm/'이(가) {file_path[len(os.getcwd()):]} 파일 내용에 포함되어 있습니다.")
            
            # 새 파일 이름이 결정되었으면 파일 이름 변경
            if new_filename:
                new_filepath = self.get_unique_filename(new_filename)
                try:
                    os.rename(file_path, new_filepath)
                    relative_file_path = os.path.relpath(file_path, os.getcwd())
                    print(f" 작업 진행 상태: 예외 처리된 파일")
                    print(f" 원본 파일 명 : \\{relative_file_path}")
                    print(f" 변경된 파일 명 : \\{new_filepath.replace(os.sep, '/')}")
                except FileNotFoundError:
                    print(f" {file_path}을(를) 찾을 수 없습니다.")
                except FileExistsError:
                    print(f" {new_filepath} 파일이 이미 존재합니다.")

        # 최종 결과 요약 출력
        global total_processed
        total_processed = self.processed_count_rename + self.processed_count_check
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
        sys.exit()  # 프로그램 종료



    # 파일 처리 함수
    def process(self, file_path, file_index, total_files):
        """
        파일을 처리하고 파일 이름을 변경하는 작업을 수행
        
        주어진 파일 경로에서 MD5 또는 xxhash64 해시를 계산하고, 해당 해시가 이미 해시 목록에 있는지 확인한 후에 파일 이름을 변경
        
        코드는 주어진 파일이름과 이동된 파일 이름을 반환

        Attributes:
            None

        Parameters:
            - file_path (str): 처리할 파일의 경로
            - file_index (int): 현재 처리 중인 파일의 인덱스
            - total_files (int): 전체 파일 수

        Returns:
            - tuple: (성공 여부(bool), 원본 파일 경로(str), 변경된 파일 경로(str))
              - 성공 여부(bool): 파일 이름 변경이 성공했는지 여부를 나타내는 불리언 값
              - 원본 파일 경로(str): 파일 이름 변경 전의 원본 파일 경로
              - 변경된 파일 경로(str): 파일 이름 변경 후의 새로운 파일 경로
        """
        hash_md5 = self.calculate_md5(file_path)  # MD5 해시 값 계산
        hash_md5_value = hash_md5.hexdigest()  # MD5 해시 값을 16진수 문자열로 변환

        # 백분율 계산
        file_index_int = int(file_index)  # 파일 인덱스를 정수로 변환
        total_files_int = int(total_files)  # 전체 파일 수를 정수로 변환
        percent_complete = (file_index_int / total_files_int) * 100  # 진행률 계산
        
        # MD5 해시로 파일 이름 변경 시도
        if hash_md5_value in self.hash_list:  # MD5 해시 값이 해시 목록에 있는지 확인
            new_filename = self.hash_list[hash_md5_value]  # 새 파일 이름을 해시 목록에서 가져옴
            new_filepath = os.path.join(os.getcwd(), new_filename)  # 새 파일 경로 생성
            if os.path.exists(new_filepath):  # 새 파일 경로가 이미 존재하는지 확인
                new_filepath = self.get_unique_filename(new_filepath)  # 고유한 파일 이름 생성
            try:
                os.rename(file_path, new_filepath)  # 파일 이름 변경
                relative_file_path = os.path.relpath(file_path, os.getcwd())  # 상대 파일 경로 계산
                return True, None, f"\n 작업 진행 상태: {file_index}/{total_files} ({percent_complete:.4f}%)\n 원본 파일 명 : \\{relative_file_path}\n 변경된 파일 명 : \\{new_filepath.replace(os.sep, '/')}"
            except FileNotFoundError:  # 파일을 찾을 수 없을 경우
                print(f" {file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None
            except FileExistsError:  # 파일이 이미 존재할 경우
                print(f" {new_filepath} 파일이 이미 존재합니다.")
                return False, file_path, None

        # xxhash64로 해시 계산 후 파일 이름 변경 시도
        hash_xxhash64 = self.calculate_xxhash64(file_path)  # xxhash64 해시 값 계산
        hash_xxhash64_value = hash_xxhash64.hexdigest()  # xxhash64 해시 값을 16진수 문자열로 변환
        if hash_xxhash64_value in self.hash_list:  # xxhash64 해시 값이 해시 목록에 있는지 확인
            new_filename = self.hash_list[hash_xxhash64_value]  # 새 파일 이름을 해시 목록에서 가져옴
            new_filepath = os.path.join(os.getcwd(), new_filename)  # 새 파일 경로 생성
            if os.path.exists(new_filepath):  # 새 파일 경로가 이미 존재하는지 확인
                new_filepath = self.get_unique_filename(new_filepath)  # 고유한 파일 이름 생성
            try:
                os.rename(file_path, new_filepath)  # 파일 이름 변경
                relative_file_path = os.path.relpath(file_path, os.getcwd())  # 상대 파일 경로 계산
                return True, None, f"\n 작업 진행 상태: {file_index}/{total_files} ({percent_complete:.4f}%)\n 원본 파일 명 : \\{relative_file_path}\n 변경된 파일 명 : \\{new_filepath.replace(os.sep, '/')}"
            except FileNotFoundError:  # 파일을 찾을 수 없을 경우
                print(f" {file_path}을(를) 찾을 수 없습니다.")
                return False, file_path, None
            except FileExistsError:  # 파일이 이미 존재할 경우
                print(f" {new_filepath} 파일이 이미 존재합니다.")
                return False, file_path, None

        # 어느 해시 값으로도 일치하지 않을 경우
        return False, file_path, None



    # 파일의 MD5 해시 값 계산
    def calculate_md5(self, file_path):
        """
        주어진 파일의 MD5 해시 계산

        Attributes:
            None

        Parameters:
            - file_path (str): MD5 해시를 계산할 파일의 경로

        Returns:
            - md5_hash (hashlib.md5 객체): 주어진 파일의 MD5 해시
        """
        md5_hash = hashlib.md5()  # MD5 해시 객체 생성
        with open(file_path, "rb") as file:  # 파일을 바이너리 모드로 엶
            for chunk in iter(lambda: file.read(4096), b""):  # 파일을 4096바이트씩 읽음
                md5_hash.update(chunk)  # 해시 객체에 데이터 업데이트
        return md5_hash  # MD5 해시 객체 반환



    # 파일의 xxhash64 해시 값 계산
    def calculate_xxhash64(self, file_path):
        """
        이 메소드는 주어진 파일의 xxhash64 해시를 계산

        Attributes:
            None

        Parameters:
            - file_path (str): xxhash64 해시를 계산할 파일의 경로

        Returns:
            - xxhash64_hash (xxhash.xxh64 객체): 주어진 파일의 xxhash64 해시
        """
        xxhash64_hash = xxhash.xxh64()  # xxhash64 해시 객체 생성
        with open(file_path, "rb") as file:  # 파일을 바이너리 모드로 엶
            for chunk in iter(lambda: file.read(4096), b""):  # 파일을 4096바이트씩 읽음
                xxhash64_hash.update(chunk)  # 해시 객체에 데이터 업데이트
        return xxhash64_hash  # xxhash64 해시 객체 반환



    # 대상 폴더 내의 모든 파일 가져오기
    def get_all_files_in_folders(self, target_folders):
        """
        이 메소드는 주어진 대상 폴더에서 모든 파일을 찾아내어 반환

        Attributes:
            None

        Parameters:
            - target_folders (list of str): 파일을 찾을 대상 폴더의 이름 목록

        Returns:
            - all_files (list of str): 대상 폴더에서 찾은 모든 파일의 경로 목록
        """
        all_files = []  # 모든 파일 목록 초기화
        for folder in target_folders:  # 각 대상 폴더에 대해
            folder_path = os.path.join(os.getcwd(), folder)  # 대상 폴더의 전체 경로 생성
            if os.path.exists(folder_path) and os.path.isdir(folder_path):  # 폴더가 존재하고 디렉토리인지 확인
                for root, _, files in os.walk(folder_path):  # 폴더 내 모든 파일에 대해
                    for file_name in files:  # 각 파일 이름에 대해
                        if self.is_sha1(file_name):  # 파일 이름이 SHA1 형식인지 확인
                            all_files.append(os.path.join(root, file_name))  # 파일 경로를 전체 파일 목록에 추가
        return all_files  # 모든 파일 목록 반환



    # 문자열이 SHA1 해시 값 형식인지 확인
    def is_sha1(self, s):
        """
        주어진 문자열이 SHA1 형식인지 확인

        Attributes:
            None

        Parameters:
            - s (str): 확인할 문자열

        Returns:
            - bool: 주어진 문자열이 SHA1 형식이면 True, 그렇지 않으면 False를 반환합니다.
        """
        return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)  # 문자열 길이가 40이고, 모든 문자가 16진수인지 확인



    # 중복된 파일 이름이 있을 경우 고유한 파일 이름 생성
    def get_unique_filename(self, file_path):
        """
        중복되지 않는 파일 이름 생성

        Attributes:
            None

        Parameters:
            - file_path (str): 중복되는 파일 이름을 생성할 파일의 경로

        Returns:
            - new_file_path (str): 중복되지 않는 새로운 파일 경로
        """
        base, extension = os.path.splitext(file_path)  # 파일 경로를 기본 이름(base)과 확장자(extension)로 분리
        counter = 1  # 중복된 파일 이름이 있을 경우 추가할 숫자(counter) 초기화
        new_file_path = f"{base}_(Duplicate_{counter}){extension}"  # 숫자를 붙인 새로운 파일 경로(new_file_path) 생성
        while os.path.exists(new_file_path):  # 새로운 파일 경로가 이미 존재하는지 확인
            counter += 1  # 존재할 경우 숫자 1 증가
            new_file_path = f"{base}_(Duplicate_{counter}){extension}"  # 증가된 숫자 붙인 새로운 파일 경로 생성
        return new_file_path  # 중복되지 않는 새로운 파일 경로 반환



# RenameHashedFile 클래스 인스턴스 생성 및 작업 시작
rename_hashed_file = RenameHashedFile()  # 클래스 인스턴스 생성
rename_hashed_file.start_processing()  # 작업 시작
