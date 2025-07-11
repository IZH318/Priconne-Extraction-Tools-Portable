import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Text, Scrollbar, PanedWindow
import UnityPy
import os
import threading
from PIL import Image
import json
import re
from datetime import datetime
import sys
import queue

# --- UnityPy 설정 ---
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# --- 상수 정의 ---
SPECIAL_TYPES = {
    "Texture2D": "Textures", "Sprite": "Sprites", "TextAsset": "TextAssets",
    "AudioClip": "Audio", "Mesh": "Meshes", "Shader": "Shaders", "Font": "Fonts",
    "VideoClip": "Videos", "MovieTexture": "Videos",
}
SUPPORTED_EXTENSIONS = ('.unity3d', '.assets', '.bundle')

class TextRedirector:
    """모든 스트림(stdout, stderr) 출력을 지정된 Queue로 보냅니다."""
    def __init__(self, queue_instance, tag="INFO"):
        self.queue = queue_instance
        self.tag = tag

    def write(self, text):
        self.queue.put((text, self.tag))

    def flush(self):
        pass

class AssetExtractorApp:
    """고급 기능을 갖춘 Unity 에셋 추출기 GUI 애플리케이션입니다."""
    def __init__(self, root):
        self.root = root
        self.root.title("Unity 에셋 추출기 (v2.7 - 최종)")
        
        self.file_paths = []
        self.output_path = ""
        self.is_running = False
        
        self.log_queue = queue.Queue()

        self._setup_ui()
        self._center_window(800, 600)
        
        sys.stdout = TextRedirector(self.log_queue, "INFO")
        sys.stderr = TextRedirector(self.log_queue, "ERROR")

        self.root.after(100, self._process_log_queue)
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

        paned_window = PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 0))

        left_frame = ttk.Frame(paned_window, padding=5)
        paned_window.add(left_frame)
        
        list_frame = ttk.LabelFrame(left_frame, text="작업할 파일 목록")
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)

        right_frame = ttk.Frame(paned_window, padding=5)
        paned_window.add(right_frame)
        log_frame = ttk.LabelFrame(right_frame, text="처리 내역")
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_scrollbar = Scrollbar(log_frame)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = Text(log_frame, wrap=tk.WORD, yscrollcommand=log_scrollbar.set, state='disabled', background='#2b2b2b')
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_scrollbar.config(command=self.log_text.yview)
        self.log_text.tag_config('INFO', foreground='white')
        self.log_text.tag_config('SUCCESS', foreground='#4CAF50')
        self.log_text.tag_config('ERROR', foreground='#F44336')
        self.log_text.tag_config('WARNING', foreground='#FFC107')
        
        bottom_controls_frame = ttk.Frame(self.root, padding=(5, 0, 5, 5))
        bottom_controls_frame.pack(fill=tk.X, padx=5, pady=(5, 0))

        bottom_controls_frame.grid_columnconfigure(0, weight=1)

        output_frame = ttk.LabelFrame(bottom_controls_frame, text="출력 폴더 설정")
        output_frame.grid(row=0, column=0, sticky='ew', padx=(0, 10))

        self.output_entry = ttk.Entry(output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(output_frame, text="찾아보기...", command=self._select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)

        start_button_container = ttk.LabelFrame(bottom_controls_frame, text="실행")
        start_button_container.grid(row=0, column=1, sticky='ns')

        self.start_button = ttk.Button(start_button_container, text="에셋 추출 시작", command=self._start_extraction_thread)
        self.start_button.pack(expand=True, padx=6)
        
        status_frame = ttk.Frame(self.root, padding=5)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.progress_label_center = ttk.Label(status_frame, text="대기 중...", anchor=tk.CENTER)
        self.progress_label_center.pack(fill=tk.X, expand=True)

    def _log(self, message, level='INFO'):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        log_message = f"{timestamp}{message}\n\n"
        self.log_queue.put((log_message, level.upper()))

    def _process_log_queue(self):
        # ==================== 수정된 부분 ====================
        try:
            # 1. 로그를 추가하기 전에, 현재 스크롤바가 맨 아래에 있는지 확인합니다.
            # yview()는 (상단비율, 하단비율) 튜플을 반환하며, 하단비율이 1.0이면 맨 아래입니다.
            scroll_at_bottom = self.log_text.yview()[1] >= 1.0

            self.log_text.config(state='normal')
            while not self.log_queue.empty():
                message, tag = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message, tag)
            self.log_text.config(state='disabled')

            # 2. 스크롤바가 맨 아래에 있었을 경우에만 자동으로 스크롤을 내립니다.
            if scroll_at_bottom:
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_log_queue)
        # =======================================================

    def _toggle_controls(self, enabled):
        state = 'normal' if enabled else 'disabled'
        self.start_button.config(state=state)
        self.output_button.config(state=state)
        try: self.menu_bar.entryconfig("메뉴", state=state)
        except tk.TclError: pass

    def _select_files(self):
        if self.is_running: return
        paths = filedialog.askopenfilenames(title="Unity3d, assets, AssetBundle 파일을 선택하세요", filetypes=(("모든 지원 파일", f"*{' *'.join(SUPPORTED_EXTENSIONS)} *.*"), ("Unity3D 파일", "*.unity3d"), ("Assets 파일", "*.assets"), ("AssetBundle 파일", "*.*")))
        if paths: self._add_files_to_list(paths)

    def _select_folder(self):
        if self.is_running: return
        folder_path = filedialog.askdirectory(title="에셋이 포함된 폴더를 선택하세요")
        if folder_path:
            found_paths = [os.path.join(r, f) for r, _, fs in os.walk(folder_path) for f in fs if f.lower().endswith(SUPPORTED_EXTENSIONS)]
            if found_paths: self._add_files_to_list(found_paths)
            else: self._log("폴더에서 지원하는 파일을 찾지 못했습니다.", "WARNING")

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
            for path in self.file_paths: self.file_listbox.insert(tk.END, os.path.basename(path))
            self._log(f"{added_count}개의 새 파일을 목록에 추가했습니다. (총 {len(self.file_paths)}개)")
    
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

    def _start_extraction_thread(self):
        if not self.file_paths: messagebox.showwarning("시작 불가", "추출할 파일이 목록에 없습니다."); return
        if not self.output_path: messagebox.showwarning("시작 불가", "결과를 저장할 출력 폴더를 지정해주세요."); return
        self.is_running = True
        self._toggle_controls(False)
        thread = threading.Thread(target=self._process_all_files, daemon=True)
        thread.start()

    def _process_all_files(self):
        total_files = len(self.file_paths)
        self._log("전체 에셋 수를 계산하기 위해 파일을 스캔합니다...")
        self.root.after(0, self._update_progress, "파일 스캔 중...", False)
        
        grand_total_assets = 0
        asset_counts_per_file = {}
        for file_path in self.file_paths:
            try:
                env = UnityPy.load(file_path)
                num_assets = len(env.objects)
                grand_total_assets += num_assets
                asset_counts_per_file[file_path] = num_assets
                del env
            except Exception as e:
                self._log(f"파일 '{os.path.basename(file_path)}' 스캔 중 오류: {e}", "WARNING")
                asset_counts_per_file[file_path] = 0

        if grand_total_assets == 0:
            self._log("처리할 에셋을 찾지 못했습니다. 작업을 종료합니다.", "WARNING")
            self.root.after(0, self._update_progress, "에셋 없음", True)
            self.is_running = False
            self.root.after(0, lambda: self._toggle_controls(True))
            return

        self._log(f"총 {total_files}개 파일에서 {grand_total_assets}개의 에셋을 발견했습니다. 추출을 시작합니다.")
        
        cumulative_assets_processed = 0
        for i, file_path in enumerate(self.file_paths, 1):
            base_name = os.path.basename(file_path)
            output_dir = os.path.join(self.output_path, f"{base_name}_extracted")
            
            self._log(f"======== 처리 시작: {base_name} ========")
            self._log(f"결과 저장 폴더: {output_dir}")
            
            total_assets_in_file = asset_counts_per_file.get(file_path, 0)
            if total_assets_in_file == 0:
                self._log(f"'{base_name}'에서 에셋을 찾을 수 없습니다. 건너뜁니다.", "WARNING")
                message = f"파일 ({i}/{total_files}): {base_name}  /  추출된 에셋: 0/0"
                self.root.after(0, self._update_progress, message, False)
                continue

            env = None
            try:
                env = UnityPy.load(file_path)
                extracted_count = 0
                
                for j, obj in enumerate(env.objects, 1):
                    message = f"파일 ({i}/{total_files}): {base_name}  /  추출된 에셋: ({j}/{total_assets_in_file})개"
                    self.root.after(0, self._update_progress, message, False)
                    saved_path = self.export_asset(obj, output_dir)
                    if saved_path:
                        extracted_count += 1

                self._log(f"추출 완료: 총 {total_assets_in_file}개 중 {extracted_count}개 추출", "SUCCESS")

            except Exception as e:
                self._log(f"파일 '{base_name}' 처리 중 심각한 오류 발생: {e}", "ERROR")
            finally:
                if env:
                    del env
                cumulative_assets_processed += total_assets_in_file

        self.root.after(0, self._update_progress, "모든 작업 완료!", True)
        self._log("========================================")
        self._log("모든 파일 처리가 완료되었습니다.")
        self.is_running = False
        self.root.after(0, lambda: self._toggle_controls(True))

    def _update_progress(self, message, is_final=False):
        self.progress_label_center.config(text=message)

    def sanitize_filename(self, name):
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def get_unique_path(self, path, obj):
        if not os.path.exists(path): return path
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        new_path = os.path.join(directory, f"{name} (#{obj.path_id}){ext}")
        if not os.path.exists(new_path): return new_path
        count = 1
        base_name_for_counting = f"{name} (#{obj.path_id})"
        while True:
            final_path = os.path.join(directory, f"{base_name_for_counting} ({count}){ext}")
            if not os.path.exists(final_path): return final_path
            count += 1

    def get_export_path(self, obj, output_dir, extension):
        data = obj.read()
        base_name = getattr(data, 'name', '') or getattr(data, 'm_Name', '') or f"{obj.type.name} #{obj.path_id}"
        folder_name = SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True)
        sanitized_name = self.sanitize_filename(base_name)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        return self.get_unique_path(initial_path, obj)

    def export_asset(self, obj, output_dir):
        try:
            obj_type = obj.type.name
            if obj_type in ["Texture2D", "Sprite"]:
                data = obj.read()
                if data.image:
                    path = self.get_export_path(obj, output_dir, ".png")
                    data.image.save(path)
                    return path
            elif obj_type == "TextAsset":
                data = obj.read()
                content = getattr(data, 'script', None) or getattr(data, 'm_Script', None)
                if content is not None:
                    path = self.get_export_path(obj, output_dir, ".bin")
                    if isinstance(content, str): content = content.encode('utf-8', 'surrogateescape')
                    with open(path, "wb") as f: f.write(content)
                    return path
            elif obj_type == "AudioClip":
                data = obj.read()
                if not data.samples: return None
                saved_path = None
                for i, (name, audio_data) in enumerate(data.samples.items()):
                    temp_obj = type('',(object,),{'type':obj.type, 'path_id':obj.path_id})()
                    temp_obj.read = lambda: type('',(object,),{'m_Name':name})()
                    path = self.get_export_path(temp_obj, output_dir, ".wav")
                    with open(path, "wb") as f: f.write(audio_data)
                    if i == 0: saved_path = path
                return saved_path
            elif obj_type == "Mesh":
                path = self.get_export_path(obj, output_dir, ".obj")
                data = obj.read().export()
                if data:
                    with open(path, "w", encoding="utf-8") as f: f.write(data)
                    return path
            elif obj_type == "Shader":
                path = self.get_export_path(obj, output_dir, ".txt")
                data = obj.read().export()
                with open(path, "w", encoding="utf-8") as f: f.write(data)
                return path
            elif obj_type == "Font":
                data = obj.read()
                if not data.m_FontData: return None
                ext = ".otf" if data.m_FontData[:4] == b"OTTO" else ".ttf"
                path = self.get_export_path(obj, output_dir, ext)
                with open(path, "wb") as f: f.write(data.m_FontData)
                return path
            elif obj_type in ["VideoClip", "MovieTexture"]:
                data = obj.read()
                if not data.m_VideoData: return None
                ext = os.path.splitext(data.m_OriginalPath)[1] if data.m_OriginalPath else ".bin"
                path = self.get_export_path(obj, output_dir, ext)
                with open(path, "wb") as f: f.write(data.m_VideoData)
                return path
            else:
                path = self.get_export_path(obj, output_dir, ".json")
                typetree = obj.read_typetree()
                with open(path, "w", encoding="utf-8") as f: json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                return path
        except Exception as e:
            try:
                path = self.get_export_path(obj, output_dir, ".json")
                typetree = obj.read_typetree()
                typetree["EXPORT_ERROR"] = str(e)
                with open(path, "w", encoding="utf-8") as f: json.dump(typetree, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                self._log(f"  - [변환 실패] JSON 저장: {os.path.basename(path)} (이유: {e})", "ERROR")
            except Exception as e2:
                self._log(f"  - [저장 완전 실패] PathID: {obj.path_id}, Type: {obj.type.name}, Error: {e2}", "ERROR")
            return None
        return None

if __name__ == "__main__":
    root = tk.Tk()
    app = AssetExtractorApp(root)
    root.mainloop()