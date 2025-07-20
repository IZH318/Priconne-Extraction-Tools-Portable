import os
import json
import re
import tkinter as tk
from tkinter import filedialog

def find_and_process_files(root_folder, output_filename):
    """
    지정된 폴더와 하위 폴더에서 특정 패턴의 JSON 파일을 찾아,
    내부의 숫자 키 구조를 유지하며 카테고리 목록을 추출하고 결과를 저장합니다.
    """
    # storydata_로 시작하고 7자리 숫자로 끝나며 .json 확장자를 가진 파일을 찾기 위한 정규식
    file_pattern = re.compile(r'^storydata_\d{7}\.json$')
    
    # 최종 결과를 파일별로 저장할 딕셔너리
    final_results = {}

    print(f"\n'{root_folder}' 폴더 및 하위 폴더에서 파일 검색을 시작합니다...")

    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if file_pattern.match(filename):
                full_path = os.path.join(dirpath, filename)
                print(f"  -> 처리 중: {full_path}")
                
                categories_by_numeric_key = {}
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    for key, value in data.items():
                        if key.isdigit() and isinstance(value, dict):
                            categories_by_numeric_key[key] = list(value.keys())
                
                except json.JSONDecodeError:
                    print(f"  [오류] '{filename}' 파일이 올바른 JSON 형식이 아닙니다. 건너뜁니다.")
                except Exception as e:
                    print(f"  [오류] '{filename}' 파일 처리 중 예외가 발생했습니다: {e}")
                
                if categories_by_numeric_key:
                    final_results[filename] = categories_by_numeric_key

    if not final_results:
        print("\n규칙에 맞는 파일을 찾지 못했습니다.")
        return

    # 1. 결과 저장
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(f"\n✨ 완료! 결과가 '{output_filename}' 파일에 성공적으로 저장되었습니다.")
    except Exception as e:
        print(f"\n[오류] 결과를 파일에 저장하는 중 오류가 발생했습니다: {e}")
        return

    # 2. 저장된 파일이 유효한 JSON인지 검증
    try:
        with open(output_filename, 'r', encoding='utf-8') as f:
            json.load(f)
        print(f"[검증 완료] 생성된 '{output_filename}' 파일은 유효한 JSON 형식입니다.")
    except Exception as e:
        print(f"\n[검증 오류] 생성된 파일에 문제가 있습니다: {e}")


def main():
    """
    사용자로부터 입력을 받아 스크립트를 실행하는 메인 함수
    """
    try:
        root = tk.Tk()
        root.withdraw()

        print("카테고리를 수집할 JSON 파일이 들어있는 폴더를 선택해주세요...")
        target_folder = filedialog.askdirectory(title="검색할 폴더를 선택하세요")

        if not target_folder:
            print("\n폴더를 선택하지 않았습니다. 프로그램을 종료합니다.")
            return
            
        output_file = input("결과를 저장할 파일 이름을 입력하세요 (예: result.json): ")
        if not output_file.lower().endswith('.json'):
            output_file += '.json'
            
        find_and_process_files(target_folder, output_file)

    except Exception as e:
        print(f"\n프로그램 실행 중 예상치 못한 오류가 발생했습니다: {e}")
    finally:
        # 3. 프로그램이 바로 종료되지 않도록 대기
        input("\n모든 작업이 완료되었습니다. Enter 키를 눌러 프로그램을 종료하세요...")


if __name__ == "__main__":
    main()