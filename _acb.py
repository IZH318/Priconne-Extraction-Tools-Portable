import os
import subprocess

class ConvertSound:
    def __init__(self, desc):
        self.process(desc)

    def process(self, desc):
        current_directory = "."  # 현재 디렉터리로 설정, 필요에 따라 변경 가능
        files = [f for f in os.listdir(current_directory) if f.endswith((".awb", ".acb"))]

        copy_folder = os.path.join(current_directory, "converted")

        cnt = 0
        for item in files:
            item_relative = os.path.relpath(item, current_directory)

            item_converted_folder = os.path.join(copy_folder, os.path.splitext(item_relative)[0])
            if not os.path.exists(item_converted_folder):
                os.makedirs(item_converted_folder)

            tracks, total_tracks = self.get_tracks(item)
            if tracks is not None:
                for track in tracks:
                    track_names = self.get_track_names(track)
                    if track_names is not None:
                        for name in track_names:
                            output_file = os.path.join(item_converted_folder, f"{name}.wav")
                            self.convert(item, output_file, track['TrackNum'])

            cnt += 1
            print(f"{desc}: {cnt}/{len(files)} - Total tracks: {total_tracks}")

    def get_tracks(self, file_path):
        try:
            vgmstream_path = self.get_vgmstream()
            result = subprocess.run([vgmstream_path, "-m", file_path], capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None, None
            
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
                    return track_info, number
                else:
                    return None, None
            else:
                track_info = [{'Name': self.get_track_name(file_path), 'TrackNum': 1}]
                return track_info, 1
        except Exception as e:
            print(f"Error occurred while getting tracks: {e}")
            return None, None

    def get_track_name(self, file_path, track_num):
        try:
            vgmstream_path = self.get_vgmstream()
            result = subprocess.run([vgmstream_path, "-m", "-s", str(track_num), file_path], capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None
            
            lines = output.splitlines()
            for line in lines:
                if line.startswith("stream name:"):
                    return line[len("stream name:"):].strip()
        except Exception as e:
            print(f"Error occurred while getting track name: {e}")
            return None

    def get_track_names(self, track):
        if 'Name' in track:
            names = track['Name'].split(';')
            return [name.strip() for name in names if name.strip()]
        return None

    def convert(self, input_file, output_file, track_num=None):
        try:
            vgmstream_path = self.get_vgmstream()
            if track_num is not None:
                subprocess.run([vgmstream_path, "-s", str(track_num), "-o", output_file, input_file], check=True)
            else:
                subprocess.run([vgmstream_path, "-o", output_file, input_file], check=True)
            print(f"File converted: {input_file} -> {output_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while converting file: {e}")

    def get_vgmstream(self):
        vgmstream_path = os.path.join("vgmstream", "test.exe")
        return vgmstream_path


def main():
    desc = "Conversion Progress"  # 진행 상황 설명
    convert_sound = ConvertSound(desc)


if __name__ == "__main__":
    main()
