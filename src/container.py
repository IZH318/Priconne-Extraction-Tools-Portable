from __future__ import annotations
import os
import json
import logging
import shutil
import tempfile
import tkinter as tk
from tkinter import font as tkfont

from src.constants import (
    APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, 
    APP_WEBSITE, APP_COPYRIGHT_YEAR
)
from src.logger import setup_global_logging

class AppContainer:
    """
    애플리케이션 전역 의존성(Dependency)을 관리하고 주입(Inject)하는 DI 컨테이너 클래스입니다.
    이곳에서 공통 인스턴스, 설정, 다국어 데이터, 로거 초기화 등을 한 번만 수행하고 각 GUI 모듈에 분배합니다.
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        
        # 전역 상태 (공유 변수)
        self.app_lang_var = tk.StringVar(value='ko')
        self.languages = self._load_languages()
        
        # 단일 통합 임시 폴더 제어 (`Priconne_Extraction_Tools_(Portable)_TEMP`)
        self.app_temp_dir = os.path.join(tempfile.gettempdir(), 'Priconne_Extraction_Tools_(Portable)_TEMP')
        
        # 모든 모듈이 공유하는 어바웃 정보
        self.about_info = {
            'program': "Priconne Extraction Tools (Portable)",
            'version': APP_VERSION,
            'updated': APP_LAST_UPDATE,
            'developer': APP_DEVELOPER,
            'website': APP_WEBSITE,
            'year': APP_COPYRIGHT_YEAR
        }
        
        # 로거에 주입할 정보
        self.app_info_for_logger = {
            'APP_VERSION': APP_VERSION,
            'APP_LAST_UPDATE': APP_LAST_UPDATE,
            'APP_DEVELOPER': APP_DEVELOPER
        }

    def _load_languages(self) -> dict:
        """다국어 언어 데이터를 안전하게 로드합니다. 파일 없음/손상 시 빈 기본값을 반환합니다."""
        try:
            lang_path = os.path.join(os.path.dirname(__file__), 'languages.json')
            with open(lang_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.warning("Failed to load languages.json: %s. Using empty fallback.", e)
            return {'ko': {}, 'en': {}, 'ja': {}}

    def initialize_core_services(self) -> None:
        """로거 및 전역 폰트 등 핵심 시스템 서비스를 초기화합니다."""
        setup_global_logging(self.root, self.app_info_for_logger, self.app_lang_var, self.languages)
        
        # 이전 실행 세션에서 남은 찌꺼기 파일 초기화 후 다시 폴더 진열
        self._reset_app_temp_dir()


    def _reset_app_temp_dir(self):
        """임시 폴더를 안전하게 지우고 새로 생성합니다. 현재 사용 중인 파일은 무시합니다."""
        if os.path.exists(self.app_temp_dir):
            shutil.rmtree(self.app_temp_dir, ignore_errors=True)
        try:
            os.makedirs(self.app_temp_dir, exist_ok=True)
        except Exception as e:
            logging.warning("Failed to create unified temp folder: %s", e)

    def cleanup_shared(self):
        """앱 종료 시 등록된 공통 자원 및 통합 임시 폴더를 삭제합니다."""
        if os.path.exists(self.app_temp_dir):
            shutil.rmtree(self.app_temp_dir, ignore_errors=True)

    def get_shared_dependencies(self) -> dict:
        """
        GUI 모듈의 생성자(Controller 등)에 넘겨주기 위한 주요 의존성 딕셔너리를 반환합니다.
        추후 DB 연결 객체, 설정 로더, 글로벌 알림 이벤트 버스 등을 여기에 추가로 주입할 수 있습니다.
        """
        return {
            'app_lang_var': self.app_lang_var,
            'about_info': self.about_info,
            'app_temp_dir': self.app_temp_dir
        }
