# 필요한 라이브러리 임포트
import os              # 파일 및 디렉토리 조작을 위한 모듈
import re              # 정규 표현식을 사용하기 위한 모듈
import tkinter as tk  # GUI 작성을 위한 모듈
from tkinter import filedialog  # 파일 대화상자를 사용하기 위한 모듈
from tqdm import tqdm  # 진행 바 표시를 위한 라이브러리 임포트



# ASCII Art 및 사용자 안내 문구 출력
print("""
           ___      _                        _____                       __  __      ___      _ ___  _         
          / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
         / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
        /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
    """)
print("""
                 _______                     __            __   _     __    ____                    __ 
                / ___/ /  ___ ________ _____/ /____ ____  / /  (_)__ / /_  / __/_ __ ___  ___  ____/ /_
               / /__/ _ \/ _ `/ __/ _ `/ __/ __/ -_) __/ / /__/ (_-</ __/ / _/ \ \ // _ \/ _ \/ __/ __/
               \___/_//_/\_,_/_/  \_,_/\__/\__/\__/_/   /____/_/___/\__/ /___//_\_\/ .__/\___/_/  \__/ 
                                                                                  /_/
    """)



# 작업 진행 여부 안내
print("\n\n [ 주의 ] 본 도구는 '02. unity3d File Converter.py'를 통해 모든 Resource를 추출 후 작업해야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")
print("\n\n Enter키를 누르면 작업이 시작됩니다.")



def find_files_with_name():
    """
    현재 디렉토리부터 시작하여 모든 하위 디렉토리를 포함해 *.json 확장자를 가진 파일들 중에서 'name' 필드를 찾아 해당 파일과 이름을 튜플로 반환.
    
    Returns:
        found_files (list): 파일 경로와 해당 이름을 포함한 튜플들의 리스트
    """
    
    print("\n\n [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
    print("          모든 파일이 불러와지면 전체 캐릭터 이름을 반환합니다.\n")
    
    found_names = set()   # 중복을 방지하기 위한 이름 집합
    found_files = []      # 파일 경로와 이름을 저장할 리스트


    """
    json_files 검색 설정 방법

    모든 *.json 파일을 검색하고 싶은 경우 (기본값):
    방법 1) [os.path.join(root, file) for root, dirs, files in os.walk(".", topdown=False) for file in files if file.endswith(".json")]
    방법 2) [os.path.join(root, file) for root, dirs, files in os.walk(".", topdown=False) for file in files if file.endswith(".json") and "" in file]

    파일 이름에 특정 문자열(storydata)이 포함 된 *.json파일을 검색하고 싶은 경우:
    [os.path.join(root, file) for root, dirs, files in os.walk(".", topdown=False) for file in files if file.endswith(".json") and "storydata" in file]
    
    """
    json_files = [os.path.join(root, file) for root, dirs, files in os.walk(".", topdown=False) for file in files if file.endswith(".json")]
    # 현재 디렉토리부터 모든 하위 디렉토리까지 검색하여 *.json 파일 목록 가져오기
    with tqdm(total=len(json_files), desc=" *.json 파일을 불러오는 중...") as pbar:  # tqdm을 이용한 진행 바 표시
        for file_path in json_files:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    match = re.search(r'"name":\s*"(.*?)"', line)  # 'name' 필드를 찾는 정규 표현식
                    if match:
                        character_name = match.group(1)
                        if character_name not in found_names:
                            found_names.add(character_name)
                            found_files.append((file_path, character_name))
                        break
            pbar.update(1)  # 진행 바 업데이트
    return found_files



def save_results_to_txt(found_files):
    """
    텍스트 파일로 저장
    
    Args:
        found_files (list): 파일 경로와 해당 이름을 포함한 튜플들의 리스트
    """
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("텍스트 문서", "*.txt")])
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            for file_info in found_files:
                f.write(f"{file_info[1]}\n")
        input("\n\n\n 텍스트 파일이 성공적으로 저장되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
        quit()
        


def main():
    """
    프로그램의 주 실행 함수
    작업이 성공적으로 완료되면 결과를 표시하거나 저장
    """
    
    while True:
        enter_check = input(" >>> ")

        if enter_check == '':
            found_files = find_files_with_name()  # 파일에서 이름을 찾는 함수 호출
            if found_files:
                
                print("\n\n\n [ Character Name List ]")
                for file_info in found_files:
                    print(f"{file_info[1]}")   # 반환된 캐릭터 이름 리스트 표시
                
                print("\n\n\n 결과를 텍스트 파일로 저장하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.)")
                
                while True:
                    save_option = input(" >>> ").strip().lower()
                    if save_option == 'y':
                        save_results_to_txt(found_files)   # 결과를 텍스트 파일로 저장하는 함수 호출
                        break
                    elif save_option == 'n':
                        return False
                    else:
                        print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")
            else:
                print("\n Character Name List를 작성할 수 없습니다.")
        else:
            print("\n\n\n [ 오류 ] 잘못된 입력입니다. Enter 키를 누르십시오.")
            
if __name__ == "__main__":
    main()   # 프로그램 실행
