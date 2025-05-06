# 필요한 라이브러리 임포트
import os  # 파일 시스템 작업을 위한 라이브러리
import sys  # 파이썬 시스템과 관련된 기능을 제공하는 sys 모듈
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
    """
    특정 디렉토리에서 ".usm" 확장자를 가진 파일들을 찾아 경로를 리스트에 저장하는 함수.

    Parameters:
        - directory (str): 파일을 찾을 디렉토리의 경로.

    Returns:
        - list: ".usm" 확장자를 가진 파일들의 경로를 담은 리스트.
    """
    usm_files = []  # ".usm" 확장자를 가진 파일들의 경로를 저장할 리스트

    # 디렉토리 내의 모든 파일에 대해 반복
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)  # 파일의 전체 경로 생성
        if os.path.isfile(file_path) and file.endswith(".usm"):  # 파일이 존재하고 ".usm" 확장자를 가진 경우
            usm_files.append(Path(file_path))  # 파일의 경로를 Path 객체로 변환하여 리스트에 추가
    return usm_files



# 디렉터리 내 하위 폴더까지 검색하여 *.usm 파일을 찾아 리스트로 반환하는 함수
def search_usm_files_in_folder(folder):
    """
    특정 폴더와 그 하위 폴더에서 ".usm" 확장자를 가진 파일들을 찾아 경로를 리스트에 저장하는 함수.

    Parameters:
        - folder (str): 파일을 찾을 폴더의 경로.

    Returns:
        - list: ".usm" 확장자를 가진 파일들의 경로를 담은 리스트.
    """
    usm_files = []  # ".usm" 확장자를 가진 파일들의 경로를 저장할 리스트

    # 주어진 폴더와 그 하위 폴더에 대해 반복
    for root, dirs, files in os.walk(folder):
        for file in files:  # 각 폴더 내의 파일에 대해 반복
            if file.endswith(".usm"):  # 파일이 ".usm" 확장자를 가진 경우
                usm_files.append(Path(os.path.join(root, file)))  # 파일의 전체 경로를 Path 객체로 변환하여 리스트에 추가
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
        sys.exit()

# 사용자의 입력에 따라 작업 진행 또는 종료
if rewrite_response == 'y':
    # usmtoolkit 경로가 존재하지 않으면 파일을 찾을 수 없음 메시지 표시
    if not usmtoolkit_path.exists():
        input(f" [ 경고 ] UsmToolkit.exe 파일이 존재하지 않습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
        sys.exit()
    else:
        # 현재 디렉터리에서 *.usm 파일 찾기
        current_directory_files = find_usm_files(os.getcwd())

        # 사용자가 지정한 폴더명
        target_folders = ["m"]

        # 각 폴더에 대해 하위 폴더까지 모두 검색하여 usm 파일 찾기
        target_folder_files = []  # target_folder_files 초기화

        # target_folders 목록의 각 폴더에 대해 반복
        for target_folder in target_folders:
            target_folder_path = os.path.join(os.getcwd(), target_folder)  # 각 폴더의 경로를 현재 작업 디렉토리에 추가하여 완전한 경로 생성

            # 해당 경로가 디렉토리인지 확인
            if os.path.isdir(target_folder_path):
                target_folder_files = search_usm_files_in_folder(target_folder_path)  # 디렉토리인 경우, search_usm_files_in_folder 함수를 사용하여 ".usm" 확장자를 가진 파일들을 찾아 리스트에 저장
            else:
                continue  # 디렉토리가 아닌 경우, 건너뜀

        # 모든 *.usm 파일 리스트 구하기
        all_usm_files = current_directory_files + target_folder_files  # 현재 디렉토리와 대상 폴더에서 찾은 ".usm" 확장자를 가진 파일들을 모두 합쳐서 전체 파일 목록을 만듦
        total_files = len(all_usm_files)  # 전체 ".usm" 파일 수 계산

        # 변환
        for idx, usm_file in enumerate(current_directory_files + target_folder_files, start=1):  # 현재 디렉토리 파일과 대상 폴더 파일을 모두 포함하여 모든 ".usm" 파일에 대해 반복
            print(f" [ Source Info ]")
            
            # _Converted 폴더 생성
            output_folder_name = "_Converted"  # 변환된 파일을 저장할 폴더 이름 설정
            output_folder_path = usm_file.parent / output_folder_name  # 변환된 파일을 저장할 폴더 경로 생성

            # 폴더가 존재하지 않으면 폴더를 생성
            if not output_folder_path.exists():
                output_folder_path.mkdir()

            # 변환할 *.mp4 파일 경로 생성
            extract_path = output_folder_path / (usm_file.stem + ".mp4")

            # 이미 변환된 파일이 존재하지 않는 경우에만 변환 작업 실행
            if not extract_path.exists():
                # 변환 명령어 생성
                command = (
                    f'cd "{usmtoolkit_path.parent.absolute()}" '  # usmtoolkit 경로로 이동
                    f'&& "{usmtoolkit_path.name}" convert '  # convert 명령어 실행
                    f'-c "{usm_file.absolute()}" '  # 변환할 원본 파일 지정
                    f'-o "{output_folder_path}"'  # 변환된 파일을 저장할 경로 지정
                )
                
                # 변환 명령어 실행
                os.system(command)

                total_processed += 1 # 처리된 파일 수 증가

                # 백분율 계산
                percent_complete = (total_processed / total_files) * 100
                
                print(f"\n [ Processing Results ]")
                print(f" 작업 진행 상태: {total_processed}/{total_files} ({percent_complete:.4f}%)")
                print(f" 원본 파일 경로: \{os.path.relpath(usm_file.absolute(), os.getcwd())}")
                print(f" 변환된 파일 경로: \{os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")
            else:
                percent_complete = (total_processed / total_files) * 100
                
                print(f" [ Processing Results ]")
                print(f" 작업 진행 상태: {total_processed}/{total_files} ({percent_complete:.4f}%)")
                print(f" 원본 파일 경로: \{os.path.relpath(usm_file.absolute(), os.getcwd())}")
                print(f" 이미 변환 된 파일: \{os.path.relpath(extract_path.absolute(), os.getcwd())}\n\n\n")

        # 작업 모두 끝나면 메시지 출력
        input(f" 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
else:
    # 프로그램 종료
    input(f" 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
