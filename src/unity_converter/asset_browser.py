"""Unity3D 번들 대화형 에셋 트리 탐색기 및 미리보기 뷰어 모듈.

트리 뷰에 내부 에셋 계층 구조, 메타데이터 및 바이트 크기 표시.
에셋을 더블 클릭하면 임시 파일로 추출하여 OS 기본 연결 프로그램(사진 뷰어, 미디어 플레이어, 텍스트 편집기 등)으로 실행.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, ClassVar

from src.constants import DEFAULT_UNITY_VERSION
from src.utils.platform_open import open_with_default_app

logger = logging.getLogger(__name__)


class AssetBrowserWindow(tk.Toplevel):
    """계층적 에셋 트리 뷰어 및 온디맨드 파일 미리보기 대화상자 클래스.

    UnityPy로 Unity 번들을 로드하고 에셋을 타입별 카테고리로 분류하여 Treeview에 표시하며,
    더블 클릭 시 선택된 항목을 즉시 임시 추출하여 외부 애플리케이션으로 미리보기 실행.

    Attributes:
        file_path: 검사 대상 Unity 번들 파일 경로.
        lang_dict: 활성 다국어 번역 딕셔너리.
        unity_version: UnityPy용으로 설정된 Unity 엔진 버전 문자열.
        tree: 에셋 카테고리 및 항목을 표시하는 Tkinter Treeview 위젯.
    """

    TYPE_GROUPS: ClassVar[dict[str, str]] = {
        "Texture2D": "Textures", "Sprite": "Sprites", "Texture2DArray": "Textures",
        "AudioClip": "Audio", "TextAsset": "TextAssets", "MonoBehaviour": "MonoBehaviours",
        "Font": "Fonts", "Mesh": "Meshes", "Shader": "Shaders",
        "AnimationClip": "Animations", "Material": "Materials",
        "MovieTexture": "Video", "VideoClip": "Video",
    }

    TYPE_EXTENSIONS: ClassVar[dict[str, str | None]] = {
        "Texture2D": ".png", "Sprite": ".png", "Texture2DArray": ".png",
        "AudioClip": None,
        "TextAsset": ".txt", "MonoBehaviour": ".json",
        "Font": ".ttf", "Mesh": ".obj", "Shader": ".txt",
        "AnimationClip": ".bin", "Material": ".json",
        "MovieTexture": ".ogv", "VideoClip": ".mp4",
    }

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """영숫자가 아닌 문자를 밑줄로 치환하여 임의의 문자열을 안전한 파일명으로 변환.

        Args:
            name: 원본 문자열 식별자.

        Returns:
            영숫자, 밑줄, 하이픈만 포함하는 안전한 파일명.
        """
        return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)

    @staticmethod
    def _format_file_size(size: int) -> str:
        """바이트 크기를 읽기 쉬운 규격 문자열(B, KB, MB)로 변환.

        Args:
            size: 바이트 단위 정수 크기.

        Returns:
            '1.2 MB' 또는 '512 KB' 등의 포맷팅 문자열.
        """
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
        app_temp_dir: Path | str | None = None,
        generate_error_log: Callable[..., None] | None = None,
    ) -> None:
        """AssetBrowserWindow 모달 대화상자 초기화.

        Args:
            master: 부모 윈도우.
            file_path: 검사할 Unity 번들 파일 시스템 경로.
            lang_dict: 다국어 번역 딕셔너리.
            unity_version: 폴백 Unity 엔진 버전.
            app_temp_dir: 미리보기 캐시용 기본 임시 디렉터리 경로.
            generate_error_log: 로드 실패 시 에러 로그 작성을 위한 콜백 함수.
        """
        super().__init__(master)
        self.withdraw()
        self.file_path = file_path
        self.lang_dict = lang_dict
        if unity_version is None:
            self.unity_version = DEFAULT_UNITY_VERSION
        else:
            self.unity_version = unity_version
        self._generate_error_log = generate_error_log
        self._asset_map: dict[str, tuple[Any, str]] = {}

        if app_temp_dir:
            self._preview_temp_dir: str = os.path.join(str(app_temp_dir), f"asset_browser_{id(self)}")
            os.makedirs(self._preview_temp_dir, exist_ok=True)
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix='priconne_asset_preview_')

        filename = os.path.basename(file_path)
        self.title(lang_dict.get('asset_browser_title', 'Asset Browser - {filename}').format(filename=filename))

        # 화면 중앙에 윈도우 배치
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
        """Treeview, 스크롤바 및 컬럼 헤더 위젯 조립 및 배치."""
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
        """UnityPy로 번들을 로드하고 에셋 타입별로 그룹화하여 트리에 배치."""
        try:
            import UnityPy
            from UnityPy import config
            config.FALLBACK_UNITY_VERSION = self.unity_version  # type: ignore[assignment]
            env = UnityPy.load(self.file_path)
        except (OSError, ValueError, RuntimeError) as e:
            if self._generate_error_log:
                self._generate_error_log([(self.file_path, str(e))], context="Asset Browser Load")
            title = self.lang_dict.get('asset_error_title', 'Error')
            notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
            messagebox.showerror(title, f"{e!s}\n\n{notice}", parent=self)
            return

        group_nodes = {}

        for obj in env.objects:
            type_name = obj.type.name
            group_name = self.TYPE_GROUPS.get(type_name, type_name)

            if group_name not in group_nodes:
                group_nodes[group_name] = self.tree.insert('', 'end', text=group_name, open=False)

            try:
                data = obj.parse_as_object()
                name = getattr(data, 'm_Name', '') or f"PathID_{obj.path_id}"
            except AttributeError:
                name = f"PathID_{obj.path_id}"

            try:
                size_str = self._format_file_size(obj.byte_size)
            except AttributeError:
                size_str = "?"

            item_id = self.tree.insert(group_nodes[group_name], 'end',
                                        text=name, values=(type_name, size_str))
            self._asset_map[item_id] = (obj, type_name)

    def _on_double_click(self, event: tk.Event) -> None:
        """항목 더블 클릭 이벤트 처리 (선택 에셋 추출 및 기본 앱 미리보기 실행).

        진행률 모달 팝업 표시, 데몬 작업자 스레드에서 에셋 추출 실행 후
        운영체제 기본 프로그램으로 파일 열기 수행.

        Args:
            event: Tkinter 마우스 이벤트 객체.
        """
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
            notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
            messagebox.showerror(title, f"{e!s}\n\n{notice}", parent=self)
            return

        # 모달 진행률 팝업 창 생성
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

        def export_worker() -> None:
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
            except Exception as e:  # noqa: BLE001
                error = e
            finally:
                try:
                    self.after(0, lambda: on_done(error))
                except tk.TclError:
                    pass

        def on_done(error: Any) -> None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            if error:
                if self._generate_error_log:
                    target_info = f"{self.file_path} > {name} ({type_name})"
                    self._generate_error_log([(target_info, str(error))], context="Asset Preview")
                title = self.lang_dict.get('asset_error_title', 'Error')
                notice = self.lang_dict.get('msgbox_error_log_saved_msg', 'An error occurred during the operation. An error log has been saved in the logs folder.')
                messagebox.showerror(title, f"{error!s}\n\n{notice}", parent=self)

        self._export_thread: threading.Thread = threading.Thread(target=export_worker, daemon=True)
        self._export_thread.start()

    def _open_with_os(self, file_path: str) -> None:
        """추출된 파일을 운영체제 기본 프로그램으로 실행."""
        open_with_default_app(file_path)

    def _get_preview_file_path(self, name: str, path_id: int, ext: str) -> str:
        """미리보기 항목에 대한 고유한 임시 파일 경로 생성.

        Args:
            name: 기본 에셋 이름.
            path_id: 오브젝트 PathID.
            ext: 확장자 (점 포함, 예: '.png').

        Returns:
            미리보기 임시 캐시 디렉터리 내의 절대 파일 경로.
        """
        import time
        safe_name = self._sanitize_name(name) or f"asset_{path_id}"
        sub_dir = os.path.join(self._preview_temp_dir, f"asset_{path_id}_{int(time.time() * 1000)}")
        os.makedirs(sub_dir, exist_ok=True)
        return os.path.join(sub_dir, f"{safe_name}{ext}")

    def _export_image(self, data: Any, name: str, path_id: int) -> None:
        """Texture2D/Sprite 에셋을 PNG로 추출하고 OS 이미지 뷰어로 열기."""
        img = data.image
        if img is None:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))

        temp_path = self._get_preview_file_path(name, path_id, ".png")
        img.save(temp_path)
        self._open_with_os(temp_path)

    def _export_texture2darray(self, data: Any, name: str, path_id: int) -> None:
        """Texture2DArray의 첫 번째 레이어를 PNG로 추출하고 OS 이미지 뷰어로 열기."""
        images = getattr(data, 'images', None)
        if not images:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))
        temp_path = self._get_preview_file_path(f"{name}_0", path_id, ".png")
        images[0].save(temp_path)
        self._open_with_os(temp_path)

    def _export_font(self, data: Any, name: str, path_id: int) -> None:
        """Font 에셋을 TTF/OTF로 추출하고 OS 폰트 뷰어로 열기."""
        if not getattr(data, 'm_FontData', None):
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))
        font_bytes = bytes(data.m_FontData)
        ext = ".otf" if font_bytes[:4] == b"OTTO" else ".ttf"
        temp_path = self._get_preview_file_path(name, path_id, ext)
        with open(temp_path, "wb") as f:
            f.write(font_bytes)
        self._open_with_os(temp_path)

    def _export_mesh(self, data: Any, name: str, path_id: int) -> None:
        """3D Mesh 에셋을 Wavefront OBJ로 추출하고 OS 3D 모델 뷰어로 열기."""
        obj_text = data.export()
        if not obj_text:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))
        temp_path = self._get_preview_file_path(name, path_id, ".obj")
        with open(temp_path, "w", encoding="utf-8", newline="") as f:
            f.write(obj_text)
        self._open_with_os(temp_path)

    def _export_shader(self, data: Any, name: str, path_id: int) -> None:
        """Shader 에셋을 텍스트 파일로 추출하고 OS 텍스트 편집기로 열기."""
        shader_text = data.export()
        if not shader_text:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))
        temp_path = self._get_preview_file_path(name, path_id, ".txt")
        with open(temp_path, "w", encoding="utf-8", newline="") as f:
            f.write(shader_text)
        self._open_with_os(temp_path)

    def _export_monobehaviour(self, obj: Any, data: Any, name: str) -> None:
        """MonoBehaviour 에셋을 포맷팅된 JSON 또는 원시 바이너리로 추출하여 기본 뷰어로 열기."""
        import json
        try:
            tree = obj.parse_as_dict()
            export_bytes = json.dumps(tree, indent=4, ensure_ascii=False, default=str).encode('utf-8')
            ext = ".json"
        except (AttributeError, ValueError, TypeError, KeyError):
            export_bytes = obj.get_raw_data()
            ext = ".bin"
        temp_path = self._get_preview_file_path(name, obj.path_id, ext)
        with open(temp_path, "wb") as f:
            f.write(export_bytes)
        self._open_with_os(temp_path)

    def _export_audio(self, data: Any, name: str, path_id: int) -> None:
        """AudioClip의 첫 번째 오디오 샘플을 추출하고 기본 미디어 플레이어로 실행."""
        if not data.samples:
            raise ValueError(self.lang_dict.get('asset_no_data', 'No previewable data in this asset.'))

        for sample_name, audio_data in data.samples.items():
            _, ext = os.path.splitext(sample_name)
            if not ext:
                ext = ".wav"
            temp_path = self._get_preview_file_path(name, path_id, ext)
            with open(temp_path, "wb") as f:
                f.write(audio_data)
            self._open_with_os(temp_path)
            break

    def _export_text(self, data: Any, name: str, path_id: int) -> None:
        """TextAsset을 TXT 또는 역직렬화된 StoryData JSON으로 추출하고 편집기로 열기."""
        text_content = data.m_Script
        if name.startswith('storydata_'):
            import json

            from src.parsers.story_deserializer import StoryDataDeserializer
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
            except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
                logger.debug("Asset preview fallback failed: %s", exc)

        if isinstance(text_content, str):
            text_content = text_content.encode('utf-8', 'surrogateescape')
        elif not isinstance(text_content, (bytes, bytearray)):
            text_content = str(text_content).encode('utf-8', 'surrogateescape')

        temp_path = self._get_preview_file_path(name, path_id, ".txt")
        with open(temp_path, "wb") as f:
            f.write(text_content)
        self._open_with_os(temp_path)

    def _export_raw(self, obj: Any, data: Any, name: str, type_name: str) -> None:
        """미지원 에셋 타입을 원시 바이너리로 추출하고 기본 프로그램으로 열기."""
        ext = self.TYPE_EXTENSIONS.get(type_name, ".bin")
        if ext is None:
            ext = ".bin"

        temp_path = self._get_preview_file_path(name, obj.path_id, ext)
        raw_data = obj.get_raw_data()
        with open(temp_path, "wb") as f:
            f.write(raw_data)
        self._open_with_os(temp_path)

    def _on_close(self) -> None:
        """대화상자 종료 시 미리보기 캐시 디렉터리 파기 및 리소스 정리."""
        if os.path.exists(self._preview_temp_dir):
            try:
                shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
            except OSError as _e:
                logger.debug('Asset browser temp cleanup failed: %s', _e)
        self.destroy()
