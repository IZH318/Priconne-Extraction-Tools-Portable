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
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_frame = ttk.Frame(paned_window, padding=5)
        paned_window.add(left_frame)
        output_frame = ttk.LabelFrame(left_frame, text="출력 폴더 설정")
        output_frame.pack(fill=tk.X, pady=(0, 10))
        self.output_entry = ttk.Entry(output_frame, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.output_button = ttk.Button(output_frame, text="찾아보기...", command=self._select_output_dir)
        self.output_button.pack(side=tk.RIGHT, padx=(0, 5), pady=5)
        list_frame = ttk.LabelFrame(left_frame, text="작업할 파일 목록")
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_scrollbar = Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=list_scrollbar.set, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        list_scrollbar.config(command=self.file_listbox.yview)
        self.start_button = ttk.Button(left_frame, text="에셋 추출 시작", command=self._start_extraction_thread)
        self.start_button.pack(fill=tk.X, pady=(10, 0))

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

        status_frame = ttk.Frame(self.root, padding=5)
        status_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.file_progress_label = ttk.Label(status_frame, text="파일 (0/0)", width=12, anchor=tk.W)
        self.file_progress_label.pack(side=tk.LEFT, padx=(0, 5))
        self.asset_progress_label = ttk.Label(status_frame, text="에셋 (0/0)", width=15, anchor=tk.E)
        self.asset_progress_label.pack(side=tk.RIGHT, padx=(5, 0))
        progress_container = ttk.Frame(status_frame)
        progress_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progressbar = ttk.Progressbar(progress_container, orient='horizontal', mode='determinate')
        self.progressbar.pack(fill=tk.X, expand=True)
        style = ttk.Style(self.root)
        style.configure('Progress.TLabel', background=style.lookup('TFrame', 'background'), foreground='black')
        self.progress_label_center = ttk.Label(progress_container, text="대기 중...", style='Progress.TLabel', anchor=tk.CENTER)
        self.progress_label_center.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
    def _log(self, message, level='INFO'):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        log_message = f"{timestamp}{message}\n"
        self.log_queue.put((log_message, level.upper()))

    def _process_log_queue(self):
        try:
            self.log_text.config(state='normal')
            while not self.log_queue.empty():
                message, tag = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message, tag)
            self.log_text.config(state='disabled')
            self.log_text.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_log_queue)

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
        self.progressbar['value'] = 0
        thread = threading.Thread(target=self._process_all_files, daemon=True)
        thread.start()

    def _process_all_files(self):
        total_files = len(self.file_paths)
        self._log(f"총 {total_files}개의 파일에 대한 에셋 추출 작업을 시작합니다.")
        
        for i, file_path in enumerate(self.file_paths, 1):
            base_name = os.path.basename(file_path)
            output_dir = os.path.join(self.output_path, f"{base_name}_extracted")
            
            loading_msg = f"로딩 중: {base_name}"
            self.root.after(0, self._update_progress, i-1, total_files, 0, 1, loading_msg)
            self._log(f"======== 처리 시작: {base_name} ========")
            
            # ==================== 수정된 부분 ====================
            # UnityPy.load() 호출 전에 결과 폴더 경로를 미리 로그로 출력합니다.
            self._log(f"결과 저장 폴더: {output_dir}")
            # =======================================================
            
            env = None
            try:
                env = UnityPy.load(file_path)
                total_assets = len(env.objects)
                if total_assets == 0:
                    self._log(f"'{base_name}'에서 에셋을 찾을 수 없습니다.", "WARNING")
                    continue
                
                self._log(f"총 {total_assets}개의 에셋 발견. 추출을 시작합니다.")
                extracted_count = 0
                
                for j, obj in enumerate(env.objects, 1):
                    saved_path = self.export_asset(obj, output_dir)
                    
                    if saved_path:
                        extracted_count += 1
                        center_message = f"저장: {os.path.basename(saved_path)}"
                        self.root.after(0, self._update_progress, i, total_files, j, total_assets, center_message)
                    elif j % 100 == 0:
                        center_message = "처리 중..."
                        self.root.after(0, self._update_progress, i, total_files, j, total_assets, center_message)

                final_msg = f"완료: {base_name}"
                self.root.after(0, self._update_progress, i, total_files, total_assets, total_assets, final_msg)
                self._log(f"추출 완료: 총 {total_assets}개 중 {extracted_count}개 추출", "SUCCESS")
            except Exception as e:
                self._log(f"파일 '{base_name}' 처리 중 심각한 오류 발생: {e}", "ERROR")
            finally:
                if env: del env
        
        self.root.after(0, self._update_progress, total_files, total_files, 1, 1, "모든 작업 완료!")
        self._log("========================================", "SUCCESS")
        self._log("모든 파일 처리가 완료되었습니다.", "SUCCESS")
        self.is_running = False
        self.root.after(0, lambda: self._toggle_controls(True))

    def _update_progress(self, file_current, file_total, asset_current, asset_total, center_message):
        if file_total > 0:
            file_progress = (file_current - 1) / file_total
            asset_progress = (asset_current / asset_total) / file_total if asset_total > 0 else 0
            total_progress = (file_progress + asset_progress) * 100
            self.progressbar['value'] = total_progress
        
        self.file_progress_label.config(text=f"파일 ({file_current}/{file_total})")
        self.asset_progress_label.config(text=f"에셋 ({asset_current}/{asset_total})")
        self.progress_label_center.config(text=center_message)

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
