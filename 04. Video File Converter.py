# 필요한 라이브러리 임포트
import os  # 파일 시스템 작업을 위한 라이브러리
from pathlib import Path  # 경로 관리를 위한 Path 클래스



# UsmToolkit.exe 경로 지정
usmtoolkit_path = Path("usmtoolkit/UsmToolkit.exe")



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
                      _   ___    __           _____ __      _____                      __         
                     | | / (_)__/ /__ ___    / __(_) /__   / ___/__  ___ _  _____ ____/ /____ ____
                     | |/ / / _  / -_) _ \  / _// / / -_) / /__/ _ \/ _ \ |/ / -_) __/ __/ -_) __/
                     |___/_/\_,_/\__/\___/ /_/ /_/_/\__/  \___/\___/_//_/___/\__/_/  \__/\__/_/
    """)



# 작업 진행여부 확인 안내 문구
print("\n\n [ 안내 ] 이미 변환 된 파일이 있을 경우 해당 파일을 생략 후 진행합니다.")
print()
print("\n\n [ 주의 ] 본 도구는 '02. unity3d File Converter.py'를 통해 모든 Resource를 추출 후 작업해야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")

print("\n\n 작업을 진행하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.)")



# 디렉터리에서 *.usm 파일을 찾아 리스트로 반환하는 함수
def find_usm_files(directory):
    usm_files = []
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path) and file.endswith(".usm"):
            usm_files.append(Path(file_path))
    return usm_files



# 디렉터리 내 하위 폴더까지 검색하여 *.usm 파일을 찾아 리스트로 반환하는 함수
def search_usm_files_in_folder(folder):
    usm_files = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".usm"):
                usm_files.append(Path(os.path.join(root, file)))
    return usm_files

while True:    
    # 사용자 입력
    rewrite_response = input(" >>> ").lower()

    # y 또는 n을 입력할 때까지 반복
    if rewrite_response in ['y', 'n']:
        print("\n\n")
        break
    else:
        print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")

# 사용자의 입력에 따라 작업 진행 또는 종료
if rewrite_response == 'y':
    
    # 현재 디렉터리에서 *.usm 파일 찾기
    current_directory_files = find_usm_files(os.getcwd())

    # 사용자가 지정한 폴더명
    target_folders = ["m"]

    # 각 폴더에 대해 하위 폴더까지 모두 검색하여 usm 파일 찾기
    for target_folder in target_folders:
        target_folder_path = os.path.join(os.getcwd(), target_folder)
        if os.path.isdir(target_folder_path):
            target_folder_files = search_usm_files_in_folder(target_folder_path)

    # 변환
    for idx, usm_file in enumerate(current_directory_files + target_folder_files, start=1):
        print(f" [ Source Info ]")
        
        # 변환할 *.mp4 파일 경로 생성
        extract_path = usm_file.parent / (usm_file.stem + ".mp4")

        # 이미 존재하는지 확인 후 없으면 변환
        if not extract_path.exists():
            command = (
                f'cd "{usmtoolkit_path.parent.absolute()}" '
                f'&& "{usmtoolkit_path.name}" convert '
                f'-c "{usm_file.absolute()}" '
                f'-o "{usm_file.parent.absolute()}"'
            )
            os.system(command)

            print(f"\n [ Processing Results ]")
            print(f" 파일 처리 순번: {idx}")
            print(f" 원본 파일 경로: {os.path.relpath(usm_file.absolute(), os.getcwd())}")
            print(f" 변환된 파일 경로: {os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")
            total_processed += 1
        else:
            print(f" [ Processing Results ]")
            print(f" 파일 처리 순번: {idx}")
            print(f" 원본 파일 경로: {os.path.relpath(usm_file.absolute(), os.getcwd())}")
            print(f" 이미 변환 된 파일: {os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")

    # 작업 모두 끝나면 메시지 출력
    input(f" 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
else:
    # 프로그램 종료
    input(f" 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
