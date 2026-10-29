"""프로그램 정보(About) 모달 대화상자 표시 모듈.

메인 런처 및 5개 서브 도구 공통 호출 대상
버전, 최종 업데이트일, 개발자 정보, 라이선스 안내 팝업 렌더링.

요구사항:
    About 팝업은 선택된 UI 언어와 무관하게 항상 영어로만 표시한다.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Mapping
from datetime import datetime
from tkinter import messagebox
from typing import Any

logger = logging.getLogger(__name__)

# About 팝업 고정 영문 문구 (다국어 제외)
_ABOUT_TITLE = 'About Program'
_ABOUT_LABEL_VERSION = 'Version'
_ABOUT_LABEL_UPDATED = 'Last Updated'
_ABOUT_LABEL_DEVELOPER = 'Developer'
_ABOUT_LABEL_WEBSITE = 'Website'


def show_about_dialog(
    about_info: dict[str, str | int] | Mapping[str, Any],
    parent: tk.Misc,
) -> None:
    """프로그램 정보(About) 메시지박스 표시 (언어와 무관하게 영어 고정).

    Title 및 라벨은 하드코딩된 영문 상수를 사용하며 언어 딕셔너리를 참조하지 않는다.

    Args:
        about_info (dict[str, str | int] | Mapping[str, Any]): 프로그램명, 버전, 개발자 정보 맵.
        parent (tk.Misc): 메시지박스를 모달 종속시킬 부모 Tkinter 위젯.
    """
    info_lines: list[str] = []

    # 1. 프로그램 이름
    if 'program' in about_info:
        info_lines.append(str(about_info['program']))
        info_lines.append("")

    # 2. 버전 및 최종 업데이트 날짜
    if 'version' in about_info:
        info_lines.append(f"{_ABOUT_LABEL_VERSION}: {about_info['version']}")
    if 'updated' in about_info:
        info_lines.append(f"{_ABOUT_LABEL_UPDATED}: {about_info['updated']}")

    if 'version' in about_info or 'updated' in about_info:
        info_lines.append("")

    # 3. 개발자 및 공식 웹사이트 URL
    if 'developer' in about_info:
        info_lines.append(f"{_ABOUT_LABEL_DEVELOPER}: {about_info['developer']}")
    if 'website' in about_info:
        info_lines.append(f"{_ABOUT_LABEL_WEBSITE}: {about_info['website']}")

    if 'developer' in about_info or 'website' in about_info:
        info_lines.append("")

    # 4. 저작권 및 라이선스 고지
    dev_name = str(about_info.get('developer', 'IZH318'))
    if '(Github)' in dev_name:
        dev_name = dev_name.replace('(Github)', '').strip()
    try:
        year: int | str = datetime.now().year
    except (ValueError, TypeError, OSError):
        year = about_info.get('year', '2026')
    info_lines.append(f"Copyright © {year} {dev_name}. Released under the GPL-3.0 License.")

    # 5. 다이얼로그 표시 (부모 위젯 유효하지 않을 시 최상위 폴백)
    try:
        messagebox.showinfo(_ABOUT_TITLE, "\n".join(info_lines), parent=parent)
    except (tk.TclError, RuntimeError) as _exc:
        logger.debug("Failed to show about dialog with parent: %s", _exc)
        try:
            messagebox.showinfo(_ABOUT_TITLE, "\n".join(info_lines))
        except (tk.TclError, RuntimeError) as _exc2:
            logger.debug("Failed to show about dialog: %s", _exc2)
