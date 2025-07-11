# ==============================================================================
# Unity 에셋 추출기 (Unity Asset Extractor)
# ------------------------------------------------------------------------------
# 이 스크립트는 Unity3D의 에셋 파일(.unity3d, .assets, .bundle)에서
# 내부 리소스(텍스처, 오디오, 메쉬 등)를 추출하는 GUI 애플리케이션입니다.
#
# 주요 기능:
# - Tkinter를 사용한 사용자 친화적 그래픽 인터페이스
# - `concurrent.futures.ProcessPoolExecutor`를 이용한 고성능 병렬 처리
# - `multiprocessing.Queue`를 통한 GUI와 워커 프로세스 간의 비동기 통신
# - 처리 중 GUI 멈춤 현상 방지를 위한 스레딩 및 큐(Queue) 폴링 메커니즘
# - 다양한 에셋 유형별 최적화된 추출 및 미지원 타입에 대한 JSON 폴백(Fallback)
# ==============================================================================

# --- 모듈 임포트 ---
# --- GUI 및 기본 유틸리티 모듈 ---
from datetime import datetime  # 로그 메시지에 타임스탬프 추가
import os                      # 파일 및 디렉토리 경로 관련 작업을 위함
import queue                   # 비동기 큐 처리 시 발생하는 예외 핸들링
import re                      # 파일명 생성을 위한 정규 표현식 사용
import sys                     # 표준 출력/오류를 리디렉션하여 GUI에 로그를 표시하기 위함
import tkinter as tk           # GUI 구성을 위한 파이썬 표준 라이브러리
from tkinter import ttk, filedialog, messagebox, Text, Scrollbar, PanedWindow # GUI 고급 위젯 및 대화상자 임포트

# --- 핵심 에셋 처리 모듈 ---
from PIL import Image          # Texture2D, Sprite 에셋을 이미지 파일로 변환 및 저장
import UnityPy                 # Unity 에셋 파일 파싱 및 데이터 추출을 위한 핵심 라이브러리

# --- 병렬 처리 및 비동기 관리를 위한 모듈 ---
import concurrent.futures      # 고수준의 프로세스 풀을 사용하여 병렬 처리를 쉽게 구현
import json                    # 미지원 에셋 타입의 데이터 구조를 저장하기 위함
from multiprocessing import Manager, cpu_count  # 프로세스 간 안전한 데이터 공유(Queue) 및 CPU 코어 수 확인
import threading               # GUI 멈춤 방지를 위해 블로킹(blocking) 작업을 별도 스레드에서 실행

# --- UnityPy 라이브러리 전역 설정 ---
# 특정 Unity 버전 정보가 없을 경우 사용할 기본(Fallback) 버전을 명시
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# --- 상수 정의 ---
# 에셋 타입에 따라 저장될 하위 폴더명을 매핑
SPECIAL_TYPES = {
    "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
    "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
    "VideoClip": "Videos", "MovieTexture": "Videos",
}
# 프로그램이 인식하고 처리할 수 있는 파일 확장자 목록
SUPPORTED_EXTENSIONS = ('.unity3d', '.assets', '.bundle')


# ==============================================================================
# 병렬 처리 워커 함수 (Worker Function for Parallel Processing)
# ==============================================================================
# ==============================================================================
# 병렬 처리 워커 함수 (Worker Function for Parallel Processing) - 수정된 버전
# ==============================================================================
def process_single_file(file_path, output_path, log_queue, progress_queue):
    """
    단일 에셋 파일을 처리하는 독립적인 워커(Worker) 함수.
    이 함수는 별도의 프로세스에서 실행되며, GUI와 직접 상호작용하지 않고
    큐(Queue)를 통해서만 상태와 로그를 전달.

    Args:
        file_path (str): 처리할 에셋 파일의 전체 경로.
        output_path (str): 추출된 파일이 저장될 최상위 폴더 경로.
        log_queue (multiprocessing.Queue): 로그 메시지를 GUI로 전달하기 위한 큐.
        progress_queue (multiprocessing.Queue): 파일별 진행 상황을 GUI로 전달하기 위한 큐.
    """
    # 로그 메시지에 어떤 파일에서 발생했는지 명시하기 위해 파일명 추출
    base_name = os.path.basename(file_path)

    # 이 워커 프로세스 내부에서 사용할 로그 기록용 헬퍼 함수
    def log(message, level='INFO'):
        # 메인 프로세스의 GUI와 통신하기 위해 (메시지, 로그 레벨) 튜플을 큐에 삽입
        log_queue.put((f"[{base_name}] {message}", level.upper()))

    try:
        # UnityPy를 사용하여 에셋 파일 로드
        env = UnityPy.load(file_path)
        objects = env.objects
        num_assets = len(objects)

        # 처리할 에셋이 없는 경우, 경고 로그를 남기고 즉시 종료
        if num_assets == 0:
            log("처리할 에셋이 없어 건너뜁니다.", "WARNING")
            # GUI에 이 파일의 처리가 완료되었음을 알리는 신호 전송
            progress_queue.put((file_path, -1, -1))
            return

        # 추출된 파일들을 저장할 개별 폴더 생성 (예: 'file.unity3d_extracted')
        output_dir = os.path.join(output_path, f"{base_name}_extracted")
        log(f"처리 시작. 총 {num_assets}개의 에셋을 발견했습니다.")
        extracted_count = 0

        # 파일명으로 사용할 수 없는 문자를 '_'로 치환하는 함수
        def sanitize_filename(name):
            return re.sub(r'[\\/:*?"<>|]', '_', name)

        # 동일한 경로에 파일이 이미 존재할 경우, 중복을 피하기 위해 고유한 이름을 생성하는 함수
        def get_unique_path(path, obj_path_id):
            if not os.path.exists(path):
                return path
            directory, filename = os.path.split(path)
            name, ext = os.path.splitext(filename)
            # 1차 중복 방지: 이름 뒤에 에셋의 고유 ID (path_id) 추가
            new_path = os.path.join(directory, f"{name} (#{obj_path_id}){ext}")
            if not os.path.exists(new_path):
                return new_path
            # 2차 중복 방지: path_id로도 중복될 경우, 뒤에 (1), (2)... 와 같이 숫자 추가
            count = 1
            base_name_for_counting = f"{name} (#{obj_path_id})"
            while True:
                final_path = os.path.join(directory, f"{base_name_for_counting} ({count}){ext}")
                if not os.path.exists(final_path):
                    return final_path
                count += 1
        
        # 에셋 객체와 확장자를 받아 최종 저장 경로를 결정하는 함수
        def get_export_path(obj, extension):
            data = obj.read()
            # 에셋의 이름(m_Name)을 가져오고, 이름이 없으면 타입과 ID로 대체
            base_name_asset = getattr(data, 'name', '') or getattr(data, 'm_Name', '') or f"{obj.type.name} (#{obj.path_id})"
            # SPECIAL_TYPES 딕셔너리를 참고하여 저장할 폴더 결정
            folder_name = SPECIAL_TYPES.get(obj.type.name, obj.type.name)
            dest_folder = os.path.join(output_dir, folder_name)
            os.makedirs(dest_folder, exist_ok=True)
            # 파일명 정리 및 고유 경로 생성
            sanitized_name = sanitize_filename(base_name_asset)
            initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
            return get_unique_path(initial_path, obj.path_id)

        # 파일 내의 모든 에셋(오브젝트)을 순회하며 처리
        for i, obj in enumerate(objects, 1):
            # GUI에 실시간 진행 상황 전송 (현재 파일, 처리중인 인덱스, 전체 개수)
            progress_queue.put((file_path, i, num_assets))
            saved_path = None
            try:
                obj_type = obj.type.name
                # --- 에셋 타입별 분기 처리 ---
                if obj_type in ["Texture2D", "Sprite"]:
                    data = obj.read()
                    if data.image:
                        path = get_export_path(obj, ".png")
                        data.image.save(path)  # PIL을 이용해 PNG로 저장
                        saved_path = path
                elif obj_type == "TextAsset":
                    data = obj.read()
                    content = getattr(data, 'script', None) or getattr(data, 'm_Script', None)
                    if content is not None:
                        path = get_export_path(obj, ".bin")
                        if isinstance(content, str):
                            # 문자열인 경우, 손상된 바이트 시퀀스를 포함할 수 있으므로
                            # 'surrogateescape'를 사용하여 데이터 손실 없이 인코딩
                            content = content.encode('utf-8', 'surrogateescape')
                        with open(path, "wb") as f:
                            f.write(content)
                        saved_path = path
                elif obj_type == "AudioClip":
                    data = obj.read()
                    if data.samples:
                        # AudioClip은 여러 개의 오디오 스트림을 포함할 수 있음
                        for idx, (name, audio_data) in enumerate(data.samples.items()):
                            # 각 오디오 클립에 맞는 고유 이름을 생성하기 위한 임시 객체
                            temp_obj_for_name = type('', (object,), {'type': obj.type, 'path_id': obj.path_id})()
                            temp_obj_for_name.read = lambda: type('', (object,), {'m_Name': name})()
                            path = get_export_path(temp_obj_for_name, ".wav")
                            with open(path, "wb") as f:
                                f.write(audio_data)
                            if idx == 0: saved_path = path # 대표 경로로 첫 번째 경로를 저장
                elif obj_type == "Mesh":
                    data = obj.read().export()  # UnityPy의 내장 .obj 변환 기능 사용
                    if data:
                        path = get_export_path(obj, ".obj")
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(data)
                        saved_path = path
                
                # ==========================================================
                # <<< 폰트 처리 블록 추가됨 >>>
                # ==========================================================
                elif obj_type == "Font":
                    data = obj.read()
                    # 폰트 데이터(m_FontData)가 있고, 비어있지 않은지 확인
                    if hasattr(data, 'm_FontData') and data.m_FontData:
                        font_data_bytes = bytes(data.m_FontData)
                        
                        # 폰트 시그니처(파일 헤더)를 확인하여 확장자 결정
                        # OpenType 폰트는 'OTTO'로 시작
                        extension = ".ttf"
                        if font_data_bytes.startswith(b"OTTO"):
                            extension = ".otf"
                        
                        # 헬퍼 함수를 사용하여 고유한 저장 경로 생성
                        path = get_export_path(obj, extension)
                        
                        # 폰트 바이너리 데이터를 파일에 쓰기
                        with open(path, "wb") as f:
                            f.write(font_data_bytes)
                        saved_path = path
                # ==========================================================
                
                else:  # 그 외 모든 지원/미지원 타입은 JSON으로 저장 (폴백)
                    path = get_export_path(obj, ".json")
                    typetree = obj.read_typetree()  # 에셋의 데이터 구조를 딕셔너리로 읽어옴
                    with open(path, "w", encoding="utf-8") as f:
                        # 직렬화 불가능한 객체는 에러 대신 문자열로 표기하여 덤프 중단을 방지
                        json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                    saved_path = path
                
                if saved_path:
                    extracted_count += 1
            except Exception as e:
                # 에셋 1개 처리 중 오류 발생 시, 전체 작업이 멈추지 않도록 예외 처리
                try:
                    # 실패한 에셋은 오류 정보와 함께 강제로 JSON으로 저장 시도
                    path = get_export_path(obj, ".json")
                    typetree = obj.read_typetree()
                    typetree["EXPORT_ERROR"] = str(e)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                    log(f"에셋(PathID:{obj.path_id}) 변환 실패, JSON으로 저장. 이유: {e}", "ERROR")
                except Exception as e2:
                    # JSON 저장조차 실패하는 최악의 경우
                    log(f"에셋(PathID:{obj.path_id}, Type:{obj.type.name}) 저장 완전 실패. 오류: {e2}", "ERROR")
        
        log(f"추출 완료: 총 {num_assets}개 중 {extracted_count}개 성공.", "SUCCESS")
    except Exception as e:
        # 파일 로드 등 심각한 오류 발생 시
        log(f"파일 처리 중 심각한 오류 발생: {e}", "ERROR")
    finally:
        # 성공/실패 여부와 관계없이, 이 파일에 대한 처리가 끝났음을 GUI에 알림
        progress_queue.put((file_path, -1, -1))

class TextRedirector:
    """
    표준 출력(stdout) 및 표준 오류(stderr)를 가로채 Tkinter 위젯으로 전달하기 위한 클래스.
    """
    def __init__(self, queue_instance, tag="INFO"):
        self.queue = queue_instance
        self.tag = tag

    def write(self, text):
        # write() 메소드가 호출되면, 텍스트를 메시지 큐에 넣어 메인 스레드로 전달
        if text.strip(): # 빈 줄은 무시
            self.queue.put((text, self.tag))

    def flush(self):
        # flush()는 호환성을 위해 필요하지만, 여기서는 아무 작업도 하지 않음
        pass


class AssetExtractorApp:
    """
    Unity 에셋 추출기 메인 애플리케이션 클래스.
    GUI 생성, 이벤트 처리, 병렬 처리 작업 관리 등 모든 로직 포함.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Unity 에셋 추출기")

        # --- 애플리케이션 상태 변수 ---
        self.file_paths = []  # 처리할 파일들의 경로 목록
        self.output_path = ""  # 결과물이 저장될 폴더 경로
        self.is_running = False  # 현재 추출 작업이 실행 중인지 여부를 나타내는 플래그

        # --- 프로세스 간 통신(IPC)을 위한 큐 ---
        # Manager.Queue()는 여러 프로세스에서 안전하게 접근할 수 있는 공유 큐를 생성
        self.manager = Manager()
        self.log_queue = self.manager.Queue()  # 워커 -> GUI 로그 메시지 전달용
        self.progress_queue = self.manager.Queue()  # 워커 -> GUI 진행 상황 전달용

        # --- UI 초기화 및 설정 ---
        self._setup_ui()
        self._center_window(800, 600)

        # --- 표준 출력/오류 리디렉션 ---
        # 이제부터 print()나 라이브러리 경고는 모두 self.log_queue로 들어감
        sys.stdout = TextRedirector(self.log_queue, "INFO")
        sys.stderr = TextRedirector(self.log_queue, "ERROR")

        # --- 비동기 큐 처리 시작 ---
        # 100ms 마다 _process_queues 함수를 호출하여 GUI를 업데이트
        self.root.after(100, self._process_queues)
        self._log("프로그램이 시작되었습니다. '메뉴'에서 파일을 선택해주세요.")
        self._update_progress_display()

    def _center_window(self, width, height):
        """애플리케이션 창을 화면 중앙에 위치시키는 헬퍼 함수."""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _setup_ui(self):
        """애플리케이션의 모든 GUI 위젯을 생성 및 배치."""
        # --- 메뉴 바 설정 ---
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="메뉴", menu=file_menu)
        file_menu.add_command(label="파일 열기", command=self._select_files)
        file_menu.add_command(label="폴더 열기", command=self._select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.root.quit)

        # --- 메인 레이아웃 (좌/우 분할) ---
        # PanedWindow를 사용해 사용자가 창 크기를 조절할 수 있게 함
        main_paned_window = PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # --- 왼쪽 패널 (파일 목록 / 진행 상황) ---
        self.left_column_pane = PanedWindow(main_paned_window, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        main_paned_window.add(self.left_column_pane, width=240)
        
        # 창이 그려진 후 분할선 위치를 설정하기 위한 이벤트 바인딩 (한 번만 실행)
        self.left_column_pane.bind("<Configure>", self._set_initial_sash_on_configure)

        # 왼쪽 상단: 파일 목록
        list_frame = ttk.LabelFrame(self.left_column_pane, text="파일 목록")
        self.left_column_pane.add(list_frame)
        list_scrollbar = Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        # 키보드 Delete 키로 항목 삭제 기능 바인딩
        self.file_listbox.bind("<Delete>", self._remove_selected_files)
        # 오른쪽 클릭 컨텍스트 메뉴 설정
        self.listbox_menu = tk.Menu(self.root, tearoff=0)
        self.listbox_menu.add_command(label="선택 항목 제거", command=self._remove_selected_files)
        self.listbox_menu.add_command(label="전체 항목 제거", command=self._remove_all_files)
        self.file_listbox.bind("<Button-3>", self._show_listbox_menu) # 오른쪽 클릭
        self.file_listbox.bind("<Button-2>", self._show_listbox_menu) # 가운데 클릭 (macOS 호환)

        # 왼쪽 하단: 실시간 진행 상황
        progress_frame = ttk.LabelFrame(self.left_column_pane, text="실시간 진행 상황")
        self.left_column_pane.add(progress_frame, height=120)
        progress_scrollbar = Scrollbar(progress_frame)
        progress_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.progress_text = Text(progress_frame, wrap=tk.WORD, yscrollcommand=progress_scrollbar.set, state='disabled', padx=5, pady=5)
        self.progress_text.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        progress_scrollbar.config(command=self.progress_text.yview)
        # 텍스트 스타일 태그 정의
        self.progress_text.tag_config('HEADER', font=('TkDefaultFont', 9, 'bold'))
        self.progress_text.tag_config('DETAIL')
        
        # --- 오른쪽 패널: 처리 내역 로그 ---
        log_frame = ttk.LabelFrame(main_paned_window, text="처리 내역")
        main_paned_window.add(log_frame)
        log_scrollbar = Scrollbar(log_frame)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.log_text = Text(log_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state='disabled', padx=5, pady=5)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        log_scrollbar.config(command=self.log_text.yview)
        
        # --- 하단 컨트롤 (출력 폴더, 시작 버튼) ---
        bottom_controls_frame = ttk.Frame(self.root)
        bottom_controls_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        bottom_controls_frame.grid_columnconfigure(0, weight=1) # 출력 폴더 프레임이 창 크기에 맞게 늘어나도록 설정

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

    def _set_initial_sash_on_configure(self, event):
        """PanedWindow의 분할선 위치를 창이 처음 그려질 때 한 번만 설정."""
        sash_y_position = event.height - 120 # 하단 진행 상황 창의 높이를 120px로 고정
        if sash_y_position > 0:
            try:
                # after_idle: 다른 UI 이벤트 처리가 끝난 후 실행하여 안정성 확보
                self.left_column_pane.after_idle(self.left_column_pane.sash_place, 0, 0, sash_y_position)
            except tk.TclError:
                # 창이 닫히는 등의 상황에서 위젯이 파괴되어 발생할 수 있는 오류 무시
                pass 
            finally:
                # 목적을 달성했으므로 더 이상 이벤트에 응답하지 않도록 바인딩 해제
                self.left_column_pane.unbind("<Configure>")

    def _log(self, message, level='INFO'):
        """
        GUI 로그 창에 표시할 메시지를 포맷하여 로그 큐에 할당.
        실제 로그 출력은 _process_queues에서 비동기적으로 처리.
        """
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        log_message = f"{timestamp}{message}\n"
        self.log_queue.put((log_message, level.upper()))

    def _process_queues(self):
        """
        백그라운드 프로세스에서 온 메시지 처리 및 GUI 업데이트.
        """
        try:
            # --- 로그 큐 처리 ---
            # 사용자가 스크롤을 맨 아래에 두었는지 확인하여 자동 스크롤 여부 결정
            scroll_at_bottom = self.log_text.yview()[1] >= 1.0
            self.log_text.config(state='normal') # Text 위젯을 수정 가능 상태로 변경
            while not self.log_queue.empty():
                message, tag = self.log_queue.get_nowait()
                # TODO: tag(level)에 따라 로그 색상을 다르게 표시하는 기능 추가 가능
                self.log_text.insert(tk.END, message)
            self.log_text.config(state='disabled') # 다시 읽기 전용으로 변경
            if scroll_at_bottom:
                self.log_text.see(tk.END) # 스크롤이 맨 아래였다면 계속 아래로 유지
            
            # --- 진행 상황 큐 처리 ---
            progress_updated = False
            while not self.progress_queue.empty():
                progress_updated = True
                file_path, current, total = self.progress_queue.get_nowait()
                # 워커에서 (..., -1, -1)을 보내면 해당 파일 처리가 끝났다는 신호
                if current == -1:
                    # 처리 중인 파일 목록에서 제거하고 완료 카운트 증가
                    self.files_in_progress.pop(file_path, None)
                    self.processed_files_count += 1
                else:
                    # 진행 중인 파일의 상태를 딕셔너리에 업데이트
                    self.files_in_progress[file_path] = (current, total)
            
            # 진행 상황에 변동이 있었을 경우에만 화면을 업데이트하여 불필요한 다시 그리기를 방지
            if progress_updated:
                self._update_progress_display()
        except queue.Empty:
            # 큐가 비어있는 것은 정상적인 상황이므로 아무것도 하지 않음
            pass
        finally:
            # 100ms 후에 다시 이 함수를 실행하도록 예약
            self.root.after(100, self._process_queues)

    def _update_progress_display(self):
        """'실시간 진행 상황' 텍스트 박스의 내용을 현재 상태에 맞게 갱신."""
        self.progress_text.config(state='normal')
        self.progress_text.delete('1.0', tk.END)

        if not self.is_running:
            self.progress_text.insert('1.0', "대기 중...")
        else:
            total_file_count = len(self.file_paths)
            header_text = f"전체 진행: {self.processed_files_count}/{total_file_count}개 파일 완료\n\n"
            self.progress_text.insert('1.0', header_text, 'HEADER')
            
            details = []
            for file, (cur, tot) in self.files_in_progress.items():
                details.append(f"  - 처리 중: {os.path.basename(file)} ({cur}/{tot})")
            
            self.progress_text.insert(tk.END, "\n".join(details), 'DETAIL')
        
        self.progress_text.config(state='disabled')

    def _toggle_controls(self, enabled):
        """작업 실행 여부에 따라 UI 컨트롤들의 활성/비활성 상태 전환."""
        state = 'normal' if enabled else 'disabled'
        self.start_button.config(state=state)
        self.output_button.config(state=state)
        try:
            # 메뉴 바의 상태 변경. 창 종료 시점에 호출될 수 있어 예외처리 추가
            self.menu_bar.entryconfig("메뉴", state=state)
        except tk.TclError:
            pass
    
    # --- 이하 사용자 이벤트 핸들러 함수들 ---
    def _select_files(self):
        """'메뉴 -> 파일 열기' 처리."""
        if self.is_running: return
        paths = filedialog.askopenfilenames(
            title="Unity3d, assets, AssetBundle 파일을 선택하세요",
            filetypes=(("모든 지원 파일", f"*{' *'.join(SUPPORTED_EXTENSIONS)}"),
                       ("Unity3D 파일", "*.unity3d"),
                       ("Assets 파일", "*.assets"),
                       ("AssetBundle 파일", "*.*"))
        )
        if paths: self._add_files_to_list(paths)
        
    def _select_folder(self):
        """'메뉴 -> 폴더 열기'를 처리하여 하위의 모든 지원 파일 찾기."""
        if self.is_running: return
        folder_path = filedialog.askdirectory(title="에셋이 포함된 폴더를 선택하세요")
        if folder_path:
            # os.walk를 사용하여 폴더 내 모든 지원 확장자 파일을 재귀적으로 검색
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths:
                self._add_files_to_list(found_paths)
            else:
                self._log("폴더에서 지원하는 파일을 찾지 못했습니다.", "WARNING")
            
    def _add_files_to_list(self, new_paths):
        """파일 목록(self.file_paths)에 중복을 피해 새 파일들을 추가, 리스트박스 업데이트."""
        current_paths_set = set(self.file_paths)
        added_count = 0
        for path in new_paths:
            if path not in current_paths_set:
                self.file_paths.append(path)
                current_paths_set.add(path)
                added_count += 1
        
        if added_count > 0:
            self.file_paths.sort() # 가나다 순으로 정렬
            self.file_listbox.delete(0, tk.END) # 기존 목록 전체 삭제
            for path in self.file_paths:
                self.file_listbox.insert(tk.END, os.path.basename(path)) # 새 목록 추가
            self._log(f"{added_count}개의 새 파일을 목록에 추가했습니다. (총 {len(self.file_paths)}개)")
            
    def _remove_selected_files(self, event=None):
        """파일 리스트박스에서 선택된 항목 제거."""
        if self.is_running: return
        selected_indices = self.file_listbox.curselection()
        if not selected_indices: return
        # 뒤에서부터 삭제해야 인덱스가 밀리는 문제를 방지할 수 있음
        for index in sorted(selected_indices, reverse=True):
            del self.file_paths[index]
            self.file_listbox.delete(index)
        self._log(f"{len(selected_indices)}개의 파일을 목록에서 제거했습니다. (남은 파일: {len(self.file_paths)}개)")
        
    def _remove_all_files(self):
        """파일 목록의 모든 항목 제거."""
        if self.is_running: return
        if not self.file_paths: return
        total_count = len(self.file_paths)
        self.file_paths.clear()
        self.file_listbox.delete(0, tk.END)
        self._log(f"모든 파일({total_count}개)을 목록에서 제거했습니다.")
        
    def _show_listbox_menu(self, event):
        """파일 리스트박스에서 우클릭 시 컨텍스트 메뉴 표시."""
        if self.is_running: return
        # 선택된 항목이 있을 때만 '선택 항목 제거' 활성화
        self.listbox_menu.entryconfig("선택 항목 제거", state=tk.NORMAL if self.file_listbox.curselection() else tk.DISABLED)
        # 목록에 파일이 있을 때만 '전체 항목 제거' 활성화
        self.listbox_menu.entryconfig("전체 항목 제거", state=tk.NORMAL if self.file_paths else tk.DISABLED)
        self.listbox_menu.post(event.x_root, event.y_root)
        
    def _select_output_dir(self):
        """'찾아보기...' 버튼을 눌러 출력 폴더를 선택하게 만듦."""
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
        """'에셋 추출 시작' 버튼의 메인 로직. 병렬 처리 시작."""
        # --- 유효성 검사 ---
        if not self.file_paths:
            messagebox.showwarning("시작 불가", "추출할 파일이 목록에 없습니다.")
            return
        if not self.output_path:
            messagebox.showwarning("시작 불가", "결과를 저장할 출력 폴더를 지정해주세요.")
            return
            
        # --- 상태 초기화 및 UI 잠금 ---
        self.is_running = True
        self._toggle_controls(False)
        self.processed_files_count = 0
        self.files_in_progress = {} # 현재 처리중인 파일 상태 딕셔너리
        self._update_progress_display()

        # --- 백그라운드 작업 시작 ---
        # ProcessPoolExecutor가 완료될 때까지 현재 스레드를 블로킹하므로, 
        # GUI 스레드가 멈추지 않도록 별도의 스레드에서 프로세스 풀 관리.
        thread = threading.Thread(target=self._run_process_pool, daemon=True)
        thread.start()

    def _run_process_pool(self):
        """
        `concurrent.futures.ProcessPoolExecutor`를 사용하여 워커 함수들을 병렬로 실행.
        이 함수는 GUI 스레드가 아닌 별도의 관리 스레드에서 실행.
        """
        # 사용할 프로세스(워커) 수를 CPU 코어 수와 파일 수 중 작은 값으로 제한
        num_workers = min(cpu_count(), len(self.file_paths))
        self._log(f"병렬 처리를 시작합니다. (최대 {num_workers}개 프로세스 사용)")
        
        # ProcessPoolExecutor를 'with' 구문과 함께 사용하면 작업 완료 후 자동 정리(shutdown)됨
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            # 모든 파일을 작업 큐에 제출 (submit은 즉시 반환되며, 비동기적으로 실행됨)
            for file_path in self.file_paths:
                executor.submit(process_single_file, file_path, self.output_path, self.log_queue, self.progress_queue)
        
        # --- 모든 작업 완료 후 처리 ---
        self.is_running = False
        # GUI 변경은 반드시 메인 스레드에서 수행해야 하므로, root.after를 사용해 스케줄링
        self.root.after(0, self._toggle_controls, True) # UI 컨트롤 잠금 해제
        self.root.after(0, self._update_progress_display) # 최종 상태 표시
        self._log("========================================")
        self._log("모든 파일 처리가 완료되었습니다.")


# ==============================================================================
# 애플리케이션 실행 진입점 (Entry Point)
# ==============================================================================
if __name__ == "__main__":
    # Tkinter 루트 윈도우 생성
    root = tk.Tk()
    # 애플리케이션 클래스 인스턴스화
    app = AssetExtractorApp(root)
    # Tkinter 이벤트 루프 시작
    root.mainloop()