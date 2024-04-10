# 필요한 라이브러리 임포트
import os
import re
import tkinter as tk
from tkinter import filedialog



# 프로그램 시작 시 화면에 출력되는 ASCII Art
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



# 작업 진행여부 확인 안내 문구
print("\n\n [ 주의 ] 본 도구는 'storydata2_assetmanifest' 에서 모든 Resource를 추출 후 작업해야 합니다.\n")

print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화)하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter키 누르기\n")

print("\n\n Enter키를 누르면 작업이 시작됩니다.")

def find_string_in_json_files(search_query):
    found_files = []
    for root, dirs, files in os.walk(".", topdown=False):
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        if re.search(fr'"name": ".*{search_query}.*"', line):
                            # Check if the line number is greater than 2
                            if i > 2:
                                vo_data = lines[i-2].strip()
                                vo_data = vo_data[7:-2]  # Extracting vo data
                            else:
                                vo_data = " 이전 라인이 없습니다."
                            # Check if the current line is not the last line
                            if i < len(lines) - 1:
                                character_dialogue = lines[i+1].strip()
                                character_dialogue = character_dialogue[9:-1]  # Extracting character dialogue
                            else:
                                character_dialogue = " 다음 라인이 없습니다."
                            character_name = line.strip()
                            character_name = character_name[9:-2]  # Extracting character name
                            found_files.append((file_path, character_name, i+1, vo_data, character_dialogue))
                            break
    return found_files



def save_results_to_txt(found_files):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            for file_info in found_files:
                f.write(f" [File Path] {file_info[0]}\n")
                f.write(f" [Searched Lines] {file_info[2]}\n")
                f.write(f" [Character Name] {file_info[1]}\n")
                f.write(f" [Vo Data] {file_info[3]}\n")
                f.write(f" [Character Dialogue] {file_info[4]}\n\n")
        print()
        print(" 검색 결과가 성공적으로 저장되었습니다. Enter키를 누르면 창이 종료됩니다.")
        print()
        input("")



def main():
    search_query = input(" >>> ")
    found_files = find_string_in_json_files(search_query)
    if found_files:
        print()
        print(f" '{search_query}'를 포함하는 *.json 파일의 정보는 다음과 같습니다:")
        print()
        for file_path, character_name, line_number, vo_data, character_dialogue in found_files:
            print(f" [File Path] {file_path}\n[Searched Lines] {line_number}\n [Character Name] {character_name}\n [Vo Data] {vo_data}\n [Character Dialogue] {character_dialogue}\n")
        
        # 저장 여부 확인 및 저장
        print()
        print()
        print()
        print(" 검색 결과를 텍스트 파일로 저장하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter키를 누르십시오.)")
        save_option = input(" >>> ").strip().lower()
        if save_option == "y":
            save_results_to_txt(found_files)
    else:
        print()
        print(f" '{search_query}'를 포함하는 문자열 또는 *.json 파일을 찾을 수 없습니다.")



if __name__ == "__main__":
    main()
