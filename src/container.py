from __future__ import annotations
import logging
import shutil
import tempfile
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

from src.constants import (
    APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, 
    APP_WEBSITE, APP_COPYRIGHT_YEAR
)
from src.logger import setup_global_logging


@dataclass(frozen=True)
class SharedDependencies:
    """GUI 모듈에 주입되는 공유 의존성 번들입니다.

    frozen=True로 설정하여, 한 번 생성된 의존성 번들이
    의도치 않게 수정되는 것을 방지합니다.

    Attributes:
        app_lang_var: 앱 전역 언어 설정 StringVar.
        about_info: About 대화상자에 표시될 정보 딕셔너리.
        app_temp_dir: 미리보기 등을 위한 공유 임시 폴더 경로 (문자열).
    """
    app_lang_var: tk.StringVar
    about_info: dict[str, str]
    app_temp_dir: str

class AppContainer:
    """
    애플리케이션 전역 의존성(Dependency)을 관리하고 주입(Inject)하는 DI 컨테이너 클래스입니다.
    이곳에서 공통 인스턴스, 설정, 다국어 데이터, 로거 초기화 등을 한 번만 수행하고 각 GUI 모듈에 분배합니다.
    """
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        
        # 전역 상태 (공유 변수)
        self.app_lang_var = tk.StringVar(value='ko')
        
        # 단일 통합 임시 폴더 제어 (`Priconne_Extraction_Tools_(Portable)_TEMP`)
        self.app_temp_dir = Path(tempfile.gettempdir()) / 'Priconne_Extraction_Tools_(Portable)_TEMP'
        
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

    def initialize_core_services(self) -> None:
        """로거 및 전역 폰트 등 핵심 시스템 서비스를 초기화합니다.

        logger에 전달할 lang_data_map은 languages.py 모듈에서 이미 로드된
        전역 데이터를 재사용하여 languages.json 이중 로드를 방지합니다.
        """
        from src.languages import get_logger_lang_data_map, get_language_load_error
        
        load_err = get_language_load_error()
        if load_err:
            from tkinter import messagebox
            logging.error("Failed to load languages.json: %s", load_err)
            messagebox.showerror(
                "언어 파일 로드 실패 (Language Load Error)",
                f"languages.json 파일을 읽을 수 없습니다.\n({load_err})\n\n번역 파일이 누락되었거나 손상되었는지 확인해 주세요.\n프로그램이 기본값으로 실행됩니다.",
                parent=self.root
            )

        setup_global_logging(self.root, self.app_info_for_logger, self.app_lang_var, get_logger_lang_data_map())
        
        # 이전 실행 세션에서 남은 찌꺼기 파일 초기화 후 다시 폴더 진열
        self._reset_app_temp_dir()


    def _reset_app_temp_dir(self) -> None:
        """임시 폴더를 안전하게 지우고 새로 생성합니다. 현재 사용 중인 파일은 무시합니다."""
        if self.app_temp_dir.exists():
            shutil.rmtree(self.app_temp_dir, ignore_errors=True)
        try:
            self.app_temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.warning("Failed to create unified temp folder: %s", e)

    def cleanup_shared(self) -> None:
        """앱 종료 시 등록된 공통 자원 및 통합 임시 폴더를 삭제합니다."""
        if self.app_temp_dir.exists():
            shutil.rmtree(self.app_temp_dir, ignore_errors=True)

    def get_shared_dependencies(self) -> SharedDependencies:
        """GUI 모듈의 생성자(Controller 등)에 넘겨주기 위한 공유 의존성 번들을 반환합니다.

        Returns:
            SharedDependencies: 타입 안전한 의존성 데이터클래스 인스턴스.
        """
        return SharedDependencies(
            app_lang_var=self.app_lang_var,
            about_info=self.about_info,
            app_temp_dir=str(self.app_temp_dir),
        )
