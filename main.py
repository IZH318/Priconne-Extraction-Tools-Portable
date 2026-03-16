import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# 모듈 임포트
from src.renamer import FileRenamerGUI
from src.unity_converter import AssetExtractorApp
from src.av_converter import AVConverterApp
from src.story_viewer import StoryViewerApp
from src.resource_remover import ResourceRemoverApp
from src.logger import setup_global_logging

# 공통 언어 데이터
import json
import os

with open(os.path.join(os.path.dirname(__file__), 'src', 'languages.json'), 'r', encoding='utf-8') as _f:
    LANGUAGES = json.load(_f)

class MainLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Initialize Global Logging Safety Net
        setup_global_logging(self)
        
        # 기본 설정
        self.app_lang_var = tk.StringVar(value='ko')
        self._configure_window()
        self._create_main_menu()
        self._create_tabs()
        
        # 언어 변경 이벤트 추적
        self.app_lang_var.trace_add('write', self._on_language_change)
        
        # 초기 텍스트 적용
        self._update_launcher_ui_text()

    def _configure_window(self):
        """메인 윈도우의 크기와 위치를 설정합니다."""
        width, height = 1000, 750
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # 아이콘 설정 (기존 앱들의 구조를 참조)
        base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        icon_path = base_path / 'icon.ico'
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    def _create_main_menu(self):
        """런처의 글로벌 메인 메뉴 바를 생성합니다."""
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        
        # 파일 메뉴 (종료 정도만 가짐)
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="", command=self.quit)
        
        # 언어 메뉴
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ko')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='en')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ja')
        
        # 메인 메뉴바에 연결 (라벨은 _update_launcher_ui_text에서 설정)
        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)
        self.menu_bar.add_command(label="", command=self._show_about_dialog)

    def _create_tabs(self):
        """각 툴 모듈을 담을 노트북 탭 구조를 생성합니다."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 1. Manifest Renamer
        self.tab1 = ttk.Frame(self.notebook)
        self.app1 = FileRenamerGUI(self.tab1, app_lang_var=self.app_lang_var)
        self.notebook.add(self.tab1, text="")
        
        # 2. .unity3d File Converter
        self.tab2 = ttk.Frame(self.notebook)
        self.app2 = AssetExtractorApp(self.tab2, app_lang_var=self.app_lang_var)
        self.notebook.add(self.tab2, text="")
        
        # 3. Audio / Video Converter
        self.tab3 = ttk.Frame(self.notebook)
        self.app3 = AVConverterApp(self.tab3, app_lang_var=self.app_lang_var)
        self.notebook.add(self.tab3, text="")
        
        # 4. Story Viewer
        self.tab4 = ttk.Frame(self.notebook)
        self.app4 = StoryViewerApp(self.tab4, app_lang_var=self.app_lang_var)
        self.notebook.add(self.tab4, text="")
        
        # 5. Resource Remover
        self.tab5 = ttk.Frame(self.notebook)
        self.app5 = ResourceRemoverApp(self.tab5, app_lang_var=self.app_lang_var)
        self.notebook.add(self.tab5, text="")

    def _on_language_change(self, *args):
        """언어 변수가 변경될 때 런처 UI 요소 텍스트를 업데이트합니다."""
        self._update_launcher_ui_text()

    def _update_launcher_ui_text(self):
        """현재 선택된 언어에 맞춰 런처 메뉴와 탭 이름을 변경합니다."""
        lang_dict = LANGUAGES.get(self.app_lang_var.get(), LANGUAGES['ko'])
        
        # 윈도우 제목
        self.title(lang_dict['window_title'])
        
        # 메뉴 라벨 업데이트
        self.menu_bar.entryconfig(1, label=lang_dict['menu_file'])
        self.menu_bar.entryconfig(2, label=lang_dict['menu_lang'])
        self.menu_bar.entryconfig(3, label=lang_dict['menu_info'])
        
        self.file_menu.entryconfig(0, label=lang_dict['menu_exit'])
        self.lang_menu.entryconfig(0, label=lang_dict['menu_lang_ko'])
        self.lang_menu.entryconfig(1, label=lang_dict['menu_lang_en'])
        self.lang_menu.entryconfig(2, label=lang_dict['menu_lang_ja'])
        
        # 탭 라벨 업데이트
        self.notebook.tab(0, text=lang_dict['tab_renamer'])
        self.notebook.tab(1, text=lang_dict['tab_unity'])
        self.notebook.tab(2, text=lang_dict['tab_av'])
        self.notebook.tab(3, text=lang_dict['tab_story'])
        self.notebook.tab(4, text=lang_dict['tab_remover'])

    def _show_about_dialog(self):
        lang_dict = LANGUAGES.get(self.app_lang_var.get(), LANGUAGES['ko'])
        messagebox.showinfo(lang_dict['about_title'], lang_dict['about_msg'], parent=self)

if __name__ == '__main__':
    app = MainLauncher()
    app.mainloop()
