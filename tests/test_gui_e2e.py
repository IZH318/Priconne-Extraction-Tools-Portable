import pytest
import tkinter as tk
from tkinter import ttk

from main import MainLauncher

@pytest.fixture(scope="session")
def app():
    """
    MainLauncher(Tk) 인스턴스를 하나만 생성하는 pytest 피스쳐입니다.
    Tkinter는 여러 개의 Tk() 인스턴스를 만들면 치명적인 행(hang)과
    이벤트 충돌(TclError 등)을 겪을 수 있으므로 session 레벨로 유지합니다.
    """
    launcher = MainLauncher()
    # 렌더링 사이클 적용 파이프라인
    launcher.update()
    yield launcher
    
    try:
        launcher.destroy()
    except tk.TclError:
        pass

@pytest.fixture(autouse=True)
def reset_ui_state(app):
    """각 테스트 후 UI 상태를 초기화하여 테스트 간 상태 오염을 방지합니다."""
    yield
    try:
        app.app_lang_var.set('ko')
        app.update()
    except tk.TclError:
        pass

def test_main_launcher_initialization(app):
    """메인 런처가 모든 탭(5개 모듈)을 성공적으로 로드하는지 테스트합니다."""
    # 노트북 위젯(탭) 객체 확인
    assert isinstance(app.notebook, ttk.Notebook)
    
    # 탭 개수 확인 (Renamer, Unity, AV, Story, Remover)
    assert app.notebook.index("end") == 5

def test_language_change_updates_ui(app):
    """
    글로벌 언어 변수(app_lang_var) 변경 시, 
    이벤트 시스템을 통해 UI 텍스트(윈도우 타이틀, 메뉴 등)가 즉각 반영되는지 테스트(E2E)합니다.
    """
    
    # 1단계: 영어를 지정하여 텍스트가 영어로 바뀌는지 검증
    app.app_lang_var.set('en')
    app.update()
    
    file_menu_en = app.menu_bar.entrycget(1, "label")
    assert file_menu_en == "Menu"
    
    # 2단계: 한국어로 변경하여 메뉴가 한글로 바뀌는지 검증
    app.app_lang_var.set('ko')
    app.update()
    
    file_menu_ko = app.menu_bar.entrycget(1, "label")
    assert file_menu_ko == "메뉴(Menu)"

def test_menu_existence(app):
    """상단 메뉴 바(File, Language)가 정상적으로 구성되어 있는지 검증합니다."""
    # menu_bar가 존재하는지 확인
    assert app.menu_bar is not None
    
    # 메뉴 캐스케이드(Cascade) 항목 확인 (File, Language)
    file_menu_label = app.menu_bar.entrycget(1, "label")
    lang_menu_label = app.menu_bar.entrycget(2, "label")
    
    assert isinstance(file_menu_label, str)
    assert isinstance(lang_menu_label, str)

def test_di_container_injection(app):
    """AppContainer(DI) 객체가 성공적으로 생성되었고 필수 의존성이 채워졌는지 검사합니다."""
    assert app.container is not None
    assert app.app_lang_var is not None
    assert isinstance(app.about_info, dict)
    assert "version" in app.about_info
