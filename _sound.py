import os
import subprocess

class ConvertSound:
    def __init__(self, desc):
        self.process(desc)

    def process(self, desc):
        current_directory = os.getcwd()  # 현재 작업 디렉터리 얻기
        files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(current_directory) for f in filenames
                 if f.endswith((".awb", ".acb"))]

        copy_folder = os.path.join(current_directory, "converted")

        cnt = 0
        for item in files:
            item_relative = os.path.relpath(item, current_directory)

            item_converted_path = os.path.join(copy_folder, os.path.splitext(item_relative)[0] + ".wav")
            item_converted_folder = os.path.dirname(item_converted_path)
            if not os.path.exists(item_converted_folder):
                os.makedirs(item_converted_folder)

            tracks = self.get_tracks(item)
            if tracks is not None:
                for track in tracks:
                    self.convert(item, os.path.join(item_converted_folder, f"{track['name']}.wav"), track['track_num'])

            cnt += 1
            print(f"{desc}: {cnt}/{len(files)}")

    def get_tracks(self, file_path):
        try:
            vgmstream_path = self.get_vgmstream()
            result = subprocess.run([vgmstream_path, "-m", file_path], capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None
            
            lines = output.splitlines()
            track_count_line = next(line for line in lines if line.startswith("stream count:"))
            track_count = int(track_count_line.split(":")[1].strip())
            
            tracks = []
            for i in range(1, track_count + 1):
                track_info = {}
                track_info["track_num"] = i
                track_info["name"] = self.get_track_name(file_path, i)
                tracks.append(track_info)
            
            return tracks
        except Exception as e:
            print(f"Error occurred while getting tracks: {e}")
            return None

    def get_track_name(self, file_path, track_num):
        try:
            vgmstream_path = self.get_vgmstream()
            result = subprocess.run([vgmstream_path, "-m", "-s", str(track_num), file_path], capture_output=True, text=True)
            output = result.stdout
            if "failed opening" in output:
                return None
            
            lines = output.splitlines()
            name_line = next(line for line in lines if line.startswith("stream name:"))
            name = name_line.split(":")[1].strip()
            
            return name
        except Exception as e:
            print(f"Error occurred while getting track name: {e}")
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
    desc = "Conversion Progress"  # Description for progress display
    convert_sound = ConvertSound(desc)


if __name__ == "__main__":
    main()
