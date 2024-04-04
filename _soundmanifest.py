import os
import subprocess
from pathlib import Path

class ConvertSound:
    def __init__(self, desc):
        self.process(desc)

    def process(self, desc):
        current_directory = "."  # 현재 디렉터리로 설정, 필요에 따라 변경 가능
        files = [f for f in os.listdir(current_directory) if f.endswith((".awb", ".acb"))]

        copy_folder = os.path.join(current_directory, "Converted")

        file_count = 0
        for item in files:
            item_path = Path(item)
            item_converted_folder = Path(copy_folder) / item_path.stem
            if not item_converted_folder.exists():
                item_converted_folder.mkdir(parents=True)

            tracks = self.get_tracks(item_path)
            if tracks is not None:
                for track in tracks:
                    output_file = item_converted_folder / f"{track['Name']}.wav"
                    if self.convert(item_path, output_file, track['TrackNum'], file_count):
                        file_count += 1

    def get_tracks(self, file_path):
        try:
            vgmstream_path = self.get_vgmstream()
            result = subprocess.run([vgmstream_path, "-m", file_path], capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None
            
            lines = output.splitlines()
            find_track = "stream count: "
            tracks = [line for line in lines if line.startswith(find_track)]
            if tracks:
                number_str = tracks[0][len(find_track):]
                if number_str.isdigit():
                    number = int(number_str)
                    track_info = []
                    for i in range(1, number + 1):
                        track = {}
                        track['Name'] = self.get_track_name(file_path, i)
                        track['TrackNum'] = i
                        track_info.append(track)
                    return track_info
                else:
                    return None
            else:
                track_info = [{'Name': self.get_track_name(file_path), 'TrackNum': 1}]
                return track_info
        except Exception as e:
            print(f"Error occurred while getting tracks: {e}")
            return None

    def get_track_name(self, file_path, track_num=None):
        try:
            vgmstream_path = self.get_vgmstream()
            command = [vgmstream_path, "-m"]
            if track_num is not None:
                command.extend(["-s", str(track_num)])
            command.append(str(file_path))
            result = subprocess.run(command, capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None
            
            lines = output.splitlines()
            for line in lines:
                if line.startswith("stream name:"):
                    return line[len("stream name:"):].strip()
            # 만약 stream name이 없으면 파일명을 기반으로 트랙 이름 생성
            return f"track_{track_num}" if track_num else "track_1"
        except Exception as e:
            print(f"Error occurred while getting track name: {e}")
            return None

    def convert(self, input_file, output_file, track_num=None, file_count=0):
        try:
            vgmstream_path = self.get_vgmstream()
            command = [vgmstream_path, "-o", str(output_file)]
            if track_num is not None:
                command.extend(["-s", str(track_num)])
            command.append(str(input_file))
            subprocess.run(command, check=True)
            print(f"파일 처리 순번: {file_count+1}")
            print(f"원본 파일명: {input_file}")
            print(f"변경된 파일명: {output_file}")
            print()
            return True  # 파일이 변환되었음을 나타내는 True 반환
        except subprocess.CalledProcessError as e:
            return False  # 변환 실패를 나타내는 False 반환

    def get_vgmstream(self):
        vgmstream_path = r".\usmtoolkit\vgmstream\test.exe"
        return vgmstream_path

def main():
    desc = "Conversion Progress"  # 진행 상황 설명
    convert_sound = ConvertSound(desc)

if __name__ == "__main__":
    main()
