import os
import subprocess
from typing import List, Optional

class ConvertSound:
    def __init__(self, folder: str, desc: str):
        target_folder = os.path.join(Program.dest, folder)

        if not os.path.exists(target_folder):
            return

        files = [f for f in os.listdir(target_folder) if f.endswith((".awb", ".acb"))]
        files_amount = len(files)
        self.folder = folder
        Progress(desc, files_amount, self.process)

    def process(self, progress):
        target_folder = os.path.join(Program.dest, self.folder)
        files = [f for f in os.listdir(target_folder) if f.endswith((".awb", ".acb"))]

        cnt = 0
        for item in files:
            item_folder = os.path.dirname(item)
            item_relative = item[len(target_folder) + 1:]

            item_converted_path = os.path.join(target_folder, f"{os.path.splitext(item)[0]}.wav")

            tracks = self.get_tracks(os.path.join(target_folder, item))
            if tracks is not None:
                for track in tracks:
                    self.convert(os.path.join(target_folder, item), item_converted_path, track['track_num'])

            cnt += 1
            progress(cnt)

    def get_tracks(self, file_path: str) -> Optional[List[dict]]:
        info = self.get_info(file_path)

        lines = info.splitlines()
        if any(line.startswith("failed opening") for line in lines):
            return None

        find_track = "stream count: "
        tracks = [line for line in lines if line.startswith(find_track)]
        if tracks:
            number = int(tracks[0][len(find_track):])
            track_info = []
            for i in range(number):
                track = {}
                track['name'] = self.get_track_name(self.get_info(file_path, i + 1))
                track['track_num'] = i + 1
                track_info.append(track)
            return track_info
        else:
            track_info = [{'name': self.get_track_name(self.get_info(file_path)), 'track_num': 1}]
            return track_info

    def get_track_name(self, info: str) -> Optional[str]:
        if not info or "failed opening" in info:
            return None

        lines = info.splitlines()
        name_lines = [line for line in lines if line.startswith("stream name: ")]
        if name_lines:
            return name_lines[0][len("stream name: "):]
        return None

    def get_info(self, file_path: str, track: Optional[int] = None) -> str:
        vgmstream_path = self.get_vgmstream()

        if track is not None:
            args = ["-m", "-s", str(track), file_path]
        else:
            args = ["-m", file_path]

        result = subprocess.run([vgmstream_path] + args, stdout=subprocess.PIPE, text=True)
        return result.stdout

    def convert(self, input_path: str, output_path: str, track: Optional[int] = None):
        vgmstream_path = self.get_vgmstream()

        if track is not None:
            args = ["-s", str(track), "-o", output_path, input_path]
        else:
            args = ["-o", output_path, input_path]

        subprocess.run([vgmstream_path] + args, stdout=subprocess.PIPE)

    def get_vgmstream(self) -> str:
        app_dir = os.path.dirname(os.path.realpath(__file__))
        vgmstream_dir = os.path.join(app_dir, "vgmstream")
        path = os.path.join(vgmstream_dir, "test.exe")
        return path

class Program:
    dest = "destination_folder_path"

class Progress:
    def __init__(self, desc, total, callback):
        self.desc = desc
        self.total = total
        self.callback = callback

    def Report(self, cnt):
        print(f"{self.desc}: {cnt}/{self.total}")

# Usage
folder = "."  # 현재 디렉토리
desc = "Converting audio files"
ConvertSound(folder, desc)
