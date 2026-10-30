"""의존성 주입(Dependency Injection) 컨테이너 및 공유 자원 수명주기 관리 모듈.

애플리케이션 전역 핵심 서비스(로거, 다국어 상태, 어바웃 메타데이터)
초기화 및 각 서브 도구 주입(SharedDependencies) 담당.
Windows API 기반 세션 격리 임시 폴더 제어로 다중 인스턴스 충돌 방지.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

from src.constants import (
    APP_COPYRIGHT_YEAR,
    APP_DEVELOPER,
    APP_LAST_UPDATE,
    APP_TEMP_DIR_NAME,
    APP_VERSION,
    APP_WEBSITE,
    DEFAULT_LANG,
    SESSION_DIR_PREFIX,
)
from src.logger import setup_global_logging
from src.utils.process_check import is_pid_alive

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedDependencies:
    """서브 도구 모듈에 주입되는 공유 의존성 객체.

    frozen=True 선언으로 런타임 공유 참조의 임의 변경 방지.

    Attributes:
        app_lang_var (tk.StringVar): 앱 전역 언어 설정 추적 Tk 변수 ('ko', 'en', 'ja').
        about_info (dict[str, str | int]): 어바웃 다이얼로그 표시용 프로그램 메타데이터.
        app_temp_dir (Path): 현재 세션 전용 격리 임시 디렉터리 경로.
    """
    app_lang_var: tk.StringVar
    about_info: dict[str, str | int]
    app_temp_dir: Path


class AppContainer:
    """애플리케이션 전역 의존성 및 수명주기 관리 DI 컨테이너.

    공통 설정, OS 로케일 감지, 다국어 초기화, 전역 예외 로거 등록 및
    세션별 임시 폴더 생성/파기 관리.
    """

    def __init__(self, root: tk.Tk) -> None:
        """컨테이너 초기화, OS 로케일 감지 및 세션 임시 디렉터리 구성.

        Args:
            root (tk.Tk): 메인 Tkinter 루트 윈도우 인스턴스.
        """
        self.root: tk.Tk = root

        # 1. OS 로케일 자동 감지 (Python 3.11+ getdefaultlocale 비권장에 따른 안전 조회)
        import locale
        try:
            try:
                _loc = (locale.getlocale()[0] or '').lower()
            except (ValueError, TypeError):
                _loc = ''
            if not _loc:
                _loc = (os.environ.get('LANG') or os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or '').lower()
        except (ValueError, TypeError, OSError):
            _loc = ''

        # 지원 언어(ko/en/ja) 매핑, 알 수 없는 로케일은 기본 언어(영어) 폴백
        if _loc.startswith('ko'):
            _initial_lang = 'ko'
        elif _loc.startswith('ja'):
            _initial_lang = 'ja'
        else:
            _initial_lang = DEFAULT_LANG
        self.app_lang_var: tk.StringVar = tk.StringVar(value=_initial_lang)

        # 2. 프로세스별 세션 격리 임시 폴더 생성 (TOCTOU 및 다중 인스턴스 간섭 완화)
        self._base_temp_dir = Path(tempfile.gettempdir()) / APP_TEMP_DIR_NAME
        self._base_temp_dir.mkdir(parents=True, exist_ok=True)
        self.app_temp_dir = Path(tempfile.mkdtemp(prefix=f"{SESSION_DIR_PREFIX}{os.getpid()}_", dir=self._base_temp_dir))

        # 3. 비정상 종료 등으로 잔류한 과거 세션 임시 디렉터리 선별 정리
        self._cleanup_old_session_dirs()

        # 4. 공통 프로그램 메타데이터
        self.about_info: dict[str, str | int] = {
            'program': "Priconne Extraction Tools (Portable)",
            'version': APP_VERSION,
            'updated': APP_LAST_UPDATE,
            'developer': APP_DEVELOPER,
            'website': APP_WEBSITE,
            'year': APP_COPYRIGHT_YEAR,
        }

        self.app_info_for_logger = {
            'APP_VERSION': APP_VERSION,
            'APP_LAST_UPDATE': APP_LAST_UPDATE,
            'APP_DEVELOPER': APP_DEVELOPER,
        }

    def initialize_core_services(self) -> None:
        """전역 로거 및 언어 데이터 유효성 검증 등 핵심 시스템 서비스 초기화.

        languages.json 파일 로드 실패 시 GUI 팝업 경고 알림.
        이미 캐시된 다국어 맵을 전역 로거에 주입하여 이중 I/O 방지.
        """
        from src.languages import get_language_load_error, get_logger_lang_data_map

        load_err = get_language_load_error()
        if load_err:
            from tkinter import messagebox
            logger.error("Failed to load languages.json: %s", load_err)
            messagebox.showerror(
                "Language Load Error",
                f"Cannot read languages.json file.\n({load_err})\n\nPlease check if the translation file is missing or corrupted.\nThe program will run with default settings.",
                parent=self.root,
            )

        setup_global_logging(self.root, self.app_info_for_logger, self.app_lang_var, get_logger_lang_data_map())

    def _cleanup_old_session_dirs(self) -> None:
        """과거 세션 폴더 중 이미 종료된 프로세스의 폴더만 선별 삭제.

        PID 생존이 '확정적으로 종료'된 경우에만 파기하며, PID 토큰이 없는 폴더와
        심볼릭 링크/정션은 삭제 대상에서 제외한다.
        """
        try:
            self._base_temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Failed to ensure base temp dir %s: %s", self._base_temp_dir, e)
            return
        try:
            for child in list(self._base_temp_dir.iterdir()):
                if not (child.name.startswith(SESSION_DIR_PREFIX) and child != self.app_temp_dir):
                    continue
                # 심볼릭 링크는 is_dir()/rmtree가 대상 경로를 따라가므로 우선 제외
                if child.is_symlink():
                    continue
                try:
                    st = os.lstat(child)
                except OSError as e:
                    logger.warning("Failed to inspect old temp dir %s: %s", child, e)
                    continue
                # 실제 디렉터리만 대상 (lstat 기준이라 링크를 따라가지 않음)
                if not stat.S_ISDIR(st.st_mode):
                    continue
                # 윈도우 정션/재분석 지점은 실디렉터리로 보이므로 별도 제외
                if getattr(st, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                    continue
                # 세션 폴더명(session_{pid}_* 또는 session_{pid}) 형태에서 PID 추출
                parts = child.name.split("_")
                if len(parts) < 2 or not parts[1].isdigit():
                    # PID 토큰 미식별 폴더는 생존 여부 판정 불가 → 삭제하지 않음
                    continue
                pid = int(parts[1])
                if is_pid_alive(pid):
                    # 실행 중이거나 생존 판정 불가한 다른 인스턴스의 작업 폴더이므로 보호
                    continue
                try:
                    shutil.rmtree(child)
                except OSError as e:
                    logger.warning("Failed to remove old temp dir %s: %s", child, e)
        except OSError as e:
            logger.warning("Failed to scan temp dir %s: %s", self._base_temp_dir, e)

    def cleanup_shared(self) -> None:
        """앱 정상 종료 시 현재 세션 전용 임시 디렉터리 삭제.

        부모 베이스 임시 디렉터리가 비어 있으면 베이스 폴더까지 함께 정리.
        """
        if self.app_temp_dir.exists():
            try:
                shutil.rmtree(self.app_temp_dir)
            except OSError as e:
                logger.warning("Failed to remove temp dir %s: %s", self.app_temp_dir, e)
        try:
            if self._base_temp_dir.exists() and not any(self._base_temp_dir.iterdir()):
                self._base_temp_dir.rmdir()
        except OSError as e:
            logger.warning("Failed to remove base temp dir %s: %s", self._base_temp_dir, e)

    def get_shared_dependencies(self) -> SharedDependencies:
        """서브 도구 주입용 공유 의존성 번들 반환.

        Returns:
            SharedDependencies: 전역 언어 변수, 어바웃 메타데이터, 세션 임시 경로를 포함하는 객체.
        """
        return SharedDependencies(
            app_lang_var=self.app_lang_var,
            about_info=self.about_info,
            app_temp_dir=self.app_temp_dir,
        )

