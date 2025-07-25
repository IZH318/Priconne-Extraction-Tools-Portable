# --- 필수 모듈 임포트 ---
# 시스템 및 운영체제 관련 모듈
import os                     # OS 기능 (경로, 파일 확인)
import sys                    # 시스템 관련 기능 (표준 출력 리디렉션)

# 데이터 처리 및 기본 라이브러리
from enum import Enum         # Enum 클래스 (열거형)
from datetime import datetime # 현재 시간 (로그 타임스탬프용)
import math                   # 수학 함수 (벡터 정규화)
import re                     # 정규 표현식 (파일명 필터링)
import base64                 # Base64 인코딩/디코딩
import json                   # JSON 데이터 처리
from struct import unpack     # 바이너리 데이터 언패킹

# 동시성 및 병렬 처리 관련 모듈
import queue                  # 스레드 간 데이터 통신
import threading              # 스레드 생성/관리
import concurrent.futures     # 병렬 처리 (프로세스 풀)
from multiprocessing import Manager, cpu_count # 프로세스 간 데이터 공유, CPU 코어 수 확인

# 그래픽 사용자 인터페이스(GUI) 관련 모듈
import tkinter as tk          # GUI 라이브러리
from tkinter import ttk, filedialog, messagebox, Text, Scrollbar, PanedWindow # GUI 확장 위젯

# 서드파티(Third-Party) 라이브러리: 별도 설치 필요
from PIL import Image         # 이미지 처리 (Pillow)
import UnityPy                # UnityPy 에셋 번들 로드/처리

# --- UnityPy 전역 설정 ---
# 특정 Unity 버전이 명시되지 않은 에셋 파일 처리 시 사용할 기본 버전 설정
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# --- 상수 정의 ---
# 프로그램에서 지원하는 파일 확장자 정의
SUPPORTED_EXTENSIONS = ('.unity3d',)

# --- 다국어 리소스 ---
LANGUAGES = {
    'ko': {
        'window_title': "unity3d File Converter",
        'menu_file': "메뉴(Menu)",
        'menu_lang': "언어(Language)",
        'menu_about': "정보(About)",
        'file_open': "파일 열기",
        'folder_open': "폴더 열기",
        'exit': "종료",
        'lang_ko': "한국어",
        'lang_en': "English",
        'lang_ja': "日本語",
        'file_list': "파일 목록",
        'remove_selected': "선택 항목 제거",
        'remove_all': "전체 항목 제거",
        'log_history': "처리 내역",
        'progress': "진행률: ",
        'waiting': "대기 중",
        'output_folder': "출력 폴더",
        'browse': "찾아보기...",
        'run': "작업 시작",
        'start_extraction': "작업 시작",
        'program_started': "프로그램이 시작되었습니다. '메뉴'에서 파일을 선택해주세요.",
        'no_files_to_process': "폴더에서 Unity3D 파일을 찾지 못했습니다.",
        'added_files': "{count}개의 새 파일을 목록에 추가했습니다. (총 {total}개)",
        'removed_selected_files': "{count}개의 파일을 목록에서 제거했습니다. (남은 파일: {total}개)",
        'removed_all_files': "모든 파일({count}개)을 목록에서 제거했습니다.",
        'output_dir_set': "출력 폴더를 '{path}'로 설정했습니다.",
        'warn_no_files_title': "시작 불가",
        'warn_no_files_msg': "추출할 파일이 목록에 없습니다.",
        'warn_no_output_title': "시작 불가",
        'warn_no_output_msg': "결과를 저장할 출력 폴더를 지정해주세요.",
        'processing_started': "병렬 처리를 시작합니다. (최대 {num_workers}개 프로세스 사용)",
        'all_tasks_completed': "모든 파일 처리가 완료되었습니다.",
        'file_dialog_title': "Unity3D 파일을 선택하세요",
        'file_dialog_type': "Unity3D 파일",
        'folder_dialog_title': "Unity3D 파일이 포함된 폴더를 선택하세요",
        # AssetProcessor 로그
        'preprocess_renderer_info': "재질 및 렌더러 정보 사전 처리 중...",
        'preprocess_renderer_fail': "렌더러(PathID:{path_id}) 사전 처리 실패: {error}",
        'processing_started_assets': "처리 시작. 총 {count}개의 에셋을 발견했습니다.",
        'no_assets_to_process': "처리할 에셋이 없어 건너뜁니다.",
        'extraction_complete': "추출 완료: 총 {total}개 중 {success}개 저장 성공.",
        'extraction_complete_with_fallback': "추출 완료: 총 {total}개 중 {success}개 저장 성공. (오류로 인해 {fallback_count}개는 .bin으로 저장)",
        'asset_processing_error': "에셋(PathID:{path_id}, Type:{obj_type}) 처리 중 오류 발생: {error}",
        'mesh_fallback_info': "메시 처리 실패. 원본 데이터를 .bin 파일로 저장합니다.",
        'json_fallback_error': "에셋(PathID:{path_id}, Type:{obj_type}) JSON 저장 실패: {error}",
        'storydata_deserialization_fail': "StoryData '{asset_name}' 역직렬화 실패: {error}. 원본 .bin 파일로 저장합니다.",
        'storydata_deserialization_success': "StoryData '{asset_name}'를 JSON으로 성공적으로 변환했습니다.",
        'submesh_index_error': "Submesh {submesh_idx}의 인덱스 범위({start}-{end})가 버퍼({buffer_len})를 초과합니다. 건너뜁니다.",
        'invalid_vertex_index': "Submesh {submesh_idx}에서 잘못된 최종 정점 인덱스 {face}를 가진 면 발견. 건너뜁니다.",
        'material_process_fail': "재질(PathID:{path_id}) 처리 실패: {error}",
        'worker_process_error': "파일 처리 중 심각한 오류 발생: {error}",
        'about_header': "[ 프로그램 정보 ]",
        'about_label_program': "프로그램 이름",
        'about_label_version': "버전",
        'about_label_updated': "최종 업데이트",
        'about_label_license': "라이선스",
        'about_label_developer': "개발자",
        'about_label_website': "웹 사이트",
    },
    'en': {
        'window_title': "unity3d File Converter",
        'menu_file': "Menu",
        'menu_lang': "Language",
        'menu_about': "About",
        'file_open': "Open Files",
        'folder_open': "Open Folder",
        'exit': "Exit",
        'lang_ko': "한국어",
        'lang_en': "English",
        'lang_ja': "日本語",
        'file_list': "File List",
        'remove_selected': "Remove Selected",
        'remove_all': "Remove All",
        'log_history': "Log History",
        'progress': "Progress: ",
        'waiting': "Waiting",
        'output_folder': "Output Folder",
        'browse': "Browse...",
        'run': "Start Process",
        'start_extraction': "Start Process",
        'program_started': "Program started. Please select files from the 'Menu'.",
        'no_files_to_process': "No Unity3D files found in the folder.",
        'added_files': "Added {count} new files to the list. (Total: {total})",
        'removed_selected_files': "Removed {count} files from the list. (Remaining: {total})",
        'removed_all_files': "All files ({count}) have been removed from the list.",
        'output_dir_set': "Output folder set to '{path}'.",
        'warn_no_files_title': "Cannot Start",
        'warn_no_files_msg': "No files to extract in the list.",
        'warn_no_output_title': "Cannot Start",
        'warn_no_output_msg': "Please specify an output folder.",
        'processing_started': "Starting parallel processing. (Using up to {num_workers} processes)",
        'all_tasks_completed': "All file processing is complete.",
        'file_dialog_title': "Select Unity3D files",
        'file_dialog_type': "Unity3D Files",
        'folder_dialog_title': "Select a folder containing Unity3D files",
        # AssetProcessor Logs
        'preprocess_renderer_info': "Preprocessing material and renderer information...",
        'preprocess_renderer_fail': "Failed to preprocess renderer (PathID:{path_id}): {error}",
        'processing_started_assets': "Processing started. Found {count} assets.",
        'no_assets_to_process': "No assets to process, skipping.",
        'extraction_complete': "Extraction complete: Succeeded in saving {success} out of {total} assets.",
        'extraction_complete_with_fallback': "Extraction complete: Succeeded in saving {success} out of {total} assets. ({fallback_count} saved as .bin due to errors)",
        'asset_processing_error': "Error processing asset (PathID:{path_id}, Type:{obj_type}): {error}",
        'mesh_fallback_info': "Mesh processing failed. Saving original data as a .bin file.",
        'json_fallback_error': "Failed to save asset as JSON (PathID:{path_id}, Type:{obj_type}): {error}",
        'storydata_deserialization_fail': "Failed to deserialize StoryData '{asset_name}': {error}. Saving original .bin file.",
        'storydata_deserialization_success': "Successfully converted StoryData '{asset_name}' to JSON.",
        'submesh_index_error': "Submesh {submesh_idx} index range ({start}-{end}) exceeds buffer size ({buffer_len}). Skipping.",
        'invalid_vertex_index': "Found a face with an invalid final vertex index {face} in Submesh {submesh_idx}. Skipping.",
        'material_process_fail': "Failed to process material (PathID:{path_id}): {error}",
        'worker_process_error': "A critical error occurred while processing the file: {error}",
        'about_header': "[ Program Information ]",
        'about_label_program': "Program",
        'about_label_version': "Version",
        'about_label_updated': "Updated",
        'about_label_license': "License",
        'about_label_developer': "Developer",
        'about_label_website': "Website",
    },
    'ja': {
        'window_title': "unity3d File Converter",
        'menu_file': "メニュー(Menu)",
        'menu_lang': "言語(Language)",
        'menu_about': "情報(About)",
        'file_open': "ファイルを開く",
        'folder_open': "フォルダを開く",
        'exit': "終了",
        'lang_ko': "한국어",
        'lang_en': "English",
        'lang_ja': "日本語",
        'file_list': "ファイルリスト",
        'remove_selected': "選択項目を削除",
        'remove_all': "すべて削除",
        'log_history': "処理履歴",
        'progress': "進捗: ",
        'waiting': "待機中",
        'output_folder': "出力フォルダ",
        'browse': "参照...",
        'run': "実行",
        'start_extraction': "実行",
        'program_started': "プログラムが起動しました。「メニュー」からファイルを選択してください。",
        'no_files_to_process': "フォルダ内にUnity3Dファイルが見つかりませんでした。",
        'added_files': "{count}個の新しいファイルをリストに追加しました。(合計: {total}個)",
        'removed_selected_files': "{count}個のファイルをリストから削除しました。(残り: {total}個)",
        'removed_all_files': "すべてのファイル({count}個)をリストから削除しました。",
        'output_dir_set': "出力フォルダを「{path}」に設定しました。",
        'warn_no_files_title': "開始不可",
        'warn_no_files_msg': "抽出するファイルがリストにありません。",
        'warn_no_output_title': "開始不可",
        'warn_no_output_msg': "結果を保存する出力フォルダを指定してください。",
        'processing_started': "並列処理を開始します。(最大{num_workers}個のプロセスを使用)",
        'all_tasks_completed': "すべてのファイルの処理が完了しました。",
        'file_dialog_title': "Unity3Dファイルを選択してください",
        'file_dialog_type': "Unity3Dファイル",
        'folder_dialog_title': "Unity3Dファイルが含まれているフォルダを選択してください",
        # AssetProcessor Logs
        'preprocess_renderer_info': "マテリアルとレンダラー情報を事前処理中...",
        'preprocess_renderer_fail': "レンダラー(PathID:{path_id})の事前処理に失敗しました: {error}",
        'processing_started_assets': "処理を開始します。{count}個のアセットが見つかりました。",
        'no_assets_to_process': "処理するアセットがないため、スキップします。",
        'extraction_complete': "抽出完了: {total}個中{success}個のアセットの保存に成功しました。",
        'extraction_complete_with_fallback': "抽出完了: {total}個中{success}個のアセットの保存に成功しました。(エラーのため{fallback_count}個は.binとして保存)",
        'asset_processing_error': "アセット(PathID:{path_id}, Type:{obj_type})の処理中にエラーが発生しました: {error}",
        'mesh_fallback_info': "メッシュの処理に失敗しました。元のデータを.binファイルとして保存します。",
        'json_fallback_error': "アセットのJSON保存に失敗しました(PathID:{path_id}, Type:{obj_type}): {error}",
        'storydata_deserialization_fail': "StoryData '{asset_name}' のデシリアライズに失敗しました: {error}。元の.binファイルを保存します。",
        'storydata_deserialization_success': "StoryData '{asset_name}' をJSONに正常に変換しました。",
        'submesh_index_error': "サブメッシュ{submesh_idx}のインデックス範囲({start}-{end})がバッファサイズ({buffer_len})を超えています。スキップします。",
        'invalid_vertex_index': "サブメッシュ{submesh_idx}で無効な最終頂点インデックス{face}を持つ面が見つかりました。スキップします。",
        'material_process_fail': "マテリアル(PathID:{path_id})の処理に失敗しました: {error}",
        'worker_process_error': "ファイルの処理中に重大なエラーが発生しました: {error}",
        'about_header': "[ プログラム情報 ]",
        'about_label_program': "プログラム名",
        'about_label_version': "バージョン",
        'about_label_updated': "最終更新",
        'about_label_license': "ライセンス",
        'about_label_developer': "開発者",
        'about_label_website': "ウェブサイト",
    }
}

# ##################################################################
# Class: StoryDataDeserializer
#
# 목적: Unity 게임의 'StoryData' 에셋에 포함된 커스텀 바이너리 데이터를
#       분석하여 사람이 읽을 수 있는 JSON 형식으로 역직렬화.
#
# 주요 기능:
# 1. 스토리에 사용되는 명령어 ID를 Enum으로 정의.
# 2. 변형된 Base64 인코딩을 디코딩하고 UTF-8 문자열로 변환.
# 3. 바이너리 스트림을 순회하며 명령어와 인자(argument)를 파싱.
# 4. 파싱된 명령어들을 논리적인 JSON 구조로 재구성.
# ##################################################################
class StoryDataDeserializer:
    # --- 스토리 명령어 ID Enum ---
    # 바이너리 데이터에 사용되는 각 명령어의 고유 ID 정의
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

def unpack_packed_bit_vector(packed_vector, is_int=False):
    """
    Unity의 압축된 비트 벡터(m_PackedBitVector)를 정수/부동소수점 배열로 변환합니다.

    Args:
        packed_vector (UnityPy Object): m_PackedBitVector 타입의 UnityPy 객체.
        is_int (bool): 결과를 정수 배열로 반환할지 여부.

    Returns:
        list: 언패킹된 값들의 리스트.
    """
    if not packed_vector.m_Data:
        return []
    unpacked_values = []
    bit_pos = 0 # 현재 비트 위치
    byte_data = bytes(packed_vector.m_Data)
    bit_size = packed_vector.m_BitSize # 각 값의 비트 크기
    if bit_size == 0:
        return [0.0] * packed_vector.m_NumItems if not is_int else [0] * packed_vector.m_NumItems
    # 각 아이템 순회
    for _ in range(packed_vector.m_NumItems):
        val = 0
        i = 0
        while i < bit_size:
            # 비트 단위로 값 읽기
            byte_index, bit_index_in_byte = divmod(bit_pos, 8)
            bits_left_in_byte = 8 - bit_index_in_byte
            bits_to_read = min(bit_size - i, bits_left_in_byte)
            mask = (1 << bits_to_read) - 1
            chunk = (byte_data[byte_index] >> bit_index_in_byte) & mask
            val |= chunk << i
            bit_pos += bits_to_read
            i += bits_to_read
        if is_int: # 정수 반환
            unpacked_values.append(val)
        else: # 부동소수점 반환 (정규화)
            denominator = (1 << bit_size) - 1
            float_val = (val / denominator) * packed_vector.m_Range + packed_vector.m_Start if denominator != 0 else 0.0
            unpacked_values.append(float_val)
    return unpacked_values

# ##################################################################
# Class: AssetProcessor
#
# 목적: 단일 .unity3d 파일 내의 모든 에셋을 처리, 변환 및 저장하는 백엔드 로직 담당.
#
# 주요 기능:
# 1. 에셋 타입에 따라 적절한 처리 함수로 분기(_dispatch_asset).
# 2. Texture2D, Mesh, AudioClip 등 주요 에셋 타입을 각각의 포맷으로 변환.
# 3. StoryData와 같은 커스텀 에셋을 JSON으로 역직렬화.
# 4. 처리 중 발생하는 로그를 멀티프로세싱 큐를 통해 GUI로 전달.
# 5. 파일명 충돌 방지 및 유효하지 않은 문자 처리.
# ##################################################################
class AssetProcessor:
    # 에셋 타입별 기본 출력 폴더명 매핑
    SPECIAL_TYPES = {
        "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
        "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
        "VideoClip": "Videos", "MovieTexture": "Videos", "Material": "Materials"
    }

    def __init__(self, file_path, output_path, base_input_path, log_queue):
        """
        AssetProcessor 인스턴스 초기화.

        Args:
            file_path (str): 처리할 .unity3d 파일의 전체 경로.
            output_path (str): 결과물이 저장될 최상위 출력 폴더 경로.
            base_input_path (str | None): 폴더 단위로 열었을 경우의 기본 입력 폴더 경로.
            log_queue (Queue): GUI와 통신하기 위한 멀티프로세싱 큐.
        """
        self.file_path = file_path
        self.output_path = output_path
        self.log_queue = log_queue
        self.base_name = os.path.basename(file_path) # 현재 처리 중인 파일 이름
        
        # 입력 경로 구조를 보존하는 출력 폴더 경로 생성
        if base_input_path:
            relative_path = os.path.relpath(file_path, base_input_path)
            folder_path_without_ext, _ = os.path.splitext(relative_path)
            self.output_dir = os.path.join(self.output_path, folder_path_without_ext)
        else:
            folder_name_without_ext, _ = os.path.splitext(self.base_name)
            self.output_dir = os.path.join(self.output_path, folder_name_without_ext)

        self.env = None # UnityPy 환경 객체
        self.mesh_to_materials_map = {} # Mesh와 Material을 연결하기 위한 맵
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

    def _get_export_path(self, obj, extension, sub_folder=None):
        """에셋을 저장할 최종 경로를 결정하고 생성합니다."""
        data = obj.read()
        base_name_asset = getattr(data, 'name', '') or getattr(data, 'm_Name', '') or obj.type.name
        folder_name = sub_folder or self.SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(self.output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True) # 폴더 자동 생성
        sanitized_name = self._sanitize_filename(base_name_asset)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        return self._get_unique_path(initial_path, obj.path_id)

    def _preprocess_materials(self):
        """Mesh를 처리하기 전에 렌더러 정보를 스캔하여 Mesh-Material 관계를 미리 구축합니다."""
        self.log("preprocess_renderer_info")
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
                self.log('preprocess_renderer_fail', "WARNING", {'path_id': renderer_obj.path_id, 'error': e})

    def process_all_assets(self):
        """파일 내의 모든 에셋을 순회하며 처리를 시작하는 메인 함수입니다."""
        self.env = UnityPy.load(self.file_path) # 파일 로드
        num_assets = len(self.env.objects)
        if num_assets == 0:
            self.log("no_assets_to_process", "WARNING")
            return 0
        
        self.log('processing_started_assets', format_args={'count': num_assets})
        self._preprocess_materials() # 재질 정보 사전 처리
        
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
                if obj_type != "Material": # 알려지지 않은 타입은 JSON으로
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

    def _export_texture(self, obj):
        """Texture2D 또는 Sprite 에셋을 .png 파일로 저장합니다."""
        data = obj.read()
        if data.image:
            path = self._get_export_path(obj, ".png")
            data.image.save(path)
            return True
        return False

    def _export_storydata_as_json(self, obj):
        """'storydata_'로 시작하는 TextAsset을 JSON으로 역직렬화하여 저장합니다."""
        data = obj.read()
        asset_name = getattr(data, 'name', '') or getattr(data, 'm_Name', '')
        
        # 원본 .bin 파일은 항상 저장
        bin_saved = self._export_textasset(obj, data)

        try:
            # 스크립트 데이터 추출 및 바이트 변환
            script_data = getattr(data, 'script', None) or getattr(data, 'm_Script', None)
            script_bytes = None
            if isinstance(script_data, (bytes, bytearray)):
                script_bytes = script_data
            elif isinstance(script_data, str):
                script_bytes = script_data.encode('utf-8', 'surrogateescape')
            elif script_data is not None:
                script_bytes = str(script_data).encode('utf-8', 'surrogateescape')

            if not script_bytes:
                raise ValueError("Story_data is empty or cannot be converted to bytes.")

            # 역직렬화 및 JSON 저장
            deserialized_data = StoryDataDeserializer.deserialize(script_bytes)
            
            path = self._get_export_path(obj, ".json")
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
        """AudioClip 에셋을 .wav 파일로 저장합니다."""
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
        """Font 에셋을 .ttf 또는 .otf 파일로 저장합니다."""
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
        """처리 규칙이 없는 모든 에셋 타입을 TypeTree 기반의 .json 파일로 저장합니다."""
        path = self._get_export_path(obj, ".json")
        typetree = obj.read_typetree()
        if error_info:
            typetree["EXPORT_ERROR"] = error_info
        with open(path, "w", encoding="utf-8") as f:
            json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
        return True

    def _export_mesh(self, obj):
        """Mesh 에셋을 처리하여 .obj 파일로 저장합니다. 압축 여부를 확인하여 분기합니다."""
        data = obj.read()
        # 정점 데이터가 비어있고 압축 메시 데이터가 있으면 압축 메시지로 처리
        is_compressed = data.m_VertexData.m_VertexCount == 0 and hasattr(data, 'm_CompressedMesh') and data.m_CompressedMesh.m_Vertices.m_NumItems > 0
        
        if is_compressed:
            return self._export_compressed_mesh(obj, data)
        else:
            data_export = data.export() # UnityPy 기본 .obj 익스포트 기능 사용
            if data_export:
                path = self._get_export_path(obj, ".obj")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data_export)
                return True
        return False

    def _export_compressed_mesh(self, obj, data):
        """압축된 메시 데이터를 수동으로 언패킹하여 .obj 파일로 저장합니다."""
        cm = data.m_CompressedMesh
        
        # 각 데이터 스트림 언패킹
        vertices = [unpack_packed_bit_vector(cm.m_Vertices)[i:i+3] for i in range(0, cm.m_Vertices.m_NumItems, 3)]
        uvs = [unpack_packed_bit_vector(cm.m_UV)[i:i+2] for i in range(0, cm.m_UV.m_NumItems, 2)]
        colors = [unpack_packed_bit_vector(cm.m_FloatColors)[i:i+4] for i in range(0, cm.m_FloatColors.m_NumItems, 4)]
        
        triangles_unpacked = unpack_packed_bit_vector(cm.m_Triangles, is_int=True)
        
        normals = [[0.0, 0.0, 0.0] for _ in range(len(vertices))]
        vertex_count = len(vertices)

        # Submesh 별로 면(face) 정보 재구성
        submesh_faces_map = {}
        if vertex_count > 0:
            for i, submesh in enumerate(data.m_SubMeshes):
                submesh_faces_map[i] = []
                index_size = 2 if data.m_IndexFormat == 0 else 4 # 인덱스 포맷에 따른 크기
                start_index = submesh.firstByte // index_size
                
                if start_index + submesh.indexCount > len(triangles_unpacked):
                    self.log('submesh_index_error', 'WARNING', {'submesh_idx': i, 'start': start_index, 'end': start_index + submesh.indexCount, 'buffer_len': len(triangles_unpacked)})
                    continue
                
                submesh_indices = triangles_unpacked[start_index : start_index + submesh.indexCount]
                base_vertex = submesh.baseVertex # Submesh의 기준 정점 오프셋
                
                for j in range(0, len(submesh_indices), 3):
                    relative_face = submesh_indices[j:j+3]
                    if len(relative_face) < 3: continue
                    
                    absolute_face = [idx + base_vertex for idx in relative_face]
                    
                    if all(0 <= idx < vertex_count for idx in absolute_face):
                        submesh_faces_map[i].append(absolute_face)
                    else:
                        self.log('invalid_vertex_index', 'WARNING', {'submesh_idx': i, 'face': absolute_face})

            # 각 정점의 법선(normal) 벡터 계산 (면 법선의 합으로 근사)
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
            
            # 법선 벡터 정규화
            for i in range(len(normals)):
                normal = normals[i]
                length_sq = sum(comp**2 for comp in normal)
                if length_sq > 1e-12:
                    length = math.sqrt(length_sq)
                    normals[i] = [comp / length for comp in normal]

        # 재질(.mtl) 파일 생성
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
                    self.log('material_process_fail', 'WARNING', {'path_id': mat_pptr.path_id, 'error': e})
        
        # .obj 파일 및 .mtl 파일 쓰기
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

def process_single_file(file_path, output_path, base_input_path, log_queue, completion_queue):
    """
    단일 파일을 처리하는 독립적인 워커(worker) 함수. (멀티프로세싱용)
    
    Args:
        file_path (str): 처리할 파일 경로.
        output_path (str): 최상위 출력 폴더 경로.
        base_input_path (str | None): 입력 기준 폴더 경로.
        log_queue (Queue): GUI에 로그를 전달하기 위한 큐.
        completion_queue (Queue): GUI에 작업 완료 신호를 전달하기 위한 큐.
    """
    try:
        processor = AssetProcessor(file_path, output_path, base_input_path, log_queue)
        processor.process_all_assets()
    except Exception as e:
        # 심각한 오류 발생 시 로그 전송
        base_name = os.path.basename(file_path)
        log_queue.put(('log', base_name, 'worker_process_error', 'ERROR', {'error': e}))
    finally:
        # 작업 완료 신호 전송
        completion_queue.put(True)

# ##################################################################
# Class: AssetExtractorApp
#
# 목적: 프로그램의 메인 GUI 창 및 사용자 상호작용, 프로세스 관리 총괄.
#
# 주요 기능:
# 1. Tkinter를 이용한 GUI 생성 및 이벤트 처리.
# 2. 다국어 지원 및 UI 실시간 업데이트.
# 3. 파일/폴더 선택, 목록 관리 기능.
# 4. '작업 시작' 시 ProcessPoolExecutor를 사용해 백엔드 작업 병렬 실행.
# 5. Manager.Queue를 통해 워커 프로세스로부터 로그/상태를 비동기적으로 수신하여 GUI에 반영.
# ##################################################################
class AssetExtractorApp:
    # 프로그램 정보
    ABOUT_INFO = {
        'program': "unity3d File Converter",
        'version': "2.0.0",
        'updated': "2025-07-26",
        'license': "GNU General Public License v3.0",
        'developer': "(Github) IZH318",
        'website': "https://github.com/IZH318",
    }

    def __init__(self, root):
        """
        AssetExtractorApp 인스턴스 초기화.

        Args:
            root (tk.Tk): Tkinter의 최상위 창(root 윈도우).
        """
        self.root = root
        self.file_paths = [] # 처리할 파일 경로 리스트
        self.output_path = "" # 출력 폴더 경로
        self.is_running = False # 작업 실행 여부 플래그
        self.processed_files_count = 0 # 처리 완료된 파일 수
        self.base_input_path = None # 폴더 열기 시 기준 경로
        self.log_events = [] # 로그 재표시를 위한 이벤트 저장소

        self.lang = tk.StringVar(value='ko') # 언어 설정 변수
        self.lang.trace_add('write', self._on_language_change)

        # 멀티프로세싱 통신을 위한 Manager 큐
        self.manager = Manager()
        self.log_queue = self.manager.Queue()
        self.completion_queue = self.manager.Queue()
        self._setup_ui() # UI 구성
        self._center_window(800, 600) # 창 중앙 정렬
        sys.stdout = TextRedirector(self, "INFO")
        sys.stderr = TextRedirector(self, "ERROR")
        
        # 큐 폴링 시작
        self.root.after(100, self._process_queues)
        self._log('program_started')

    def _center_window(self, width, height):
        """윈도우를 화면 중앙에 배치합니다."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        """Tkinter 위젯들을 생성하고 배치합니다."""
        # 메뉴바 설정
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)

        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)

        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)
        self.menu_bar.add_command(label="", command=self._show_about_info)
        
        self.file_menu.add_command(label="", command=self._select_files)
        self.file_menu.add_command(label="", command=self._select_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="", command=self.root.quit)

        self.lang_menu.add_radiobutton(label=LANGUAGES['ko']['lang_ko'], variable=self.lang, value='ko')
        self.lang_menu.add_radiobutton(label=LANGUAGES['en']['lang_en'], variable=self.lang, value='en')
        self.lang_menu.add_radiobutton(label=LANGUAGES['ja']['lang_ja'], variable=self.lang, value='ja')

        # 메인 레이아웃 (좌: 파일 목록, 우: 로그)
        main_paned_window = PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 좌측 패널 (파일 목록)
        left_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(left_pane, width=240)
        
        self.list_frame = ttk.LabelFrame(left_pane, text="")
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(self.list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.file_listbox = tk.Listbox(self.list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<Delete>", self._remove_selected_files)
        
        # 우측 패널 (로그 및 진행률)
        self.log_frame = ttk.LabelFrame(main_paned_window, text="")
        main_paned_window.add(self.log_frame)
        self.log_frame.grid_rowconfigure(0, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)
        log_text_frame = ttk.Frame(self.log_frame)
        log_text_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 5))
        log_text_frame.grid_rowconfigure(0, weight=1)
        log_text_frame.grid_columnconfigure(0, weight=1)
        log_scrollbar = Scrollbar(log_text_frame)
        log_scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text = Text(log_text_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state='disabled', padx=5, pady=5)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        log_scrollbar.config(command=self.log_text.yview)
        
        # 로그 레벨별 태그 설정
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", background="#FFF3CD", foreground="#856404")
        self.log_text.tag_config("ERROR", background="#F8D7DA", foreground="#721C24")
        self.log_text.tag_config("SUCCESS", background="#D4EDDA", foreground="#155724")

        progress_info_frame = ttk.Frame(self.log_frame)
        progress_info_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))
        progress_info_frame.grid_columnconfigure(1, weight=1)
        self.progress_label = ttk.Label(progress_info_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.progress_bar = ttk.Progressbar(progress_info_frame, orient='horizontal', mode='determinate')
        self.progress_bar.grid(row=0, column=1, sticky='ew')
        
        # 하단 컨트롤 (출력 폴더, 시작 버튼)
        bottom_controls_frame = ttk.Frame(self.root)
        bottom_controls_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom_controls_frame.grid_columnconfigure(0, weight=1)
        self.output_frame = ttk.LabelFrame(bottom_controls_frame, text="")
        self.output_frame.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.output_entry = ttk.Entry(self.output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(self.output_frame, text="", command=self._select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)
        self.start_button_container = ttk.LabelFrame(bottom_controls_frame, text="")
        self.start_button_container.grid(row=0, column=1, sticky='ns')
        self.start_button = ttk.Button(self.start_button_container, text="", command=self._start_extraction)
        self.start_button.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 파일 목록 컨텍스트 메뉴
        self.listbox_menu = tk.Menu(self.root, tearoff=0)
        self.listbox_menu.add_command(label="", command=self._remove_selected_files)
        self.listbox_menu.add_command(label="", command=self._remove_all_files)
        self.file_listbox.bind("<Button-3>", self._show_listbox_menu)
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu)

        self._update_ui_text() # UI 텍스트 초기화

    def _on_language_change(self, *args):
        """언어 변경 시 UI 텍스트 업데이트 및 로그 재표시를 호출합니다."""
        self._update_ui_text()
        d = LANGUAGES[self.lang.get()]
        lang_name = d.get(f'lang_{self.lang.get()}', self.lang.get())
        self._redisplay_logs()

    def _update_ui_text(self):
        """UI의 모든 텍스트 요소를 현재 선택된 언어로 갱신합니다."""
        lang = self.lang.get()
        d = LANGUAGES[lang]
        self.root.title(d['window_title'])
        self.menu_bar.entryconfig(1, label=d['menu_file'])
        self.menu_bar.entryconfig(2, label=d['menu_lang'])
        self.menu_bar.entryconfig(3, label=d['menu_about'])
        self.file_menu.entryconfig(0, label=d['file_open'])
        self.file_menu.entryconfig(1, label=d['folder_open'])
        self.file_menu.entryconfig(3, label=d['exit'])
        self.list_frame.config(text=d['file_list'])
        self.log_frame.config(text=d['log_history'])
        self.output_frame.config(text=d['output_folder'])
        self.output_button.config(text=d['browse'])
        self.start_button_container.config(text=d['run'])
        self.start_button.config(text=d['start_extraction'])
        self.listbox_menu.entryconfig(0, label=d['remove_selected'])
        self.listbox_menu.entryconfig(1, label=d['remove_all'])
        self._update_progress_bar()

    def _redisplay_logs(self):
        """언어 변경 시, 저장된 로그 이벤트를 새 언어로 다시 렌더링합니다."""
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        for event in self.log_events:
            self._render_log_event(event)
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)

    def _add_log_event(self, message_key, level='INFO', format_args=None, prefix=None):
        """로그 이벤트를 내부 리스트에 저장하고 반환합니다."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event = (timestamp, prefix, message_key, level, format_args)
        self.log_events.append(event)
        return event

    def _render_log_event(self, event, widget=None):
        """단일 로그 이벤트를 로그 위젯에 렌더링합니다."""
        target_widget = widget or self.log_text
        timestamp, prefix, message_key, level, format_args = event
        
        if message_key == 'show_about_info':
            self._display_about_info_in_log(target_widget)
            return

        lang = self.lang.get()
        message_template = LANGUAGES[lang].get(message_key, message_key)
        
        if message_key == 'raw_text':
            message = format_args.get('text', '') if format_args else ''
        else:
            message = message_template.format(**format_args) if format_args else message_template
        
        log_prefix = f"[{prefix}] " if prefix else ""
        full_message = f"[{timestamp}] {log_prefix}{message}\n"
        
        target_widget.config(state='normal')
        target_widget.insert(tk.END, full_message, level)
        target_widget.config(state='disabled')

    def _log(self, message_key, level='INFO', format_args=None, prefix=None):
        """로그를 기록하고 즉시 화면에 표시합니다."""
        event = self._add_log_event(message_key, level, format_args, prefix)
        self._render_log_event(event)
        self.log_text.see(tk.END)

    def _show_about_info(self):
        """'정보' 메뉴 클릭 시 로그 기록을 트리거합니다."""
        self._log('show_about_info', level='INFO')

    def _display_about_info_in_log(self, widget):
        """'정보' 내용을 로그 위젯에 특수 포맷으로 표시합니다."""
        lang = self.lang.get()
        d = LANGUAGES[lang]
        separator = "-" * 70 + "\n"
        
        widget.config(state='normal')
        widget.insert(tk.END, separator, "INFO")
        
        header_text = f"{d['about_header']}\n"
        widget.insert(tk.END, header_text, "INFO")
        
        about_lines = []
        for key, value in self.ABOUT_INFO.items():
            label_key = f'about_label_{key}'
            label_text = d.get(label_key, key.capitalize())
            about_lines.append(f"  - {label_text} : {value}")
        
        widget.insert(tk.END, "\n".join(about_lines) + "\n", "INFO")
        widget.insert(tk.END, separator, "INFO")
        widget.config(state='disabled')

    def _process_queues(self):
        """
        주기적으로 실행되어 워커 프로세스로부터 온 메시지를 GUI에 반영합니다.
        GUI가 멈추지 않도록 비동기적으로 작동하는 핵심 부분입니다.
        """
        log_batch = []
        completion_batch_size = 0

        try:
            # 성능을 위해 메시지를 일괄 처리
            while not self.log_queue.empty():
                log_batch.append(self.log_queue.get_nowait())
            while not self.completion_queue.empty():
                self.completion_queue.get_nowait()
                completion_batch_size += 1
        except queue.Empty:
            pass

        # 로그 일괄 렌더링
        if log_batch:
            self.log_text.config(state='normal')
            for log_item in log_batch:
                log_type, *data = log_item
                if log_type == 'log':
                    prefix, message_key, level, format_args = data
                    event = self._add_log_event(message_key, level, format_args, prefix)
                    self._render_log_event(event)
                elif log_type == 'raw':
                    text, level = data
                    event = self._add_log_event('raw_text', level, {'text': text})
                    self._render_log_event(event)
            self.log_text.config(state='disabled')
            self.log_text.see(tk.END)

        # 진행률 일괄 업데이트
        if completion_batch_size > 0:
            self.processed_files_count += completion_batch_size
            self._update_progress_bar()

        # 다음 폴링 예약
        self.root.after(100, self._process_queues)
    
    def _update_progress_bar(self):
        """진행률 표시줄과 레이블의 상태를 현재 진행 상황에 맞게 업데이트합니다."""
        d = LANGUAGES[self.lang.get()]
        if self.is_running and self.file_paths:
            total_files = len(self.file_paths)
            self.progress_label.config(text=f"{d['progress']}{self.processed_files_count} / {total_files}")
            self.progress_bar['value'] = self.processed_files_count
        else:
            self.progress_bar['value'] = 0
            self.progress_label.config(text=f"{d['progress']}{d['waiting']}")

    def _toggle_controls(self, enabled):
        """작업 시작/종료 시 UI 컨트롤들의 활성화/비활성화 상태를 전환합니다."""
        state = 'normal' if enabled else 'disabled'
        self.start_button.config(state=state)
        self.output_button.config(state=state)
        try:
            self.menu_bar.entryconfig(1, state=state)
            self.menu_bar.entryconfig(2, state=state)
            self.menu_bar.entryconfig(3, state=state)
        except tk.TclError:
            pass
    
    def _select_files(self):
        """'파일 열기' 대화상자를 통해 파일을 선택하고 목록에 추가합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        paths = filedialog.askopenfilenames(
            title=d['file_dialog_title'],
            filetypes=((d['file_dialog_type'], "*.unity3d"),)
        )
        if paths:
            self.base_input_path = None
            self._add_files_to_list(paths)
        
    def _select_folder(self):
        """'폴더 열기' 대화상자를 통해 폴더 내의 모든 지원 파일을 목록에 추가합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        folder_path = filedialog.askdirectory(title=d['folder_dialog_title'])
        if folder_path:
            self.base_input_path = folder_path
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log('no_files_to_process', "WARNING")
            
    def _add_files_to_list(self, new_paths):
        """새 파일들을 중복 없이 정렬하여 목록과 리스트 박스에 추가합니다."""
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
            self._log('added_files', format_args={'count': added_count, 'total': len(self.file_paths)})
            
    def _remove_selected_files(self, event=None):
        """리스트 박스에서 선택된 항목들을 목록과 리스트 박스에서 제거합니다."""
        if self.is_running: return
        selected_indices = self.file_listbox.curselection()
        if not selected_indices: return
        
        count = len(selected_indices)
        for index in sorted(selected_indices, reverse=True):
            del self.file_paths[index]
            self.file_listbox.delete(index)
        self._log('removed_selected_files', format_args={'count': count, 'total': len(self.file_paths)})
        
    def _remove_all_files(self):
        """모든 파일을 목록에서 제거합니다."""
        if self.is_running: return
        if not self.file_paths: return
        count = len(self.file_paths)
        self.file_paths.clear()
        self.file_listbox.delete(0, tk.END)
        self.base_input_path = None
        self._log('removed_all_files', format_args={'count': count})
        
    def _show_listbox_menu(self, event):
        """파일 목록에서 우클릭 시 컨텍스트 메뉴를 표시합니다."""
        if self.is_running: return
        self.listbox_menu.entryconfig(0, state=tk.NORMAL if self.file_listbox.curselection() else tk.DISABLED)
        self.listbox_menu.entryconfig(1, state=tk.NORMAL if self.file_paths else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)
        
    def _select_output_dir(self):
        """'출력 폴더' 대화상자를 열고 선택된 경로를 저장합니다."""
        if self.is_running: return
        d = LANGUAGES[self.lang.get()]
        path = filedialog.askdirectory(title=d['output_folder'])
        if path:
            self.output_path = path
            self.output_entry.config(state='normal')
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)
            self.output_entry.config(state='readonly')
            self._log('output_dir_set', format_args={'path': path})

    def _start_extraction(self):
        """'작업 시작' 버튼 클릭 시 유효성 검사 후 백엔드 처리를 시작합니다."""
        d = LANGUAGES[self.lang.get()]
        if not self.file_paths:
            messagebox.showwarning(d['warn_no_files_title'], d['warn_no_files_msg'])
            return
        if not self.output_path:
            messagebox.showwarning(d['warn_no_output_title'], d['warn_no_output_msg'])
            return
            
        self.is_running = True
        self._toggle_controls(False)
        self.processed_files_count = 0
        self.progress_bar.config(maximum=len(self.file_paths))
        self._update_progress_bar()
        thread = threading.Thread(target=self._run_process_pool, daemon=True)
        thread.start()

    def _run_process_pool(self):
        """ProcessPoolExecutor를 생성하고 파일 처리 작업을 워커 프로세스에 제출합니다."""
        num_workers = min(cpu_count(), len(self.file_paths))
        self._log('processing_started', format_args={'num_workers': num_workers})

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            for file_path in self.file_paths:
                executor.submit(process_single_file, file_path, self.output_path, self.base_input_path, self.log_queue, self.completion_queue)
        
        executor.shutdown(wait=True)

        self.root.after(0, self._on_extraction_complete)

    def _on_extraction_complete(self):
        """모든 워커 프로세스가 종료된 후 호출됩니다."""
        self.root.after(200, self._finalize_completion) # 큐에 남은 메시지 처리를 위해 약간의 지연

    def _finalize_completion(self):
        """최종 완료 로그를 남기고 UI 컨트롤을 다시 활성화합니다."""
        self._log("raw_text", format_args={'text': "========================================"})
        self._log('all_tasks_completed', "SUCCESS")
        self.is_running = False
        self.root.after(0, self._toggle_controls, True)


# ##################################################################
# Class: TextRedirector
#
# 목적: `print`와 오류 출력을 GUI 텍스트 위젯으로 리디렉션.
#       UnityPy와 같이 내부적으로 print를 사용하는 라이브러리의 출력을
#       GUI에서 확인하기 위해 사용.
# ##################################################################
class TextRedirector:
    def __init__(self, app_instance, tag="INFO"):
        """
        TextRedirector 인스턴스 초기화.

        Args:
            app_instance (AssetExtractorApp): GUI 애플리케이션의 인스턴스.
            tag (str): 리디렉션된 텍스트에 적용할 기본 로그 레벨 태그.
        """
        self.app = app_instance
        self.tag = tag
    def write(self, text):
        """표준 출력을 가로채서 GUI의 로그 큐로 전송합니다."""
        # 빈 줄은 무시하고, 텍스트가 있을 경우에만 큐에 넣음
        if text.strip():
            self.app.log_queue.put(('raw', text.strip(), self.tag))
    def flush(self):
        """`flush` 호출을 처리하기 위한 빈 메서드 (호환성 목적)."""
        pass

# --- 프로그램 실행 진입점 ---
if __name__ == "__main__":
    # PyInstaller 등으로 패키징 시 Windows에서 멀티프로세싱을 위한 필수 코드
    from multiprocessing import freeze_support
    freeze_support()

    root = tk.Tk()
    app = AssetExtractorApp(root)
    root.mainloop()