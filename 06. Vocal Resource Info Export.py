# 필요한 라이브러리 임포트
import os  # 파일 및 디렉토리 조작을 위한 라이브러리
import re  # 정규 표현식 사용을 위한 라이브러리
import tkinter as tk  # GUI 생성을 위한 라이브러리
from tkinter import filedialog  # 파일 대화상자 기능을 사용하기 위한 라이브러리 임포트
from tqdm import tqdm  # 진행 바 표시를 위한 라이브러리 임포트



print("""
           ___      _                        _____                       __  __      ___      _ ___  _         
          / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____ 
         / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
        /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
    """)
print("""
           _   __         ___                                  ____     ___       ____                    __ 
          | | / /__      / _ \___ ___ ___  __ _____________   /  _/__  / _/__    / __/_ __ ___  ___  ____/ /_
          | |/ / _ \_   / , _/ -_|_-</ _ \/ // / __/ __/ -_) _/ // _ \/ _/ _ \  / _/ \ \ // _ \/ _ \/ __/ __/
          |___/\___(_) /_/|_|\__/___/\___/\_,_/_/  \__/\__/ /___/_//_/_/ \___/ /___//_\_\/ .__/\___/_/  \__/ 
                                                                                        /_/
    """)



print(" [ 안내 ] 찾고자 하는 캐릭터 명의 일부분 또는 전체를 입력하십시오.")
print("          ( * 아무 값도 입력하지 않을 시 모든 내용을 반환합니다.)\n")
print(" [ 주의 ] 본 도구는 '02. unity3d File Converter.py'에서 모든 Resource를 추출 후 작업해야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter키 누르기\n")
print("\n\n 입력 후 Enter키를 누르면 작업이 시작됩니다.")



def find_string_in_json_files(search_query):
    """
    주어진 검색어를 포함하는 *.JSON 파일을 찾고, 해당 파일 내의 정보를 추출하는 함수
    :param search_query: 검색할 문자열
    :return: 검색어를 포함하는 *.JSON 파일 내의 정보 리스트
    """

    print("\n\n\n [ 안내 ] 작업할 파일의 개수가 많거나 저장 장치의 읽기 쓰기 속도가 느릴 경우 시간이 오래 걸릴 수 있습니다.")
    print("          모든 파일이 불러와지면 조회된 내용을 반환합니다.\n")
    
    found_files = []  # 검색된 파일 정보를 저장할 리스트
    total_files = 0  # 전체 파일 수를 저장할 변수
    for root, dirs, files in os.walk(".", topdown=False):  # 현재 디렉토리부터 재귀적으로 파일 검색
        for file in files:
            if file.endswith(".json"):  # JSON 파일인 경우에만 처리
                total_files += 1  # JSON 파일의 수 증가
    pbar = tqdm(total=total_files, desc=" *.json 파일을 불러오는 중...")  # tqdm을 사용하여 진행 바 생성
    for root, dirs, files in os.walk(".", topdown=False):  # 현재 디렉토리부터 재귀적으로 파일 검색
        for file in files:
            if file.endswith(".json"):  # JSON 파일인 경우에만 처리
                pbar.update(1)  # tqdm 진행 바 업데이트
                file_path = os.path.join(root, file)  # 파일 경로
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()  # 파일의 모든 라인을 읽어옴
                    for i, line in enumerate(lines):
                        if re.search(fr'"name": ".*{search_query}.*"', line):  # 검색어를 포함하는 라인을 찾음
                            # 이전 라인에 있는 VO 데이터 추출
                            if i > 2:
                                vo_data = lines[i-2].strip()[7:-2]
                            else:
                                vo_data = " 이전 라인이 없습니다."
                            # 다음 라인에 있는 캐릭터 대화 추출
                            if i < len(lines) - 1:
                                character_dialogue = lines[i+1].strip()[9:-1]
                            else:
                                character_dialogue = " 다음 라인이 없습니다."
                            character_name = line.strip()[9:-2]  # 캐릭터 이름 추출
                            found_files.append((file_path, character_name, i+1, vo_data, character_dialogue))  # 결과 추가
                            break
    pbar.close()  # tqdm 진행 바 종료
    return found_files



def save_results_to_txt(found_files):
    """
    검색 결과를 텍스트 파일로 저장하는 함수
    :param found_files: 검색 결과 리스트
    """
    root = tk.Tk()  # tkinter의 기본 루트 윈도우 생성
    root.withdraw()  # 윈도우를 숨김
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("텍스트 문서", "*.txt")])  # 저장 대화상자 표시
    if file_path:  # 파일 경로가 선택된 경우에만 처리
        with open(file_path, "w", encoding="utf-8") as f:
            for file_info in found_files:
                f.write(f" [File Path] {file_info[0]}\n")
                f.write(f" [Searched Lines] {file_info[2]}\n")
                f.write(f" [Character Name] {file_info[1]}\n")
                f.write(f" [Vo Data] {file_info[3]}\n")
                f.write(f" [Character Dialogue] {file_info[4]}\n\n")
        input("\n\n\n 검색 결과가 성공적으로 저장되었습니다. Enter 키를 누르면 창이 종료됩니다.\n >>> ")
        sys.exit()



def main():
    """
    프로그램의 메인 함수
    """
    search_query = input(" >>> ")  # 사용자로부터 검색어 입력 받기
    found_files = find_string_in_json_files(search_query)  # 검색 실행
    if found_files:  # 검색 결과가 있는 경우
        print()
        print(f"\n\n '{search_query}'를 포함하는 *.json 파일의 정보는 다음과 같습니다:\n")
        for file_path, character_name, line_number, vo_data, character_dialogue in found_files:
            print(f" [File Path] {file_path}\n [Searched Lines] {line_number}\n [Character Name] {character_name}\n [Vo Data] {vo_data}\n [Character Dialogue] {character_dialogue}\n")
        
        # 결과를 텍스트 파일로 저장할지 여부 묻기
        print("\n\n 결과를 텍스트 파일로 저장하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter 키를 누르십시오.)")

        while True:
            save_option = input(" >>> ").strip().lower()
            if save_option == "y":  # 저장하기로 선택한 경우
                save_results_to_txt(found_files)  # 결과 저장
            elif save_option == "n":
                return False
            else:
                print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")
                
    else:  # 검색 결과가 없는 경우
        input("\n\n\n *.json 파일에서 '{search_query}'이(가) 포함된 문자열을 찾을 수 없습니다. Enter 키를 누르면 창이 종료됩니다.\n >>> ")

if __name__ == "__main__":
    main()  # 메인 함수 실행
