"""프로그램 정보(About) 모달 대화상자 표시 모듈.

메인 런처 및 5개 서브 도구 공통 호출 대상
버전, 최종 업데이트일, 개발자 정보, 라이선스 안내 팝업 렌더링.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Mapping
from datetime import datetime
from tkinter import messagebox
from typing import Any

logger = logging.getLogger(__name__)


def show_about_dialog(
    lang_dict: dict[str, str],
    about_info: dict[str, str | int] | Mapping[str, Any],
    parent: tk.Misc,
) -> None:
    """프로그램 정보(About) 메시지박스 표시.

    Args:
        lang_dict (dict[str, str]): 현재 활성화된 언어의 라벨 번역 딕셔너리.
        about_info (dict[str, str | int] | Mapping[str, Any]): 프로그램명, 버전, 개발자 정보 맵.
        parent (tk.Misc): 메시지박스를 모달 종속시킬 부모 Tkinter 위젯.
    """
    if not isinstance(lang_dict, dict):
        lang_dict = {}
    title = lang_dict.get('about_title', 'About Program')

    info_lines: list[str] = []

    # 1. 프로그램 이름
    if 'program' in about_info:
        info_lines.append(str(about_info['program']))
        info_lines.append("")

    # 2. 버전 및 최종 업데이트 날짜
    if 'version' in about_info:
        label = lang_dict.get('about_label_version', 'Version')
        info_lines.append(f"{label}: {about_info['version']}")
    if 'updated' in about_info:
        label = lang_dict.get('about_label_updated', 'Last Updated')
        info_lines.append(f"{label}: {about_info['updated']}")

    if 'version' in about_info or 'updated' in about_info:
        info_lines.append("")

    # 3. 개발자 및 공식 웹사이트 URL
    if 'developer' in about_info:
        label = lang_dict.get('about_label_developer', 'Developer')
        info_lines.append(f"{label}: {about_info['developer']}")
    if 'website' in about_info:
        label = lang_dict.get('about_label_website', 'Website')
        info_lines.append(f"{label}: {about_info['website']}")

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
        messagebox.showinfo(title, "\n".join(info_lines), parent=parent)
    except (tk.TclError, RuntimeError) as _exc:
        logger.debug("Failed to show about dialog with parent: %s", _exc)
        try:
            messagebox.showinfo(title, "\n".join(info_lines))
        except (tk.TclError, RuntimeError) as _exc2:
            logger.debug("Failed to show about dialog: %s", _exc2)

