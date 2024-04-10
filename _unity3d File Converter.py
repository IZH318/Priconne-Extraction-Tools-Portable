# 필요한 라이브러리 임포트
import os  # 파일 및 디렉토리 관리
import UnityPy  # Unity3D 파일 처리
import json  # JSON 파일 작성
import base64  # 데이터 디코딩
from enum import Enum  # 열거형 사용
from struct import unpack  # 데이터 언패킹
from PIL import Image  # 이미지 처리

# 변환된 파일의 총 수를 계산하기 위한 변수
total_processed = 0

# UnityPy의 기본 Unity 버전 설정
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# 시작 화면 출력
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

# 현재 디렉토리와 주어진 폴더 목록에서 Unity3D 파일을 찾는 함수
def find_unity3d_files(root_directories: list[str]):
    """
    Args:
        root_directories (list[str]): Unity3D 파일을 찾을 디렉토리 목록

    Returns:
        list[str]: 발견된 Unity3D 파일 경로의 리스트
    """
    # 발견된 Unity3D 파일 경로를 저장할 리스트
    unity3d_files = []

    # 각 디렉토리에 대해 반복
    for directory in root_directories:
        # 디렉토리가 존재하는지 확인
        if os.path.exists(directory):
            # 디렉토리인지 확인
            if os.path.isdir(directory):
                # 디렉토리 명이 "a"인 경우
                if os.path.basename(directory) in ["a"]:
                    # 재귀적으로 해당 디렉토리 내의 Unity3D 파일을 찾아 추가
                    for root, _, filenames in os.walk(directory):
                        for filename in filenames:
                            if filename.endswith(".unity3d"):
                                unity3d_files.append(os.path.relpath(os.path.join(root, filename), start=os.getcwd()))
                # 현재 작업 디렉토리인 경우
                elif directory == os.getcwd():
                    # 현재 디렉토리 내의 Unity3D 파일을 찾아 추가
                    for filename in os.listdir(directory):
                        if filename.endswith(".unity3d"):
                            unity3d_files.append(os.path.relpath(os.path.join(directory, filename), start=os.getcwd()))
            # 파일인 경우
            elif os.path.isfile(directory) and directory.endswith(".unity3d"):
                # Unity3D 파일을 리스트에 추가
                unity3d_files.append(os.path.relpath(directory, start=os.getcwd()))
    
    return unity3d_files




# Unity3D 파일을 처리하는 함수
def process_unity3d_files(unity3d_files: list[str], destination_folder: str):
    """
    Args:
        unity3d_files (list[str]): 처리할 Unity3D 파일의 경로 목록
        destination_folder (str): 추출된 리소스를 저장할 폴더 경로

    Returns:
        None
    """
    # 각 Unity3D 파일에 대해 반복
    for file_path in unity3d_files:
        # Source Info 출력
        print(f"\n\n\n [ Source Info ]")
        print(f" 원본 파일 경로: \{file_path} \n")
        print(f" [ Processing Results ]")

        # 처리된 파일 개수를 전역 변수로 설정
        global total_processed

        try:
            # UnityPy를 사용하여 *.unity3d 파일 로드
            env = UnityPy.load(file_path)

            # 파일명에서 확장자 제거하여 폴더명으로 사용
            folder_name = os.path.splitext(os.path.basename(file_path))[0]
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
                            print(f" 추출된 파일 경로: {dest}")

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
            print(f" 오류 발생: 추출할 수 없는 리소스가 발견되었습니다. 해당 리소스를 무시하고 다음 작업을 진행합니다.")
            print(f" 오류 정보: {e}.")
            continue






# 사용자에게 작업을 프롬프트하는 함수
def prompt_user():
    print("\n\n [ 안내 ] 이미 변환 된 파일이 있을 경우 해당 파일을 덮어쓰기 처리하여 새로 작업 합니다.")
    print()
    print(" [ 주의 ] 작업 진행 중 콘솔 창 내부를 클릭하면 진행이 멈출 수 있습니다.")
    print("          ( 임시 해결 방법: 콘솔 창의 [최대화] 버튼과 [이전 크기로 복원] 버튼을 번갈아가며 클릭 )\n")

    print(" 작업을 진행하시겠습니까? ([Y]/[N], 대소문자 구분 없음.))")
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
    """
    주어진 데이터를 역직렬화하여 명령 ID와 해당 명령의 인수 리스트를 반환합니다.

    Args:
        data: 역직렬화할 스크립트 데이터

    Returns:
        tuple[CommandId, list[str]]: 명령 ID와 인수 리스트를 담은 튜플
    """
    # 명령 ID 추출
    index = data[0]
    args = []
    # 인수가 있는 경우 인수 추출
    if len(data) > 1:
        args = data[1:]
    array = []
    # 각 인수를 역직렬화하여 리스트에 추가
    for arg in args:
        array2 = []
        for byte in arg:
            if byte > 127:
                array2.append(255 - byte)
            else:
                array2.append(byte)
        str_ = base64.b64decode(bytearray(array2))
        array.append(str_.decode())
    # 명령 ID와 역직렬화된 인수 리스트를 튜플로 반환
    return (CommandId(index), array)


# 스토리 데이터 원시 바이트열 역직렬화
def deserialize_story_raw(bytes_: bytes) -> list[tuple[CommandId, list[str]]]:
    """
    주어진 바이트열을 역직렬화하여 스토리 데이터의 명령 목록을 반환합니다.

    Args:
        bytes_: 스토리 데이터를 나타내는 바이트열

    Returns:
        list[tuple[CommandId, list[str]]]: 명령 ID와 해당 명령의 인수 리스트를 담은 튜플의 리스트
    """
    commands = []  # 역직렬화된 명령 목록을 담을 리스트
    fs = 0  # 바이트열을 읽을 현재 위치
    raw_commands = []  # 원시 명령 목록을 담을 리스트
    i = 2  # 인덱스 이동 단위
    # 바이트열을 분석하여 원시 명령 목록 생성
    while i < len(bytes_):
        args: list[bytes | int] = []  # 명령의 인덱스와 인수를 담을 리스트
        # 명령 인덱스 추출
        index = int(unpack(">H", bytes_[fs : fs + 2])[0])
        fs += 2
        args.append(index)
        num = i
        # 인수가 있는 경우 인수 추출
        while True:
            # 인수의 길이 추출
            length = int(unpack(">l", bytes_[fs : fs + 4])[0])
            fs += 4
            if length == 0:
                break
            # 인수 추출
            array = bytes_[fs : fs + length]
            fs += length
            args.append(array)
            num += 4 + length
        i = num + 4
        raw_commands.append(args)
        i += 2
    # 역직렬화된 원시 명령 중에서 인수가 있는 경우만 추출하여 명령 목록에 추가
    for raw_command in raw_commands:
        if len(raw_command) > 1:
            commands.append(deserialize_command(raw_command))
    return commands


# 스토리 데이터 역직렬화 후 *.json 파일로 저장하는 함수
def deserialize_story(bytes_: bytes, dest: str) -> None:
    """
    입력:
        - bytes_: 역직렬화할 스토리 데이터를 나타내는 바이트열
        - dest: 스토리 데이터를 저장할 JSON 파일 경로
    출력: None
    """
    global total_processed  # 전역 변수 total_processed를 사용하기 위해 선언

    # 스토리 데이터 역직렬화
    commands = deserialize_story_raw(bytes_)

    # 스토리 데이터를 저장할 딕셔너리 초기화
    story: dict[int, dict] = {}
    num = 0
    story[num] = {}
    block: dict[str, str | tuple | dict] = story[num]

    # 명령 목록을 반복하여 각 명령을 처리
    for command_id, args in commands:
        # 명령 ID에 따라 다른 처리 수행
        match command_id:
            case CommandId.PRINT:
                # PRINT 명령 처리: 대화 출력
                cmd = block.setdefault(command_id.name.lower(), {})
                cmd.setdefault("name", args[0])
                cmd["text"] = (cmd.get("text") or "") + clean_text(args[1])
            case CommandId.CHOICE:
                # CHOICE 명령 처리: 선택지 추가
                block.setdefault(command_id.name.lower(), [])
                block[command_id.name.lower()].append(
                    {
                        "text": args[0],
                        "tag": args[1],
                    }
                )
            case CommandId.BUSTUP:
                # BUSTUP 명령 처리: 캐릭터 변경
                num += 1
                block = story.setdefault(num, {})
            case CommandId.TAG:
                # TAG 명령 처리: 태그 설정
                story.setdefault(num + 1, {})
                story[num + 1][command_id.name.lower()] = args[0]
            case CommandId.TITLE | CommandId.SITUATION | CommandId.OUTLINE | CommandId.VO | CommandId.GOTO:
                # TITLE, SITUATION, OUTLINE, VO, GOTO 명령 처리: 제목, 상황, 개요, 음성, 이동 설정
                if len(args) == 1:
                    args = args[0]
                block[command_id.name.lower()] = args
    
    # JSON 파일로 스토리 데이터 작성
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(story, f, indent=4, ensure_ascii=False)
        total_processed += 1
        print(f" 추출된 파일 경로: \{dest}")


# 텍스트를 정리하여 특수 문자 및 문자열 치환을 수행하는 함수
def clean_text(text: str) -> str:
    """
    입력:
        - text: 정리할 텍스트 문자열
    출력:
        - 정리된 텍스트 문자열
    """
    # 특수 문자 및 문자열 치환을 위한 대체 쌍 정의
    replace_pairs = (
        ("\\n", "\n"),      # '\\n'을 개행 문자 '\n'으로 대체
        ("{0}", "{player_name}"),  # '{0}'을 '{player_name}'으로 대체
        ('\\"', '"'),       # 이스케이프된 큰따옴표 '\"'를 일반 큰따옴표 '"'로 대체
    )
    
    # 각 대체 쌍을 반복하면서 텍스트를 정리
    for pair in replace_pairs:
        text = text.replace(*pair)
    
    return text  # 정리된 텍스트 반환


# 메인 함수
def main():
    if prompt_user():
        root_directories = ["a", "b", os.getcwd()]  # 현재 디렉터리와 a, b 폴더에서 Unity3D 파일 검색
        unity3d_files = find_unity3d_files(root_directories)
        destination_folder = "_Converted"
        process_unity3d_files(unity3d_files, destination_folder)
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")
    else:
        input(f"\n\n\n 총 {total_processed}개의 파일이 처리되었습니다. Enter 키를 입력하여 종료하십시오.")

if __name__ == "__main__":
    main()
