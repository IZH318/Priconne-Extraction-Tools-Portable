# src/unity_converter/extractor.py
import os
import re
import json
import base64
from struct import unpack
from enum import Enum
import UnityPy


class StoryDataDeserializer:
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
    def _deserialize_command(data) -> tuple['StoryDataDeserializer.CommandId', list[str]]:
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
        while i < len(bytes_):
            args: list[bytes | int] = []
            try:
                # 2바이트(Big-endian)를 읽어 명령어 인덱스 파싱
                index = int(unpack(">H", bytes_[fs : fs + 2])[0])
            except Exception:
                break 
            fs += 2
            args.append(index)
            num = i
            while True:
                try:
                    # 4바이트(Big-endian)를 읽어 인자의 길이 파싱
                    length = int(unpack(">l", bytes_[fs : fs + 4])[0])
                except Exception:
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


class AssetProcessor:
    # 에셋 타입별 기본 출력 폴더명 매핑
    SPECIAL_TYPES = {
        "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
        "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
        "VideoClip": "Videos", "MovieTexture": "Videos", "Material": "Materials",
        "MonoBehaviour": "MonoBehaviours", "Texture2DArray": "Textures",
        "AnimationClip": "Animations",
    }

    # 추출이 불필요한 내부 엔진/메타데이터 타입 목록
    # (이 타입들은 직접적인 에셋 데이터가 아니라 Unity 내부 구조체입니다.)
    SKIP_TYPES = {
        "GameObject", "Transform", "RectTransform", "AssetBundle", "PreloadData",
        "MeshRenderer", "SkinnedMeshRenderer", "MeshFilter", "Canvas", "CanvasRenderer",
        "MonoScript", "BuildSettings", "Animator", "SpriteAtlas",
    }

    # 전용 핸들러가 있는 에셋 타입 목록 (체크박스 UI용)
    HANDLER_TYPES = [
        "Texture2D", "Sprite", "TextAsset", "AudioClip", "Mesh",
        "Font", "Shader", "MonoBehaviour", "Texture2DArray",
        "MovieTexture", "VideoClip", "AnimationClip",
    ]

    # 기본적으로 추출이 활성화되는 타입 (HANDLER_TYPES 전체)
    DEFAULT_ENABLED = set(HANDLER_TYPES)

    # 기본적으로 비활성화되지만 사용자가 활성화할 수 있는 타입
    OPTIONAL_TYPES = sorted(SKIP_TYPES) + ["Material", "_OTHER_"]

    def __init__(self, file_path, output_path, base_input_path, log_queue, enabled_types=None):
        """
        AssetProcessor 인스턴스 초기화.

        Args:
            file_path (str): 처리할 .unity3d 파일의 전체 경로.
            output_path (str): 결과물이 저장될 최상위 출력 폴더 경로.
            base_input_path (str | None): 폴더 단위로 열었을 경우의 기본 입력 폴더 경로.
            log_queue (Queue): GUI와 통신하기 위한 멀티프로세싱 큐.
            enabled_types (set | None): 추출할 에셋 타입 이름 집합. None이면 기본값 사용.
        """
        self.file_path = file_path
        self.output_path = output_path
        self.log_queue = log_queue
        self.base_name = os.path.basename(file_path) # 현재 처리 중인 파일 이름
        self.enabled_types = enabled_types if enabled_types is not None else self.DEFAULT_ENABLED
        
        # 입력 경로 구조를 보존하는 출력 폴더 경로 생성
        if base_input_path:
            relative_path = os.path.relpath(file_path, base_input_path)
            folder_path_without_ext, _ = os.path.splitext(relative_path)
            self.output_dir = os.path.join(self.output_path, folder_path_without_ext)
        else:
            folder_name_without_ext, _ = os.path.splitext(self.base_name)
            self.output_dir = os.path.join(self.output_path, folder_name_without_ext)

        self.env = None # UnityPy 환경 객체
        self.fallback_count = 0 # 오류로 인해 원본(.bin)으로 저장된 에셋 수

    def log(self, message_key, level='INFO', format_args=None):
        """로그 메시지를 통신 큐에 추가합니다."""
        self.log_queue.put(('log', self.base_name, message_key, level, format_args))

    def _sanitize_filename(self, name):
        """파일 시스템에서 사용할 수 없는 문자를 '_'로 치환합니다."""
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def _get_unique_path(self, path, obj_path_id):
        """파일명 충돌 시 `(#PathID)` 또는 `(count)` 접미사를 붙여 고유한 경로를 생성합니다."""
        if not os.path.exists(path):
            return path
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        new_path = os.path.join(directory, f"{name} (#{obj_path_id}){ext}")
        if not os.path.exists(new_path):
            return new_path
        count = 1
        base_name_for_counting = f"{name} (#{obj_path_id})"
        while True:
            final_path = os.path.join(directory, f"{base_name_for_counting} ({count}){ext}")
            if not os.path.exists(final_path):
                return final_path
            count += 1

    def _get_export_path(self, obj, extension, data=None, sub_folder=None):
        """
        에셋을 저장할 최종 경로를 결정하고 생성합니다.
        
        Args:
            obj: UnityPy ObjectReader.
            extension (str): 파일 확장자 (예: ".png").
            data: 이미 파싱된 데이터 객체 (None이면 내부에서 파싱).
            sub_folder (str | None): 특수 하위 폴더 이름.
        """
        if data is None:
            data = obj.parse_as_object()
        base_name_asset = getattr(data, 'm_Name', '') or obj.type.name
        folder_name = sub_folder or self.SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(self.output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True) # 폴더 자동 생성
        sanitized_name = self._sanitize_filename(base_name_asset)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        return self._get_unique_path(initial_path, obj.path_id)

    def process_all_assets(self):
        """파일 내의 모든 에셋을 순회하며 처리를 시작하는 메인 함수입니다."""
        self.env = UnityPy.load(self.file_path) # 파일 로드
        num_assets = len(self.env.objects)
        if num_assets == 0:
            self.log("no_assets_to_process", "WARNING")
            return 0
        
        self.log('processing_started_assets', format_args={'count': num_assets})
        
        extracted_count = 0
        for obj in self.env.objects:
            if self._dispatch_asset(obj): # 각 에셋 처리
                extracted_count += 1
        
        # 최종 결과 로그
        if self.fallback_count > 0:
            self.log('extraction_complete_with_fallback', 'SUCCESS', {'total': num_assets, 'success': extracted_count, 'fallback_count': self.fallback_count})
        else:
            self.log('extraction_complete', 'SUCCESS', {'total': num_assets, 'success': extracted_count})

    def _dispatch_asset(self, obj):
        """에셋의 타입에 따라 적절한 처리 함수를 호출하는 라우터 역할을 합니다."""
        obj_type = obj.type.name

        # 사용자가 선택하지 않은 타입은 스킵
        if obj_type not in self.enabled_types:
            # 전용 핸들러가 없는 기타 타입인 경우 "_OTHER_" 체크
            if obj_type not in self.HANDLER_TYPES and obj_type != "Material" and "_OTHER_" in self.enabled_types:
                pass  # 아래 제네릭 처리로 계속 진행
            else:
                return False

        try:
            if obj_type == "Texture2D":
                return self._export_texture2d(obj)
            elif obj_type == "Sprite":
                return self._export_sprite(obj)
            elif obj_type == "TextAsset":
                return self._export_textasset_dispatch(obj)
            elif obj_type == "AudioClip":
                return self._export_audioclip(obj)
            elif obj_type == "Mesh":
                return self._export_mesh(obj)
            elif obj_type == "Font":
                return self._export_font(obj)
            elif obj_type == "Shader":
                return self._export_shader(obj)
            elif obj_type == "MonoBehaviour":
                return self._export_monobehaviour(obj)
            elif obj_type == "Texture2DArray":
                return self._export_texture2darray(obj)
            elif obj_type == "MovieTexture":
                return self._export_movietexture(obj)
            elif obj_type == "VideoClip":
                return self._export_videoclip(obj)
            elif obj_type == "AnimationClip":
                return self._export_animationclip(obj)
            elif obj_type == "Material":
                if "Material" in self.enabled_types:
                    return self._export_generic_json(obj)
                return False
            else:
                # 전용 핸들러가 없는 기타 타입: SKIP_TYPES에 속하면 제네릭 JSON
                return self._export_generic_json(obj)
        except Exception as e:
            # 처리 실패 시 예외 로깅 및 대체 저장 시도
            self.log('asset_processing_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': obj_type, 'error': e})
            if obj_type == "Mesh":
                self.log('mesh_fallback_info', "WARNING")
                if self._export_raw_data(obj):
                    self.fallback_count += 1
                    return True
                return False
            else:
                try:
                    return self._export_generic_json(obj, error_info=str(e))
                except Exception as e2:
                    self.log('json_fallback_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': obj.type.name, 'error': e2})
        return False

    def _export_raw_data(self, obj):
        """에셋을 처리할 수 없을 때 원본 바이너리 데이터(.bin)로 저장합니다."""
        try:
            path = self._get_export_path(obj, ".bin")
            raw_data = obj.get_raw_data()
            with open(path, "wb") as f:
                f.write(raw_data)
            return True
        except Exception as e:
            self.log('asset_processing_error', 'ERROR', {'path_id': obj.path_id, 'obj_type': 'raw data', 'error': e})
            return False

    # =====================================================================
    # Texture2D 추출
    # UnityPy의 .image 속성이 PIL.Image로 변환해줌.
    # m_Width 체크로 빈 텍스처 크래시 방지.
    # =====================================================================
    def _export_texture2d(self, obj):
        """Texture2D 에셋을 .png 파일로 저장합니다."""
        data = obj.parse_as_object()
        if data.m_Width and data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # Sprite 추출
    # Sprite는 텍스처의 일부분이며, 별도의 알파 이미지를 가질 수 있음.
    # UnityPy가 자동으로 알파 이미지를 합성하여 .image로 반환함.
    # =====================================================================
    def _export_sprite(self, obj):
        """Sprite 에셋을 .png 파일로 저장합니다 (알파 합성 포함)."""
        data = obj.parse_as_object()
        if data.image:
            path = self._get_export_path(obj, ".png", data=data)
            data.image.save(path)
            return True
        return False

    # =====================================================================
    # TextAsset 추출
    # 'storydata_' 접두사를 가진 에셋은 커스텀 바이너리 역직렬화를 시도.
    # m_Script는 UnityPy에서 str로 반환됨.
    # =====================================================================
    def _export_textasset_dispatch(self, obj):
        """TextAsset의 이름에 따라 일반 바이너리 또는 StoryData JSON으로 분기합니다."""
        data = obj.parse_as_object()
        asset_name = data.m_Name or ''
        if asset_name.startswith('storydata_'):
            return self._export_storydata_as_json(obj, data)
        else:
            return self._export_textasset(obj, data)

    def _export_storydata_as_json(self, obj, data):
        """'storydata_'로 시작하는 TextAsset을 JSON으로 역직렬화하여 저장합니다."""
        asset_name = data.m_Name or ''
        
        # 원본 .bin 파일은 항상 저장
        bin_saved = self._export_textasset(obj, data)

        try:
            # m_Script에서 바이너리 데이터 추출
            # UnityPy에서 m_Script는 str로 반환되므로 surrogateescape로 바이트 복원
            script_bytes = data.m_Script.encode('utf-8', 'surrogateescape')

            if not script_bytes:
                raise ValueError("Story_data is empty or cannot be converted to bytes.")

            # 역직렬화 및 JSON 저장
            deserialized_data = StoryDataDeserializer.deserialize(script_bytes)
            
            path = self._get_export_path(obj, ".json", data=data)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(deserialized_data, f, indent=4, ensure_ascii=False)
            self.log('storydata_deserialization_success', 'SUCCESS', {'asset_name': asset_name})
        
        except Exception as e:
            # 실패 시 로그 기록
            self.log('storydata_deserialization_fail', 'ERROR', {'asset_name': asset_name, 'error': e})
        
        return bin_saved

    def _export_textasset(self, obj, data=None):
        """TextAsset을 원본 바이너리(.bin) 파일로 저장합니다."""
        if data is None:
            data = obj.parse_as_object()
        content = data.m_Script
        if content is not None:
            path = self._get_export_path(obj, ".bin", data=data)
            # UnityPy에서 m_Script는 str로 반환됨 → bytes로 변환
            if isinstance(content, str):
                content = content.encode('utf-8', 'surrogateescape')
            elif not isinstance(content, (bytes, bytearray)):
                content = str(content).encode('utf-8', 'surrogateescape')

            with open(path, "wb") as f:
                f.write(content)
            return True
        return False

    # =====================================================================
    # AudioClip 추출
    # UnityPy의 .samples 속성이 딕셔너리를 반환 → {파일명: 바이너리 데이터}
    # 파일명에 올바른 확장자(.wav, .ogg, .m4a)가 포함되어 있음.
    # =====================================================================
    def _export_audioclip(self, obj):
        """AudioClip 에셋을 올바른 형식(.wav/.ogg/.m4a)으로 저장합니다."""
        data = obj.parse_as_object()
        if data.samples:
            for sample_name, audio_data in data.samples.items():
                # samples dict의 키에서 실제 확장자 추출
                _, ext = os.path.splitext(sample_name)
                if not ext:
                    ext = ".wav" # 폴백
                
                # 에셋 이름으로 저장 (확장자는 samples dict에서 가져옴)
                dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["AudioClip"])
                os.makedirs(dest_folder, exist_ok=True)
                sanitized_name = self._sanitize_filename(sample_name)
                # sample_name에 이미 확장자가 포함되어 있으므로 그대로 사용
                initial_path = os.path.join(dest_folder, sanitized_name)
                path = self._get_unique_path(initial_path, obj.path_id)
                
                with open(path, "wb") as f:
                    f.write(audio_data)
            return True
        return False

    # =====================================================================
    # Font 추출
    # m_FontData 바이트 배열에서 TTF/OTF를 판별하여 저장.
    # =====================================================================
    def _export_font(self, obj):
        """Font 에셋을 .ttf 또는 .otf 파일로 저장합니다."""
        data = obj.parse_as_object()
        if data.m_FontData:
            font_data_bytes = bytes(data.m_FontData)
            extension = ".otf" if font_data_bytes[:4] == b"OTTO" else ".ttf"
            path = self._get_export_path(obj, extension, data=data)
            with open(path, "wb") as f:
                f.write(font_data_bytes)
            return True
        return False

    # =====================================================================
    # Mesh 추출
    # UnityPy의 내장 Mesh.export()가 압축/비압축 메시 모두 처리함.
    # MeshHelper.MeshHandler가 내부적으로 CompressedMesh 언패킹도 수행.
    # =====================================================================
    def _export_mesh(self, obj):
        """Mesh 에셋을 .obj 파일로 저장합니다 (UnityPy 내장 export 사용)."""
        data = obj.parse_as_object()
        exported = data.export()
        if exported:
            path = self._get_export_path(obj, ".obj", data=data)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(exported)
            return True
        return False

    # =====================================================================
    # Shader 추출
    # UnityPy의 내장 Shader.export()가 셰이더 소스 코드를 텍스트로 변환.
    # =====================================================================
    def _export_shader(self, obj):
        """Shader 에셋을 .shader 텍스트 파일로 저장합니다."""
        data = obj.parse_as_object()
        exported = data.export()
        if exported:
            path = self._get_export_path(obj, ".shader", data=data)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(exported)
            self.log('shader_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

    # =====================================================================
    # MonoBehaviour 추출
    # TypeTree를 사용하여 JSON으로 추출 시도.
    # TypeTree가 없으면 바이너리(.bin)로 폴백.
    # =====================================================================
    def _export_monobehaviour(self, obj):
        """MonoBehaviour 에셋을 JSON 또는 바이너리로 저장합니다."""
        try:
            # TypeTree 기반 JSON 추출 시도
            tree = obj.parse_as_dict()
            export_data = json.dumps(tree, indent=4, ensure_ascii=False, 
                                     default=lambda o: f"<Unserializable: {type(o).__name__}>")
            export_bytes = export_data.encode("utf-8", errors="surrogateescape")
            extension = ".json"
        except Exception:
            # TypeTree가 없는 경우 바이너리로 폴백
            export_bytes = obj.get_raw_data()
            extension = ".bin"
            self.fallback_count += 1
        
        # 이름 추출 (파싱하지 않고 peek_name 사용하여 성능 향상)
        try:
            asset_name = obj.peek_name() or obj.type.name
        except Exception:
            asset_name = obj.type.name
        
        dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["MonoBehaviour"])
        os.makedirs(dest_folder, exist_ok=True)
        sanitized_name = self._sanitize_filename(asset_name)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        path = self._get_unique_path(initial_path, obj.path_id)
        
        with open(path, "wb") as f:
            f.write(export_bytes)
        return True

    # =====================================================================
    # Texture2DArray 추출
    # UnityPy의 .images 속성이 PIL.Image 리스트를 반환.
    # 각 이미지를 인덱스를 붙여 개별 .png로 저장.
    # =====================================================================
    def _export_texture2darray(self, obj):
        """Texture2DArray 에셋의 각 레이어를 개별 .png 파일로 저장합니다."""
        data = obj.parse_as_object()
        try:
            images = data.images  # property로 접근
        except Exception:
            return False
        
        if not images:
            return False
        
        dest_folder = os.path.join(self.output_dir, self.SPECIAL_TYPES["Texture2DArray"])
        os.makedirs(dest_folder, exist_ok=True)
        asset_name = self._sanitize_filename(data.m_Name or "Texture2DArray")
        
        for i, image in enumerate(images):
            image_path = os.path.join(dest_folder, f"{asset_name}_{i}.png")
            image_path = self._get_unique_path(image_path, obj.path_id)
            image.save(image_path)
        
        self.log('texture2darray_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})', 'count': len(images)})
        return True

    # =====================================================================
    # MovieTexture 추출 (레거시, Unity 5 이전)
    # m_MovieData 바이트 배열에 Ogg Theora 비디오 데이터가 저장됨.
    # =====================================================================
    def _export_movietexture(self, obj):
        """MovieTexture 에셋의 비디오 데이터를 .ogv 파일로 저장합니다."""
        data = obj.parse_as_object()
        if hasattr(data, 'm_MovieData') and data.m_MovieData:
            movie_data = bytes(data.m_MovieData)
            path = self._get_export_path(obj, ".ogv", data=data)
            with open(path, "wb") as f:
                f.write(movie_data)
            self.log('movietexture_export_success', 'SUCCESS', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return True
        return False

    # =====================================================================
    # VideoClip 추출 (Unity 5.6+)
    # 비디오 데이터는 m_ExternalResources에 StreamedResource로 참조됨.
    # 또는 에셋 내부에 직접 포함될 수 있음.
    # =====================================================================
    def _export_videoclip(self, obj):
        """VideoClip 에셋의 비디오 데이터를 추출합니다."""
        data = obj.parse_as_object()
        
        video_data = None
        
        # 외부 리소스에서 데이터 로드 시도
        if hasattr(data, 'm_ExternalResources') and data.m_ExternalResources:
            resource = data.m_ExternalResources
            source = getattr(resource, 'm_Source', '') or getattr(resource, 'path', '')
            if source:
                try:
                    from UnityPy.helpers.ResourceReader import get_resource_data
                    video_data = get_resource_data(
                        source,
                        obj.assets_file,
                        resource.m_Offset if hasattr(resource, 'm_Offset') else getattr(resource, 'offset', 0),
                        resource.m_Size if hasattr(resource, 'm_Size') else getattr(resource, 'size', 0),
                    )
                except Exception:
                    pass
        
        if video_data:
            # OriginalPath에서 확장자 추출 시도
            ext = ".mp4"
            if hasattr(data, 'm_OriginalPath') and data.m_OriginalPath:
                _, original_ext = os.path.splitext(data.m_OriginalPath)
                if original_ext:
                    ext = original_ext
            
            path = self._get_export_path(obj, ext, data=data)
            with open(path, "wb") as f:
                f.write(video_data)
            return True
        else:
            self.log('videoclip_no_data', 'WARNING', {'asset_name': data.m_Name or f'(PathID:{obj.path_id})'})
            return False

    # =====================================================================
    # AnimationClip 추출
    # TypeTree를 사용하여 JSON으로 추출.
    # =====================================================================
    def _export_animationclip(self, obj):
        """AnimationClip 에셋을 JSON 파일로 저장합니다."""
        tree = obj.parse_as_dict()
        path = self._get_export_path(obj, ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False,
                      default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

    # =====================================================================
    # 제네릭 JSON 추출 (기타 모든 타입)
    # TypeTree를 사용하여 오브젝트 데이터를 JSON으로 저장.
    # =====================================================================
    def _export_generic_json(self, obj, error_info=None):
        """처리 규칙이 없는 모든 에셋 타입을 TypeTree 기반의 .json 파일로 저장합니다."""
        path = self._get_export_path(obj, ".json")
        typetree = obj.parse_as_dict()
        if error_info:
            typetree["EXPORT_ERROR"] = error_info
        with open(path, "w", encoding="utf-8") as f:
            json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True


def process_single_file(file_path, output_path, base_input_path, log_queue, completion_queue, unity_version="2021.3.20f1", enabled_types=None):
    """
    단일 파일을 처리하는 독립적인 워커(worker) 함수. (멀티프로세싱용)
    
    Args:
        file_path (str): 처리할 파일 경로.
        output_path (str): 최상위 출력 폴더 경로.
        base_input_path (str | None): 입력 기준 폴더 경로.
        log_queue (Queue): GUI에 로그를 전달하기 위한 큐.
        completion_queue (Queue): GUI에 작업 완료 신호를 전달하기 위한 큐.
        unity_version (str): 유니티 파싱을 위한 백업/강제 버전 지정.
        enabled_types (set | None): 추출할 에셋 타입 집합. None이면 기본값.
    """
    try:
        from UnityPy import config
        config.FALLBACK_UNITY_VERSION = unity_version
        
        processor = AssetProcessor(file_path, output_path, base_input_path, log_queue, enabled_types)
        processor.process_all_assets()
    except Exception as e:
        # 심각한 오류 발생 시 로그 전송
        base_name = os.path.basename(file_path)
        log_queue.put(('log', base_name, 'worker_process_error', 'ERROR', {'error': e}))
    finally:
        # 작업 완료 신호 전송
        completion_queue.put(True)
