from __future__ import annotations
import tkinter as tk
from tkinter import messagebox


def show_about_dialog(lang_dict: dict[str, str], about_info: dict[str, str], parent: tk.Misc) -> None:
    """프로그램 정보(About) 대화상자를 표시합니다.

    5개 모듈(Renamer, Unity, AV, Story, Resource)에서 중복되던 로직을 통합합니다.

    Args:
        lang_dict: 현재 선택된 언어의 다국어 딕셔너리.
        about_info: About 대화상자에 표시될 정보 딕셔너리.
        parent: 대화상자의 부모 위젯.
    """
    title = lang_dict.get('about_title', lang_dict.get('about_header', 'Program Information'))
    
    info_lines = []
    
    # 1. 프로그램 이름
    if 'program' in about_info:
        info_lines.append(about_info['program'])
        info_lines.append("")
        
    # 2. 버전 및 업데이트
    if 'version' in about_info:
        label = lang_dict.get('about_label_version', 'Version')
        info_lines.append(f"{label}: {about_info['version']}")
    if 'updated' in about_info:
        label = lang_dict.get('about_label_updated', 'Updated')
        info_lines.append(f"{label}: {about_info['updated']}")
        
    if 'version' in about_info or 'updated' in about_info:
        info_lines.append("")
        
    # 3. 개발자 및 웹사이트
    if 'developer' in about_info:
        label = lang_dict.get('about_label_developer', 'Developer')
        info_lines.append(f"{label}: {about_info['developer']}")
    if 'website' in about_info:
        label = lang_dict.get('about_label_website', 'Website')
        info_lines.append(f"{label}: {about_info['website']}")
        
    if 'developer' in about_info or 'website' in about_info:
        info_lines.append("")
        
    # 4. 저작권
    dev_name = about_info.get('developer', 'IZH318')
    if '(Github)' in dev_name:
        dev_name = dev_name.replace('(Github)', '').strip()
    year = about_info.get('year', '2026')
    info_lines.append(f"Copyright © {year} {dev_name}. Released under the GPL-3.0 License.")
    
    messagebox.showinfo(title, "\n".join(info_lines), parent=parent)
