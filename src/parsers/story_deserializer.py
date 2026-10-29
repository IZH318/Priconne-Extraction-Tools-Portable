"""Unity AssetBundle 내 Princess Connect! Re:Dive 스토리 데이터 바이너리 역직렬화 모듈.

게임 클라이언트 내 TextAsset으로 패키징된 커스텀 스토리 바이너리 포맷 파싱.
바이너리는 빅엔디언(Big-endian) 기반 가변 길이 명령어 스트림으로 구성되어 있으며,
비표준 바이트 반전 난독화 및 Base64 인코딩을 거쳐 대사, 화자, 보이스 파일명,
선택지 및 연출 커맨드가 포함된 JSON 호환 딕셔너리로 변환.
"""
from __future__ import annotations

import base64
import binascii
from enum import Enum
from struct import error as struct_error
from struct import unpack
from typing import Any, Final


class StoryDataCorruptedError(Exception):
    """스토리 바이너리 스트림이 손상되었거나 오프셋 조작으로 비정상 무한 루프가 감지되었을 때 발생하는 예외."""


MAX_COMMAND_LIMIT: Final[int] = 100_000


class StoryDataDeserializer:
    """프리코네 스토리 바이너리 역직렬화 클래스.

    바이너리 구조:
    1. 명령어 헤더: 2바이트 빅엔디언 부호 없는 정수(>H) - Opcode (CommandId)
    2. 인자 길이 필드: 4바이트 빅엔디언 정수(>l) - 인자 바이트 길이 (0 이하이면 명령어 종료)
    3. 인자 페이로드: 가변 바이트 - 바이트 값이 127 초과 시 255 - byte로 반전 후 Base64/UTF-8 디코딩
    """

    MAX_COMMAND_LIMIT: Final[int] = MAX_COMMAND_LIMIT

    class CommandId(Enum):
        """스토리 연출 스크립트의 명령어(Opcode) 식별자 열거형.

        게임 엔진 내 대사 출력, 카메라 줌, BGM 재생, 화면 전환, 선택지 표시 등 제어.
        """
        NONE = -1
        TITLE = 0
        OUTLINE = 1
        VISIBLE = 2
        FACE = 3
        FOCUS = 4
        BACKGROUND = 5
        PRINT = 6              # 캐릭터 대사 및 화자 출력
        TAG = 7                # 분기 태그 마커
        GOTO = 8               # 분기 점프
        BGM = 9                # 배경음악 재생
        TOUCH = 10
        CHOICE = 11            # 유저 선택지 분기
        VO = 12                # 음성(보이스) 리소스 트리거
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
        SE = 26                # 효과음 재생
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
        MOVIE = 46             # 인게임 컷신 비디오
        MOVIE_STAY = 47
        BATTLE = 48
        STILL = 49             # 스틸컷 일러스트
        BUSTUP = 50            # 새로운 대사 씬 블록 구분자
        ENV = 51               # 환경음
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
    def _deserialize_command(data: list[Any]) -> tuple[StoryDataDeserializer.CommandId, list[str]]:
        """원시 명령어 데이터 리스트 바이트 역난독화 및 UTF-8 문자열 인자 디코딩 수행.

        난독화 해제 규칙:
            각 바이트 $b$에 대해 $b > 127$이면 $255 - b$, 그렇지 않으면 $b$ 유지.
            해당 바이트 시퀀스 Base64 디코딩 후 UTF-8 해석.

        Args:
            data (list[Any]): [명령어 인덱스 정수, 원시 바이트 인자 1, 원시 바이트 인자 2, ...] 형태의 리스트.

        Returns:
            tuple[CommandId, list[str]]: 해석된 CommandId 및 디코딩된 문자열 파라미터 리스트.
        """
        index = data[0]
        args = data[1:] if len(data) > 1 else []
        array = []
        for arg in args:
            # 비표준 바이트 역변환 (127 초과 시 255에서 감산)
            array2 = bytearray()
            for byte in arg:
                array2.append(255 - byte if byte > 127 else byte)
            # 바이트 디코딩: Base64 디코딩 후 UTF-8 문자열 변환 (surrogateescape로 깨진 문자 보호)
            try:
                str_ = base64.b64decode(array2)
                array.append(str_.decode('utf-8', 'surrogateescape'))
            except (binascii.Error, ValueError):
                array.append(bytes(array2).decode('utf-8', 'surrogateescape'))

        # 식별되지 않은 명령어 번호는 UNKNOWN으로 안전 폴백
        try:
            cmd_id = StoryDataDeserializer.CommandId(index)
        except ValueError:
            cmd_id = StoryDataDeserializer.CommandId.UNKNOWN
        return (cmd_id, array)

    @staticmethod
    def _deserialize_story_raw(bytes_: bytes) -> list[tuple[StoryDataDeserializer.CommandId, list[str]]]:
        """바이너리 바이트 스트림 전체 순회 기반 명령어 및 인자 단위 분할 파싱 수행.

        무한 루프 방지 목적의 최대 반복 횟수
        MAX_COMMAND_LIMIT (100,000) 초과 시 예외 발생 처리.

        Args:
            bytes_ (bytes): 원본 스토리 바이너리 데이터.

        Returns:
            list[tuple[CommandId, list[str]]]: 파싱 및 디코딩 완료 순차 명령어 튜플 목록.

        Raises:
            StoryDataCorruptedError: 데이터 구조 파괴 또는 무한 루프 감지 시 발생.
        """
        commands = []
        fs = 0  # 바이너리 파일 스트림 커서 포인터
        raw_commands = []
        i = 2
        max_command_limit = MAX_COMMAND_LIMIT
        iteration_count = 0
        buffer_len = len(bytes_)

        while i < len(bytes_):
            iteration_count += 1
            if iteration_count > max_command_limit:
                raise StoryDataCorruptedError(
                    f"Abnormal infinite loop detected in story binary data (iteration {iteration_count} exceeded limit {max_command_limit})."
                )

            args: list[bytes | int] = []
            try:
                # 2바이트 빅엔디언 부호 없는 정수로 명령어 Opcode 파싱
                index = int(unpack(">H", bytes_[fs : fs + 2])[0])
            except (struct_error, IndexError):
                break  # 스트림 끝(EOF) 도달
            fs += 2
            args.append(index)
            num = i
            while True:
                if fs + 4 > buffer_len:
                    break
                try:
                    # 4바이트 빅엔디언 부호 있는 정수로 인자 바이트 길이 파싱
                    length = int(unpack(">l", bytes_[fs : fs + 4])[0])
                except (struct_error, IndexError):
                    break
                fs += 4
                if length <= 0:  # 길이가 0 이하이면 현재 명령어의 인자 목록 종료
                    break
                if fs + length > buffer_len:
                    # 버퍼 오버플로우 방지: 잔여 버퍼만 읽고 탈출
                    array = bytes_[fs:buffer_len]
                    fs = buffer_len
                    args.append(array)
                    num += 4 + len(array)
                    break
                # 유효한 길이만큼 인자 바이트 슬라이싱
                array = bytes_[fs : fs + length]
                fs += length
                args.append(array)
                num += 4 + length
            i = num + 4
            raw_commands.append(args)
            i += 2

        # 파싱된 원시 바이트 명령어들을 디코딩하여 결과 리스트에 축적
        for raw_command in raw_commands:
            if len(raw_command) > 1:
                commands.append(StoryDataDeserializer._deserialize_command(raw_command))
        return commands

    @staticmethod
    def _clean_text(text: str) -> str:
        """이스케이프 줄바꿈 및 플레이스홀더 정규화.

        치환 규칙:
        - \\n -> 실제 개행 \n
        - {0} -> 유저 플레이어명 치환자 {player_name}
        - \\" -> 일반 큰따옴표 "

        Args:
            text (str): 원시 파싱된 문자열.

        Returns:
            str: 정규화된 텍스트.
        """
        replace_pairs = (
            ("\\n", "\n"),
            ("{0}", "{player_name}"),
            ('\\"', '"'),
        )
        for pair in replace_pairs:
            text = text.replace(*pair)
        return text

    @staticmethod
    def deserialize(bytes_: bytes) -> dict[int, dict[str, Any]]:
        """스토리 바이너리를 파싱하여 계층적 딕셔너리로 변환.

        BUSTUP 커맨드 기준 씬(블록) 번호 증가,
        대사(PRINT), 선택지(CHOICE), 보이스(VO), BGM 등 블록 단위 묶음 저장.

        Args:
            bytes_ (bytes): Unity TextAsset에서 추출한 원본 바이너리 바이트 스트림.

        Returns:
            dict: 블록 인덱스를 키로 하고, 해당 블록의 대사/연출 커맨드 매핑을 값으로 갖는 딕셔너리.
        """
        commands = StoryDataDeserializer._deserialize_story_raw(bytes_)
        story: dict[int, dict[str, Any]] = {}
        num = 0  # 현재 활성화된 스토리 씬 블록 인덱스
        story[num] = {}
        block: dict[str, Any] = story[num]

        # 명령어 유형별 상태 머신(State Machine) 구조화
        for command_id, args in commands:
            match command_id:
                case StoryDataDeserializer.CommandId.PRINT:  # 캐릭터 대사 및 이름
                    cmd_key = command_id.name.lower()
                    cmd = block.get(cmd_key)
                    if not isinstance(cmd, dict):
                        cmd = {}
                        block[cmd_key] = cmd
                    name = args[0] if len(args) > 0 else ""
                    text = args[1] if len(args) > 1 else ""
                    if name and not cmd.get("name"):
                        cmd["name"] = name
                    else:
                        cmd.setdefault("name", name)
                    cmd["text"] = (cmd.get("text") or "") + StoryDataDeserializer._clean_text(text)
                case StoryDataDeserializer.CommandId.CHOICE:  # 플레이어 인터랙티브 선택지
                    choices_key = command_id.name.lower()
                    choices = block.get(choices_key)
                    if not isinstance(choices, list):
                        choices = []
                        block[choices_key] = choices
                    choice_text = args[0] if len(args) > 0 else ""
                    choice_tag = args[1] if len(args) > 1 else ""
                    choices.append({"text": choice_text, "tag": choice_tag})
                case StoryDataDeserializer.CommandId.BUSTUP:  # 새로운 연출/대사 블록 시작 (블록 번호 증가)
                    num += 1
                    block = story.setdefault(num, {})
                case StoryDataDeserializer.CommandId.TAG:     # 스토리 분기 태그
                    story.setdefault(num + 1, {})
                    tag_val = args[0] if args else ""
                    story[num + 1][command_id.name.lower()] = tag_val
                case StoryDataDeserializer.CommandId.OUTLINE: # 스토리 시놉시스/개요 텍스트
                    if args:
                        block[command_id.name.lower()] = StoryDataDeserializer._clean_text(args[0])
                case StoryDataDeserializer.CommandId.TITLE | StoryDataDeserializer.CommandId.SITUATION | StoryDataDeserializer.CommandId.VO | StoryDataDeserializer.CommandId.GOTO:
                    block[command_id.name.lower()] = args[0] if len(args) == 1 else args
                case _:  # 기타 연출 및 환경 커맨드 목록 축적
                    if command_id.name.lower() not in block or not isinstance(block[command_id.name.lower()], list):
                        block[command_id.name.lower()] = []
                    block[command_id.name.lower()].append(args[0] if len(args) == 1 else args)

        return story

