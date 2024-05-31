# 필요한 라이브러리 임포트
import os  # 파일 및 디렉터리 관리를 위한 os 모듈
import subprocess  # 외부 프로세스 실행을 위한 subprocess 모듈
import sys  # 파이썬 시스템과 관련된 기능을 제공하는 sys 모듈
from pathlib import Path  # 경로 관리를 위한 Path 클래스



# 파일 처리 질문
print("")
print("""
           ___      _                        _____                       __  __      ___      _ ___  _         
          / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
         / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
        /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
    """)
print("""
                       ___          ___        _____ __      _____                      __         
                      / _ |__ _____/ (_)__    / __(_) /__   / ___/__  ___ _  _____ ____/ /____ ____
                     / __ / // / _  / / _ \  / _// / / -_) / /__/ _ \/ _ \ |/ / -_) __/ __/ -_) __/
                    /_/ |_\_,_/\_,_/_/\___/ /_/ /_/_/\__/  \___/\___/_//_/___/\__/_/  \__/\__/_/
    """)



# 작업 진행여부 확인 안내 문구
print("\n\n [ 안내 ] 이미 변환된 파일이 있을 경우 처음부터 작업하시겠습니까?")
print("          ( [Y] = 기존 파일 덮어쓰기 / [N] = 기존 파일 작업 생략 )")
print()
print("\n\n [ 주의 ] 본 도구는 '02. unity3d File Converter.py'를 통해 모든 Resource를 추출 후 작업해야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")

print("\n\n [Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.")



class ConvertSound:
    def __init__(self, desc):
        """
        클래스가 인스턴스화될 때 호출, 주어진 desc 처리하는 process 메서드 호출

        Attributes:
            None

        Parameters:
            - desc (str): 초기화 작업에 사용될 설명 문자열

        Returns:
            None
        """
        self.process(desc)  # 생성자에서 process 메서드 호출



    def process(self, desc):
        """
        주어진 desc 처리, 현재 디렉터리와 하위 폴더에서 *.acb, *.awb 파일을 검색하여 처리

        Attributes:
            None

        Parameters:
            - desc (str): 처리할 설명 문자열

        Returns:
            None
        """

        current_directory = "."  # 현재 디렉터리로 설정, 필요에 따라 변경 가능
        
        # 현재 디렉터리에 있는 *.acb, *.awb 파일 검색
        current_files = [f for f in os.listdir(current_directory) if f.endswith((".acb", ".awb"))]

        # b, s, v 폴더에 있는 모든 하위 폴더의 *.awb 파일 검색
        subfolder_files = []  # 현재 디렉토리에서 하위 디렉토리의 파일 경로를 저장할 리스트
        for folder_name in ["b", "s", "v"]:  # 현재 디렉토리와 탐색할 폴더명 리스트
            folder_path = os.path.join(current_directory, folder_name)  # 탐색할 폴더의 경로 생성
            if os.path.isdir(folder_path):  # 만약 폴더가 존재한다면
                for root, dirs, files in os.walk(folder_path):  # 해당 폴더 내의 모든 하위 디렉토리 및 파일에 대해 반복
                    subfolder_files.extend([os.path.join(root, f) for f in files if f.endswith((".acb", ".awb"))])  # 파일들 중 "*.acb", ".awb" 확장자를 가진 파일들의 경로를 리스트에 추가

        files = current_files + subfolder_files
        self.total_files = len(files)  # 전체 파일 수 업데이트

        file_count = 0  # 처리된 파일의 수 초기화
        file_converted_count = 0  # 변환 된 총 파일의 수 초기화
        
        skip_existing_files = self.ask_user_skip_existing_files()  # 사용자에게 작업 방식을 묻고, 이미 존재하는 파일을 생략할지 여부 결정
        for item in files:
            item_path = Path(item)  # 파일 경로를 Path 객체로 변환
            item_folder = item_path.parent  # 파일이 위치한 폴더 경로
            converted_folder = item_folder / "_Converted"  # _Converted 폴더 경로 생성
            if not converted_folder.exists():  # Converted 폴더가 없으면 생성
                converted_folder.mkdir(parents=True)

            item_converted_folder = converted_folder / self.sanitize_filename(item_path.stem)  # 원본 파일명으로 폴더 경로 생성
            if not item_converted_folder.exists():  # 원본 파일명으로 폴더가 없으면 생성
                item_converted_folder.mkdir(parents=True)

            # 이미 변환된 파일이 있는 경우 작업 방식에 따라 처리
            if any((item_converted_folder / f"{self.sanitize_filename(track['Name'])}.wav").exists() for track in self.get_tracks(item_path)):
                if skip_existing_files:
                    continue  # 이미 변환된 파일이 있다면 해당 파일 생략

            tracks = self.get_tracks(item_path)  # 파일의 트랙 정보 가져오기
            if tracks is not None:
                file_count += 1  # 처리된 파일 수 증가
                for track in tracks:
                    output_file = item_converted_folder / f"{self.sanitize_filename(track['Name'])}.wav"  # *.wav 파일 경로 생성
                    if self.convert(item_path, output_file, track['TrackNum'], file_count):  # 파일 변환 수행
                        file_converted_count += 1  # 변환 된 총 파일의 수 증가

        input(f"\n\n\n 총 {file_converted_count}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
        sys.exit()



    def ask_user_skip_existing_files(self):
        """
        사용자에게 이미 존재하는 파일을 생략할지 묻고, 사용자의 입력에 따라 해당 작업 방식 반환

        Attributes:
            None

        Parameters:
            None

        Returns:
            - bool: 처음부터 작업할 경우 False, 이미 존재하는 파일을 생략할 경우 True 반환
        """
        while True:
            user_input = input(" >>> ").strip().lower()
            if user_input == 'y':
                return False  # 처음부터 작업
            elif user_input == 'n':
                print("\n\n\n [ 안내 ] 이미 변환 된 파일을 찾고 있습니다. 파일 개수에 따라 시간이 오래 거릴 수 있습니다.")
                return True  # 이미 존재하는 파일을 생략
            else:
                print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")



    def get_tracks(self, file_path):
        """
        주어진 파일에서 트랙 정보 가져와 반환

        Attributes:
            None

        Parameters:
            - file_path (str): 트랙 정보를 가져올 파일의 경로

        Returns:
            - list[dict] 또는 None: 트랙 정보를 담은 리스트 또는 파일을 열지 못했거나 예외가 발생한 경우 None 반환
        """
        try:
            vgmstream_path = self.get_vgmstream()  # vgmstream 실행 경로 가져오기
            result = subprocess.run([vgmstream_path, "-m", file_path], capture_output=True, text=True)  # vgmstream으로 트랙 정보 가져오기
            output = result.stdout
            if "failed opening" in output:  # 파일을 열 수 없는 경우 None 반환
                return None
            
            lines = output.splitlines()  # 출력을 라인별로 분할
            find_track = "stream count: "  # 트랙 정보 찾기
            tracks = [line for line in lines if line.startswith(find_track)]  # 트랙 정보 추출
            if tracks:
                number_str = tracks[0][len(find_track):]
                if number_str.isdigit():
                    number = int(number_str)
                    track_info = []
                    for i in range(1, number + 1):  # 트랙 정보를 딕셔너리로 저장
                        track = {}
                        track['Name'] = self.get_track_name(file_path, i)
                        track['TrackNum'] = i
                        track_info.append(track)
                    return track_info  # 트랙 정보 반환
                else:
                    return None
            else:
                track_info = [{'Name': self.get_track_name(file_path), 'TrackNum': 1}]  # 기본 트랙 정보 생성
                return track_info
        except Exception as e:
            print(f" Error occurred while getting tracks: {e}")
            return None



    def get_track_name(self, file_path, track_num=None):
        """
        주어진 파일의 트랙 이름을 가져와 반환

        Attributes:
            None

        Parameters:
            - file_path (str): 트랙 이름을 가져올 파일의 경로
            - track_num (int 또는 None): 특정 트랙의 번호 (기본값: None)

        Returns:
            - str 또는 None: 트랙 이름을 반환하거나 파일을 열지 못했거나 예외가 발생한 경우 None 반환
        """
        try:
            vgmstream_path = self.get_vgmstream()  # vgmstream 실행 경로 가져오기
            command = [vgmstream_path, "-m"]  # vgmstream으로 트랙 이름 가져오기
            if track_num is not None:
                command.extend(["-s", str(track_num)])
            command.append(str(file_path))
            result = subprocess.run(command, capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:  # 파일을 열 수 없는 경우 None 반환
                return None
            
            lines = output.splitlines()  # 출력을 라인별로 분할
            for line in lines:
                if line.startswith("stream name:"):  # 트랙 이름 정보 추출
                    return line[len("stream name:"):].strip()
            # 만약 stream name이 없으면 파일명 기반으로 트랙 이름 생성
            return f"track_{track_num}" if track_num else "track_1"
        except Exception as e:
            print(f"Error occurred while getting track name: {e}")
            return None



    def convert(self, input_file, output_file, track_num=None, file_count=0):
        """
        주어진 파일을 변환하여 지정된 경로에 파일로 저장

        Attributes:
            None

        Parameters:
            - input_file (str): 변환할 입력 파일의 경로
            - output_file (str): 변환된 파일을 저장할 출력 파일의 경로
            - track_num (int 또는 None): 특정 트랙의 번호 (기본값: None)
            - file_count (int): 처리된 파일의 순서 (기본값: 0)

        Returns:
            - bool: 변환이 성공하면 True 반환, 실패하면 False 반환
        """
        try:
            # 백분율 계산
            percent_complete = (file_count / self.total_files) * 100
            
            print("\n\n")
            print(f" [ Processing ]")
            print(f" 작업 진행 상태: {file_count}/{self.total_files} ({percent_complete:.4f}%)")  # 처리된 파일 순서 출력
            print(f" 원본 파일 경로: \{input_file}")  # 변환된 파일 정보 출력
            print(f" 변환된 파일 경로: \{output_file}")
            print()
            print(f" [ Source Info ]")
            vgmstream_path = self.get_vgmstream()  # vgmstream 실행 경로 가져오기
            command = [vgmstream_path, "-o", str(output_file)]  # *.wav 파일로 변환하는 명령 생성
            if track_num is not None:
                command.extend(["-s", str(track_num)])  # 특정 트랙만 변환하는 경우
            command.append(str(input_file))
            subprocess.run(command, check=True)  # 외부 프로세스 실행
            return True  # 파일이 변환되었음을 나타내는 True 반환
        except subprocess.CalledProcessError as e:
            return False  # 변환 실패를 나타내는 False 반환



    def get_vgmstream(self):
        """
        vgmstream 실행 파일 경로 반환

        Attributes:
            None

        Parameters:
            None

        Returns:
            - str: vgmstream 실행 파일 경로 반환
        """
        vgmstream_path = r".\usmtoolkit\vgmstream\test.exe"  # vgmstream 실행 경로 반환
        if not os.path.exists(vgmstream_path):  # vgmstream_path에 지정 한 경로에 파일이 존재하지 않는 경우
            print(f"\n\n\n [ 경고 ] vgmstream 실행 파일을 찾을 수 없습니다. usmtoolkit 폴더 내에 test.exe 파일이 있는지 확인하십시오.")
            input(f"\n          Enter 키를 눌러 창을 종료하십시오.\n >>> ")
            sys.exit()  # 프로그램 종료
        return vgmstream_path



    def sanitize_filename(self, filename):
        """
        파일 이름에서 세미콜론을 쉼표로 대체

        Attributes:
            None

        Parameters:
            - filename (str): 처리할 파일 이름

        Returns:
            - str: 세미콜론이 쉼표로 대체된 파일 이름 반환
        """
        return filename.replace(';', ',')



def main():
    """
    ConvertSound 클래스의 인스턴스를 생성하여 사운드 변환 작업 시작

    Attributes:
        None

    Parameters:
        None

    Returns:
        None
    """
    desc = "Conversion Progress"  # 진행 상황 설명
    convert_sound = ConvertSound(desc)  # ConvertSound 클래스 인스턴스 생성



if __name__ == "__main__":
    main()  # 메인 함수 실행
