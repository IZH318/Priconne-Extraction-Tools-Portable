import os  # 파일 및 디렉터리 관리를 위한 os 모듈
import subprocess  # 외부 프로세스 실행을 위한 subprocess 모듈
from pathlib import Path  # 경로 관리를 위한 Path 클래스

class ConvertSound:
    def __init__(self, desc):
        self.process(desc)  # 생성자에서 process 메서드 호출

    def process(self, desc):
        current_directory = "."  # 현재 디렉터리로 설정, 필요에 따라 변경 가능
        
        # 현재 디렉터리와 b, s, v 폴더에 있는 모든 파일 검색
        files = []
        for folder_name in ["", "b", "s", "v"]:
            folder_path = os.path.join(current_directory, folder_name)
            if os.path.isdir(folder_path):
                files.extend([os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith((".awb", ".acb"))])

        file_count = 0  # 처리된 파일의 수 초기화
        for item in files:
            item_path = Path(item)  # 파일 경로를 Path 객체로 변환
            item_folder = item_path.parent  # 파일이 위치한 폴더 경로
            converted_folder = item_folder / "Converted"  # Converted 폴더 경로 생성
            if not converted_folder.exists():  # Converted 폴더가 없으면 생성
                converted_folder.mkdir(parents=True)

            item_converted_folder = converted_folder / item_path.stem  # 원본 파일명으로 폴더 경로 생성
            if not item_converted_folder.exists():  # 원본 파일명으로 폴더가 없으면 생성
                item_converted_folder.mkdir(parents=True)

            tracks = self.get_tracks(item_path)  # 파일의 트랙 정보 가져오기
            if tracks is not None:
                for track in tracks:
                    output_file = item_converted_folder / f"{track['Name']}.wav"  # WAV 파일의 경로 생성
                    if self.convert(item_path, output_file, track['TrackNum'], file_count):  # 파일 변환 수행
                        file_count += 1  # 처리된 파일 수 증가

    def get_tracks(self, file_path):
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
            print(f"Error occurred while getting tracks: {e}")
            return None

    def get_track_name(self, file_path, track_num=None):
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
            # 만약 stream name이 없으면 파일명을 기반으로 트랙 이름 생성
            return f"track_{track_num}" if track_num else "track_1"
        except Exception as e:
            print(f"Error occurred while getting track name: {e}")
            return None

    def convert(self, input_file, output_file, track_num=None, file_count=0):
        try:
            vgmstream_path = self.get_vgmstream()  # vgmstream 실행 경로 가져오기
            command = [vgmstream_path, "-o", str(output_file)]  # WAV 파일로 변환하는 명령 생성
            if track_num is not None:
                command.extend(["-s", str(track_num)])  # 특정 트랙만 변환하는 경우
            command.append(str(input_file))
            subprocess.run(command, check=True)  # 외부 프로세스 실행
            print(f"파일 처리 순번: {file_count+1}")  # 처리된 파일 순서 출력
            print(f"원본 파일명: {input_file}")  # 변환된 파일 정보 출력
            print(f"변경된 파일명: {output_file}")
            print()
            return True  # 파일이 변환되었음을 나타내는 True 반환
        except subprocess.CalledProcessError as e:
            return False  # 변환 실패를 나타내는 False 반환

    def get_vgmstream(self):
        vgmstream_path = os.path.join("usmtoolkit", "vgmstream", "test.exe")  # vgmstream 실행 경로 반환
        return vgmstream_path

def main():
    desc = "Conversion Progress"  # 진행 상황 설명
    convert_sound = ConvertSound(desc)  # ConvertSound 클래스 인스턴스 생성

if __name__ == "__main__":
    main()  # 메인 함수 실행
