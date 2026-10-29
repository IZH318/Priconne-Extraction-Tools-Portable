"""Priconne Extraction Tools 메인 런처.

5개 서브 도구(Manifest Renamer, Unity Converter, AV Converter, Story Viewer,
Resource Remover) 탭을 통합 제공하며, 다국어 설정 및 앱 수명주기를 관리.
"""

from __future__ import annotations

import logging
import multiprocessing
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from tkinterdnd2 import TkinterDnD  # type: ignore[import-untyped]

from src.av_converter import AVConverterApp
from src.container import AppContainer, SharedDependencies
from src.languages import MAIN_MENU_LANGUAGES, pick_language
from src.protocols import ModuleController, validate_module_controller

# 서브 도구 모듈 임포트
from src.renamer import FileRenamerGUI
from src.resource_remover import ResourceRemoverApp
from src.story_viewer import StoryViewerApp
from src.subprocess_runner import SubprocessRunner
from src.unity_converter import AssetExtractorApp
from src.utils.about_dialog import show_about_dialog
from src.utils.dialogs import center_window
from src.utils.task_pool import shutdown_registered_process_pools

logger = logging.getLogger(__name__)


class _MenuBarIndex:
    """메인 메뉴바 cascade 인덱스."""

    FILE = 0
    LANGUAGE = 1


class _FileMenuIndex:
    """파일 메뉴 항목 인덱스."""

    ABOUT = 0
    SEPARATOR = 1
    EXIT = 2


class _LangMenuIndex:
    """언어 메뉴 항목 인덱스."""

    KOREAN = 0
    ENGLISH = 1
    JAPANESE = 2


class _TabIndex:
    """노트북 탭 인덱스."""

    RENAMER = 0
    UNITY = 1
    AV = 2
    STORY = 3
    REMOVER = 4


class MainLauncher(TkinterDnD.Tk):
    """Priconne Extraction Tools 메인 윈도우 런처.

    드래그 앤 드롭 이벤트를 지원하며, AppContainer를 통해
    공유 의존성(언어 설정, 프로그램 정보, 임시 디렉터리)을
    각 서브 모듈에 주입하고 통합 탭 뷰를 구성.

    Attributes:
        container (AppContainer): DI 컨테이너 인스턴스.
        app_lang_var (tk.StringVar): 공용 활성 언어 변수.
        about_info (dict[str, str | int]): 프로그램 버전 및 정보.
        notebook (ttk.Notebook): 서브 도구 배치용 탭 컨테이너.
        apps (list[Any]): 서브 도구 인스턴스 목록.
    """

    def __init__(self) -> None:
        """MainLauncher 초기화 및 서브 도구 구성."""
        super().__init__()
        self.withdraw()

        
        # 1. DI 컨테이너 및 핵심 서비스 초기화
        self.container = AppContainer(self)
        self.container.initialize_core_services()
        
        # 2. 공유 의존성 참조 획득
        deps = self.container.get_shared_dependencies()
        self.app_lang_var = deps.app_lang_var
        self.about_info = deps.about_info

        # 3. 메인 윈도우 UI 및 레이아웃 구성
        self._configure_window()
        self._create_main_menu()
        self._create_tabs(deps)
        
        # 4. 언어 변경 이벤트 바인딩
        self.app_lang_var.trace_add('write', self._on_language_change)
        
        # 5. 초기 텍스트 적용
        self._update_launcher_ui_text()
        self.deiconify()

    def _configure_window(self) -> None:
        """메인 윈도우 크기 설정 및 화면 중앙 배치."""
        width, height = 800, 600
        center_window(self, width, height)
        
        # 아이콘 설정
        base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        icon_path = base_path / 'icon.ico'
        if icon_path.exists():
            try:
                self.iconbitmap(icon_path)
            except (tk.TclError, OSError):
                pass

    def _create_main_menu(self) -> None:
        """메인 메뉴바 생성."""
        self.menu_bar = tk.Menu(self, tearoff=0)
        self.config(menu=self.menu_bar)
        
        # 파일 메뉴
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="", command=self._show_about_info) # 0번 (About)
        self.file_menu.add_separator()                                        # 1번
        self.file_menu.add_command(label="", command=self.on_closing)          # 2번 (Exit)
        
        # 언어 메뉴
        self.lang_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ko')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='en')
        self.lang_menu.add_radiobutton(label="", variable=self.app_lang_var, value='ja')
        
        # 메인 메뉴바에 연결 (라벨은 _update_launcher_ui_text에서 설정)
        self.menu_bar.add_cascade(label="", menu=self.file_menu)
        self.menu_bar.add_cascade(label="", menu=self.lang_menu)

    def _create_tabs(self, deps: SharedDependencies) -> None:
        """서브 도구 탭 생성 및 의존성 주입."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 각 서브 도구에 공유 의존성 주입
        
        self.apps: list[Any] = []

        # 1. Manifest File Renamer
        self.tab1 = ttk.Frame(self.notebook)
        self.apps.append(FileRenamerGUI(self.tab1, app_lang_var=deps.app_lang_var, about_info=deps.about_info))
        self.notebook.add(self.tab1, text="")
        
        # 2. unity3d File Converter
        self.tab2 = ttk.Frame(self.notebook)
        self.apps.append(AssetExtractorApp(self.tab2, app_lang_var=deps.app_lang_var, about_info=deps.about_info, app_temp_dir=deps.app_temp_dir))
        self.notebook.add(self.tab2, text="")
        
        # 3. Audio/Video Converter
        self.tab3 = ttk.Frame(self.notebook)
        self.apps.append(AVConverterApp(self.tab3, app_lang_var=deps.app_lang_var, about_info=deps.about_info, app_temp_dir=deps.app_temp_dir))
        self.notebook.add(self.tab3, text="")
        
        # 4. Story Viewer
        self.tab4 = ttk.Frame(self.notebook)
        self.apps.append(StoryViewerApp(self.tab4, app_lang_var=deps.app_lang_var, about_info=deps.about_info))
        self.notebook.add(self.tab4, text="")
        
        # 5. Resource Remover
        self.tab5 = ttk.Frame(self.notebook)
        self.apps.append(ResourceRemoverApp(self.tab5, app_lang_var=deps.app_lang_var, about_info=deps.about_info))
        self.notebook.add(self.tab5, text="")

        # 서브 도구의 ModuleController 프로토콜 준수 여부 검증
        for app in self.apps:
            controller = getattr(app, 'controller', None)
            if controller is None:
                continue
            if not isinstance(controller, ModuleController):
                logger.warning(
                    "%s.controller does not implement ModuleController protocol. "
                    "cleanup() may be skipped on exit.",
                    type(app).__name__,
                )
            elif not validate_module_controller(controller):
                logger.warning(
                    "%s.controller implements ModuleController but fails signature validation.",
                    type(app).__name__,
                )

    def _on_language_change(self, *args: str) -> None:
        """언어 변경 시 UI 텍스트 갱신."""
        self._update_launcher_ui_text()

    def _update_launcher_ui_text(self) -> None:
        """현재 언어에 맞춰 메뉴와 탭 명칭 갱신."""
        lang_dict = pick_language(self.app_lang_var.get(), MAIN_MENU_LANGUAGES)
        
        self.title(lang_dict.get('window_title', 'Priconne Extraction Tools (Portable)'))
        
        self.menu_bar.entryconfig(_MenuBarIndex.FILE, label=lang_dict.get('menu_file', 'Menu'))
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
        """프로그램 정보 대화상자 표시."""
        show_about_dialog(self.about_info, self)
        
    def on_closing(self) -> None:
        """앱 종료 시 서브 도구 자원 정리 및 창 닫기."""
        if getattr(self, "_closing", False):
            return
        self._closing = True

        # 1. 창을 먼저 숨겨 스레드 조인(join) 대기 중 UI 멈춤 현상(freeze)을 방지
        try:
            self.withdraw()
        except tk.TclError:
            pass

        # 2. 진행 중인 외부 도구(ffmpeg/UsmToolkit/vgmstream) 프로세스 트리 일괄 종료
        #    (communicate 대기 중인 워커 스레드를 해제하여 스레드 join 지연 단축)
        try:
            terminated = SubprocessRunner.terminate_all()
            if terminated:
                logger.info("Terminated %d active child process(es) on exit", terminated)
        except Exception as e:  # noqa: BLE001
            logger.warning("Error during subprocess termination: %s", e)

        # 2-1. 등록된 프로세스 풀 워커 종료
        #      (스키마 해석/추출 진행 중 종료 시 워커 프로세스가 남아 대기하는 것을 방지)
        try:
            shutdown_registered_process_pools()
        except Exception as e:  # noqa: BLE001
            logger.warning("Error during process pool shutdown: %s", e)

        # 3. 서브 도구 컨트롤러 정리
        for app in self.apps:
            controller = getattr(app, 'controller', None)
            if isinstance(controller, ModuleController):
                try:
                    controller.cleanup()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Error during cleanup: %s", e)

        try:
            # 앱 공용 임시 폴더 등 공유 자원 정리
            if hasattr(self, 'container') and hasattr(self.container, 'cleanup_shared'):
                self.container.cleanup_shared()

            # 종료 직전 대기 중인 UI 콜백(after 태스크) 비우기(drain)
            try:
                from src.utils.tk_safe import drain_ui_callbacks
                drain_ui_callbacks()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error during UI callback drain: %s", e)
        finally:
            # 정리 단계에서 예외가 발생해도 창은 반드시 닫도록 보장
            self.destroy()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    # 이전 실행이 비정상 종료된 경우 남은 임시 파일 정리
    try:
        from src.utils.temp_registry import sweep_stale_temp_artifacts
        _swept = sweep_stale_temp_artifacts()
        if _swept:
            logger.info("Swept %d stale temp artifact(s) from previous run", _swept)
    except Exception as _sweep_err:  # noqa: BLE001
        logger.warning("Error during stale temp artifact sweep: %s", _sweep_err)
    app = MainLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
