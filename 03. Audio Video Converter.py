import os
import sys
import subprocess
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, Listbox, Menu
import concurrent.futures
import urllib.request # requests 대신 urllib.request 사용
import zipfile
import shutil

# --- 다국어 텍스트 데이터 (원본으로 복원) ---
LANGUAGES = {
    'ko': {
        'window_title': "오디오/비디오 변환기",
        'video_tab': "비디오 변환기 (.usm → .mp4)",
        'audio_tab': "오디오 변환기 (.awb → .wav)",
        'input_section': "1. 원본 파일/폴더 선택",
        'add_files': "파일 추가",
        'add_folder': "폴더 추가",
        'file_list_section': "파일 목록",
        'output_section': "2. 저장 경로 선택",
        'browse': "경로 지정",
        'action_section': "3. 변환 실행",
        'start_conversion': "변환 시작",
        'cancel_conversion': "변환 중단",
        'overwrite_option': "기존 파일 덮어쓰기",
        'log_section': "처리 내역",
        # 메뉴 및 메시지
        'remove_selected': "선택 항목 제거",
        'remove_all': "전체 항목 제거",
        'alert_files_exist': "[알림] 선택한 파일들은 이미 목록에 존재합니다.",
        'log_files_added': "{count}개의 새 파일이 추가되었습니다.",
        'log_total_files': "총 파일 수: {total}개",
        'log_files_removed': "{count}개의 파일이 목록에서 삭제되었습니다.",
        'log_all_files_removed': "파일 목록 전체가 삭제되었습니다. ({count}개)",
        'log_conversion_cancelled': "사용자에 의해 변환 작업이 중단되었습니다.",
        'error_no_files': "[오류] 변환할 파일을 먼저 추가하세요.",
        'error_no_output_video': "[오류] 비디오를 저장할 경로를 지정하세요.",
        'error_no_output_audio': "[오류] 오디오를 저장할 경로를 지정하세요.",
        # 상태 라벨 텍스트
        'status_idle': "상태: 대기 중",
        'status_starting': "처리 시작... (총 {total}개)",
        'status_processing': "처리중: {current} / {total}",
        'status_complete': "완료: {current} / {total}",
        'status_cancelled': "중단됨: {current} / {total}",
        # 초기 상태 로그
        'env_check_header': "--- 프로그램 환경 점검 ---",
        'env_success': "  [성공] {tool_name} 발견",
        'env_path': "    > 경로: {path}",
        'env_error': "  [오류] {tool_name}을(를) 찾을 수 없음",
        'env_error_desc_video': "    > 비디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        'env_error_desc_audio': "    > 오디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        # FFmpeg 관련 새로운 설명 메시지 추가
        'env_error_desc_ffmpeg_auto_download': "    > 비디오 변환 시작 시 자동으로 FFmpeg 다운로드", # 이 부분 변경됨
        'env_check_footer': "--------------------------",
        # FFmpeg 관련 메시지 (추가)
        'ffmpeg_not_found': "[알림] FFmpeg (ffmpeg.exe)이 발견되지 않았습니다. {path} 경로로 다운로드 및 설치를 시도합니다.",
        'ffmpeg_already_exists': "[알림] FFmpeg (ffmpeg.exe)이 {path} 경로에 이미 존재합니다. (패스)",
        'ffmpeg_download_start': "  > FFmpeg 다운로드 시작: {url}",
        'ffmpeg_download_complete': "  > FFmpeg 다운로드 완료.",
        'ffmpeg_download_fail': "[오류] FFmpeg 다운로드 실패: {error}",
        'ffmpeg_extract_start': "  > FFmpeg 압축 해제 시작...",
        'ffmpeg_extract_complete': "  > FFmpeg 압축 해제 및 설치 완료: {path}",
        'ffmpeg_extract_fail': "[오류] FFmpeg 압축 해제 및 설치 실패: {error}",
        'ffmpeg_prepare_fail': "[오류] FFmpeg이 준비되지 않아 비디오 변환을 시작할 수 없습니다.",
        'ffmpeg_no_usm_path': "[오류] UsmToolkit.exe 경로를 알 수 없어 FFmpeg을 다운로드할 위치를 결정할 수 없습니다. 변환을 중단합니다.",
        'ffmpeg_zip_structure_error': "FFmpeg ZIP 파일 내부에 예상되는 폴더 구조를 찾을 수 없습니다.",
        'ffmpeg_exe_not_found_in_zip': "압축 해제 후 '{path}'를 찾을 수 없습니다. ZIP 파일 구조를 확인해주세요.",
        'ffmpeg_downloading': "FFmpeg 다운로드 중... (진행: {progress:.1f}%)",
    }
}

# --- 핵심 변환 로직 ---
class ConversionLogic:
    cpu_threads = os.cpu_count() or 1
    MAX_WORKERS = max(1, cpu_threads // 2)

    def __init__(self, log_queue, base_path):
        self.log_queue = log_queue
        self.base_path = base_path
        self._log(f"[시스템] 시스템 부하를 고려하여 최대 {self.MAX_WORKERS}개의 파일을 동시에 변환합니다.", 'video')
        self._log(f"[시스템] 시스템 부하를 고려하여 최대 {self.MAX_WORKERS}개의 파일을 동시에 변환합니다.", 'audio')

    def _log(self, message, target_tab):
        self.log_queue.put(('log', target_tab, message))

    def _get_relative_path(self, full_path):
        try: return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError): return str(full_path)

    def _run_subprocess(self, command):
        return subprocess.run(
            command, capture_output=True, text=True, encoding='utf-8',
            errors='ignore', check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

    # --- 비디오 변환 로직 (변경 없음) ---
    def _convert_single_video_task(self, usm_file_str, output_dir, usmtoolkit_path):
        usm_file = Path(usm_file_str)
        usmtoolkit_dir = usmtoolkit_path.parent
        extract_path = Path(output_dir) / (usm_file.stem + ".mp4")
        log_lines = ["\n" + "-" * 60, f"  [원본]\n    {self._get_relative_path(usm_file)}"]
        status = "unknown"
        if extract_path.exists():
            log_lines.append("\n  [결과]\n    이미 변환된 파일입니다. (건너뜀)")
            status = "skipped"
        else:
            command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(Path(output_dir).resolve())]
            try:
                result = subprocess.run(command, cwd=usmtoolkit_dir, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                if extract_path.exists():
                    log_lines.append(f"\n  [결과]\n    변환 성공: {self._get_relative_path(extract_path)}")
                    status = "success"
                else:
                    log_lines.append("\n  [결과]\n    [오류] 변환은 성공했으나 결과 파일이 없습니다.")
                    status = "error"
                tool_output = result.stdout.strip()
                if tool_output:
                    log_lines.append("\n  [상세 로그]")
                    log_lines.extend([f"    > {line}" for line in tool_output.splitlines()])
            except subprocess.CalledProcessError as e:
                log_lines.append(f"\n  [결과]\n    [오류] 변환 실패 - {usm_file.name}")
                status = "error"
                error_output = (e.stderr or e.stdout or "No error output.").strip()
                if error_output:
                    log_lines.append("\n  [상세 오류]")
                    log_lines.extend([f"    > {line}" for line in error_output.splitlines()])
            except Exception as e:
                log_lines.append(f"\n  [결과]\n    [오류] 치명적 예외 발생 - {e}")
                status = "error"
        log_lines.append("-" * 60)
        return status, log_lines

    def run_video_conversion(self, input_paths, output_dir, usmtoolkit_path, cancel_event):
        target_tab = 'video'
        self._log("\n--- 비디오 변환 작업을 시작합니다. ---", target_tab)
        self._log("[알림] 기존 파일은 항상 건너뜁니다.", target_tab)
        if not usmtoolkit_path:
            self._log("\n[오류] UsmToolkit.exe를 찾을 수 없습니다. 변환을 중단합니다.\n", target_tab)
            self.log_queue.put(('__VIDEO_DONE__', True))
            return
        total_files = len(input_paths)
        success_count, skipped_count, error_count, completed_tasks = 0, 0, 0, 0
        self.log_queue.put(('progress_start', target_tab, total_files))
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_single_video_task, path, output_dir, usmtoolkit_path): path for path in input_paths}
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_event.is_set(): break
                try:
                    status, log_lines = future.result()
                    for line in log_lines: self._log(line, target_tab)
                    if status == "success": success_count += 1
                    elif status == "skipped": skipped_count += 1
                    else: error_count += 1
                except Exception as e:
                    path = future_to_path[future]
                    self._log(f"  [오류] 작업자 실행 중 예외: {Path(path).name} - {e}", target_tab)
                    error_count += 1
                finally:
                    completed_tasks += 1
                    self.log_queue.put(('progress_update', target_tab, completed_tasks))
        if cancel_event.is_set(): self._log(f"\n{LANGUAGES['ko']['log_conversion_cancelled']}", target_tab)
        self._log("\n--- 비디오 변환 작업이 완료되었습니다. ---", target_tab)
        summary = f"총 {total_files}개 파일 중 {success_count}개 변환, {skipped_count}개 건너뜀, {error_count}개 오류.\n"
        self._log(summary, target_tab)
        self.log_queue.put(('__VIDEO_DONE__', cancel_event.is_set()))

    # --- 오디오 변환 로직 (새로운 로직) ---
    def run_audio_conversion(self, input_paths, output_dir, vgmstream_path, overwrite, cancel_event):
        target_tab = 'audio'
        self._log("\n--- 오디오 변환 작업을 시작합니다. ---", target_tab)
        self._log("[옵션] 기존 파일을 덮어씁니다." if overwrite else "[옵션] 기존 파일은 건너뜠습니다.", target_tab)

        if not vgmstream_path:
            self._log("\n[오류] vgmstream 실행 파일(test.exe)을 찾을 수 없습니다. 변환을 중단합니다.\n", target_tab)
            self.log_queue.put(('__AUDIO_DONE__', True))
            return
            
        total_files = len(input_paths)
        total_converted_tracks = 0
        completed_tasks = 0
        self.log_queue.put(('progress_start', target_tab, total_files))

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_path = {executor.submit(self._convert_audio_container, path, output_dir, vgmstream_path, overwrite, cancel_event): path for path in input_paths}
            for future in concurrent.futures.as_completed(future_to_path):
                if cancel_event.is_set(): break
                try:
                    converted_count, log_lines = future.result()
                    for line in log_lines: self._log(line, target_tab)
                    total_converted_tracks += converted_count
                except Exception as e:
                    path = future_to_path[future]
                    self._log(f"  [오류] 작업자 실행 중 예외: {Path(path).name} - {e}", target_tab)
                finally:
                    completed_tasks += 1
                    self.log_queue.put(('progress_update', target_tab, completed_tasks))
                    
        if cancel_event.is_set(): self._log(f"\n{LANGUAGES['ko']['log_conversion_cancelled']}", target_tab)

        self._log("\n--- 오디오 변환 작업이 완료되었습니다. ---", target_tab)
        self._log(f"총 {total_converted_tracks}개의 트랙이 WAV 파일로 변환되었습니다.\n", target_tab)
        self.log_queue.put(('__AUDIO_DONE__', cancel_event.is_set()))

    def _get_stream_count(self, file_path, vgmstream_path):
        result = self._run_subprocess([str(vgmstream_path), "-m", str(file_path)])
        if result.returncode != 0: return 0
        for line in result.stdout.splitlines():
            if line.startswith("stream count:"):
                try: return int(line.split(":")[1].strip())
                except (ValueError, IndexError): return 1
        return 1

    def _get_stream_name(self, file_path, stream_num, vgmstream_path):
        result = self._run_subprocess([str(vgmstream_path), "-m", "-s", str(stream_num), str(file_path)])
        if result.returncode != 0: return f"track_{stream_num}"
        for line in result.stdout.splitlines():
            if line.startswith("stream name:"):
                # 세미콜론(;)으로 구분된 이름 중 첫 번째 것을 사용
                return line.split(":")[1].strip().split(';')[0].strip()
        return f"track_{stream_num}"

    def _convert_audio_container(self, item_path_str, output_dir, vgmstream_path, overwrite, cancel_event):
        item_path = Path(item_path_str)
        log_lines = ["\n" + "-" * 60, f"  [원본]\n    {self._get_relative_path(item_path)}", "\n  [결과]"]
        total_converted = 0
        
        item_output_folder = Path(output_dir) / item_path.stem
        item_output_folder.mkdir(parents=True, exist_ok=True)

        num_streams = self._get_stream_count(item_path, vgmstream_path)
        if num_streams == 0:
            log_lines.append("    [오류] 파일의 스트림 정보를 읽을 수 없습니다.")
            log_lines.append("-" * 60)
            return 0, log_lines

        for i in range(1, num_streams + 1):
            if cancel_event.is_set(): break
            
            stream_name = self._get_stream_name(item_path, i, vgmstream_path)
            output_file = item_output_folder / f"{stream_name}.wav"

            if not overwrite and output_file.exists():
                log_lines.append(f"    알림: 이미 변환된 파일 (건너뜀) - {output_file.name}")
                continue

            command = [str(vgmstream_path), "-s", str(i), "-o", str(output_file), str(item_path)]
            result = self._run_subprocess(command)

            if result.returncode == 0 and output_file.exists():
                log_lines.append(f"    성공: {self._get_relative_path(output_file)}")
                total_converted += 1
            else:
                log_lines.append(f"    [오류] 스트림 #{i} 변환 실패 - {stream_name}")
                error_output = (result.stderr or result.stdout or "No error output.").strip()
                if error_output:
                    log_lines.append("\n    [상세 오류]")
                    log_lines.extend([f"      > {line}" for line in error_output.splitlines()])

        if cancel_event.is_set(): log_lines.append(f"\n{LANGUAGES['ko']['log_conversion_cancelled']}")
        log_lines.append("-" * 60)
        return total_converted, log_lines

# --- FFmpeg 다운로드 및 설치 클래스 ---
class FFmpegDownloader:
    # BtbN/FFmpeg-Builds의 최신 윈도우용 GPL 빌드 링크
    # 이 URL은 변경될 수 있으니, 작동하지 않으면 https://github.com/BtbN/FFmpeg-Builds/releases 에서 최신 릴리스를 확인하세요.
    FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    FFMPEG_ZIP_FILENAME = "ffmpeg_temp.zip"
    FFMPEG_EXE_NAME = "ffmpeg.exe"

    def __init__(self, log_queue, usmtoolkit_path_parent_dir: Path):
        self.log_queue = log_queue
        self.download_dir = usmtoolkit_path_parent_dir # UsmToolkit.exe가 있는 경로를 FFmpeg 설치 경로로 사용
        self.ffmpeg_path = self.download_dir / self.FFMPEG_EXE_NAME
        self.d = LANGUAGES['ko'] # 다국어 텍스트

        os.makedirs(self.download_dir, exist_ok=True) # 다운로드 디렉토리 생성 (필요하다면)

    def _log(self, message):
        # 'video' 탭의 로그로 보내기 위해 큐에 ('log', 'video', message) 형태로 삽입
        self.log_queue.put(('log', 'video', message))

    def _update_progress_status(self, progress_value=None):
        if progress_value is not None:
            self.log_queue.put(('progress_update_status', 'video', self.d['ffmpeg_downloading'].format(progress=progress_value), progress_value))
        else:
            self.log_queue.put(('progress_update_status', 'video', self.d['status_idle'], 0))

    def ensure_ffmpeg_ready(self) -> concurrent.futures.Future:
        """
        FFmpeg이 준비되었는지 확인하고, 필요하면 다운로드 및 설치를 시작합니다.
        이 과정은 비동기적으로 진행되며, Future 객체를 반환합니다.
        Future.result()는 성공 시 True, 실패 시 False를 반환합니다.
        """
        # 스레드 풀을 사용하여 다운로드 작업을 백그라운드에서 실행
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._actual_download_and_extract)
        return future

    def _actual_download_and_extract(self) -> bool:
        local_zip_path = self.download_dir / self.FFMPEG_ZIP_FILENAME
        temp_extract_dir = None

        if self.ffmpeg_path.exists():
            self._log(self.d['ffmpeg_already_exists'].format(path=self.download_dir))
            return True

        self._log(self.d['ffmpeg_not_found'].format(path=self.download_dir))

        try:
            # 1. FFmpeg ZIP 파일 다운로드
            self._log(self.d['ffmpeg_download_start'].format(url=self.FFMPEG_URL))
            self._update_progress_status(0) # 다운로드 시작 시 진행바 초기화

            with urllib.request.urlopen(self.FFMPEG_URL) as response:
                if response.status != 200:
                    raise Exception(f"HTTP Error: {response.status} {response.reason}")
                
                # total_size를 얻어 reporthook에 전달
                total_size = int(response.info().get('Content-Length', -1))
                block_size = 8192
                block_num = 0

                with open(local_zip_path, 'wb') as out_file:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        out_file.write(buffer)
                        block_num += 1
                        # 수동으로 진행 업데이트 (총 크기를 알 때만)
                        if total_size > 0:
                            progress = (block_num * block_size / total_size) * 100
                            self._update_progress_status(progress)

            self._log(self.d['ffmpeg_download_complete'])
            self._update_progress_status(100) # 다운로드 완료 시 진행바 채우기

            # 2. 압축 해제 및 ffmpeg.exe 찾기
            self._log(self.d['ffmpeg_extract_start'])
            temp_extract_dir = self.download_dir / "ffmpeg_extracted_temp"
            os.makedirs(temp_extract_dir, exist_ok=True)

            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                # ZIP 파일 내에서 ffmpeg.exe의 경로를 찾음 (예: ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe)
                ffmpeg_internal_path = None
                for name in zip_ref.namelist():
                    if name.endswith(f'/bin/{self.FFMPEG_EXE_NAME}'):
                        ffmpeg_internal_path = name
                        break
                
                if not ffmpeg_internal_path:
                    raise Exception(self.d['ffmpeg_zip_structure_error'])

                # ffmpeg.exe만 임시 폴더에 추출
                zip_ref.extract(ffmpeg_internal_path, temp_extract_dir)
                
                # 추출된 ffmpeg.exe의 실제 경로 (temp_extract_dir/ffmpeg-master.../bin/ffmpeg.exe)
                extracted_exe_full_path = temp_extract_dir / ffmpeg_internal_path
                
                # 최종 목적지로 이동
                shutil.move(extracted_exe_full_path, self.ffmpeg_path)
                
            self._log(self.d['ffmpeg_extract_complete'].format(path=self.ffmpeg_path))
            return True

        except Exception as e:
            self._log(self.d['ffmpeg_download_fail'].format(error=e))
            self._update_progress_status(0) # 실패 시 진행바 초기화
            return False
        finally:
            # --- 다운로드된 ZIP 파일과 임시 압축 해제 폴더 정리 ---
            if local_zip_path.exists():
                os.remove(local_zip_path)
                
            if temp_extract_dir and temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir)
            # --------------------------------------------------

# --- GUI 애플리케이션 ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.lang_data = LANGUAGES['ko']
        self.usmtoolkit_path, self.vgmstream_path = None, None # ffmpeg_path는 FFmpegDownloader에서 관리
        
        self.video_full_paths, self.audio_full_paths = [], []
        self.video_filenames_var, self.audio_filenames_var = tk.StringVar(), tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)

        self.video_cancel_event, self.audio_cancel_event = threading.Event(), threading.Event()
        self.video_total_files, self.audio_total_files = 0, 0
        
        self.base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        self.log_queue = queue.Queue()
        self.logic = ConversionLogic(self.log_queue, self.base_path)

        self._configure_window()
        self._find_tools()
        
        # FFmpegDownloader 인스턴스 생성
        # usmtoolkit_path가 발견되지 않았더라도 일단 기본 경로를 넘겨줌 (FFmpegDownloader 내부에서 에러 처리)
        ffmpeg_parent_dir = self.usmtoolkit_path.parent if self.usmtoolkit_path else self.base_path
        self.ffmpeg_downloader = FFmpegDownloader(self.log_queue, ffmpeg_parent_dir)

        self._setup_ui()
        self._log_initial_status()
        self._process_log_queue()

    def _configure_window(self):
        self.title(self.lang_data['window_title'])
        width, height = 800, 600
        self.geometry(f'{width}x{height}+{self.winfo_screenwidth()//2 - width//2}+{self.winfo_screenheight()//2 - height//2}')

    def _find_tools(self):
        # UsmToolkit, vgmstream 찾기
        for root, _, files in os.walk(self.base_path):
            if not self.usmtoolkit_path and "usmtoolkit.exe" in (f.lower() for f in files):
                self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "test.exe" in (f.lower() for f in files) and "vgmstream" in str(Path(root)).lower():
                self.vgmstream_path = Path(root) / "test.exe"
        
        # NOTE: ffmpeg.exe는 App 초기화 시 FFmpegDownloader가 관리하므로, 여기서 직접 찾지 않음
        # 단, App 시작 시 UsmToolkit.exe의 존재 여부는 알아야 FFmpegDownloader에게 올바른 경로를 줄 수 있음.


    def _setup_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.video_tab, self.audio_tab = ttk.Frame(self.notebook), ttk.Frame(self.notebook)
        
        self.notebook.add(self.video_tab, text=self.lang_data['video_tab'])
        self.notebook.add(self.audio_tab, text=self.lang_data['audio_tab'])
        
        self._create_tab_content(self.video_tab, 'video')
        self._create_tab_content(self.audio_tab, 'audio')
    
    def _log_initial_status(self):
        d = self.lang_data

        # 비디오 탭 환경 점검 로그 (UsmToolkit 및 FFmpeg)
        video_log_lines = [d['env_check_header']]
        if self.usmtoolkit_path:
            video_log_lines.extend([
                d['env_success'].format(tool_name="UsmToolkit.exe"),
                d['env_path'].format(path=self.logic._get_relative_path(self.usmtoolkit_path))
            ])
            # FFmpegDownloader에서 관리하는 ffmpeg_path를 사용
            if self.ffmpeg_downloader.ffmpeg_path.exists():
                video_log_lines.extend([
                    d['env_success'].format(tool_name="FFmpeg (ffmpeg.exe)"),
                    d['env_path'].format(path=self.logic._get_relative_path(self.ffmpeg_downloader.ffmpeg_path))
                ])
            else:
                video_log_lines.extend([
                    d['env_error'].format(tool_name="FFmpeg (ffmpeg.exe)"),
                    d['env_error_desc_ffmpeg_auto_download'] # 이 부분 변경됨
                ])
        else:
            video_log_lines.extend([
                d['env_error'].format(tool_name="UsmToolkit.exe"),
                d['env_error_desc_video']
            ])
            video_log_lines.extend([
                d['env_error'].format(tool_name="FFmpeg (ffmpeg.exe)"),
                d['env_error_desc_ffmpeg_auto_download'] # 이 부분도 변경됨 (UsmToolkit이 없어도 다운로드 시도 안내)
            ])
        video_log_lines.append(d['env_check_footer'] + "\n")
        self.log_to_gui('\n'.join(video_log_lines), self.video_log_text, clear_first=True)

        # 오디오 탭 환경 점검 로그 (vgmstream)
        audio_log_lines = [d['env_check_header']]
        if self.vgmstream_path:
            audio_log_lines.extend([
                d['env_success'].format(tool_name="vgmstream(test.exe)"),
                d['env_path'].format(path=self.logic._get_relative_path(self.vgmstream_path))
            ])
        else:
            audio_log_lines.extend([
                d['env_error'].format(tool_name="vgmstream(test.exe)"),
                d['env_error_desc_audio']
            ])
        audio_log_lines.append(d['env_check_footer'] + "\n")
        self.log_to_gui('\n'.join(audio_log_lines), self.audio_log_text, clear_first=True)


    def _create_tab_content(self, parent_tab, tab_type):
        d = self.lang_data
        is_audio_tab = (tab_type == 'audio')
        
        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(tab_pane, width=240)
        tab_pane.add(controls_frame) 
        
        log_frame_container = ttk.LabelFrame(tab_pane, text=d['log_section'])
        tab_pane.add(log_frame_container)
        
        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state='disabled')
        log_text_widget.pack(side='top', fill="both", expand=True, padx=5, pady=(5,0))
        
        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=(2,5))

        status_label = ttk.Label(status_frame, text=d['status_idle'])
        status_label.pack(side='left')
        
        progress_bar = ttk.Progressbar(status_frame, orient='horizontal', mode='determinate')
        progress_bar.pack(side='left', fill='x', expand=True, padx=(5,0))

        input_frame = ttk.LabelFrame(controls_frame, text=d['input_section'])
        input_frame.pack(fill='x', pady=5, padx=5)
        
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio_tab else [("USM Video files", "*.usm")]
        
        full_paths = self.audio_full_paths if is_audio_tab else self.video_full_paths
        filenames_var = self.audio_filenames_var if is_audio_tab else self.video_filenames_var
        
        add_files_btn = ttk.Button(input_frame, text=d['add_files'], command=lambda: self._add_files(file_types, full_paths, filenames_var, log_text_widget))
        add_files_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        add_folder_btn = ttk.Button(input_frame, text=d['add_folder'], command=lambda: self._add_folder(file_types, full_paths, filenames_var, log_text_widget))
        add_folder_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')

        list_container = ttk.LabelFrame(controls_frame, text=d['file_list_section'])
        list_container.pack(fill='both', expand=True, pady=5, padx=5)
        
        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
        scrollbar.pack(side='right', fill='y')
        listbox.config(yscrollcommand=scrollbar.set)
        self._create_right_click_menu(listbox, full_paths, filenames_var, log_text_widget)
        
        output_frame = ttk.LabelFrame(controls_frame, text=d['output_section'])
        output_frame.pack(fill='x', pady=5, padx=5)
        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        ttk.Button(output_frame, text=d['browse'], command=lambda: self._select_output_folder(output_entry)).pack(side='left', padx=5, pady=5)

        action_frame = ttk.LabelFrame(controls_frame, text=d['action_section'])
        action_frame.pack(fill='x', pady=5, padx=5)

        action_button = ttk.Button(action_frame, text=d['start_conversion'])
        
        widgets_dict = {'action_btn': action_button, 'add_files_btn': add_files_btn, 'add_folder_btn': add_folder_btn,
                        'output_entry': output_entry, 'progress': progress_bar, 'status_label': status_label}
                        
        if is_audio_tab:
            action_button.pack(side='left', pady=5, padx=5)
            overwrite_check = ttk.Checkbutton(action_frame, text=d['overwrite_option'], variable=self.audio_overwrite_var)
            overwrite_check.pack(side='left', pady=5, padx=10)
            action_button.config(command=lambda: self.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get()))
            widgets_dict['overwrite_check'] = overwrite_check
            self.audio_widgets = widgets_dict
            self.audio_log_text = log_text_widget
        else:
            action_button.pack(fill='x', pady=5, padx=5)
            action_button.config(command=lambda: self.start_video_conversion(output_entry.get()))
            self.video_widgets = widgets_dict
            self.video_log_text = log_text_widget
        
    def _create_right_click_menu(self, listbox, full_paths, filenames_var, log_widget):
        d = self.lang_data
        menu = Menu(listbox, tearoff=0)
        
        menu.add_command(label=d['remove_selected'], command=lambda: self._remove_selected_from_list(listbox, full_paths, filenames_var, log_widget))
        menu.add_command(label=d['remove_all'], command=lambda: self._clear_list(full_paths, filenames_var, log_widget))
        
        def show_menu(event):
            menu.entryconfig(d['remove_selected'], state="normal" if listbox.curselection() else "disabled")
            menu.entryconfig(d['remove_all'], state="normal" if listbox.size() > 0 else "disabled")
            menu.post(event.x_root, event.y_root)

        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self._remove_selected_from_list(listbox, full_paths, filenames_var, log_widget))

    def _set_ui_state(self, widgets, state):
        for widget_name, widget in widgets.items():
            if widget_name in ['action_btn', 'progress', 'status_label']: continue
            if isinstance(widget, ttk.Entry) and state == 'disabled': widget.config(state='readonly')
            else: widget.config(state=state)

    def _reset_video_ui_state(self):
        d = self.lang_data
        self._set_ui_state(self.video_widgets, 'normal')
        self.video_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_video_conversion(self.video_widgets['output_entry'].get()))
        self.video_widgets['status_label'].config(text=d['status_idle'])
        self.video_widgets['progress']['value'] = 0

    def _reset_audio_ui_state(self):
        d = self.lang_data
        self._set_ui_state(self.audio_widgets, 'normal')
        self.audio_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_audio_conversion(self.audio_widgets['output_entry'].get(), self.audio_overwrite_var.get()))
        self.audio_widgets['status_label'].config(text=d['status_idle'])
        self.audio_widgets['progress']['value'] = 0

    def _select_files(self, ft): return list(filedialog.askopenfilenames(title="파일을 선택하세요", filetypes=ft) or [])
    def _select_folder_and_search(self, ft):
        folder = filedialog.askdirectory(title="폴더를 선택하세요")
        if not folder: return []
        exts = [ext.strip('*.') for _, p in ft for ext in p.split()]
        return [str(Path(r) / f) for r, _, fs in os.walk(folder) for f in fs if any(f.lower().endswith(f".{ext}") for ext in exts)]
    
    def _select_output_folder(self, entry_widget):
        folder = filedialog.askdirectory(title="저장할 폴더를 선택하세요")
        if folder:
            entry_widget.config(state='normal'); entry_widget.delete(0, tk.END); entry_widget.insert(0, folder); entry_widget.config(state='readonly')

    def _update_listbox(self, fp, fv): fv.set([os.path.basename(p) for p in fp])
    def _add_paths_to_list(self, new_paths, full_paths, filenames_var, log_widget):
        if not new_paths: return
        d = self.lang_data
        unique_new_paths = [p for p in new_paths if p not in set(full_paths)]
        if not unique_new_paths: self.log_to_gui(f"\n{d['alert_files_exist']}\n", log_widget); return
        full_paths.extend(unique_new_paths)
        self._update_listbox(full_paths, filenames_var)
        self.log_to_gui(f"\n{d['log_files_added'].format(count=len(unique_new_paths))}\n{d['log_total_files'].format(total=len(full_paths))}\n", log_widget)
        
    def _add_files(self, ft, fp, fv, lw): self._add_paths_to_list(self._select_files(ft), fp, fv, lw)
    def _add_folder(self, ft, fp, fv, lw): self._add_paths_to_list(self._select_folder_and_search(ft), fp, fv, lw)
        
    def _remove_selected_from_list(self, lb, fp, fv, lw):
        sel_idx = lb.curselection()
        if not sel_idx: return
        for i in sorted(sel_idx, reverse=True): del fp[i]
        self._update_listbox(fp, fv)
        self.log_to_gui(f"\n{self.lang_data['log_files_removed'].format(count=len(sel_idx))}\n", lw)
        
    def _clear_list(self, fp, fv, lw):
        if not fp: return
        count = len(fp)
        fp.clear()
        self._update_listbox(fp, fv)
        self.log_to_gui(f"\n{self.lang_data['log_all_files_removed'].format(count=count)}\n", lw)

    def start_video_conversion(self, output_dir):
        d = self.lang_data
        if not self.video_full_paths: self.log_to_gui(f"\n{d['error_no_files']}\n", self.video_log_text); return
        if not output_dir: self.log_to_gui(f"\n{d['error_no_output_video']}\n", self.video_log_text); return
        
        # FFmpeg 다운로드 및 설치를 비동기적으로 시작하고 그 결과를 기다림
        self._start_ffmpeg_download_if_needed(output_dir)

    def _start_ffmpeg_download_if_needed(self, output_dir):
        d = self.lang_data
        # UsmToolkit.exe가 없으면 FFmpeg을 어디에 설치할지 알 수 없으므로 바로 중단
        if not self.usmtoolkit_path:
            self.log_to_gui(f"\n{d['ffmpeg_no_usm_path']}\n", self.video_log_text)
            self._reset_video_ui_state()
            return
            
        # GUI 비활성화 및 상태 업데이트
        self._set_ui_state(self.video_widgets, 'disabled')
        self.video_widgets['action_btn'].config(state='disabled') # 다운로드 중에는 버튼도 비활성화
        self.video_widgets['status_label'].config(text=d['ffmpeg_downloading'].format(progress=0.0))
        self.video_widgets['progress']['value'] = 0

        # FFmpeg 다운로드 및 설치 작업 시작 (비동기)
        download_future = self.ffmpeg_downloader.ensure_ffmpeg_ready()
        
        # 다운로드 작업 완료 시 호출될 콜백 등록
        def on_download_complete(future):
            ffmpeg_ready = future.result()
            if ffmpeg_ready:
                # 다운로드가 성공했으면 변환 작업 시작
                self.video_widgets['status_label'].config(text=d['status_idle']) # 다운로드 완료 후 상태 초기화
                self.video_widgets['progress']['value'] = 0 # 진행바 초기화
                threading.Thread(target=self.logic.run_video_conversion, daemon=True, args=(self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.video_cancel_event)).start()
                self.video_widgets['action_btn'].config(text=d['cancel_conversion'], command=self.cancel_video_conversion, state='normal')
            else:
                # 다운로드가 실패했으면 GUI를 원래 상태로 복원
                self.log_to_gui(f"\n{d['ffmpeg_prepare_fail']}\n", self.video_log_text)
                self._reset_video_ui_state()

        # Future가 완료되면 콜백을 GUI 스레드에서 실행하도록 설정
        download_future.add_done_callback(on_download_complete)


    def cancel_video_conversion(self):
        self.video_widgets['action_btn'].config(state='disabled'); self.video_cancel_event.set()

    def start_audio_conversion(self, output_dir, overwrite):
        d = self.lang_data
        if not self.audio_full_paths: self.log_to_gui(f"\n{d['error_no_files']}\n", self.audio_log_text); return
        if not output_dir: self.log_to_gui(f"\n{d['error_no_output_audio']}\n", self.audio_log_text); return

        self.audio_cancel_event.clear()
        self._set_ui_state(self.audio_widgets, 'disabled')
        self.audio_widgets['action_btn'].config(text=d['cancel_conversion'], command=self.cancel_audio_conversion)
        threading.Thread(target=self.logic.run_audio_conversion, daemon=True, args=(self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.audio_cancel_event)).start()

    def cancel_audio_conversion(self):
        self.audio_widgets['action_btn'].config(state='disabled'); self.audio_cancel_event.set()

    def log_to_gui(self, message, log_widget, clear_first=False):
        log_widget.config(state='normal')
        if clear_first: log_widget.delete('1.0', tk.END)
        log_widget.insert(tk.END, message)
        log_widget.config(state='disabled')
        log_widget.see(tk.END)

    def _process_log_queue(self):
        MAX_MESSAGES_PER_CYCLE = 200
        try:
            for _ in range(MAX_MESSAGES_PER_CYCLE):
                msg = self.log_queue.get_nowait()
                msg_type, *args = msg
                
                if msg_type.startswith('__'): 
                    was_cancelled = args[0]
                    d = self.lang_data
                    if msg_type == '__VIDEO_DONE__':
                        widgets, total = self.video_widgets, self.video_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_video_ui_state()
                    elif msg_type == '__AUDIO_DONE__':
                        widgets, total = self.audio_widgets, self.audio_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_audio_ui_state()
                
                elif msg_type == 'log':
                    target_tab, text = args
                    log_widget = self.video_log_text if target_tab == 'video' else self.audio_log_text
                    self.log_to_gui(text + '\n', log_widget)
                
                elif msg_type == 'progress_start':
                    target_tab, total = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    if target_tab == 'video': self.video_total_files = total
                    else: self.audio_total_files = total
                    
                    widgets['progress'].config(maximum=total, value=0)
                    widgets['status_label'].config(text=self.lang_data['status_starting'].format(total=total))
                
                elif msg_type == 'progress_update':
                    target_tab, value = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    total = self.video_total_files if target_tab == 'video' else self.audio_total_files
                    
                    widgets['progress']['value'] = value
                    widgets['status_label'].config(text=self.lang_data['status_processing'].format(current=value, total=total))
                
                # FFmpeg 다운로드 진행 상황 업데이트를 위한 새로운 큐 메시지 타입
                elif msg_type == 'progress_update_status':
                    target_tab, status_text, progress_value = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    widgets['status_label'].config(text=status_text)
                    widgets['progress']['value'] = progress_value

        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()