# 필요한 라이브러리 임포트
import os  # 파일 및 디렉토리 관리
import sys  # 파이썬 시스템과 관련된 기능을 제공하는 sys 모듈
import UnityPy  # Unity3D 파일 처리
import json  # JSON 파일 작성
import base64  # 데이터 디코딩
import re  # 정규 표현식 사용
from enum import Enum  # 열거형 사용
from struct import unpack, error as struct_error  # 데이터 언패킹
from PIL import Image  # 이미지 처리
from pathlib import Path # 경로 관련 처리를 위한 pathlib 모듈



# 변환된 파일의 총 수를 계산하기 위한 변수
total_processed = 0



# UnityPy의 기본 Unity 버전 설정
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"



# 프로그램 시작 시 화면에 출력되는 ASCII Art
print("""
           ___      _                        _____                       __  __      ___      _ ___  _
          / _ \____(_)__  _______ ___ ___   / ___/__  ___  ___  ___ ____/ /_/ /     / _ \___ (_) _ \(_)  _____
         / ___/ __/ / _ \/ __/ -_|_-<(_-<  / /__/ _ \/ _ \/ _ \/ -_) __/ __/_/     / , _/ -_) / // / / |/ / -_)
        /_/  /_/ /_/_//_/\__/\__/___/___/  \___/\___/_//_/_//_/\__/\__/\__(_)     /_/|_|\__(_)____/_/|___/\__/
    """)
print("""
                            _ __       ____    __  _____ __      _____                      __
                 __ _____  (_) /___ __|_  /___/ / / __(_) /__   / ___/__  ___ _  _____ ____/ /____ ____
                / // / _ \/ / __/ // //_ </ _  / / _// / / -_) / /__/ _ \/ _ \ |/ / -_) __/ __/ -_) __/
                \_,_/_//_/_/\__/\_, /____/\_,_/ /_/ /_/_/\__/  \___/\___/_//_/___/\__/_/  \__/\__/_/
                               /___/
    """)



# 작업 진행여부 확인 안내 문구
print("\n\n [ 안내 ] 이미 변환 된 파일이 있을 경우 해당 파일을 덮어쓰기 처리하여 새로 작업합니다.")
print()
print("\n\n [ 주의 ] 본 도구는 '01. Manifest File Renamer.py'를 통해 모든 파일의 이름을 변경한 후 작업해야 합니다.\n")
print("          작업 진행 중 콘솔 창 내부를 클릭(*선택 모드 활성화) 하면 진행이 멈출 수 있습니다.\n")
print("          (임시 해결 방법) 01. 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭")
print("                           02. 콘솔 내부 클릭 후 Enter 키 누르기\n")

print("\n\n 작업을 진행하시겠습니까? ([Y]/[N] 중 대소문자 구분 없이 입력 후 Enter키를 누르십시오.)")



# 명령 ID를 나타내는 열거형 정의
class CommandId(Enum):
    NONE = -1
    TITLE = 0
    OUTLINE = 1
    VISIBLE = 2
    FACE = 3
    FOCUS = 4
    BACKGROUND = 5
    PRINT = 6
    TAG = 7
    GOTO = 8
    BGM = 9
    TOUCH = 10
    CHOICE = 11
    VO = 12
    WAIT = 13
    IN_L = 14
    IN_R = 15
    OUT_L = 16
    OUT_R = 17
    FADEIN = 18
    FADEOUT = 19
    IN_FLOAT = 20
    OUT_FLOAT = 21
    JUMP = 22
    SHAKE = 23
    POP = 24
    NOD = 25
    SE = 26
    BLACK_OUT = 27
    BLACK_IN = 28
    WHITE_OUT = 29
    WHITE_IN = 30
    TRANSITION = 31
    SITUATION = 32
    COLOR_FADEIN = 33
    FLASH = 34
    SHAKE_TEXT = 35
    TEXT_SIZE = 36
    SHAKE_SCREEN = 37
    DOUBLE = 38
    SCALE = 39
    TITLE_TELOP = 40
    WINDOW_VISIBLE = 41
    LOG = 42
    NOVOICE = 43
    CHANGE = 44
    FADEOUT_ALL = 45
    MOVIE = 46
    MOVIE_STAY = 47
    BATTLE = 48
    STILL = 49
    BUSTUP = 50
    ENV = 51
    TUTORIAL_REWARD = 52
    NAME_EDIT = 53
    EFFECT = 54
    EFFECT_DELETE = 55
    EYE_OPEN = 56
    MOUTH_OPEN = 57
    AUTO_END = 58
    EMOTION = 59
    EMOTION_END = 60
    ENV_STOP = 61
    BGM_PAUSE = 62
    BGM_RESUME = 63
    BGM_VOLUME_CHANGE = 64
    ENV_RESUME = 65
    ENV_VOLUME = 66
    SE_PAUSE = 67
    CHARA_FULL = 68
    SWAY = 69
    BACKGROUND_COLOR = 70
    PAN = 71
    STILL_UNIT = 72
    SLIDE_CHARA = 73
    SHAKE_SCREEN_ONCE = 74
    TRANSITION_RESUME = 75
    SHAKE_LOOP = 76
    SHAKE_DELETE = 77
    UNFACE = 78
    WAIT_TOKEN = 79
    EFFECT_ENV = 80
    BRIGHT_CHANGE = 81
    CHARA_SHADOW = 82
    UI_VISIBLE = 83
    FADEIN_ALL = 84
    CHANGE_WINDOW = 85
    BG_PAN = 86
    STILL_MOVE = 87
    STILL_NORMALIZE = 88
    VOICE_EFFECT = 89
    TRIAL_END = 90
    SE_EFFECT = 91
    CHARACTER_UP_DOWN = 92
    BG_CAMERA_ZOOM = 93
    BACKGROUND_SPLIT = 94
    CAMERA_ZOOM = 95
    SPLIT_SLIDE = 96
    BGM_TRANSITION = 97
    SHAKE_ANIME = 98
    INSERT_STORY = 99
    PLACE = 100
    IGNORE_BGM = 101
    MULTI_LIPSYNC = 102
    JINGLE = 103
    TOUCH_TO_START = 104
    EVENT_ADV_MOVE_HORIZONTAL = 105
    BG_PAN_X = 106
    BACKGROUND_BLUR = 107
    SEASONAL_REWARD = 108
    MINI_GAME = 109
    MAX = 110
    UNKNOWN = 112


# 현재 디렉토리와 주어진 폴더 목록에서 Unity3D 파일을 찾는 함수
def find_unity3d_files(root_directories: list[str]):
    unity3d_files = []
    for directory in root_directories:
        if os.path.exists(directory):
            if os.path.isdir(directory):
                if os.path.basename(directory) in ["a"]:
                    for root, _, filenames in os.walk(directory):
                        for filename in filenames:
                            if filename.endswith(".unity3d"):
                                unity3d_files.append(os.path.relpath(os.path.join(root, filename), start=os.getcwd()))
                elif directory == os.getcwd():
                    for filename in os.listdir(directory):
                        if filename.endswith(".unity3d"):
                            unity3d_files.append(os.path.relpath(os.path.join(directory, filename), start=os.getcwd()))
            elif os.path.isfile(directory) and directory.endswith(".unity3d"):
                unity3d_files.append(os.path.relpath(directory, start=os.getcwd()))
    return unity3d_files


# Unity3D 파일을 처리하는 메인 함수
def process_unity3d_files(unity3d_files: list[str], destination_folder: str):
    global total_processed
    for index, file_path in enumerate(unity3d_files, start=1):
        percent_complete = (index / len(unity3d_files)) * 100
        print(f"\n\n\n [ Source Info ]")
        print(f" 작업 진행 상태: {index}/{len(unity3d_files)} ({percent_complete:.4f}%)")
        print(f" 원본 파일 경로: \{file_path} \n")
        print(f" [ Processing Results ]")

        try:
            env = UnityPy.load(file_path)
            folder_name = os.path.splitext(os.path.basename(file_path))[0]
            converted_folder_path = os.path.join(os.path.dirname(file_path), "_Converted")
            os.makedirs(converted_folder_path, exist_ok=True)
            folder_path = os.path.join(converted_folder_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            # <<<--- [수정] Mesh 파일명을 위한 카운터 변수 ---
            mesh_counter = 0

            # 모든 객체 순회 (Font, AudioClip, Mesh 등 이름 없는 객체 포함)
            for obj in env.objects:
                if obj.type.name == "Font":
                    # (이하 Font 처리 로직은 동일)
                    font = obj.read()
                    if font.m_FontData:
                        extension = ".ttf"
                        if font.m_FontData[:4] == b"OTTO":
                            extension = ".otf"
                        dest = os.path.join(folder_path, font.name + extension)
                        with open(dest, "wb") as f:
                            f.write(font.m_FontData)
                        total_processed += 1
                        print(f" 추출된 파일 경로: \{dest}")

                elif obj.type.name == "AudioClip":
                    # (이하 AudioClip 처리 로직은 동일)
                    clip = obj.read()
                    for name, data in clip.samples.items():
                        dest = os.path.join(folder_path, name + ".wav")
                        with open(dest, "wb") as f:
                            f.write(data)
                        total_processed += 1
                        print(f" 추출된 파일 경로: \{dest}")

                # <<<--- [수정] Mesh 처리 로직 ---
                elif obj.type.name == "Mesh":
                    try:
                        mesh = obj.read()
                        # 파일 이름을 원본 .unity3d 파일명과 카운터로 생성
                        obj_name = f"{folder_name}_{mesh_counter}.obj"
                        dest = os.path.join(folder_path, obj_name)
                        with open(dest, "wt", newline="") as f:
                            f.write(mesh.export())
                        total_processed += 1
                        mesh_counter += 1 # 다음 Mesh를 위해 카운터 증가
                        print(f" 추출된 파일 경로: \{dest}")
                    except Exception as e:
                        print(f" 오류 발생 (Mesh): 메쉬 데이터를 처리할 수 없습니다. {e}")
                        continue
                # (이하 다른 객체 처리 로직은 동일)
                elif obj.type.name == "Texture2DArray":
                    data = obj.read()
                    for i, image in enumerate(data.images):
                        dest = os.path.join(folder_path, f"{data.name}_{i}.png")
                        image.save(dest)
                        total_processed += 1
                        print(f" 추출된 파일 경로: \{dest}")

                elif obj.type.name in ["MonoBehaviour", "MonoScript", "GameObject", "Transform", "AssetBundle"]:
                    try:
                        if hasattr(obj, "serialized_type") and getattr(obj.serialized_type, "nodes", None):
                            tree = obj.read_typetree()
                            obj_name = tree.get("m_Name", "") or os.path.splitext(os.path.basename(file_path))[0]
                            json_dest = os.path.join(folder_path, f"{obj_name}.json")
                            with open(json_dest, "wt", encoding="utf8") as f:
                                json.dump(tree, f, ensure_ascii=False, indent=4)
                            total_processed += 1
                            print(f" 추출된 파일 경로: \{json_dest}")
                        elif hasattr(obj, "read"):
                            data = obj.read()
                            obj_name = getattr(data, 'name', '') or getattr(data, 'm_Name', '') or os.path.splitext(os.path.basename(file_path))[0]

                            data_dict = {}
                            if hasattr(data, 'recordList'):
                                record_list = []
                                for record in data.recordList:
                                    record_dict = {field: getattr(record, field) for field in ['voice_id', 'time', 'is_enable', 'is_new_method'] if hasattr(record, field)}
                                    record_list.append(record_dict)
                                data_dict['recordList'] = record_list

                            json_dest = os.path.join(folder_path, f"{obj_name}.json")
                            with open(json_dest, "wt", encoding="utf8") as f:
                                json.dump(data_dict, f, ensure_ascii=False, indent=4)
                            total_processed += 1
                            print(f" 추출된 파일 경로: \{json_dest}")
                    except Exception as e:
                        print(f" 오류 발생 ({obj.type.name}): 리소스를 처리할 수 없습니다. {e}")
                        continue

            # (이하 env.container 루프 로직은 동일)
            for path, obj in env.container.items():
                if obj.type.name in ["Texture2D", "Sprite"]:
                    data = obj.read()
                    dest_path = Path(folder_path) / Path(path).parent
                    os.makedirs(dest_path, exist_ok=True)
                    dest = (dest_path / Path(path).stem).with_suffix(".png")
                    data.image.save(dest)
                    total_processed += 1
                    print(f" 추출된 파일 경로: \{dest}")

                elif obj.type.name == "TextAsset":
                    try:
                        data = obj.read()
                        asset_name = data.name if hasattr(data, 'name') and data.name else os.path.basename(path)
                        script_bytes = bytes(data.script) if hasattr(data, 'script') else b""

                        if not script_bytes:
                            print(f" 경고: {asset_name}의 스크립트 데이터를 찾을 수 없습니다.")
                            continue

                        if "storydata" in asset_name.lower() and asset_name.lower().endswith(".bytes"):
                            original_dest = Path(folder_path) / asset_name
                            with open(original_dest, "wb") as f:
                                f.write(script_bytes)
                            total_processed += 1
                            print(f" 원본 추출된 파일 경로: \{original_dest}")

                            json_dest = original_dest.with_suffix(".json")
                            deserialize_story(script_bytes, str(json_dest))
                            print(f" JSON 변환된 파일 경로: \{json_dest}")
                            continue
                        else:
                            original_dest = os.path.join(folder_path, asset_name)
                            with open(original_dest, "wb") as f:
                                f.write(script_bytes)
                            total_processed += 1
                            print(f" 추출된 파일 경로: \{original_dest}")

                    except Exception as e:
                        print(f" 오류 발생 (TextAsset): 리소스를 처리할 수 없습니다. {e}")
                        continue

        except Exception as e:
            print(f" 오류 발생 (File Load): 파일을 처리할 수 없습니다. 다음 파일로 넘어갑니다.")
            print(f" 오류 메시지: {e}")
            continue

# 사용자에게 작업을 프롬프트하는 함수
def prompt_user():
    while True:
        user_input = input(" >>> ").strip().lower()
        if user_input == 'y':
            return True
        elif user_input == 'n':
            return False
        else:
            print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")

# 스크립트 데이터 역직렬화 헬퍼 함수
def deserialize_command(data) -> tuple[CommandId, list[str]]:
    index = data[0]
    args = data[1:] if len(data) > 1 else []
    array = []
    for arg in args:
        array2 = bytearray()
        for byte in arg:
            array2.append(255 - byte if byte > 127 else byte)
        try:
            array.append(base64.b64decode(array2).decode('utf-8'))
        except UnicodeDecodeError:
            array.append(base64.b64decode(array2).decode('shift_jis', errors='ignore'))
    try:
        command_id = CommandId(index)
    except ValueError:
        command_id = CommandId.UNKNOWN
    return command_id, array

# 스토리 데이터 원시 바이트열 역직렬화
def deserialize_story_raw(bytes_: bytes) -> list[tuple[CommandId, list[str]]]:
    commands = []
    fs = 0
    i = 2
    while i < len(bytes_):
        try:
            index = unpack(">H", bytes_[fs : fs + 2])[0]
            fs += 2
            args_raw = [index]
            num = i
            while True:
                length = unpack(">l", bytes_[fs : fs + 4])[0]
                fs += 4
                if length == 0:
                    break
                args_raw.append(bytes_[fs : fs + length])
                fs += length
                num += 4 + length
            i = num + 4
            if len(args_raw) > 1:
                commands.append(deserialize_command(args_raw))
            i += 2
        except struct_error:
            break
        except Exception as e:
            print(f"deserialize_story_raw에서 오류 발생: {e}")
            break
    return commands

# 스토리 데이터 역직렬화 후 *.json 파일로 저장하는 함수
def deserialize_story(bytes_: bytes, dest: str) -> None:
    global total_processed
    
    commands = deserialize_story_raw(bytes_)
    story: dict[int, dict] = {}
    num = 0
    story[num] = {}
    block: dict[str, str | tuple | dict] = story[num]

    for command_id, args in commands:
        cmd_name = command_id.name.lower()
        match command_id:
            case CommandId.PRINT:
                cmd = block.setdefault(cmd_name, {})
                cmd.setdefault("name", args[0])
                cmd["text"] = (cmd.get("text") or "") + clean_text(args[1])
            case CommandId.CHOICE:
                block.setdefault(cmd_name, []).append({"text": args[0], "tag": args[1]})
            case CommandId.BUSTUP:
                num += 1
                block = story.setdefault(num, {})
            case CommandId.TAG:
                story.setdefault(num + 1, {})[cmd_name] = args[0]
            case CommandId.TITLE | CommandId.SITUATION | CommandId.OUTLINE | CommandId.VO | CommandId.GOTO:
                block[cmd_name] = args[0] if len(args) == 1 else args
            case _:
                if len(args) == 1:
                    block[cmd_name] = args[0]
                elif len(args) > 1:
                    block[cmd_name] = args
    
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(story, f, indent=4, ensure_ascii=False)
    total_processed += 1

# 텍스트 정리하여 특수 문자 및 문자열 치환을 수행하는 함수
def clean_text(text: str) -> str:
    replace_pairs = (
        ("\\n", "\n"),
        ("{0}", "{player_name}"),
        ('\\"', '"'),
    )
    for pair in replace_pairs:
        text = text.replace(*pair)
    return text

# 메인 함수
def main():
    if prompt_user():
        root_directories = ["a", os.getcwd()]
        unity3d_files = find_unity3d_files(root_directories)
        destination_folder = "_Converted"
        process_unity3d_files(unity3d_files, destination_folder)
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 눌러 창을 종료하십시오.\n >>> ")
        sys.exit()
    else:
        print(f"\n\n\n 작업이 취소되었습니다. Enter 키를 눌러 창을 종료하십시오.")
        input(" >>> ")
        sys.exit()

if __name__ == "__main__":
    main()
