from __future__ import annotations
import base64
from enum import Enum
from struct import unpack, error as struct_error
from typing import Any


class StoryDataCorruptedError(Exception):
    """스토리 바이너리 데이터가 손상되었거나 비정상적인 무한 반복이 감지되었을 때 발생하는 예외입니다."""
    pass


class StoryDataDeserializer:
    """Unity AssetBundle 내 StoryData 바이너리를 역직렬화하는 클래스입니다.

    프리코네 스토리 데이터는 커스텀 바이너리 포맷으로 인코딩되어 있습니다.
    이 클래스는 해당 바이너리를 명령어 목록으로 파싱하고,
    최종적으로 JSON 구조의 딕셔너리로 변환합니다.
    """

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
    
    @staticmethod
    def _deserialize_command(data: list[Any]) -> tuple['StoryDataDeserializer.CommandId', list[str]]:
        """단일 명령어 데이터를 디코딩하고 문자열로 변환합니다."""
        index = data[0] # 명령어 ID
        args = data[1:] if len(data) > 1 else [] # 인자 목록
        array = [] # 디코딩된 인자를 저장할 리스트
        for arg in args:
            # 비표준 바이트 변환 (값이 127보다 크면 255에서 뺌)
            array2 = bytearray()
            for byte in arg:
                array2.append(255 - byte if byte > 127 else byte)
            # Base64 디코딩 및 UTF-8 문자열 변환
            str_ = base64.b64decode(array2)
            array.append(str_.decode('utf-8', 'surrogateescape'))
        
        # 숫자 ID를 CommandId Enum 멤버로 변환
        try:
            cmd_id = StoryDataDeserializer.CommandId(index)
        except ValueError:
            cmd_id = StoryDataDeserializer.CommandId.UNKNOWN # 알 수 없는 ID는 UNKNOWN으로 처리
        return (cmd_id, array)

    @staticmethod
    def _deserialize_story_raw(bytes_: bytes) -> list[tuple['StoryDataDeserializer.CommandId', list[str]]]:
        """전체 스토리 바이너리 데이터를 읽어 명령어 목록으로 파싱합니다."""
        commands = []
        fs = 0 # 파일 스트림 포인터
        raw_commands = []
        i = 2
        max_command_limit = max(100_000, len(bytes_))
        iteration_count = 0

        while i < len(bytes_):
            iteration_count += 1
            if iteration_count > max_command_limit:
                raise StoryDataCorruptedError(
                    f"Abnormal infinite loop detected in story binary data (iteration {iteration_count} exceeded limit {max_command_limit})."
                )

            args: list[bytes | int] = []
            try:
                # 2바이트(Big-endian)를 읽어 명령어 인덱스 파싱
                index = int(unpack(">H", bytes_[fs : fs + 2])[0])
            except (struct_error, IndexError):
                break  # 바이너리 버퍼가 소진되었거나 형식이 맞지 않음
            fs += 2
            args.append(index)
            num = i
            while True:
                try:
                    # 4바이트(Big-endian)를 읽어 인자의 길이 파싱
                    length = int(unpack(">l", bytes_[fs : fs + 4])[0])
                except (struct_error, IndexError):
                    length = 0
                fs += 4
                if length == 0: # 길이가 0이면 명령어의 끝
                    break
                # 해당 길이만큼 읽어 인자 데이터로 저장
                array = bytes_[fs : fs + length]
                fs += length
                args.append(array)
                num += 4 + length
            i = num + 4
            raw_commands.append(args)
            i += 2
        # 파싱된 각 raw 명령어를 디코딩
        for raw_command in raw_commands:
            if len(raw_command) > 1:
                commands.append(StoryDataDeserializer._deserialize_command(raw_command))
        return commands
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """역직렬화된 텍스트의 특수 문자들을 정리합니다."""
        replace_pairs = (
            ("\\n", "\n"),
            ("{0}", "{player_name}"),
            ('\\"', '"'),
        )
        for pair in replace_pairs:
            text = text.replace(*pair)
        return text

    @staticmethod
    def deserialize(bytes_: bytes) -> dict:
        """
        메인 역직렬화 함수. 바이너리 데이터를 받아 최종 JSON 구조의 딕셔너리로 변환합니다.

        Args:
            bytes_ (bytes): StoryData 에셋의 원본 바이너리 데이터.

        Returns:
            dict: 스토리가 재구성된 딕셔너리.
        """
        if not isinstance(bytes_, (bytes, bytearray)):
            bytes_ = str(bytes_).encode('utf-8', 'surrogateescape')
        
        commands = StoryDataDeserializer._deserialize_story_raw(bytes_)
        story: dict[int, dict] = {} # 최종 스토리 딕셔너리
        num = 0 # 현재 스토리 블록 번호
        story[num] = {}
        block: dict[str, str | tuple | dict] = story[num]

        # 명령어 ID에 따라 데이터 구조화
        for command_id, args in commands:
            match command_id:
                case StoryDataDeserializer.CommandId.PRINT: # 대사
                    cmd = block.setdefault(command_id.name.lower(), {})
                    cmd.setdefault("name", args[0])
                    cmd["text"] = (cmd.get("text") or "") + StoryDataDeserializer._clean_text(args[1])
                case StoryDataDeserializer.CommandId.CHOICE: # 선택지
                    choices = block.setdefault(command_id.name.lower(), [])
                    if isinstance(choices, list):
                        choices.append({"text": args[0], "tag": args[1]})
                case StoryDataDeserializer.CommandId.BUSTUP: # 새 블록 시작
                    num += 1
                    block = story.setdefault(num, {})
                case StoryDataDeserializer.CommandId.TAG: # 태그
                    story.setdefault(num + 1, {})
                    story[num + 1][command_id.name.lower()] = args[0]
                case StoryDataDeserializer.CommandId.OUTLINE: # 개요 텍스트 정리
                    if args:
                        block[command_id.name.lower()] = StoryDataDeserializer._clean_text(args[0])
                case StoryDataDeserializer.CommandId.TITLE | StoryDataDeserializer.CommandId.SITUATION | StoryDataDeserializer.CommandId.VO | StoryDataDeserializer.CommandId.GOTO:
                    block[command_id.name.lower()] = args[0] if len(args) == 1 else args
                case _: # 기타 명령어들은 리스트에 추가
                    if command_id.name.lower() not in block or not isinstance(block[command_id.name.lower()], list):
                        block[command_id.name.lower()] = []
                    block[command_id.name.lower()].append(args[0] if len(args) == 1 else args)

        return story

    @staticmethod
    def show_corrupted_error_dialog(parent: Any = None, lang: str = 'ko') -> None:
        """스토리 데이터 손상 및 무한 반복(루프) 감지 시 다국어 메시지 박스를 표시합니다."""
        import json
        from pathlib import Path
        from tkinter import messagebox

        title = "스토리 파일 분석 실패"
        msg = (
            "선택하신 스토리 파일이 손상되었거나 올바른 형식이 아닙니다.\n\n"
            "파일 내부 데이터 손상으로 인해 비정상적인 무한 반복(루프)이 감지되어, "
            "프로그램과 컴퓨터가 멈추는 것을 방지하기 위해 분석 작업을 안전하게 중단했습니다.\n\n"
            "원본 게임 파일이 정상적으로 다운로드되었는지 확인해 주세요."
        )

        lang_path = Path(__file__).resolve().parent.parent / "languages.json"
        if lang_path.is_file():
            try:
                with open(lang_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sv = data.get('story_viewer', {}).get(lang, {})
                title = sv.get('msgbox_story_loop_limit_title', title)
                msg = sv.get('msgbox_story_loop_limit_msg', msg)
            except Exception:
                pass

        messagebox.showerror(title, msg, parent=parent)
