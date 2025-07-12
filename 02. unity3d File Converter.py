# ==============================================================================
# Unity 에셋 추출기 (Unity Asset Extractor)
# ------------------------------------------------------------------------------
# 이 스크립트는 Unity3D의 에셋 파일에서 내부 리소스를 추출하는 GUI 애플리케이션입니다.
#
# v4.5 주요 변경 사항:
# - 처리 대상 제한: .unity3d 파일만 처리하도록 파일 선택 다이얼로그 및 폴더 검색 로직 수정.
# ==============================================================================

# --- 모듈 임포트 ---
from datetime import datetime
import os
import queue
import re
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Text, Scrollbar, PanedWindow
import math
from PIL import Image
import UnityPy
import concurrent.futures
import json
from multiprocessing import Manager, cpu_count
import threading
from enum import Enum
from struct import unpack
import base64

# --- UnityPy 라이브러리 전역 설정 ---
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# --- 상수 정의 ---
SUPPORTED_EXTENSIONS = ('.unity3d',)

# ==============================================================================
# StoryData 정밀 역직렬화 클래스 (Advanced StoryData Deserializer Class)
# ==============================================================================
class StoryDataDeserializer:
    """
    참고 코드를 기반으로 StoryData(.bin) 파일을 정밀하게 역직렬화하여
    구조화된 Python 딕셔너리로 변환합니다.
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
    def _deserialize_command(data) -> tuple['StoryDataDeserializer.CommandId', list[str]]:
        index = data[0]
        args = data[1:] if len(data) > 1 else []
        array = []
        for arg in args:
            array2 = bytearray()
            for byte in arg:
                array2.append(255 - byte if byte > 127 else byte)
            str_ = base64.b64decode(array2)
            array.append(str_.decode('utf-8', 'surrogateescape'))
        
        try:
            cmd_id = StoryDataDeserializer.CommandId(index)
        except ValueError:
            cmd_id = StoryDataDeserializer.CommandId.UNKNOWN
        return (cmd_id, array)

    @staticmethod
    def _deserialize_story_raw(bytes_: bytes) -> list[tuple['StoryDataDeserializer.CommandId', list[str]]]:
        commands = []
        fs = 0
        raw_commands = []
        i = 2
        while i < len(bytes_):
            args: list[bytes | int] = []
            try:
                index = int(unpack(">H", bytes_[fs : fs + 2])[0])
            except Exception:
                break 
            fs += 2
            args.append(index)
            num = i
            while True:
                try:
                    length = int(unpack(">l", bytes_[fs : fs + 4])[0])
                except Exception:
                    length = 0
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
                commands.append(StoryDataDeserializer._deserialize_command(raw_command))
        return commands
    
    @staticmethod
    def _clean_text(text: str) -> str:
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
        if not isinstance(bytes_, (bytes, bytearray)):
            bytes_ = str(bytes_).encode('utf-8', 'surrogateescape')
        
        commands = StoryDataDeserializer._deserialize_story_raw(bytes_)
        story: dict[int, dict] = {}
        num = 0
        story[num] = {}
        block: dict[str, str | tuple | dict] = story[num]

        for command_id, args in commands:
            match command_id:
                case StoryDataDeserializer.CommandId.PRINT:
                    cmd = block.setdefault(command_id.name.lower(), {})
                    cmd.setdefault("name", args[0])
                    cmd["text"] = (cmd.get("text") or "") + StoryDataDeserializer._clean_text(args[1])
                case StoryDataDeserializer.CommandId.CHOICE:
                    choices = block.setdefault(command_id.name.lower(), [])
                    if isinstance(choices, list):
                        choices.append({"text": args[0], "tag": args[1]})
                case StoryDataDeserializer.CommandId.BUSTUP:
                    num += 1
                    block = story.setdefault(num, {})
                case StoryDataDeserializer.CommandId.TAG:
                    story.setdefault(num + 1, {})
                    story[num + 1][command_id.name.lower()] = args[0]
                case StoryDataDeserializer.CommandId.TITLE | StoryDataDeserializer.CommandId.SITUATION | StoryDataDeserializer.CommandId.OUTLINE | StoryDataDeserializer.CommandId.VO | StoryDataDeserializer.CommandId.GOTO:
                    block[command_id.name.lower()] = args[0] if len(args) == 1 else args
                case _:
                    # Ensure the value is a list before appending
                    if command_id.name.lower() not in block or not isinstance(block[command_id.name.lower()], list):
                        block[command_id.name.lower()] = []
                    block[command_id.name.lower()].append(args[0] if len(args) == 1 else args)

        return story

# ==============================================================================
# 압축 해제 헬퍼 함수 (Decompression Helper Function)
# ==============================================================================
def unpack_packed_bit_vector(packed_vector, is_int=False):
    """Unity의 PackedBitVector 데이터를 실제 숫자 리스트로 압축 해제합니다."""
    if not packed_vector.m_Data:
        return []
    unpacked_values = []
    bit_pos = 0
    byte_data = bytes(packed_vector.m_Data)
    bit_size = packed_vector.m_BitSize
    if bit_size == 0:
        return [0.0] * packed_vector.m_NumItems if not is_int else [0] * packed_vector.m_NumItems
    for _ in range(packed_vector.m_NumItems):
        val = 0
        i = 0
        while i < bit_size:
            byte_index, bit_index_in_byte = divmod(bit_pos, 8)
            bits_left_in_byte = 8 - bit_index_in_byte
            bits_to_read = min(bit_size - i, bits_left_in_byte)
            mask = (1 << bits_to_read) - 1
            chunk = (byte_data[byte_index] >> bit_index_in_byte) & mask
            val |= chunk << i
            bit_pos += bits_to_read
            i += bits_to_read
        if is_int:
            unpacked_values.append(val)
        else:
            denominator = (1 << bit_size) - 1
            float_val = (val / denominator) * packed_vector.m_Range + packed_vector.m_Start if denominator != 0 else 0.0
            unpacked_values.append(float_val)
    return unpacked_values

# ==============================================================================
# 에셋 처리 클래스 (Asset Processor Class)
# ==============================================================================
class AssetProcessor:
    """에셋 파일 처리 로직을 캡슐화하는 클래스."""
    SPECIAL_TYPES = {
        "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
        "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
        "VideoClip": "Videos", "MovieTexture": "Videos", "Material": "Materials"
    }

    def __init__(self, file_path, output_path, base_input_path, log_queue):
        self.file_path = file_path
        self.output_path = output_path
        self.log_queue = log_queue
        self.base_name = os.path.basename(file_path)
        
        if base_input_path:
            relative_path = os.path.relpath(file_path, base_input_path)
            folder_path_without_ext, _ = os.path.splitext(relative_path)
            self.output_dir = os.path.join(self.output_path, folder_path_without_ext)
        else:
            folder_name_without_ext, _ = os.path.splitext(self.base_name)
            self.output_dir = os.path.join(self.output_path, folder_name_without_ext)

        self.env = None
        self.mesh_to_materials_map = {}
        self.fallback_count = 0 

    def log(self, message, level='INFO'):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        full_message = f"{timestamp}[{self.base_name}] {message}\n"
        self.log_queue.put((full_message, level.upper()))

    def _sanitize_filename(self, name):
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def _get_unique_path(self, path, obj_path_id):
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

    def _get_export_path(self, obj, extension, sub_folder=None):
        data = obj.read()
        base_name_asset = getattr(data, 'name', '') or getattr(data, 'm_Name', '') or obj.type.name
        folder_name = sub_folder or self.SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(self.output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True)
        sanitized_name = self._sanitize_filename(base_name_asset)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        return self._get_unique_path(initial_path, obj.path_id)

    def _preprocess_materials(self):
        """메시와 재질(Material)을 미리 매핑하여 성능 향상."""
        self.log("재질 및 렌더러 정보 사전 처리 중...")
        renderers = [obj for obj in self.env.objects if obj.type.name in ["MeshRenderer", "SkinnedMeshRenderer"]]
        for renderer_obj in renderers:
            try:
                renderer_data = renderer_obj.read()
                if hasattr(renderer_data, 'm_Mesh') and renderer_data.m_Mesh.path_id != 0:
                    mesh_path_id = renderer_data.m_Mesh.path_id
                    materials = [mat_pptr for mat_pptr in renderer_data.m_Materials if mat_pptr.path_id != 0]
                    if materials:
                        self.mesh_to_materials_map[mesh_path_id] = materials
            except Exception as e:
                self.log(f"렌더러(PathID:{renderer_obj.path_id}) 사전 처리 실패: {e}", "WARNING")

    def process_all_assets(self):
        """파일 내 모든 에셋을 처리하는 메인 메서드."""
        self.env = UnityPy.load(self.file_path)
        num_assets = len(self.env.objects)
        if num_assets == 0:
            self.log("처리할 에셋이 없어 건너뜁니다.", "WARNING")
            return 0
        
        self.log(f"처리 시작. 총 {num_assets}개의 에셋을 발견했습니다.")
        self._preprocess_materials()
        
        extracted_count = 0
        for obj in self.env.objects:
            if self._dispatch_asset(obj):
                extracted_count += 1
        
        success_log = f"추출 완료: 총 {num_assets}개 중 {extracted_count}개 저장 성공."
        if self.fallback_count > 0:
            success_log += f" (오류로 인해 {self.fallback_count}개는 .bin으로 저장)"
        self.log(success_log, "SUCCESS")

    def _dispatch_asset(self, obj):
        """에셋 타입에 따라 적절한 추출 메서드를 호출."""
        obj_type = obj.type.name
        try:
            if obj_type in ["Texture2D", "Sprite"]:
                return self._export_texture(obj)
            elif obj_type == "TextAsset":
                data = obj.read()
                asset_name = getattr(data, 'name', '') or getattr(data, 'm_Name', '')
                if asset_name.startswith('storydata_'):
                    return self._export_storydata_as_json(obj)
                else:
                    return self._export_textasset(obj, data)
            elif obj_type == "AudioClip":
                return self._export_audioclip(obj)
            elif obj_type == "Mesh":
                return self._export_mesh(obj)
            elif obj_type == "Font":
                return self._export_font(obj)
            else:
                if obj_type != "Material":
                    return self._export_generic_json(obj)
        except Exception as e:
            self.log(f"에셋(PathID:{obj.path_id}, Type:{obj_type}) 처리 중 오류 발생: {e}", "ERROR")
            if obj_type == "Mesh":
                self.log(f"메시 처리 실패. 원본 데이터를 .bin 파일로 저장합니다.", "WARNING")
                if self._export_raw_data(obj):
                    self.fallback_count += 1
                    return True
                return False
            else:
                try:
                    return self._export_generic_json(obj, error_info=str(e))
                except Exception as e2:
                    self.log(f"에셋(PathID:{obj.path_id}, Type:{obj.type.name}) JSON 저장 실패: {e2}", "ERROR")
        return False

    def _export_raw_data(self, obj):
        """에셋의 원본 바이트 데이터를 .bin 파일로 저장합니다."""
        try:
            path = self._get_export_path(obj, ".bin")
            raw_data = obj.get_raw_data()
            with open(path, "wb") as f:
                f.write(raw_data)
            return True
        except Exception as e:
            self.log(f"원본 데이터(PathID:{obj.path_id}) 저장 실패: {e}", "ERROR")
            return False

    def _export_texture(self, obj):
        data = obj.read()
        if data.image:
            path = self._get_export_path(obj, ".png")
            data.image.save(path)
            return True
        return False

    def _export_storydata_as_json(self, obj):
        """StoryData를 .bin으로 항상 저장하고, 추가로 JSON 역직렬화를 시도합니다."""
        data = obj.read()
        asset_name = getattr(data, 'name', '') or getattr(data, 'm_Name', '')
        
        # 1. 원본 보존을 위해 .bin 파일을 항상 먼저 저장합니다.
        bin_saved = self._export_textasset(obj, data)

        # 2. JSON 역직렬화 및 저장을 시도합니다.
        try:
            # TextAsset에서 원시 데이터를 다시 가져옵니다.
            script_data = getattr(data, 'script', None) or getattr(data, 'm_Script', None)

            # 가져온 데이터를 바이트 형식으로 변환합니다.
            script_bytes = None
            if isinstance(script_data, (bytes, bytearray)):
                script_bytes = script_data
            elif isinstance(script_data, str):
                script_bytes = script_data.encode('utf-8', 'surrogateescape')
            elif script_data is not None:
                script_bytes = str(script_data).encode('utf-8', 'surrogateescape')

            if not script_bytes:
                raise ValueError("Story_data가 비어있거나 바이트 형식으로 변환할 수 없습니다.")

            # 새로운 역직렬화 클래스를 사용하여 데이터를 변환합니다.
            deserialized_data = StoryDataDeserializer.deserialize(script_bytes)
            
            # .json 파일 경로를 가져옵니다. (sub_folder 인자 제거)
            path = self._get_export_path(obj, ".json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(deserialized_data, f, indent=4, ensure_ascii=False)
            self.log(f"StoryData '{asset_name}'를 JSON으로 성공적으로 변환했습니다.", "SUCCESS")
        
        except Exception as e:
            # JSON 변환 실패는 오류로 로그에 남기지만, 전체 처리를 실패로 간주하지는 않습니다.
            self.log(f"StoryData '{asset_name}' JSON 변환 실패: {e}.", "ERROR")
        
        # .bin 파일 저장 여부에 따라 최종 성공 여부를 반환합니다.
        return bin_saved


    def _export_textasset(self, obj, data=None):
        if data is None:
            data = obj.read()
        content = getattr(data, 'script', None) or getattr(data, 'm_Script', None)
        if content is not None:
            path = self._get_export_path(obj, ".bin")
            if isinstance(content, str):
                content = content.encode('utf-8', 'surrogateescape')
            elif not isinstance(content, (bytes, bytearray)):
                content = str(content).encode('utf-8', 'surrogateescape')

            with open(path, "wb",) as f:
                f.write(content)
            return True
        return False

    def _export_audioclip(self, obj):
        data = obj.read()
        if data.samples:
            for name, audio_data in data.samples.items():
                temp_obj = type('', (object,), {'type': obj.type, 'path_id': obj.path_id})()
                temp_obj.read = lambda: type('', (object,), {'m_Name': name})()
                path = self._get_export_path(temp_obj, ".wav")
                with open(path, "wb") as f:
                    f.write(audio_data)
            return True
        return False

    def _export_font(self, obj):
        data = obj.read()
        if hasattr(data, 'm_FontData') and data.m_FontData:
            font_data_bytes = bytes(data.m_FontData)
            extension = ".ttf" if not font_data_bytes.startswith(b"OTTO") else ".otf"
            path = self._get_export_path(obj, extension)
            with open(path, "wb") as f:
                f.write(font_data_bytes)
            return True
        return False
        
    def _export_generic_json(self, obj, error_info=None):
        path = self._get_export_path(obj, ".json")
        typetree = obj.read_typetree()
        if error_info:
            typetree["EXPORT_ERROR"] = error_info
        with open(path, "w", encoding="utf-8") as f:
            json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

    def _export_mesh(self, obj):
        data = obj.read()
        is_compressed = data.m_VertexData.m_VertexCount == 0 and hasattr(data, 'm_CompressedMesh') and data.m_CompressedMesh.m_Vertices.m_NumItems > 0
        
        if is_compressed:
            return self._export_compressed_mesh(obj, data)
        else:
            data_export = data.export()
            if data_export:
                path = self._get_export_path(obj, ".obj")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data_export)
                return True
        return False

    def _export_compressed_mesh(self, obj, data):
        """압축된 메시를 처리하여 .obj와 .mtl 파일을 생성합니다."""
        cm = data.m_CompressedMesh
        
        vertices = [unpack_packed_bit_vector(cm.m_Vertices)[i:i+3] for i in range(0, cm.m_Vertices.m_NumItems, 3)]
        uvs = [unpack_packed_bit_vector(cm.m_UV)[i:i+2] for i in range(0, cm.m_UV.m_NumItems, 2)]
        colors = [unpack_packed_bit_vector(cm.m_FloatColors)[i:i+4] for i in range(0, cm.m_FloatColors.m_NumItems, 4)]
        
        triangles_unpacked = unpack_packed_bit_vector(cm.m_Triangles, is_int=True)
        
        normals = [[0.0, 0.0, 0.0] for _ in range(len(vertices))]
        vertex_count = len(vertices)

        submesh_faces_map = {}
        if vertex_count > 0:
            for i, submesh in enumerate(data.m_SubMeshes):
                submesh_faces_map[i] = []
                index_size = 2 if data.m_IndexFormat == 0 else 4
                start_index = submesh.firstByte // index_size
                
                if start_index + submesh.indexCount > len(triangles_unpacked):
                    self.log(f"Submesh {i}의 인덱스 범위({start_index}-{start_index+submesh.indexCount})가 버퍼({len(triangles_unpacked)})를 초과합니다. 건너뜁니다.", "WARNING")
                    continue
                
                submesh_indices = triangles_unpacked[start_index : start_index + submesh.indexCount]
                base_vertex = submesh.baseVertex
                
                for j in range(0, len(submesh_indices), 3):
                    relative_face = submesh_indices[j:j+3]
                    if len(relative_face) < 3: continue
                    
                    absolute_face = [idx + base_vertex for idx in relative_face]
                    
                    if all(0 <= idx < vertex_count for idx in absolute_face):
                        submesh_faces_map[i].append(absolute_face)
                    else:
                        self.log(f"Submesh {i}에서 잘못된 최종 정점 인덱스 {absolute_face}를 가진 면 발견. 건너뜁니다.", "WARNING")

            for submesh_idx in submesh_faces_map:
                for face in submesh_faces_map[submesh_idx]:
                    idx1, idx2, idx3 = face
                    p1, p2, p3 = vertices[idx1], vertices[idx2], vertices[idx3]
                    edge1 = [p2[k] - p1[k] for k in range(3)]
                    edge2 = [p3[k] - p1[k] for k in range(3)]
                    face_normal = [
                        edge1[1] * edge2[2] - edge1[2] * edge2[1],
                        edge1[2] * edge2[0] - edge1[0] * edge2[2],
                        edge1[0] * edge2[1] - edge1[1] * edge2[0]
                    ]
                    for k in range(3):
                        normals[idx1][k] += face_normal[k]
                        normals[idx2][k] += face_normal[k]
                        normals[idx3][k] += face_normal[k]
            
            for i in range(len(normals)):
                normal = normals[i]
                length_sq = sum(comp**2 for comp in normal)
                if length_sq > 1e-12:
                    length = math.sqrt(length_sq)
                    normals[i] = [comp / length for comp in normal]

        materials = self.mesh_to_materials_map.get(obj.path_id, [])
        material_names = []
        mtl_content = ""
        
        if materials:
            for i, mat_pptr in enumerate(materials):
                try:
                    mat_obj = mat_pptr.read()
                    mat_name = self._sanitize_filename(mat_obj.name or f"mat_{i}")
                    material_names.append(mat_name)
                    
                    mat_lines = []
                    props = getattr(mat_obj, 'm_SavedProperties', None)
                    if props:
                        colors_dict = getattr(props, 'm_Colors', {})
                        for name, color in colors_dict.items():
                            if name == "_Color":
                                mat_lines.append(f"Kd {color.get('r', 1)} {color.get('g', 1)} {color.get('b', 1)}")
                                mat_lines.append(f"d {color.get('a', 1)}")

                        tex_envs_dict = getattr(props, 'm_TexEnvs', {})
                        for name, tex_env in tex_envs_dict.items():
                            texture_pptr = getattr(tex_env, 'm_Texture', None)
                            if name == "_MainTex" and texture_pptr and texture_pptr.path_id != 0:
                                tex_obj = texture_pptr.read()
                                tex_name = self._sanitize_filename(getattr(tex_obj, 'name', 'texture'))
                                mat_lines.append(f"map_Kd ../Textures/{tex_name}.png")
                    
                    if mat_lines:
                        mtl_content += f"newmtl {mat_name}\n"
                        mtl_content += "\n".join(f"  {line}" for line in mat_lines) + "\n\n"

                except Exception as e:
                    self.log(f"재질(PathID:{mat_pptr.path_id}) 처리 실패: {e}", "WARNING")
        
        obj_path = self._get_export_path(obj, ".obj")
        mtl_path = None
        
        if mtl_content:
            mtl_path = self._get_export_path(obj, ".mtl", sub_folder="Meshes")
            with open(mtl_path, "w", encoding="utf-8") as mtl_file:
                mtl_file.write(mtl_content.strip())
        
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write(f"# Extracted by Unity Asset Extractor\n")
            if mtl_path:
                f.write(f"mtllib {os.path.basename(mtl_path)}\n")

            for i, v in enumerate(vertices):
                f.write(f"v {v[0]} {v[1]} {v[2]}")
                if i < len(colors):
                    f.write(f" {colors[i][0]} {colors[i][1]} {colors[i][2]}")
                f.write("\n")
            for uv in uvs: f.write(f"vt {uv[0]} {uv[1]}\n")
            for n in normals: f.write(f"vn {n[0]} {n[1]} {n[2]}\n")

            for i, submesh in enumerate(data.m_SubMeshes):
                f.write(f"\ng {data.m_Name}_{i}\n")
                if i < len(material_names):
                    f.write(f"usemtl {material_names[i]}\n")
                
                faces_for_submesh = submesh_faces_map.get(i, [])
                for face in faces_for_submesh:
                    f1, f2, f3 = face[0] + 1, face[1] + 1, face[2] + 1
                    f.write(f"f {f1}/{f1}/{f1} {f2}/{f2}/{f2} {f3}/{f3}/{f3}\n")
        
        return True

# ==============================================================================
# 병렬 처리 워커 함수 (Worker Function for Parallel Processing)
# ==============================================================================
def process_single_file(file_path, output_path, base_input_path, log_queue, completion_queue):
    """단일 에셋 파일을 처리하는 독립적인 워커 함수."""
    try:
        processor = AssetProcessor(file_path, output_path, base_input_path, log_queue)
        processor.process_all_assets()
    except Exception as e:
        base_name = os.path.basename(file_path)
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        log_queue.put((f"{timestamp}[{base_name}] 파일 처리 중 심각한 오류 발생: {e}\n", "ERROR"))
    finally:
        completion_queue.put(True)

# ==============================================================================
# GUI 애플리케이션 클래스 (GUI Application Class)
# ==============================================================================
class AssetExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Unity 에셋 추출기 (전문가 버전 v4.5)")
        self.file_paths = []
        self.output_path = ""
        self.is_running = False
        self.processed_files_count = 0
        self.base_input_path = None

        self.manager = Manager()
        self.log_queue = self.manager.Queue()
        self.completion_queue = self.manager.Queue()
        self._setup_ui()
        self._center_window(800, 600)
        sys.stdout = TextRedirector(self.log_queue, "INFO")
        sys.stderr = TextRedirector(self.log_queue, "ERROR")
        self.root.after(100, self._process_queues)
        self._log("프로그램이 시작되었습니다. '메뉴'에서 파일을 선택해주세요.")

    def _center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="메뉴", menu=file_menu)
        file_menu.add_command(label="파일 열기", command=self._select_files)
        file_menu.add_command(label="폴더 열기", command=self._select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.root.quit)

        main_paned_window = PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        left_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(left_pane, width=240)
        
        list_frame = ttk.LabelFrame(left_pane, text="파일 목록")
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<Delete>", self._remove_selected_files)
        self.listbox_menu = tk.Menu(self.root, tearoff=0)
        self.listbox_menu.add_command(label="선택 항목 제거", command=self._remove_selected_files)
        self.listbox_menu.add_command(label="전체 항목 제거", command=self._remove_all_files)
        self.file_listbox.bind("<Button-3>", self._show_listbox_menu)
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu)
        
        log_frame = ttk.LabelFrame(main_paned_window, text="처리 내역")
        main_paned_window.add(log_frame)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        log_text_frame.grid_rowconfigure(0, weight=1)
        log_text_frame.grid_columnconfigure(0, weight=1)
        log_scrollbar = Scrollbar(log_text_frame)
        log_scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text = Text(log_text_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state='disabled', padx=5, pady=5)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_scrollbar.config(command=self.log_text.yview)
        
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", background="#FFF3CD", foreground="#856404")
        self.log_text.tag_config("ERROR", background="#F8D7DA", foreground="#721C24")
        self.log_text.tag_config("SUCCESS", background="#D4EDDA", foreground="#155724")

        progress_info_frame = ttk.Frame(log_frame)
        progress_info_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))
        progress_info_frame.grid_columnconfigure(1, weight=1)
        self.progress_label = ttk.Label(progress_info_frame, text="진행률: 대기 중")
        self.progress_label.grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.progress_bar = ttk.Progressbar(progress_info_frame, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=0, column=1, sticky='ew')
        
        bottom_controls_frame = ttk.Frame(self.root)
        bottom_controls_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom_controls_frame.grid_columnconfigure(0, weight=1)
        output_frame = ttk.LabelFrame(bottom_controls_frame, text="출력 폴더")
        output_frame.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.output_entry = ttk.Entry(output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(output_frame, text="찾아보기...", command=self._select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)
        start_button_container = ttk.LabelFrame(bottom_controls_frame, text="실행")
        start_button_container.grid(row=0, column=1, sticky='ns')
        self.start_button = ttk.Button(start_button_container, text="에셋 추출 시작", command=self._start_extraction)
        self.start_button.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _log(self, message, level='INFO'):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        log_message = f"{timestamp}{message}\n"
        self.log_queue.put((log_message, level.upper()))

    def _process_queues(self):
        try:
            scroll_at_bottom = self.log_text.yview()[1] >= 1.0
            self.log_text.config(state='normal')
            while not self.log_queue.empty():
                message, tag = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message, tag)
            self.log_text.config(state='disabled')
            if scroll_at_bottom:
                self.log_text.see(tk.END)
            
            while not self.completion_queue.empty():
                self.completion_queue.get_nowait()
                self.processed_files_count += 1
                self._update_progress_bar()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_queues)
    
    def _update_progress_bar(self):
        if self.is_running and self.file_paths:
            total_files = len(self.file_paths)
            self.progress_bar['value'] = self.processed_files_count
            self.progress_label.config(text=f"진행률: {self.processed_files_count} / {total_files}")
        else:
            self.progress_bar['value'] = 0
            self.progress_label.config(text="진행률: 대기 중")

    def _toggle_controls(self, enabled):
        state = 'normal' if enabled else 'disabled'
        self.start_button.config(state=state)
        self.output_button.config(state=state)
        try:
            self.menu_bar.entryconfig("메뉴", state=state)
        except tk.TclError:
            pass
    
    def _select_files(self):
        if self.is_running: return
        paths = filedialog.askopenfilenames(
            title="Unity3D 파일을 선택하세요",
            filetypes=(("Unity3D 파일", "*.unity3d"),)
        )
        if paths:
            self.base_input_path = None
            self._add_files_to_list(paths)
        
    def _select_folder(self):
        if self.is_running: return
        folder_path = filedialog.askdirectory(title="Unity3D 파일이 포함된 폴더를 선택하세요")
        if folder_path:
            self.base_input_path = folder_path
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log("폴더에서 Unity3D 파일을 찾지 못했습니다.", "WARNING")
            
    def _add_files_to_list(self, new_paths):
        current_paths_set = set(self.file_paths)
        added_count = 0
        for path in new_paths:
            if path not in current_paths_set:
                self.file_paths.append(path)
                current_paths_set.add(path)
                added_count += 1
        
        if added_count > 0:
            self.file_paths.sort()
            self.file_listbox.delete(0, tk.END)
            for path in self.file_paths:
                self.file_listbox.insert(tk.END, os.path.basename(path))
            self._log(f"{added_count}개의 새 파일을 목록에 추가했습니다. (총 {len(self.file_paths)}개)")
            
    def _remove_selected_files(self, event=None):
        if self.is_running: return
        selected_indices = self.file_listbox.curselection()
        if not selected_indices: return
        for index in sorted(selected_indices, reverse=True):
            del self.file_paths[index]
            self.file_listbox.delete(index)
        self._log(f"{len(selected_indices)}개의 파일을 목록에서 제거했습니다. (남은 파일: {len(self.file_paths)}개)")
        
    def _remove_all_files(self):
        if self.is_running: return
        if not self.file_paths: return
        total_count = len(self.file_paths)
        self.file_paths.clear()
        self.file_listbox.delete(0, tk.END)
        self.base_input_path = None
        self._log(f"모든 파일({total_count}개)을 목록에서 제거했습니다.")
        
    def _show_listbox_menu(self, event):
        if self.is_running: return
        self.listbox_menu.entryconfig("선택 항목 제거", state=tk.NORMAL if self.file_listbox.curselection() else tk.DISABLED)
        self.listbox_menu.entryconfig("전체 항목 제거", state=tk.NORMAL if self.file_paths else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)
        
    def _select_output_dir(self):
        if self.is_running: return
        path = filedialog.askdirectory(title="결과를 저장할 폴더를 선택하세요")
        if path:
            self.output_path = path
            self.output_entry.config(state='normal')
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)
            self.output_entry.config(state='readonly')
            self._log(f"출력 폴더를 '{path}'로 설정했습니다.")

    def _start_extraction(self):
        if not self.file_paths:
            messagebox.showwarning("시작 불가", "추출할 파일이 목록에 없습니다.")
            return
        if not self.output_path:
            messagebox.showwarning("시작 불가", "결과를 저장할 출력 폴더를 지정해주세요.")
            return
            
        self.is_running = True
        self._toggle_controls(False)
        self.processed_files_count = 0
        self.progress_bar.config(maximum=len(self.file_paths))
        self._update_progress_bar()
        thread = threading.Thread(target=self._run_process_pool, daemon=True)
        thread.start()

    def _run_process_pool(self):
        num_workers = min(cpu_count(), len(self.file_paths))
        self._log(f"병렬 처리를 시작합니다. (최대 {num_workers}개 프로세스 사용)")
        self._log("StoryData 자동 변환이 기본 활성화되었습니다.")

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            for file_path in self.file_paths:
                executor.submit(process_single_file, file_path, self.output_path, self.base_input_path, self.log_queue, self.completion_queue)
        
        executor.shutdown(wait=True)

        self.root.after(0, self._on_extraction_complete)

    def _on_extraction_complete(self):
        """추출 완료 후 UI를 업데이트하는 메서드."""
        self.is_running = False
        self._toggle_controls(True)
        self._log("========================================", "INFO")
        self._log("모든 파일 처리가 완료되었습니다.", "SUCCESS")


class TextRedirector:
    def __init__(self, queue_instance, tag="INFO"):
        self.queue = queue_instance
        self.tag = tag
    def write(self, text):
        if text.strip():
            self.queue.put((f"{datetime.now().strftime('[%H:%M:%S] ')}{text.strip()}\n", self.tag))
    def flush(self):
        pass

# ==============================================================================
# 애플리케이션 실행 진입점 (Entry Point)
# ==============================================================================
if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()

    root = tk.Tk()
    app = AssetExtractorApp(root)
    root.mainloop()
