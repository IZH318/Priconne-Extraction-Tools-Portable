from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
import queue
import threading
import os
from typing import Any

from src.languages import RESOURCE_REMOVER_LANGUAGES as LANGUAGES
from src.constants import EXTENSION_CATEGORIES
from src.queue_events import SearchDoneEvent, DeleteDoneEvent
from .logic import ResourceRemoverLogic
from .view import ResourceRemoverView

class ResourceRemoverController:
    def __init__(self, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None) -> None:
        self.master = master
        self.logic = ResourceRemoverLogic()
        self.about_info = about_info or {}
        
        self.use_trash_var = tk.BooleanVar(value=True)
        self.chk_vars = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)
            
        self.status_var = tk.StringVar()
        self.is_complete = False
        self.task_queue = queue.Queue()

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.view = ResourceRemoverView(master, self)
        
        self.lang_var.trace_add('write', self._on_language_change_event)

        self.view.update_ui_text()
        self._process_queue()

    def _process_queue(self) -> None:
        try:
            while not self.task_queue.empty():
                msg = self.task_queue.get_nowait()
                if isinstance(msg, SearchDoneEvent):
                    self._handle_search_done(msg.target_files, msg.lang_dict)
                elif isinstance(msg, DeleteDoneEvent):
                    self._handle_delete_done(msg.deleted_count, msg.errors, msg.log_path, msg.lang_dict)
        except queue.Empty:
            pass
        finally:
            self.view.after(100, self._process_queue)

    def get_lang_dict(self) -> dict:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

    def _on_language_change_event(self, *args) -> None:
        try:
            self.view.update_ui_text()
        except (tk.TclError, AttributeError):
            pass

    def _get_selected_extensions(self) -> list[str]:
        selected = []
        for cat in EXTENSION_CATEGORIES:
            if self.chk_vars[cat["key"]].get():
                selected.extend(cat["extensions"])
        return selected

    def start_removal(self) -> None:
        """선택된 카테고리의 리소스 파일 삭제를 시작합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(lang_dict.get('warn_title', 'Warning'), lang_dict['warn_no_selection'], parent=self.view)
            return
            
        self.is_complete = False
        self.view.set_control_state('disabled')
        self.status_var.set(lang_dict.get('status_searching', "Searching..."))
        self.view.set_status_color("blue")
        
        threading.Thread(target=self._search_thread, args=(selected_exts, lang_dict), daemon=True).start()

    def _search_thread(self, selected_exts, lang_dict) -> None:
        target_files = self.logic.count_resources(selected_exts)
        self.task_queue.put(SearchDoneEvent(
            target_files=target_files,
            lang_dict=lang_dict
        ))

    def _handle_search_done(self, target_files, lang_dict) -> None:
        file_count = len(target_files)
        
        if file_count == 0:
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), lang_dict.get('no_files_found', 'No files found to delete.'), parent=self.view)
            return

        use_trash = self.use_trash_var.get()
        msg_key = 'confirm_msg_trash' if use_trash else 'confirm_msg_permanent'
        msg = lang_dict.get(msg_key, 'Proceed?').format(count=file_count)

        if messagebox.askyesno(lang_dict.get('confirm_title', 'Confirm Deletion'), msg, parent=self.view):
            self.status_var.set(lang_dict.get('status_processing', "Processing..."))
            self.view.set_status_color("blue")
            selected_exts = self._get_selected_extensions()
            threading.Thread(target=self._delete_thread, args=(target_files, selected_exts, lang_dict, use_trash), daemon=True).start()
        else:
            self.view.set_control_state('normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            self.view.set_status_color("black")

    def _delete_thread(self, target_files, selected_exts, lang_dict, use_trash) -> None:
        deleted_count, errors, log_filename = self.logic.remove_resources(target_files=target_files, extensions_to_remove=selected_exts, use_trash=use_trash)
        self.task_queue.put(DeleteDoneEvent(
            deleted_count=deleted_count,
            errors=errors,
            log_path=log_filename,
            lang_dict=lang_dict
        ))

    def _handle_delete_done(self, deleted_count, errors, log_filename, lang_dict) -> None:
        self.view.set_control_state('normal')
        self.is_complete = True
            
        if not errors:
            success_txt = lang_dict.get('success_msg', 'Deletion complete.').replace('{log}', str(os.path.basename(log_filename)) if log_filename else 'None')
            self.status_var.set(success_txt)
            self.view.set_status_color("green")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), success_txt, parent=self.view)
        else:
            error_msg = lang_dict.get('status_error', 'Error: {error}').format(error=f"{len(errors)} errors")
            self.status_var.set(error_msg)
            self.view.set_status_color("red")
            messagebox.showerror(lang_dict.get('error_title', 'Error'), lang_dict.get('error_delete_failed', '{count} files failed.').format(count=len(errors)), parent=self.view)

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다. (현재 리소스 없음)"""
        pass
