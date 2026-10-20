from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, messagebox
import tempfile
import shutil
import threading
from typing import Any, Callable

from src.constants import DEFAULT_UNITY_VERSION
from src.utils.platform_open import open_with_default_app


class AssetBrowserWindow(tk.Toplevel):
    """Unity3D 파일의 에셋을 계층 구조로 탐색하고 더블클릭 시 임시 파일로 추출하여 OS 기본 프로그램으로 여는 창."""

    # 에셋 타입별 그룹 이름
    TYPE_GROUPS = {
        "Texture2D": "Textures", "Sprite": "Sprites", "Texture2DArray": "Textures",
        "AudioClip": "Audio", "TextAsset": "TextAssets", "MonoBehaviour": "MonoBehaviours",
        "Font": "Fonts", "Mesh": "Meshes", "Shader": "Shaders",
        "AnimationClip": "Animations", "Material": "Materials",
        "MovieTexture": "Video", "VideoClip": "Video",
    }

    # 에셋 타입별 추출 확장자
    TYPE_EXTENSIONS = {
        "Texture2D": ".png", "Sprite": ".png", "Texture2DArray": ".png",
        "AudioClip": None,  # 샘플에서 자동 결정
        "TextAsset": ".txt", "MonoBehaviour": ".json",
        "Font": ".ttf", "Mesh": ".obj", "Shader": ".txt",
        "AnimationClip": ".bin", "Material": ".json",
        "MovieTexture": ".ogv", "VideoClip": ".mp4",
    }

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """파일 시스템에 안전한 이름으로 변환합니다."""
        return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)

    @staticmethod
    def _format_file_size(size: int) -> str:
        """바이트 단위의 크기를 사람이 읽기 쉬운 문자열로 변환합니다."""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        file_path: str,
        lang_dict: dict[str, str],
        unity_version: str | None = None,
        app_temp_dir: str | None = None,
        generate_error_log: Callable[[list[tuple[str, str]], str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.file_path = file_path
        self.lang_dict = lang_dict
        self.unity_version = unity_version or DEFAULT_UNITY_VERSION
        self._generate_error_log = generate_error_log
        self._asset_map = {}  # tree item id → (obj, type_name)
        
        if app_temp_dir:
            self._preview_temp_dir = os.path.join(app_temp_dir, f"asset_browser_{id(self)}")
            os.makedirs(self._preview_temp_dir, exist_ok=True)
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix='priconne_asset_preview_')

        filename = os.path.basename(file_path)
        self.title(lang_dict.get('asset_browser_title', 'Asset Browser - {filename}').format(filename=filename))

        # 창을 화면 가운데에 배치
        win_w, win_h = 600, 500
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w // 2) - (win_w // 2)
        y = (screen_h // 2) - (win_h // 2)
        self.geometry(f'{win_w}x{win_h}+{x}+{y}')
        self.transient(master)

        self._build_ui()
        self._load_assets()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.deiconify()

    def _build_ui(self) -> None:
        """트리뷰 UI를 구성합니다."""
        d = self.lang_dict

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('type', 'size')
        self.tree = ttk.Treeview(frame, columns=columns, show='tree headings')
        self.tree.heading('#0', text=d.get('asset_col_name', 'Name'))
        self.tree.heading('type', text=d.get('asset_col_type', 'Type'))
        self.tree.heading('size', text=d.get('asset_col_size', 'Size'))
        self.tree.column('#0', width=300)
        self.tree.column('type', width=120)
        self.tree.column('size', width=80)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<Double-Button-1>', self._on_double_click)

    def _load_assets(self) -> None:
        """UnityPy로 파일을 로드하고 트리에 에셋을 표시합니다."""
        try:
            import UnityPy
            from UnityPy import config
            config.FALLBACK_UNITY_VERSION = self.unity_version
            env = UnityPy.load(self.file_path)
        except (OSError, ValueError, RuntimeError) as e:
            if self._generate_error_log:
                self._generate_error_log([(self.file_path, str(e))], context="Asset Browser Load")
            title = self.lang_dict.get('asset_error_title', 'Error')
            notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error log has been saved in the logs folder.')
            messagebox.showerror(title, f"{str(e)}\n\n{notice}", parent=self)
            return

        group_nodes = {}

        for obj in env.objects:
            type_name = obj.type.name
            group_name = self.TYPE_GROUPS.get(type_name, type_name)

            if group_name not in group_nodes:
                group_nodes[group_name] = self.tree.insert('', 'end', text=group_name, open=False)

            # 에셋 이름 추출
            try:
                data = obj.parse_as_object()
                name = getattr(data, 'm_Name', '') or f"PathID_{obj.path_id}"
            except AttributeError:
                name = f"PathID_{obj.path_id}"

            # 크기 계산
            try:
                size_str = self._format_file_size(obj.byte_size)
            except AttributeError:
                size_str = "?"

            item_id = self.tree.insert(group_nodes[group_name], 'end',
                                        text=name, values=(type_name, size_str))
            self._asset_map[item_id] = (obj, type_name)

    def _on_double_click(self, event: tk.Event) -> None:
        """트리 항목 더블클릭 시 임시 파일로 추출하여 OS 기본 프로그램으로 엽니다."""
        item_id = self.tree.focus()
        if item_id not in self._asset_map:
            return

        obj, type_name = self._asset_map[item_id]

        try:
            data = obj.parse_as_object()
            name = getattr(data, 'm_Name', '') or f"PathID_{obj.path_id}"
        except (AttributeError, ValueError) as e:
            if self._generate_error_log:
                target_info = f"{self.file_path} > PathID_{obj.path_id} ({type_name})"
                self._generate_error_log([(target_info, str(e))], context="Asset Preview")
            title = self.lang_dict.get('asset_error_title', 'Error')
            notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error log has been saved in the logs folder.')
            messagebox.showerror(title, f"{str(e)}\n\n{notice}", parent=self)
            return

        # 진행 상태 팝업
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title(self.lang_dict.get('preview_converting', 'Processing...'))
        win_w, win_h = 360, 105
        sx = popup.winfo_screenwidth()
        sy = popup.winfo_screenheight()
        popup.geometry(f'{win_w}x{win_h}+{sx // 2 - win_w // 2}+{sy // 2 - win_h // 2}')
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)

        main_frame = ttk.Frame(popup, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text=self.lang_dict.get('preview_converting', 'Processing...'), anchor="center", justify="center").pack(fill=tk.X, pady=(10, 12))
        progress = ttk.Progressbar(main_frame, mode='indeterminate')
        progress.pack(fill=tk.X, padx=15, pady=(0, 10))
        progress.start(15)
        popup.deiconify()

        def export_worker():
            error = None
            try:
                if type_name in ('Texture2D', 'Sprite'):
                    self._export_image(data, name, obj.path_id)
                elif type_name == 'Texture2DArray':
                    self._export_texture2darray(data, name, obj.path_id)
                elif type_name == 'AudioClip':
                    self._export_audio(data, name, obj.path_id)
                elif type_name == 'TextAsset':
                    self._export_text(data, name, obj.path_id)
                elif type_name == 'Font':
                    self._export_font(data, name, obj.path_id)
                elif type_name == 'Mesh':
                    self._export_mesh(data, name, obj.path_id)
                elif type_name == 'Shader':
                    self._export_shader(data, name, obj.path_id)
                elif type_name == 'MonoBehaviour':
                    self._export_monobehaviour(obj, data, name)
                else:
                    self._export_raw(obj, data, name, type_name)
            except Exception as e:
                error = e
            finally:
                self.after(0, lambda: on_done(error))

        def on_done(error):
            try:
                popup.destroy()
            except tk.TclError:
                pass
            if error:
                if self._generate_error_log:
                    target_info = f"{self.file_path} > {name} ({type_name})"
                    self._generate_error_log([(target_info, str(error))], context="Asset Preview")
                title = self.lang_dict.get('asset_error_title', 'Error')
                notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error log has been saved in the logs folder.')
                messagebox.showerror(title, f"{str(error)}\n\n{notice}", parent=self)

        threading.Thread(target=export_worker, daemon=True).start()

    def _open_with_os(self, file_path: str) -> None:
        """OS 기본 프로그램으로 파일을 엽니다."""
        open_with_default_app(file_path)

    def _get_preview_file_path(self, name: str, path_id: int, ext: str) -> str:
        """미리보기 파일의 고유한 격리 경로를 생성하여 반환합니다."""
        import time
        safe_name = self._sanitize_name(name) or f"asset_{path_id}"
        sub_dir = os.path.join(self._preview_temp_dir, f"asset_{path_id}_{int(time.time() * 1000)}")
        os.makedirs(sub_dir, exist_ok=True)
        return os.path.join(sub_dir, f"{safe_name}{ext}")

    def _export_image(self, data: Any, name: str, path_id: int) -> None:
        """이미지 에셋을 .png로 추출하여 OS 기본 프로그램으로 엽니다."""
        img = data.image
        if img is None:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))

        temp_path = self._get_preview_file_path(name, path_id, ".png")
        img.save(temp_path)
        self._open_with_os(temp_path)

    def _export_texture2darray(self, data: Any, name: str, path_id: int) -> None:
        """Texture2DArray 에셋의 첫 번째 레이어를 .png로 추출하여 OS 기본 프로그램으로 엽니다."""
        images = getattr(data, 'images', None)
        if not images:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))
        temp_path = self._get_preview_file_path(f"{name}_0", path_id, ".png")
        images[0].save(temp_path)
        self._open_with_os(temp_path)

    def _export_font(self, data: Any, name: str, path_id: int) -> None:
        """Font 에셋을 .ttf 또는 .otf로 추출하여 OS 기본 프로그램으로 엽니다."""
        if not getattr(data, 'm_FontData', None):
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))
        font_bytes = bytes(data.m_FontData)
        ext = ".otf" if font_bytes[:4] == b"OTTO" else ".ttf"
        temp_path = self._get_preview_file_path(name, path_id, ext)
        with open(temp_path, "wb") as f:
            f.write(font_bytes)
        self._open_with_os(temp_path)

    def _export_mesh(self, data: Any, name: str, path_id: int) -> None:
        """Mesh 에셋을 Wavefront OBJ 파일로 추출하여 OS 기본 프로그램으로 엽니다."""
        obj_text = data.export()
        if not obj_text:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))
        temp_path = self._get_preview_file_path(name, path_id, ".obj")
        with open(temp_path, "w", encoding="utf-8", newline="") as f:
            f.write(obj_text)
        self._open_with_os(temp_path)

    def _export_shader(self, data: Any, name: str, path_id: int) -> None:
        """Shader 에셋을 .txt 텍스트 파일로 추출하여 OS 기본 프로그램으로 엽니다."""
        shader_text = data.export()
        if not shader_text:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))
        temp_path = self._get_preview_file_path(name, path_id, ".txt")
        with open(temp_path, "w", encoding="utf-8", newline="") as f:
            f.write(shader_text)
        self._open_with_os(temp_path)

    def _export_monobehaviour(self, obj: Any, data: Any, name: str) -> None:
        """MonoBehaviour 에셋을 포맷팅된 JSON 또는 바이너리로 추출하여 OS 기본 프로그램으로 엽니다."""
        import json
        try:
            tree = obj.parse_as_dict()
            export_bytes = json.dumps(tree, indent=4, ensure_ascii=False, default=str).encode('utf-8')
            ext = ".json"
        except Exception:
            export_bytes = obj.get_raw_data()
            ext = ".bin"
        temp_path = self._get_preview_file_path(name, obj.path_id, ext)
        with open(temp_path, "wb") as f:
            f.write(export_bytes)
        self._open_with_os(temp_path)

    def _export_audio(self, data: Any, name: str, path_id: int) -> None:
        """오디오 에셋을 추출하여 OS 기본 프로그램으로 엽니다."""
        if not data.samples:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No data.'))

        for sample_name, audio_data in data.samples.items():
            _, ext = os.path.splitext(sample_name)
            if not ext:
                ext = ".wav"
            temp_path = self._get_preview_file_path(name, path_id, ext)
            with open(temp_path, "wb") as f:
                f.write(audio_data)
            self._open_with_os(temp_path)
            break  # 첫 번째 샘플만

    def _export_text(self, data: Any, name: str, path_id: int) -> None:
        """텍스트 에셋을 .txt 또는 StoryData JSON으로 추출하여 OS 기본 프로그램으로 엽니다."""
        text_content = data.m_Script
        if name.startswith('storydata_'):
            from src.parsers.story_deserializer import StoryDataDeserializer
            import json
            try:
                if isinstance(text_content, str):
                    raw_bytes = text_content.encode('utf-8', 'surrogateescape')
                else:
                    raw_bytes = bytes(text_content)
                deserialized = StoryDataDeserializer.deserialize(raw_bytes)
                temp_path = self._get_preview_file_path(name, path_id, ".json")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(deserialized, f, indent=4, ensure_ascii=False)
                self._open_with_os(temp_path)
                return
            except Exception:
                pass  # 실패 시 일반 텍스트 저장으로 폴백

        if isinstance(text_content, str):
            text_content = text_content.encode('utf-8', 'surrogateescape')
        elif not isinstance(text_content, (bytes, bytearray)):
            text_content = str(text_content).encode('utf-8', 'surrogateescape')

        temp_path = self._get_preview_file_path(name, path_id, ".txt")
        with open(temp_path, "wb") as f:
            f.write(text_content)
        self._open_with_os(temp_path)

    def _export_raw(self, obj: Any, data: Any, name: str, type_name: str) -> None:
        """기타 에셋을 raw 바이너리로 추출하여 OS 기본 프로그램으로 엽니다."""
        ext = self.TYPE_EXTENSIONS.get(type_name, ".bin")
        if ext is None:
            ext = ".bin"

        temp_path = self._get_preview_file_path(name, obj.path_id, ext)

        # raw bytes 추출
        raw_data = obj.get_raw_data()
        with open(temp_path, "wb") as f:
            f.write(raw_data)
        self._open_with_os(temp_path)

    def _on_close(self) -> None:
        """창 종료 시 내부 임시 폴더를 정리합니다."""
        if os.path.exists(self._preview_temp_dir):
            try:
                shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
            except OSError:
                pass
        self.destroy()
