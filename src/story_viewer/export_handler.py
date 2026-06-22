from __future__ import annotations
import json
import os
import sqlite3
import tkinter as tk
from typing import Any, Callable, TYPE_CHECKING
import queue

from src.queue_events import ActionEvent
from .logic import StoryDataLoader, StoryFormatter
from . import db_helper

if TYPE_CHECKING:
    from .view import StoryViewerView
    from .db_manager import StoryDBManager


class StoryExportHandler:
    """Story Viewer의 데이터 내보내기 기능을 전담하는 핸들러 클래스입니다.

    스토리 데이터, 파일명 목록, 캐릭터/BGM/배경 이름 등의
    일괄 내보내기를 담당합니다.

    Note:
        Controller와의 순환 참조를 방지하기 위해, Controller 전체를 참조하지 않고
        필요한 콜백과 데이터 접근자만 개별 인자로 주입받습니다.
    """

    def __init__(
        self,
        get_lang_dict: Callable[[], dict[str, str]],
        task_queue: queue.Queue[ActionEvent],
        master: tk.Tk | tk.Toplevel,
        view_mode_var: tk.StringVar,
        get_current_filenames: Callable[[], list[str]],
        get_loaded_filenames: Callable[[], list[str]],
        get_all_files: Callable[[], dict[str, str]],
        get_search_data: Callable[[], dict[str, list[str]]],
        get_server_db_info: Callable[[], dict[str, Any]],
        get_db_manager: Callable[[], StoryDBManager],
        view: StoryViewerView,
    ) -> None:
        """StoryExportHandler를 초기화합니다.

        Args:
            get_lang_dict: 현재 언어 딕셔너리를 반환하는 콜백.
            task_queue: 메인 스레드로 액션을 전달할 큐.
            master: 최상위 Tk 윈도우 (다이얼로그 위치 기준용).
            view_mode_var: 뷰 모드 StringVar (simple/detail).
            get_current_filenames: 현재 리스트에 표시 중인 파일명 리스트 반환 콜백.
            get_loaded_filenames: 전체 로드된 파일명 리스트 반환 콜백.
            get_all_files: 파일명→경로 딕셔너리 반환 콜백.
            get_search_data: 검색 데이터 딕셔너리 반환 콜백.
            get_server_db_info: 서버 DB 정보 딕셔너리 반환 콜백.
            get_db_manager: StoryDBManager 인스턴스 반환 콜백.
            view: StoryViewerView 인스턴스 (UI 조작용).
        """
        self._get_lang_dict = get_lang_dict
        self._task_queue = task_queue
        self._master = master
        self._view_mode_var = view_mode_var
        self._get_current_filenames = get_current_filenames
        self._get_loaded_filenames = get_loaded_filenames
        self._get_all_files = get_all_files
        self._get_search_data = get_search_data
        self._get_server_db_info = get_server_db_info
        self._get_db_manager = get_db_manager
        self._view = view

    @staticmethod
    def _save_list_to_file(data_list: list[str], filename_suffix: str, output_folder: str, header: str = "") -> tuple[bool, Exception | None]:
        """문자열 리스트를 텍스트 파일로 저장합니다.

        Args:
            data_list: 저장할 문자열 리스트.
            filename_suffix: 생성될 파일명의 접미사.
            output_folder: 파일이 저장될 출력 폴더.
            header: 파일 상단에 추가할 헤더 텍스트 (옵션).

        Returns:
            (성공 여부, 에러 객체) 튜플.
        """
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    if header:
                        f.write(f"--- {header} ---\n\n")
                    for item in data_list:
                        f.write(f"{item}\n")
                else:
                    f.write(f"(No data found for {filename_suffix})\n")
            return True, None
        except OSError as e:
            return False, e

    def export_master_thread(self, selected_options: dict[str, Any], output_folder: str) -> None:
        """선택된 여러 유형의 데이터들을 백그라운드 스레드에서 파일로 내보냅니다.

        Args:
            selected_options: 사용자가 선택한 내보내기 옵션 딕셔너리.
            output_folder: 내보낼 대상 폴더 경로.
        """
        lang_dict = self._get_lang_dict()
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []

        if selected_options['story_data']:
            story_data_scope = selected_options['story_data_scope']
            filenames_to_export = []
            if story_data_scope == 'current_list':
                filenames_to_export = self._get_current_filenames()
            elif story_data_scope == 'all_loaded':
                filenames_to_export = self._get_loaded_filenames()
            
            if not filenames_to_export:
                export_results['story_data'] = {'success': 0, 'failed': 0, 'details': ["No story data files selected for export."]}
            else:
                type_name = lang_dict.get('export_type_story_data', 'Story Data')
                success_count = 0
                fail_count = 0
                current_failed_details = []

                all_files = self._get_all_files()
                for i, filename in enumerate(filenames_to_export):
                    current_success = success_count
                    current_fail = fail_count
                    def _update_export_status(tn=type_name, s=current_success, f=current_fail, idx=i, tf=len(filenames_to_export)):
                        self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=idx+1, t=tf)
                    self._task_queue.put(ActionEvent(action=_update_export_status))
                    filepath = all_files.get(filename)
                    if not filepath:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (File Not Found)")
                        continue
                    
                    is_valid, data, _ = StoryDataLoader.is_valid_storydata(filepath)
                    if not is_valid:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Parse Error)")
                        continue
                        
                    output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".txt")
                    try:
                        text_to_write = "".join([text for text, _ in StoryFormatter.format_story_data(data, self._view_mode_var.get())])
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(text_to_write)
                        success_count += 1
                    except (OSError, json.JSONDecodeError) as e:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Error: {e})")
                
                export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        loaded_filenames = self._get_loaded_filenames()
        search_data = self._get_search_data()
        other_export_types = [
            {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': lambda: sorted(list(loaded_filenames)), 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
            {'type': 'character_names', 'name_key': 'export_type_character_names', 'data_func': lambda: sorted(search_data.get('character_names', [])), 'file_suffix': 'character_names', 'header_key': 'export_type_character_names'},
            {'type': 'bgm_names', 'name_key': 'export_type_bgm_names', 'data_func': lambda: sorted(search_data.get('bgms', [])), 'file_suffix': 'bgm_names', 'header_key': 'export_type_bgm_names'},
            {'type': 'background_names', 'name_key': 'export_type_background_names', 'data_func': lambda: sorted(search_data.get('backgrounds', [])), 'file_suffix': 'background_names', 'header_key': 'export_type_background_names'},
        ]
        
        if selected_options.get('event_list_master'):
            server_db_info = self._get_server_db_info()
            db_manager = self._get_db_manager()
            def get_event_list(server_key):
                db_info = server_db_info.get(server_key)
                if not db_info or not db_manager.db_status.get(server_key):
                    return []
                try:
                    return sorted(db_helper.fetch_event_names(db_info))
                except sqlite3.Error:
                    return []

            other_export_types.extend([
                {'type': 'event_list_jp', 'name_key': 'export_type_event_list_jp', 'data_func': lambda: get_event_list('JP'), 'file_suffix': 'event_list_jp', 'header_key': 'export_type_event_list_jp'},
                {'type': 'event_list_kr', 'name_key': 'export_type_event_list_kr', 'data_func': lambda: get_event_list('KR'), 'file_suffix': 'event_list_kr', 'header_key': 'export_type_event_list_kr'}
            ])
        
        for task in other_export_types:
            task_type = task['type']
            if not selected_options.get(task_type):
                continue

            type_name = lang_dict.get(task['name_key'], task_type)
            success_count = 0
            fail_count = 0
            current_failed_details = []

            self._task_queue.put(ActionEvent(action=lambda tn=type_name: self._view.update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0)))
            try:
                data_list = task['data_func']()
                if not data_list:
                    export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                    continue

                success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name) if 'event_list' in task_type else "")
                if success:
                    success_count = 1
                else:
                    fail_count = 1
                    current_failed_details.append(f"{type_name} (Error: {error})")
            except (sqlite3.Error, OSError) as e:
                fail_count += 1
                current_failed_details.append(f"{type_name} (Unexpected Error: {e})")

            export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
            total_exported_count += success_count
            total_failed_count += fail_count
            all_failed_details.extend(current_failed_details)


        self._task_queue.put(ActionEvent(action=lambda: self._finish_export(total_exported_count, total_failed_count, all_failed_details)))

    def _finish_export(self, exported_count: int, failed_count: int, failed_list: list[str]) -> None:
        """데이터 내보내기 작업 완료 후 결과를 UI와 사용자에게 알립니다.

        Args:
            exported_count: 성공적으로 내보낸 항목 수.
            failed_count: 내보내기에 실패한 항목 수.
            failed_list: 실패 원인이 포함된 문자열 리스트.
        """
        from tkinter import messagebox
        lang_dict = self._get_lang_dict()

        if exported_count > 0:
            messagebox.showinfo(lang_dict['msgbox_export_complete_title'], lang_dict['msgbox_export_complete_msg'].format(exported_count=exported_count), parent=self._master)
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        else:
            messagebox.showwarning(lang_dict['msgbox_export_failed_title'], lang_dict['msgbox_export_failed_msg'].format(failed_count=failed_count), parent=self._master)
            self._view.update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        
        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(lang_dict['msgbox_export_error_details_title'], lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg), parent=self._master)
