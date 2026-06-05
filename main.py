from __future__ import annotations
import sys
import logging
import tkinter as tk
from tkinter import ttk
from typing import Any
from pathlib import Path
from tkinterdnd2 import TkinterDnD

# 모듈 및 컨테이너 임포트
from src.renamer import FileRenamerGUI
from src.unity_converter import AssetExtractorApp
from src.av_converter import AVConverterApp
from src.story_viewer import StoryViewerApp
from src.resource_remover import ResourceRemoverApp
from src.container import AppContainer
from src.protocols import ModuleController
from src.languages import MAIN_MENU_LANGUAGES
from src.utils.about_dialog import show_about_dialog


class _MenuBarIndex:
    """메인 메뉴바의 cascade 인덱스 (Tkinter Menu는 1-based)."""
    FILE = 1
    LANGUAGE = 2


class _FileMenuIndex:
    """파일 메뉴 내 항목 인덱스 (0-based)."""
    ABOUT = 0
    # SEPARATOR = 1
    EXIT = 2


class _LangMenuIndex:
    """언어 메뉴 내 항목 인덱스 (0-based)."""
    KOREAN = 0
    ENGLISH = 1
    JAPANESE = 2


class _TabIndex:
    """노트북 탭 인덱스 (0-based)."""
    RENAMER = 0
    UNITY = 1
    AV = 2
    STORY = 3
    REMOVER = 4

class MainLauncher(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        
        # 1. 의존성 주입(DI) 컨테이너 초기화 및 핵심 서비스 가동
        self.container = AppContainer(self)
        self.container.initialize_core_services()
        
        # 2. 컨테이너로부터 공유 인스턴스(의존성) 참조 획득
        deps = self.container.get_shared_dependencies()
        self.app_lang_var = deps['app_lang_var']
        self.about_info = deps['about_info']

        # 3. 메인 윈도우 UI 및 레이아웃 구성
        self._configure_window()
        self._create_main_menu()
        self._create_tabs(deps)
        
        # 4. 언어 변경 이벤트 바인딩
        self.app_lang_var.trace_add('write', self._on_language_change)
        
        # 5. 초기 텍스트 적용
        self._update_launcher_ui_text()

    def _configure_window(self) -> None:
        """메인 윈도우의 크기와 위치를 설정합니다."""
        width, height = 800, 600
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # 아이콘 설정
        base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        icon_path = base_path / 'icon.ico'
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except (tk.TclError, OSError):
                pass

    def _create_main_menu(self) -> None:
        """런처의 글로벌 메인 메뉴 바를 생성합니다."""
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        
        # 파일 메뉴
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="", command=self._show_about_info) # 0번 (About)
        self.file_menu.add_separator()                                        # 1번
        self.file_menu.add_command(label="", command=self.quit)               # 2번 (Exit)
        
        # 언어 메뉴
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ko')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='en')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ja')
        
        # 메인 메뉴바에 연결 (라벨은 _update_launcher_ui_text에서 설정)
        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)

    def _create_tabs(self, deps: dict[str, Any]) -> None:
        """각 툴 모듈을 담을 노트북 탭 구조를 생성하고, 컨테이너 리소스를 주입합니다."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 모듈 생성 시 생성자 주입(Constructor Injection) 방식으로 공유 객체 전달
        
        self.apps = []

        # 1. Manifest File Renamer
        self.tab1 = ttk.Frame(self.notebook)
        self.apps.append(FileRenamerGUI(self.tab1, app_lang_var=deps['app_lang_var'], about_info=deps['about_info']))
        self.notebook.add(self.tab1, text="")
        
        # 2. unity3d File Converter
        self.tab2 = ttk.Frame(self.notebook)
        self.apps.append(AssetExtractorApp(self.tab2, app_lang_var=deps['app_lang_var'], about_info=deps['about_info'], app_temp_dir=deps.get('app_temp_dir')))
        self.notebook.add(self.tab2, text="")
        
        # 3. Audio/Video Converter
        self.tab3 = ttk.Frame(self.notebook)
        self.apps.append(AVConverterApp(self.tab3, app_lang_var=deps['app_lang_var'], about_info=deps['about_info'], app_temp_dir=deps.get('app_temp_dir')))
        self.notebook.add(self.tab3, text="")
        
        # 4. Story Viewer
        self.tab4 = ttk.Frame(self.notebook)
        self.apps.append(StoryViewerApp(self.tab4, app_lang_var=deps['app_lang_var'], about_info=deps['about_info']))
        self.notebook.add(self.tab4, text="")
        
        # 5. Resource Remover
        self.tab5 = ttk.Frame(self.notebook)
        self.apps.append(ResourceRemoverApp(self.tab5, app_lang_var=deps['app_lang_var'], about_info=deps['about_info']))
        self.notebook.add(self.tab5, text="")

    def _on_language_change(self, *args: str) -> None:
        """언어 변수가 변경될 때 런처 UI 요소 텍스트를 업데이트합니다."""
        self._update_launcher_ui_text()

    def _update_launcher_ui_text(self) -> None:
        """현재 선택된 언어에 맞춰 런처 메뉴와 탭 이름을 변경합니다."""
        lang_dict = MAIN_MENU_LANGUAGES.get(self.app_lang_var.get(), MAIN_MENU_LANGUAGES.get('ko', {}))
        
        self.title(lang_dict.get('window_title', 'Priconne Extraction Tools'))
        
        self.menu_bar.entryconfig(_MenuBarIndex.FILE, label=lang_dict.get('menu_file', 'File'))
        self.menu_bar.entryconfig(_MenuBarIndex.LANGUAGE, label=lang_dict.get('menu_lang', 'Language'))
        
        self.file_menu.entryconfig(_FileMenuIndex.ABOUT, label=lang_dict.get('menu_info', 'About'))
        self.file_menu.entryconfig(_FileMenuIndex.EXIT, label=lang_dict.get('menu_exit', 'Exit'))
        self.lang_menu.entryconfig(_LangMenuIndex.KOREAN, label=lang_dict.get('menu_lang_ko', '한국어'))
        self.lang_menu.entryconfig(_LangMenuIndex.ENGLISH, label=lang_dict.get('menu_lang_en', 'English'))
        self.lang_menu.entryconfig(_LangMenuIndex.JAPANESE, label=lang_dict.get('menu_lang_ja', '日本語'))
        
        self.notebook.tab(_TabIndex.RENAMER, text=lang_dict.get('tab_renamer', "[※] Manifest File Renamer"))
        self.notebook.tab(_TabIndex.UNITY, text=lang_dict.get('tab_unity', "unity3d File Converter"))
        self.notebook.tab(_TabIndex.AV, text=lang_dict.get('tab_av', "Audio / Video Converter"))
        self.notebook.tab(_TabIndex.STORY, text=lang_dict.get('tab_story', "storydata Viewer"))
        self.notebook.tab(_TabIndex.REMOVER, text=lang_dict.get('tab_remover', "Original Resource Remover"))

    def _show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = MAIN_MENU_LANGUAGES.get(self.app_lang_var.get(), MAIN_MENU_LANGUAGES.get('ko', {}))
        show_about_dialog(lang_dict, self.about_info, self)
        
    def on_closing(self) -> None:
        """앱 종료 시 등록된 모든 모듈의 자원을 해제합니다."""
        for app in self.apps:
            controller = getattr(app, 'controller', None)
            if isinstance(controller, ModuleController):
                try:
                    controller.cleanup()
                except (AttributeError, RuntimeError) as e:
                    logging.warning("Error during cleanup: %s", e)
                    
        # 앱 전체 공유 자원 해제 (앱 전역 임시 폴더 삭제 등)
        if hasattr(self, 'container') and hasattr(self.container, 'cleanup_shared'):
            self.container.cleanup_shared()
                    
        self.destroy()

if __name__ == '__main__':
    app = MainLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
