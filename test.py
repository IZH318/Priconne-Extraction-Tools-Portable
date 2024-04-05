import os
from pathlib import Path

# UsmToolkit.exe의 경로를 직접 지정합니다.
usmtoolkit_path = Path("usmtoolkit/UsmToolkit.exe")

def find_usm_files(directory):
    usm_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".usm"):
                usm_files.append(Path(root) / file)
    return usm_files

# 현재 디렉터리에서 usm 파일을 찾습니다.
current_directory_files = find_usm_files(os.getcwd())

# "m" 폴더에서 usm 파일을 찾습니다.
m_directory_files = find_usm_files(os.path.join(os.getcwd(), "m"))

# 모든 usm 파일을 한 리스트로 합칩니다.
all_usm_files = current_directory_files + m_directory_files

# 각 usm 파일을 변환 작업을 수행합니다.
for usm_file in all_usm_files:
    # 변환할 mp4 파일의 경로를 생성합니다.
    extract_path = usm_file.parent / (usm_file.stem + ".mp4")

    # 변환할 mp4 파일이 이미 존재하는지 확인하고, 없으면 변환 작업을 수행합니다.
    if not extract_path.exists():
        command = (
            f"cd {usmtoolkit_path.parent.absolute()} "
            f"&& {usmtoolkit_path.name} convert "
            f"-c {usm_file.absolute()} "
            f"-o {usm_file.parent.absolute()}"
        )
        os.system(command)
        print(f"변환 완료: {usm_file.name} -> {extract_path}")
