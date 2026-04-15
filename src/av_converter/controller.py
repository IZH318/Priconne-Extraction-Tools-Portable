from __future__ import annotations
import logging
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
import queue
import threading
from src.cancellation_token import CancellationToken
from pathlib import Path
import tempfile
import shutil
from typing import Any

from src.languages import AV_CONVERTER_LANGUAGES as LANGUAGES
from src.constants import SEPARATOR_LONG as SEPARATOR, APP_VERSION, APP_LAST_UPDATE, APP_DEVELOPER, APP_WEBSITE
from src.queue_events import (
    QueueEvent, LogEvent, LogBlockEvent, ProgressEvent, CompletionEvent
)
from .logic import ConversionLogic, FFmpegDownloader
from .view import AVConverterView

class AVConverterController:
    def __init__(self, master: Any, app_lang_var: tk.StringVar | None = None, about_info: dict[str, str] | None = None, app_temp_dir: str | None = None) -> None:
        self.master = master
        
        self.current_lang = 'ko'
        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value=self.current_lang)
        self.lang_data = LANGUAGES.get(self.current_lang, {})
        self.lang_var.trace_add("write", self._on_language_change_event)
        
        self.base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
        self.log_queue = queue.Queue()
        self.cancel_token = CancellationToken()
        self.logic = ConversionLogic(self.log_queue, self.base_path)
        
        self.view = AVConverterView(master, self)
        
        self.about_info = about_info or {
            'program': "AV Converter", 'version': APP_VERSION, 'updated': APP_LAST_UPDATE,
            'developer': APP_DEVELOPER, 'website': APP_WEBSITE
        }
        
        if app_temp_dir:
            self._preview_temp_dir = app_temp_dir
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix='priconne_preview_')
        
        self.usmtoolkit_path = None
        self.vgmstream_path = None
        self.video_full_paths = []
        self.audio_full_paths = []
        self.video_total_files = 0
        self.audio_total_files = 0
        self.video_log_history = []
        self.audio_log_history = []

        self._find_tools()
        ffmpeg_parent_dir = self.usmtoolkit_path.parent if self.usmtoolkit_path else self.base_path
        self.ffmpeg_downloader = FFmpegDownloader(self.log_queue, ffmpeg_parent_dir, lambda: self.lang_data)
        self.last_log_timestamp = {'video': None, 'audio': None}

        self._log_initial_status()
        self._process_log_queue()

    def get_lang_dict(self) -> dict:
        """현재 선택된 언어의 다국어 딕셔너리를 반환합니다."""
        return LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])

    def _on_language_change_event(self, *args) -> None:
        lang_code = self.lang_var.get()
        if lang_code in LANGUAGES:
            self.lang_data = LANGUAGES[lang_code]
            self.view.switch_language(lang_code)
            self._redraw_logs()

    def _find_tools(self) -> None:
        for root, _, files in os.walk(self.base_path.parent):
            lower_files = [f.lower() for f in files]
            if not self.usmtoolkit_path and "usmtoolkit.exe" in lower_files:
                self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "vgmstream-cli.exe" in lower_files and "vgmstream" in str(Path(root)).lower():
                self.vgmstream_path = Path(root) / "vgmstream-cli.exe"
                # UsmToolkit의 구버전 하드코딩(test.exe) 호환성을 위해 파일 복사
                test_exe_path = Path(root) / "test.exe"
                if not test_exe_path.exists():
                    try:
                        shutil.copy2(self.vgmstream_path, test_exe_path)
                    except Exception:
                        pass

    def show_about_info(self) -> None:
        """프로그램 정보 대화상자를 표시합니다."""
        lang_dict = LANGUAGES.get(self.lang_var.get(), LANGUAGES['ko'])
        title = lang_dict.get('about_header', 'Program Information')
        info_lines = []
        for key, value in self.about_info.items():
            label_key = f'about_label_{key}'
            label_text = lang_dict.get(label_key, key.capitalize())
            info_lines.append(f"{label_text}: {value}")
        messagebox.showinfo(title, "\n".join(info_lines), parent=self.view)

    def _log_tool_status(self, tab: str, tool_path, tool_name: str, error_desc_key: str) -> None:
        if tool_path:
            self._add_log_entry(tab, 'env_success', tool_name=tool_name)
            self._add_log_entry(tab, 'env_path', path=self.logic.get_relative_path(tool_path))
        else:
            self._add_log_entry(tab, 'env_error', tool_name=tool_name)
            self._add_log_entry(tab, error_desc_key)

    def _log_initial_status(self):
        self.video_log_history.clear()
        self.audio_log_history.clear()
        
        for tab in ['video', 'audio']:
            self._add_log_entry(tab, 'program_started')
            self.log_queue.put(LogEvent(target=tab, un_timestamped=True, kwargs={'text': ""}))

        self._add_log_entry('video', 'env_check_header')
        self._log_tool_status('video', self.usmtoolkit_path, "UsmToolkit.exe", 'env_error_desc_video')
        if self.usmtoolkit_path:
            ffmpeg_path = self.ffmpeg_downloader.ffmpeg_path if self.ffmpeg_downloader.ffmpeg_path.exists() else None
            self._log_tool_status('video', ffmpeg_path, "FFmpeg (ffmpeg.exe)", 'env_error_desc_ffmpeg_auto_download')
        self.log_queue.put(LogEvent(target='video', un_timestamped=True, kwargs={'text': ""}))
        self._add_log_entry('video', 'max_worker_log', count=self.logic.MAX_WORKERS)
        self.log_queue.put(LogEvent(target='video', un_timestamped=True, kwargs={'text': ""}))
        self._add_spacing('video')

        self._add_log_entry('audio', 'env_check_header')
        self._log_tool_status('audio', self.vgmstream_path, "vgmstream(vgmstream-cli.exe)", 'env_error_desc_audio')
        self.log_queue.put(LogEvent(target='audio', un_timestamped=True, kwargs={'text': ""}))
        self._add_log_entry('audio', 'max_worker_log', count=self.logic.MAX_WORKERS)
        self.log_queue.put(LogEvent(target='audio', un_timestamped=True, kwargs={'text': ""}))
        self._add_spacing('audio')

    def add_files_cmd(self, tab_type: str) -> None:
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_files(file_types), file_types, full_paths, filenames_var, tab_type)

    def add_folder_cmd(self, tab_type: str) -> None:
        is_audio = (tab_type == 'audio')
        file_types = [("CRIWARE Audio", "*.awb")] if is_audio else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if is_audio else self.view.video_filenames_var
        self._add_paths_to_list(self._select_folder_and_search(file_types), file_types, full_paths, filenames_var, tab_type)

    def on_dnd_drop(self, event, listbox, tab_type) -> None:
        if tab_type == 'audio':
            full_paths = self.audio_full_paths
            filenames_var = self.view.audio_filenames_var
            file_types = [("CRIWARE Audio", "*.awb")]
            if self.view.audio_widgets.get('action_btn', tk.Button).cget('state') == 'disabled':
                return
        else:
            full_paths = self.video_full_paths
            filenames_var = self.view.video_filenames_var
            file_types = [("USM Video files", "*.usm")]
            if self.view.video_widgets.get('action_btn', tk.Button).cget('state') == 'disabled':
                return

        paths = self._parse_dnd_files(event.data)
        if not paths:
            return
        self._add_paths_to_list(paths, file_types, full_paths, filenames_var, tab_type)

    def _parse_dnd_files(self, data) -> list[str]:
        try:
            return self.view.winfo_toplevel().tk.splitlist(data)
        except (AttributeError, tk.TclError):
            import shlex
            try:
                return shlex.split(data)
            except ValueError:
                import re
                return [p.strip('{}') for p in re.findall(r'\{[^{}]*\}|[^ ]+', data) if p.strip()]

    def _select_files(self, file_types) -> list[str]:
        return list(filedialog.askopenfilenames(title=self.lang_data.get('dialog_select_files', '파일을 선택하세요'), filetypes=file_types) or [])

    def _select_folder_and_search(self, file_types) -> list[str]:
        folder = filedialog.askdirectory(title=self.lang_data.get('dialog_select_folder', '폴더를 선택하세요'))
        if not folder:
            return []
        exts = [ext.strip('*.') for _, p in file_types for ext in p.split()]
        found_files = []
        for r, _, fs in os.walk(folder):
            for f in fs:
                if any(f.lower().endswith(f".{ext}") for ext in exts):
                    found_files.append(str(Path(r) / f))
        return found_files

    def _update_listbox(self, fp, fv) -> None:
        fv.set([os.path.basename(p) for p in fp])
        
    def _add_paths_to_list(self, new_paths, file_types, full_paths, filenames_var, tab_type) -> None:
        if not new_paths:
            return

        unique_new_paths = [p for p in new_paths if p not in set(full_paths)]
        if not unique_new_paths:
            self._add_spacing(tab_type)
            self._add_log_entry(tab_type, 'alert_files_exist')
            self._add_spacing(tab_type)
            return

        full_paths.extend(unique_new_paths)
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_files_added', count=len(unique_new_paths))
        self._add_log_entry(tab_type, 'log_total_files', total=len(full_paths))
        self._add_spacing(tab_type)

    def remove_selected_from_list(self, listbox, tab_type) -> None:
        full_paths = self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if tab_type == 'audio' else self.view.video_filenames_var
        
        sel_idx = listbox.curselection()
        if not sel_idx: 
            return
        
        for i in sorted(sel_idx, reverse=True): 
            del full_paths[i]
            
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_files_removed', count=len(sel_idx))
        self._add_spacing(tab_type)

    def clear_list(self, tab_type) -> None:
        full_paths = self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        filenames_var = self.view.audio_filenames_var if tab_type == 'audio' else self.view.video_filenames_var
        
        if not full_paths: 
            return
        
        count = len(full_paths)
        full_paths.clear()
        
        self._update_listbox(full_paths, filenames_var)
        self._add_spacing(tab_type)
        self._add_log_entry(tab_type, 'log_all_files_removed', count=count)
        self._add_spacing(tab_type)

    def start_video_conversion(self, output_dir) -> None:
        """비디오 변환 작업을 백그라운드 스레드로 시작합니다.

        Workflow: start_video_conversion → _start_ffmpeg_preparation → _start_actual_video_conversion
        """
        if not self.video_full_paths:
            self._add_log_entry('video', 'error_no_files')
            return
        if not output_dir:
            self._add_log_entry('video', 'error_no_output_video')
            return
        self._start_ffmpeg_preparation(output_dir)

    def _start_ffmpeg_preparation(self, output_dir) -> None:
        if not self.usmtoolkit_path:
            self._add_log_entry('video', 'ffmpeg_no_usm_path')
            return

        self.view.set_ui_state('video', 'disabled')
        self._add_log_entry('video', 'ffmpeg_preparing')
        
        download_future = self.ffmpeg_downloader.ensure_ffmpeg_ready()

        def check_ffmpeg_status():
            if download_future.done():
                try:
                    if download_future.result(): 
                        self._start_actual_video_conversion(output_dir)
                    else: 
                        self._add_log_entry('video', 'ffmpeg_prepare_fail')
                        self.view.reset_ui_state('video')
                except Exception as e:
                    self._add_log_entry('video', 'ffmpeg_prepare_fail')
                    self._add_log_entry('video', 'conv_log_error_exception', error=e)
                    self.view.reset_ui_state('video')
            else: 
                self.view.after(100, check_ffmpeg_status)
                
        self.view.after(100, check_ffmpeg_status)
    
    def _start_conversion_thread(self, tab_type, target_func, args) -> None:
        self._add_spacing(tab_type)
        widgets = self.view.video_widgets if tab_type == 'video' else self.view.audio_widgets
        
        self.view.set_ui_state(tab_type, 'disabled')
        self.cancel_token.reset()
        
        widgets['action_btn'].config(
            state='normal', 
            text=self.lang_data.get('cancel_conversion', 'Cancel'),
            command=self.cancel_token.cancel
        )
        
        thread = threading.Thread(target=target_func, daemon=True, args=args)
        thread.start()

    def _start_actual_video_conversion(self, output_dir) -> None:
        self._start_conversion_thread(
            'video',
            self.logic.run_video_conversion,
            (self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.cancel_token)
        )

    def start_audio_conversion(self, output_dir, overwrite) -> None:
        """오디오 변환 작업을 백그라운드 스레드로 시작합니다."""
        if not self.audio_full_paths:
            self._add_log_entry('audio', 'error_no_files')
            return
        if not output_dir:
            self._add_log_entry('audio', 'error_no_output_audio')
            return

        self._start_conversion_thread(
            'audio',
            self.logic.run_audio_conversion,
            (self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.cancel_token)
        )

    def _render_log_entry(self, timestamp, key, kwargs, last_ts=None) -> str:
        if key == 'spacing': 
            return "\n"

        content = ""
        if key == 'raw':
            content = kwargs.get('text', '')
        elif key == 'about_header':
            content = self.lang_data.get(key, '[ Program Information ]') + '\n'
        elif key == 'about_line_key':
            label_key = kwargs.get('label_key')
            label = self.lang_data.get(label_key, label_key)
            value = kwargs.get('value', '')
            content = self.lang_data.get('about_line', "  - {label}\\t: {value}").format(label=label, value=value)
        else:
            template = self.lang_data.get(key)
            if template:
                try: 
                    content = template.format(**kwargs)
                except (KeyError, TypeError) as e: 
                    content = f"<{key}: formatting error {e}>"
            else: 
                content = f"<{key} not found in language data>"

        first_line_prefix = ""
        subsequent_line_prefix = ""
        if timestamp:
            if timestamp != last_ts: 
                first_line_prefix = f"[{timestamp}] "
            else: 
                first_line_prefix = " " * 13
            subsequent_line_prefix = " " * 13
        
        lines = content.splitlines()
        if not lines: 
            if key not in ('about_line_key'):
                return first_line_prefix.rstrip() + '\n'
            else:
                return first_line_prefix.rstrip()

        processed_lines = [f"{first_line_prefix}{lines[0]}"]
        processed_lines.extend([f"{subsequent_line_prefix}{line}" for line in lines[1:]])
        
        final_message = '\n'.join(processed_lines)
        return final_message + '\n'
        
    def _add_log_entry(self, target_tab, log_key, **kwargs) -> None:
        self.log_queue.put(LogEvent(target=target_tab, key=log_key, kwargs=kwargs))

    def _add_spacing(self, target_tab) -> None:
        self.log_queue.put(LogEvent(target=target_tab, is_spacing=True))
    
    def _redraw_logs(self) -> None:
        log_configs = [
            ('video', self.video_log_history, self.view.video_log_text),
            ('audio', self.audio_log_history, self.view.audio_log_text)
        ]
        for tab, history_list, log_widget in log_configs:
            log_widget.config(state='normal')
            log_widget.delete('1.0', tk.END)
            last_ts = None
            
            block_ts_map = {}
            for i, (timestamp, key, kwargs) in enumerate(history_list):
                if timestamp:
                    if i > 0 and timestamp == history_list[i-1][0] and key != 'raw' and history_list[i-1][1] != 'raw':
                         render_ts = timestamp
                         last_ts_for_render = block_ts_map.get((timestamp, key), timestamp)
                    else:
                         render_ts = timestamp
                         last_ts_for_render = last_ts
                         block_ts_map[(timestamp, key)] = timestamp
                else:
                    render_ts = None
                    last_ts_for_render = last_ts
                
                message = self._render_log_entry(render_ts, key, kwargs, last_ts_for_render)
                log_widget.insert(tk.END, message)
                
                if render_ts: 
                    last_ts = render_ts

            self.last_log_timestamp[tab] = last_ts
            log_widget.config(state='disabled')
            log_widget.see(tk.END)

    def _process_log_queue(self) -> None:
        try:
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                if not isinstance(msg, QueueEvent):
                    continue

                if isinstance(msg, ProgressEvent) or isinstance(msg, CompletionEvent):
                    if isinstance(msg, ProgressEvent): 
                        self._handle_progress_update(msg)
                    else: 
                        self._handle_completion_signal(msg)
                    continue

                target_tab, log_widget, history = (msg.target, self.view.video_log_text, self.video_log_history) if msg.target == 'video' else (msg.target, self.view.audio_log_text, self.audio_log_history)
                log_widget.config(state='normal')

                if isinstance(msg, LogEvent):
                    if msg.is_spacing:
                        history.append((None, 'spacing', {}))
                        log_widget.insert(tk.END, '\n')
                    else:
                        timestamp = None if msg.un_timestamped else datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        log_key = msg.key
                        kwargs = msg.kwargs
                        last_ts = self.last_log_timestamp[target_tab]
                        history.append((timestamp, log_key, kwargs))
                        log_widget.insert(tk.END, self._render_log_entry(timestamp, log_key, kwargs, last_ts))
                        
                        logging.info("[AV_%s] %s %s", target_tab.upper(), log_key, kwargs)
                        
                        if timestamp: 
                            self.last_log_timestamp[target_tab] = timestamp
                            
                elif isinstance(msg, LogBlockEvent):
                    log_entries = msg.entries
                    block_timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    last_ts_before_block = self.last_log_timestamp[target_tab]

                    for i, (l_key, l_kwargs) in enumerate(log_entries):
                        last_ts_for_render = last_ts_before_block if i == 0 else block_timestamp
                        history.append((block_timestamp, l_key, l_kwargs))
                        log_widget.insert(tk.END, self._render_log_entry(block_timestamp, l_key, l_kwargs, last_ts_for_render))
                        logging.info("[AV_%s] %s %s", target_tab.upper(), l_key, l_kwargs)

                    if log_entries:
                        self.last_log_timestamp[target_tab] = block_timestamp
                
                log_widget.see(tk.END)
                log_widget.config(state='disabled')

        except queue.Empty: 
            pass
        finally: 
            self.view.after(100, self._process_log_queue)
    
    def _handle_progress_update(self, msg: ProgressEvent) -> None:
        d = self.lang_data
        target_tab = msg.target
        widgets = self.view.video_widgets if target_tab == 'video' else self.view.audio_widgets
        
        if msg.is_start:
            total = msg.total
            setattr(self, f'{target_tab}_total_files', total)
            widgets['progress'].config(maximum=total, value=0)
            widgets['status_label'].config(text=d['status_starting'].format(total=total))
        else:
            value = msg.current
            total = getattr(self, f'{target_tab}_total_files')
            widgets['progress']['value'] = value
            widgets['status_label'].config(text=d['status_processing'].format(current=value, total=total))
    
    def _handle_completion_signal(self, msg: CompletionEvent) -> None:
        d = self.lang_data
        tab_type = 'video' if msg.target == '__VIDEO_DONE__' else 'audio'
        widgets = self.view.video_widgets if tab_type == 'video' else self.view.audio_widgets
        total = getattr(self, f'{tab_type}_total_files')
        current = widgets['progress']['value']
        widgets['status_label'].config(text=d['status_complete'].format(current=current, total=total))
        self.view.reset_ui_state(tab_type)

    def preview_selected(self, listbox, tab_type) -> None:
        full_paths = self.audio_full_paths if tab_type == 'audio' else self.video_full_paths
        selection = listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(full_paths):
            return
        file_path = full_paths[idx]
        
        if tab_type == 'audio':
            self._preview_audio(file_path)
        else:
            self._preview_video(file_path)

    def _run_preview_task(self, worker_func, callback_func) -> None:
        popup = self.view.create_progress_popup()
        def thread_target():
            result = worker_func()
            self.view.after(0, lambda: [self.view.destroy_popup_safely(popup), callback_func(result)])
        threading.Thread(target=thread_target, daemon=True).start()

    def _preview_audio(self, file_path) -> None:
        d = self.lang_data
        if not self.vgmstream_path:
            messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_no_tool_audio', 'vgmstream not found.'), parent=self.view)
            return
        
        def on_analyze_done(stream_count):
            if stream_count == 0:
                messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_error', 'Preview failed: {error}').format(error='No streams'), parent=self.view)
                return
            
            if stream_count == 1:
                stream_name = self.logic.get_stream_name(file_path, 1, self.vgmstream_path)
                self._play_audio_stream(file_path, 1, stream_name)
            else:
                def map_builder(tree):
                    stream_map = {}
                    name_map = {}
                    for i in range(1, stream_count + 1):
                        name = self.logic.get_stream_name(file_path, i, self.vgmstream_path)
                        item_id = tree.insert('', tk.END, values=(i, name))
                        stream_map[item_id] = i
                        name_map[item_id] = name
                    tree.stream_map = stream_map
                    tree.name_map = name_map
                    
                def on_double_click(tree):
                    item_id = tree.focus()
                    if hasattr(tree, 'stream_map') and item_id in tree.stream_map:
                        self._play_audio_stream(file_path, tree.stream_map[item_id], tree.name_map[item_id])
                        
                self.view.show_track_selector(stream_count, map_builder, on_double_click)
        
        self._run_preview_task(
            lambda: self.logic.get_stream_count(file_path, self.vgmstream_path),
            on_analyze_done
        )

    def _play_audio_stream(self, file_path, stream_num, stream_name=None) -> None:
        d = self.lang_data
        filename = f"{stream_name}.wav" if stream_name else f"preview_{os.path.basename(file_path)}_{stream_num}.wav"
        temp_wav = os.path.join(self._preview_temp_dir, filename)
        if os.path.exists(temp_wav):
            try: os.remove(temp_wav)
            except OSError: pass
        
        def on_done(success):
            if success:
                os.startfile(temp_wav)
            else:
                messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_error', 'Preview failed: {error}').format(error='Conversion failed'), parent=self.view)
        
        self._run_preview_task(
            lambda: self.logic.preview_single_audio(file_path, stream_num, temp_wav, self.vgmstream_path),
            on_done
        )

    def _preview_video(self, file_path) -> None:
        d = self.lang_data
        if not self.usmtoolkit_path:
            messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_no_tool_video', 'UsmToolkit not found.'), parent=self.view)
            return
        
        import time
        temp_dir = os.path.join(self._preview_temp_dir, f"video_{os.path.basename(file_path)}_{int(time.time() * 1000)}")
        os.makedirs(temp_dir, exist_ok=True)
        
        def on_convert_done(result_path):
            if result_path:
                os.startfile(str(result_path))
            else:
                messagebox.showwarning(d.get('preview_menu', 'Preview'), d.get('preview_error', 'Preview failed: {error}').format(error='Conversion failed'), parent=self.view)
        
        self._run_preview_task(
            lambda: self.logic.preview_single_video(file_path, temp_dir, self.usmtoolkit_path),
            on_convert_done
        )

    def cleanup(self) -> None:
        """앱 종료 시 메인 프로그램에서 호출되는 정리 메서드입니다.

        프리뷰 임시 파일의 정리는 전역 임시 폴더(app_temp_dir)를 사용하므로,
        AppContainer.cleanup_shared()에서 통합 관리합니다.
        """
