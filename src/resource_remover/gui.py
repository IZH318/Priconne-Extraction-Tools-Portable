# src/resource_remover/gui.py
import tkinter as tk
import os
import threading
import queue
from tkinter import ttk, messagebox
from pathlib import Path

from .languages import LANGUAGES
from .logic import ResourceRemoverLogic

# 확장자 카테고리 정의 (체크박스 단위)
EXTENSION_CATEGORIES = [
    {
        "key": "chk_assetbundle",
        "extensions": [".unity3d"],
    },
    {
        "key": "chk_audio",
        "extensions": [".awb", ".acb"],
    },
    {
        "key": "chk_video",
        "extensions": [".usm"],
    },
]

class ResourceRemoverApp(ttk.Frame):
    def __init__(self, master, app_lang_var=None, about_info=None):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.master = master
        self.logic = ResourceRemoverLogic()
        self.about_info = about_info or {}
        self.use_trash_var = tk.BooleanVar(value=True)
        
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')

        self.lang_var.trace_add('write', self._on_language_change_event)

        # 체크박스 변수 초기화
        self.chk_vars = {}
        for cat in EXTENSION_CATEGORIES:
            self.chk_vars[cat["key"]] = tk.BooleanVar(value=True)

        self.lbl_desc = None
        self.chk_frame = None
        self.chk_widgets = {}
        self.lbl_warn = None
        self.chk_trash = None
        self.btn_start = None
        self.status_var = tk.StringVar()
        self.lbl_status = None

        self.task_queue = queue.Queue()

        self._create_widgets()
        self._update_ui_text()
        self._process_queue()

    def _process_queue(self):
        try:
            while not self.task_queue.empty():
                msg = self.task_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "search_done":
                    self._handle_search_done(msg["target_files"], msg["selected_exts"], msg["lang_dict"])
                elif msg_type == "delete_done":
                    self._handle_delete_done(msg["deleted_count"], msg["errors"], msg["log_filename"], msg["lang_dict"])
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_queue)

    def _on_language_change_event(self, *args):
        try:
            self._update_ui_text()
        except tk.TclError:
            pass

    def _create_widgets(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        self.lbl_desc = ttk.Label(container, text="", justify=tk.CENTER, font=("TkDefaultFont", 10))
        self.lbl_desc.pack(pady=(10, 10))

        # 체크박스 프레임
        self.chk_frame = ttk.LabelFrame(container, text="", padding=10)
        self.chk_frame.pack(pady=5, padx=40, fill=tk.X)

        self.chk_widgets = {}
        for cat in EXTENSION_CATEGORIES:
            chk = ttk.Checkbutton(
                self.chk_frame,
                text="",
                variable=self.chk_vars[cat["key"]],
            )
            chk.pack(anchor=tk.W, pady=2)
            self.chk_widgets[cat["key"]] = chk

        self.lbl_warn = ttk.Label(container, text="", justify=tk.CENTER, foreground="red", font=("TkDefaultFont", 10))
        self.lbl_warn.pack(pady=(10, 15))

        # 하단 컨트롤 (시작/경고 등)
        control_frame = ttk.Frame(container) # Changed parent from content_frame to container
        control_frame.pack(fill='x', pady=5)
        
        # Trash Checkbox
        self.chk_trash = ttk.Checkbutton(control_frame, variable=self.use_trash_var, command=self._update_ui_text)
        self.chk_trash.pack(side='left', padx=5)

        self.btn_start = ttk.Button(control_frame, text="", command=self.start_removal)
        self.btn_start.pack(side='right', padx=5)

        self.lbl_status = ttk.Label(container, textvariable=self.status_var, font=("TkDefaultFont", 10))
        self.lbl_status.pack(side=tk.BOTTOM, pady=10)

    def _update_ui_text(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']

        if self.lbl_desc: self.lbl_desc.config(text=lang_dict['desc'])
        if self.chk_frame: self.chk_frame.config(text=lang_dict['chk_frame_title'])
        if self.lbl_warn:
            if self.use_trash_var.get():
                self.lbl_warn.config(text=lang_dict.get('warn_trash', 'Files will be moved to the Recycle Bin.'), foreground="blue")
            else:
                self.lbl_warn.config(text=lang_dict.get('warn_permanent', 'Files will be permanently deleted.'), foreground="red")
        if self.btn_start: self.btn_start.config(text=lang_dict['btn_start'])
        if self.chk_trash: self.chk_trash.config(text=lang_dict.get('use_trash', 'Move to Recycle Bin'))

        # 체크박스 라벨 업데이트
        if self.chk_widgets:
            for cat in EXTENSION_CATEGORIES:
                self.chk_widgets[cat["key"]].config(text=lang_dict[cat["key"]])

        status_text = self.status_var.get()
        if not status_text or "!" in status_text or "삭제 완료" in status_text or "완료" in status_text or "complete" in status_text or "完了" in status_text:
            pass 
        else:
            self.status_var.set(lang_dict['status_ready'])
            
        if not self.status_var.get():
            self.status_var.set(lang_dict['status_ready'])

    def _get_selected_extensions(self):
        """체크된 카테고리의 확장자 목록을 반환합니다."""
        selected = []
        for cat in EXTENSION_CATEGORIES:
            if self.chk_vars[cat["key"]].get():
                selected.extend(cat["extensions"])
        return selected

    def start_removal(self):
        lang_dict = LANGUAGES[self.lang_var.get()]

        selected_exts = self._get_selected_extensions()
        if not selected_exts:
            messagebox.showwarning(lang_dict.get('warn_title', 'Warning'), lang_dict['warn_no_selection'], parent=self)
            return
            
        self.btn_start.config(state='disabled')
        if hasattr(self, 'chk_trash') and self.chk_trash:
            self.chk_trash.config(state='disabled')
        self.status_var.set(lang_dict.get('status_searching', "Searching..."))
        if self.lbl_status: self.lbl_status.config(foreground="blue")
        
        threading.Thread(target=self._search_thread, args=(selected_exts, lang_dict), daemon=True).start()

    def _search_thread(self, selected_exts, lang_dict):
        target_files = self.logic.count_resources(selected_exts)
        self.task_queue.put({
            "type": "search_done",
            "target_files": target_files,
            "selected_exts": selected_exts,
            "lang_dict": lang_dict
        })

    def _handle_search_done(self, target_files, selected_exts, lang_dict):
        file_count = len(target_files)
        
        if file_count == 0:
            self.btn_start.config(state='normal')
            if hasattr(self, 'chk_trash') and self.chk_trash:
                self.chk_trash.config(state='normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            if self.lbl_status: self.lbl_status.config(foreground="black")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), "삭제할 발견된 파일이 없습니다.", parent=self)
            return

        use_trash = self.use_trash_var.get()
        msg_key = 'confirm_msg_trash' if use_trash else 'confirm_msg_permanent'
        msg = lang_dict.get(msg_key, 'Proceed?').format(count=file_count)

        if messagebox.askyesno(lang_dict.get('confirm_title', 'Confirm Deletion'), msg, parent=self):
            self.status_var.set(lang_dict.get('status_processing', "Processing..."))
            if self.lbl_status: self.lbl_status.config(foreground="blue")
            threading.Thread(target=self._delete_thread, args=(target_files, selected_exts, lang_dict, use_trash), daemon=True).start()
        else:
            self.btn_start.config(state='normal')
            if hasattr(self, 'chk_trash') and self.chk_trash:
                self.chk_trash.config(state='normal')
            self.status_var.set(lang_dict.get('status_ready', 'Ready...'))
            if self.lbl_status: self.lbl_status.config(foreground="black")

    def _delete_thread(self, target_files, selected_exts, lang_dict, use_trash):
        deleted_count, errors, log_filename = self.logic.remove_resources(target_files=target_files, extensions_to_remove=selected_exts, use_trash=use_trash)
        self.task_queue.put({
            "type": "delete_done",
            "deleted_count": deleted_count,
            "errors": errors,
            "log_filename": log_filename,
            "lang_dict": lang_dict
        })

    def _handle_delete_done(self, deleted_count, errors, log_filename, lang_dict):
        if hasattr(self, 'chk_trash') and self.chk_trash:
            self.chk_trash.config(state='normal')
            
        if not errors:
            success_txt = lang_dict.get('success_msg', 'Deletion complete.').replace('{log}', str(os.path.basename(log_filename)) if log_filename else 'None')
            self.status_var.set(success_txt)
            if self.lbl_status: self.lbl_status.config(foreground="green")
            messagebox.showinfo(lang_dict.get('info_title', 'Info'), success_txt, parent=self)
        else:
            error_msg = lang_dict.get('status_error', 'Error: {error}').format(error=f"{len(errors)} errors")
            self.status_var.set(error_msg)
            if self.lbl_status: self.lbl_status.config(foreground="red")
            messagebox.showerror(lang_dict.get('error_title', 'Error'), f"{len(errors)} files failed. See log.", parent=self)

        self.btn_start.config(state='normal')
