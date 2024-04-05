import os
from pathlib import Path

# UsmToolkit.exe의 경로를 직접 지정합니다.
usmtoolkit_path = Path("usmtoolkit/UsmToolkit.exe")

# 실제로 *.usm 파일이 *.mp4 파일로 변환 된 파일 수 계산
total_processed = 0

def find_usm_files(directory):
    usm_files = []
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path) and file.endswith(".usm"):
            usm_files.append(Path(file_path))
    return usm_files

def search_usm_files_in_folder(folder):
    usm_files = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".usm"):
                usm_files.append(Path(os.path.join(root, file)))
    return usm_files

while True:
    # 사용자에게 작업을 계속할지 물어봅니다.
    rewrite_response = input("작업을 진행하시겠습니까? (Y/N): ").lower()

    # y 또는 n을 입력할 때까지 반복합니다.
    if rewrite_response in ['y', 'n']:
        print("\n\n")
        break
    else:
        print("잘못된 입력입니다. Y 또는 N을 입력하십시오.\n")

# 사용자의 입력에 따라 작업을 진행하거나 종료합니다.
if rewrite_response == 'y':
    
    # 현재 디렉터리에서 usm 파일을 찾습니다.
    current_directory_files = find_usm_files(os.getcwd())

    # 사용자가 지정한 폴더명
    target_folders = ["m"]

    # 각 폴더에 대해 하위 폴더까지 모두 검색하여 usm 파일을 찾습니다.
    for target_folder in target_folders:
        target_folder_path = os.path.join(os.getcwd(), target_folder)
        if os.path.isdir(target_folder_path):
            target_folder_files = search_usm_files_in_folder(target_folder_path)

    # 변환 작업을 수행합니다.
    for idx, usm_file in enumerate(current_directory_files + target_folder_files, start=1):
        # 변환할 mp4 파일의 경로를 생성합니다.
        extract_path = usm_file.parent / (usm_file.stem + ".mp4")

        # 이미 존재하는지 확인하고, 없으면 변환 작업을 수행합니다.
        if not extract_path.exists():
            command = (
                f'cd "{usmtoolkit_path.parent.absolute()}" '
                f'&& "{usmtoolkit_path.name}" convert '
                f'-c "{usm_file.absolute()}" '
                f'-o "{usm_file.parent.absolute()}"'
            )
            os.system(command)

            print(f"\n[ Processing Results ]")
            print(f"파일 처리 순번: {idx}")
            print(f"원본 파일 경로: {os.path.relpath(usm_file.absolute(), os.getcwd())}")
            print(f"변경된 파일 경로: {os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")
            total_processed += 1
        else:
            print(f"[ Processing Results ]")
            print(f"파일 처리 순번: {idx}")
            print(f"원본 파일 경로: {os.path.relpath(usm_file.absolute(), os.getcwd())}")
            print(f"이미 존재하는 파일: {os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")

    # 작업이 모두 끝나면 메시지 출력
    input(f"총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")
else:
    # 프로그램 종료
    input(f"Enter 키를 입력하여 종료하십시오.")
