import os
import UnityPy
import json
import base64
from enum import Enum
from struct import unpack
from PIL import Image

# 변환된 파일의 총 수를 계산하기 위한 변수
total_processed = 0

# UnityPy의 기본 Unity 버전 설정
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

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
    UNKNOWN = 112  # todo: find the actual name

# 현재 디렉토리와 a, ab, bb 폴더에서 Unity3D 파일을 찾는 함수
def find_unity3d_files(root_directories: list[str]):
    unity3d_files = []
    for directory in root_directories:
        if os.path.exists(directory):
            if os.path.isfile(directory) and directory.endswith(".unity3d"):
                unity3d_files.append(directory)
            elif os.path.isdir(directory):
                for dirpath, _, filenames in os.walk(directory):
                    if dirpath == directory:  # 현재 디렉터리에서만 검색
                        for filename in filenames:
                            if filename.endswith(".unity3d"):
                                unity3d_files.append(os.path.join(dirpath, filename))
                    elif os.path.basename(directory) in ["a", "ab", "bb"]:  # a, ab, bb 폴더에서는 모든 하위 디렉터리 검색
                        for filename in filenames:
                            if filename.endswith(".unity3d"):
                                unity3d_files.append(os.path.join(dirpath, filename))
                        break  # a, ab, bb 폴더는 하위 디렉터리 검색 후 탐색 중지
    return unity3d_files

# Unity3D 파일을 처리하는 함수
def process_unity3d_files(unity3d_files: list[str], destination_folder: str):
    for file_path in unity3d_files:
        # Source Info 출력
            print(f"\n\n\n [ Source Info ]")
            print(f" 원본 파일 경로: \{file_path} \n")  # 변수명 수정: file_name -> file_path
            print(f" [ Processing Results ]")

            # 처리된 파일 개수를 전역 변수로 설정
            global total_processed

            try:
                # UnityPy를 사용하여 *.unity3d 파일 로드
                env = UnityPy.load(file_path)

                # 파일명에서 확장자 제거하여 폴더명으로 사용
                folder_name = os.path.splitext(os.path.basename(file_path))[0]  # 수정된 부분
                folder_path = os.path.join(destination_folder, folder_name)
                os.makedirs(folder_path, exist_ok=True)

                # *.unity3d 파일 내 객체들을 반복하여 처리
                for obj in env.objects:
                    # Font 객체인 경우 폰트 데이터를 추출하여 저장
                    if obj.type.name == "Font":
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

            except Exception as e:
                continue

            try:
                # UnityPy를 사용하여 *.unity3d 파일 다시 로드
                env = UnityPy.load(file_path)

                # 폴더 생성 (이미 존재할 경우 무시)
                os.makedirs(folder_path, exist_ok=True)

                # *.unity3d 파일 내 객체들을 반복하여 처리
                for path, obj in env.container.items():
                    # Texture2D 또는 Sprite 객체인 경우 이미지를 추출하여 저장
                    if obj.type.name in ["Texture2D", "Sprite"]:
                        data = obj.read()
                        dest = os.path.join(folder_path, path)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        dest, _ = os.path.splitext(dest)
                        dest = dest + ".png"
                        data.image.save(dest)
                        total_processed += 1
                        print(f" 추출된 파일 경로: \{dest}")

                    # TextAsset 객체인 경우 텍스트 데이터를 추출하여 저장
                    elif obj.type.name == "TextAsset":
                        data = obj.read()
                        dest = os.path.join(folder_path, data.name)
                        if "storydata" in data.name:
                            dest_json = os.path.join(folder_path, data.name + ".json")
                            deserialize_story(data.script, dest_json)
                        else:
                            with open(dest, "wb") as f:
                                f.write(bytes(data.script))
                                total_processed += 1
                                print(f" 추출된 파일 경로: \{dest}")

                    # AudioClip 객체인 경우 오디오 클립을 추출하여 저장
                    elif obj.type.name == "AudioClip":
                        clip = obj.read()
                        for name, data in clip.samples.items():
                            dest = os.path.join(folder_path, name + ".wav")
                            with open(dest, "wb") as f:
                                f.write(data)
                                total_processed += 1
                                print(f" 추출된 파일 경로: \{dest}")

                    # Mesh 객체인 경우 메시 데이터를 추출하여 저장
                    elif obj.type.name == "Mesh":
                        mesh = obj.read()
                        dest = os.path.join(folder_path, f"{mesh.name}.obj")
                        with open(dest, "wt", newline="") as f:
                            f.write(str(mesh.export()))
                            total_processed += 1
                            print(f" 추출된 파일 경로: \{dest}")

                    # Texture2DArray 객체인 경우 텍스처 배열 이미지를 추출하여 저장
                    elif obj.type.name == "Texture2DArray":
                        data = obj.read()
                        for i, image in enumerate(data.images):
                            dest = os.path.join(folder_path, f"{data.name}_{i}.png")
                            image.save(dest)
                            total_processed += 1
                            print(f" 추출된 파일 경로: \{dest}")

            except Exception as e:
                print(f" 오류 발생: 추출할 수 없는 리소스가 발견되었습니다. 해당 리소스를 무시하고 다음 작업을 진행합니다")
                print(f" 오류 정보: {e}.")
                continue





# 사용자에게 작업을 프롬프트하는 함수
def prompt_user():
    print("\n\n [ 안내 ] 이미 변환 된 파일이 있을 경우 해당 파일을 덮어쓰기 처리하여 새로 작업 합니다.")
    print()
    print(" [ 주의 ] 작업 진행 중 콘솔 창 내부를 클릭하면 진행이 멈출 수 있습니다.")
    print("          ( 임시 해결 방법: 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭 )\n")

    print(" 작업을 진행하시겠습니까? (Y/N, 대소문자 구분 없음.)")
    while True:
        user_input = input(" >>> ").strip().lower()
        if user_input == 'y':
            return True
        elif user_input == 'n':
            return False
        else:
            print("\n\n\n [ 오류 ] 잘못된 입력입니다. [Y] 또는 [N] 을 입력하십시오.")

# 스크립트 데이터 역직렬화
def deserialize_command(data) -> tuple[CommandId, list[str]]:
    # Function implementation...
    index = data[0]
    args = []
    if len(data) > 1:
        args = data[1:]
    array = []
    for arg in args:
        array2 = []
        for byte in arg:
            if byte > 127:
                array2.append(255 - byte)
            else:
                array2.append(byte)
        str_ = base64.b64decode(bytearray(array2))
        array.append(str_.decode())
    return (CommandId(index), array)

# 스토리 데이터 원시 바이트열 역직렬화
def deserialize_story_raw(bytes_: bytes) -> list[tuple[CommandId, list[str]]]:
    commands = []
    fs = 0
    raw_commands = []
    i = 2
    while i < len(bytes_):
        args: list[bytes | int] = []
        index = int(unpack(">H", bytes_[fs : fs + 2])[0])
        fs += 2
        args.append(index)
        num = i
        while True:
            length = int(unpack(">l", bytes_[fs : fs + 4])[0])
            fs += 4
            if length == 0:
                break
            array = bytes_[fs : fs + length]
            fs += length
            args.append(array)
            num += 4 + length
        i = num + 4
        raw_commands.append(args)
        i += 2
    for raw_command in raw_commands:
        if len(raw_command) > 1:
            commands.append(deserialize_command(raw_command))
    return commands

# 스토리 데이터 역직렬화 후 *.json 파일로 저장
def deserialize_story(bytes_: bytes, dest: str) -> None:
    global total_processed
    commands = deserialize_story_raw(bytes_)
    story: dict[int, dict] = {}
    num = 0
    story[num] = {}
    block: dict[str, str | tuple | dict] = story[num]
    for command_id, args in commands:
        match command_id:
            case CommandId.PRINT:
                cmd = block.setdefault(command_id.name.lower(), {})
                cmd.setdefault("name", args[0])
                cmd["text"] = (cmd.get("text") or "") + clean_text(args[1])
            case CommandId.CHOICE:
                block.setdefault(command_id.name.lower(), [])
                block[command_id.name.lower()].append(
                    {
                        "text": args[0],
                        "tag": args[1],
                    }
                )
            case CommandId.BUSTUP:
                num += 1
                block = story.setdefault(num, {})
            case CommandId.TAG:
                story.setdefault(num + 1, {})
                story[num + 1][command_id.name.lower()] = args[0]
            case CommandId.TITLE | CommandId.SITUATION | CommandId.OUTLINE | CommandId.VO | CommandId.GOTO:
                if len(args) == 1:
                    args = args[0]
                block[command_id.name.lower()] = args
    
    # JSON 파일로 스토리 데이터 작성
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(story, f, indent=4, ensure_ascii=False)
        total_processed += 1
        print(f" 추출된 파일 경로: \{dest}")

# 텍스트 정리
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
        root_directories = ["a", "b", os.getcwd()]  # 현재 디렉터리와 a, ab, bb 폴더에서 Unity3D 파일 검색
        unity3d_files = find_unity3d_files(root_directories)
        destination_folder = "_Converted"
        process_unity3d_files(unity3d_files, destination_folder)
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")
    else:
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")

if __name__ == "__main__":
    main()
