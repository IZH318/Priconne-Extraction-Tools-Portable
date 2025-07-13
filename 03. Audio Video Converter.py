import os
import sys
import subprocess
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, Listbox, Menu

# --- 다국어 텍스트 데이터 (변경 없음) ---
LANGUAGES = {
    'ko': {
        'window_title': "오디오/비디오 변환기",
        'video_tab': "비디오 변환기 (.usm → .mp4)",
        'audio_tab': "오디오 변환기 (.acb, .awb → .wav)",
        'input_section': "1. 원본 파일/폴더 선택",
        'add_files': "파일 추가",
        'add_folder': "폴더 추가",
        'file_list_section': "파일 목록",
        'output_section': "2. 저장 경로 선택",
        'browse': "경로 지정",
        'action_section': "3. 변환 실행",
        'start_conversion': "변환 시작",
        'cancel_conversion': "변환 중단",
        'overwrite_option': "기존 파일 덮어쓰기",
        'log_section': "처리 내역",
        # 메뉴 및 메시지
        'remove_selected': "선택 항목 제거",
        'remove_all': "전체 항목 제거",
        'alert_files_exist': "[알림] 선택한 파일들은 이미 목록에 존재합니다.",
        'log_files_added': "{count}개의 새 파일이 추가되었습니다.",
        'log_total_files': "총 파일 수: {total}개",
        'log_files_removed': "{count}개의 파일이 목록에서 삭제되었습니다.",
        'log_all_files_removed': "파일 목록 전체가 삭제되었습니다. ({count}개)",
        'log_conversion_cancelled': "사용자에 의해 변환 작업이 중단되었습니다.",
        'error_no_files': "[오류] 변환할 파일을 먼저 추가하세요.",
        'error_no_output_video': "[오류] 비디오를 저장할 경로를 지정하세요.",
        'error_no_output_audio': "[오류] 오디오를 저장할 경로를 지정하세요.",
        # 상태 라벨 텍스트
        'status_idle': "상태: 대기 중",
        'status_starting': "처리 시작... (총 {total}개)",
        'status_processing': "처리중: {current} / {total}",
        'status_complete': "완료: {current} / {total}",
        'status_cancelled': "중단됨: {current} / {total}",
        # 초기 상태 로그
        'env_check_header': "--- 프로그램 환경 점검 ---",
        'env_success': "  [성공] {tool_name} 발견",
        'env_path': "    > 경로: {path}",
        'env_error': "  [오류] {tool_name}을(를) 찾을 수 없음",
        'env_error_desc_video': "    > 비디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        'env_error_desc_audio': "    > 오디오 변환 탭이 정상 작동하지 않을 수 있습니다.",
        'env_check_footer': "--------------------------",
    }
}

# --- 핵심 변환 로직 (변경 없음) ---
class ConversionLogic:
    def __init__(self, log_queue, base_path):
        self.log_queue = log_queue
        self.base_path = base_path

    def _log(self, message, target_tab):
        self.log_queue.put(('log', target_tab, message))

    def _get_relative_path(self, full_path):
        try:
            return os.path.relpath(full_path, self.base_path)
        except (ValueError, TypeError):
            return str(full_path)

    def run_video_conversion(self, input_paths, output_dir, usmtoolkit_path, cancel_event):
        target_tab = 'video'
        self._log("\n--- 비디오 변환 작업을 시작합니다. ---", target_tab)
        self._log("[알림] 기존 파일은 항상 건너뜁니다.", target_tab)
        
        if not usmtoolkit_path:
            self._log("\n[오류] UsmToolkit.exe를 찾을 수 없습니다. 변환을 중단합니다.\n", target_tab)
            self.log_queue.put(('__VIDEO_DONE__', True))
            return
            
        usmtoolkit_dir = usmtoolkit_path.parent
        total_files, processed_count, skipped_count = len(input_paths), 0, 0
        self.log_queue.put(('progress_start', target_tab, total_files))

        for idx, usm_file_str in enumerate(input_paths, start=1):
            if cancel_event.is_set():
                self._log(f"\n{LANGUAGES['ko']['log_conversion_cancelled']}", target_tab)
                break
            
            self.log_queue.put(('progress_update', target_tab, idx))
            usm_file = Path(usm_file_str)
            self._log(f"\n--- [ {idx}/{total_files} ] --------------------", target_tab)
            self._log(f"  [소스]\n    {self._get_relative_path(usm_file)}", target_tab)
            
            extract_path = Path(output_dir) / (usm_file.stem + ".mp4")
            if extract_path.exists():
                self._log("\n  [결과]\n    이미 변환된 파일입니다. (건너뜀)", target_tab)
                skipped_count += 1
                self._log("---------------------------------", target_tab)
                continue
                
            command = [str(usmtoolkit_path), 'convert', '-c', str(usm_file.resolve()), '-o', str(Path(output_dir).resolve())]
            try:
                result = subprocess.run(command, cwd=usmtoolkit_dir, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                if extract_path.exists():
                    self._log(f"\n  [결과]\n    변환 성공: {self._get_relative_path(extract_path)}", target_tab)
                    processed_count += 1
                else:
                    self._log(f"\n  [결과]\n    [오류] 변환은 성공했으나 결과 파일이 없습니다.", target_tab)
                tool_output = result.stdout.strip()
                if tool_output: self._log("\n  [상세 로그]", target_tab); [self._log(f"    > {line}", target_tab) for line in tool_output.splitlines()]
            except subprocess.CalledProcessError as e:
                self._log(f"\n  [결과]\n    [오류] 변환 실패 - {usm_file.name}", target_tab)
                if e.stderr or e.stdout: self._log("\n  [상세 오류]", target_tab); [self._log(f"    > {line}", target_tab) for line in (e.stderr.strip() or e.stdout.strip()).splitlines()]
            except Exception as e:
                self._log(f"\n  [결과]\n    [오류] 치명적 예외 발생 - {e}\n", target_tab)
            self._log("---------------------------------", target_tab)
            
        self._log("\n--- 비디오 변환 작업이 완료되었습니다. ---", target_tab)
        self._log(f"총 {total_files}개 파일 중 {processed_count}개 변환, {skipped_count}개 건너뜀.\n", target_tab)
        self.log_queue.put(('__VIDEO_DONE__', cancel_event.is_set()))

    def run_audio_conversion(self, input_paths, output_dir, vgmstream_path, overwrite, cancel_event):
        target_tab = 'audio'
        self._log("\n--- 오디오 변환 작업을 시작합니다. ---", target_tab)
        self._log("[옵션] 기존 파일을 덮어씁니다." if overwrite else "[옵션] 기존 파일은 건너뜁니다.", target_tab)

        if not vgmstream_path:
            self._log("\n[오류] vgmstream 실행 파일(test.exe)을 찾을 수 없습니다. 변환을 중단합니다.\n", target_tab)
            self.log_queue.put(('__AUDIO_DONE__', True))
            return
            
        total_files, total_converted_tracks = len(input_paths), 0
        self.log_queue.put(('progress_start', target_tab, total_files))

        for idx, item_path_str in enumerate(input_paths, start=1):
            if cancel_event.is_set():
                self._log(f"\n{LANGUAGES['ko']['log_conversion_cancelled']}", target_tab)
                break

            self.log_queue.put(('progress_update', target_tab, idx))
            item_path = Path(item_path_str)
            self._log(f"\n--- [ {idx}/{total_files} ] --------------------", target_tab)
            self._log(f"  [소스]\n    {self._get_relative_path(item_path)}", target_tab)
            self._log("\n  [결과]", target_tab)
            
            item_converted_folder = Path(output_dir) / self._sanitize_filename(item_path.stem)
            item_converted_folder.mkdir(parents=True, exist_ok=True)
            try:
                tracks = self._get_tracks(item_path, vgmstream_path)
                if not tracks:
                    self._log("    알림: 트랙 정보가 없어 건너뜁니다.", target_tab)
                    self._log("---------------------------------", target_tab)
                    continue
                for track in tracks:
                    if cancel_event.is_set(): break
                    output_file = item_converted_folder / f"{self._sanitize_filename(track['Name'])}.wav"
                    if not overwrite and output_file.exists():
                        self._log(f"    알림: 이미 변환된 트랙 (건너뜀) - {track['Name']}.wav", target_tab)
                        continue
                    if self._convert_track(item_path, output_file, track['TrackNum'], vgmstream_path):
                        self._log(f"    성공: {self._get_relative_path(output_file)}", target_tab)
                        total_converted_tracks += 1
                    else:
                        self._log(f"    [오류] 트랙 변환 실패 - {track['Name']}", target_tab)
            except Exception as e:
                self._log(f"\n    [오류] 처리 중 예외 발생 - {e}\n", target_tab)
            if cancel_event.is_set(): break
            self._log("---------------------------------", target_tab)
            
        self._log("\n--- 오디오 변환 작업이 완료되었습니다. ---", target_tab)
        self._log(f"총 {total_converted_tracks}개의 트랙이 WAV 파일로 변환되었습니다.\n", target_tab)
        self.log_queue.put(('__AUDIO_DONE__', cancel_event.is_set()))

    def _sanitize_filename(self, filename): return filename.replace(';', ',')
    def _run_vgmstream(self, command, vgmstream_path): return subprocess.run([str(vgmstream_path)] + command, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    def _get_tracks(self, file_path, vgmstream_path):
        result = self._run_vgmstream(["-m", str(file_path)], vgmstream_path)
        if "failed opening" in result.stdout: return None
        lines, find_track, track_info = result.stdout.splitlines(), "stream count: ", []
        tracks = [line for line in lines if line.startswith(find_track)]
        if tracks and tracks[0][len(find_track):].isdigit():
            for i in range(1, int(tracks[0][len(find_track):]) + 1): track_info.append({'Name': self._get_track_name(file_path, vgmstream_path, i), 'TrackNum': i})
            return track_info
        track_info.append({'Name': self._get_track_name(file_path, vgmstream_path), 'TrackNum': 1})
        return track_info
    def _get_track_name(self, file_path, vgmstream_path, track_num=None):
        command = ["-m"]
        if track_num is not None: command.extend(["-s", str(track_num)])
        command.append(str(file_path))
        result = self._run_vgmstream(command, vgmstream_path)
        if "failed opening" in result.stdout: return f"track_{track_num or 1}"
        for line in result.stdout.splitlines():
            if line.startswith("stream name:"): return line[len("stream name:"):].strip()
        return f"track_{track_num}" if track_num else "track_1"
    def _convert_track(self, input_file, output_file, track_num, vgmstream_path): return self._run_vgmstream(["-o", str(output_file), "-s", str(track_num), str(input_file)], vgmstream_path).returncode == 0


# --- GUI 애플리케이션 ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.lang_data = LANGUAGES['ko']
        self.usmtoolkit_path, self.vgmstream_path = None, None
        
        self.video_full_paths, self.audio_full_paths = [], []
        self.video_filenames_var, self.audio_filenames_var = tk.StringVar(), tk.StringVar()
        self.audio_overwrite_var = tk.BooleanVar(value=False)

        self.video_cancel_event, self.audio_cancel_event = threading.Event(), threading.Event()
        self.video_total_files, self.audio_total_files = 0, 0
        
        self.base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        self.log_queue = queue.Queue()
        self.logic = ConversionLogic(self.log_queue, self.base_path)

        self._configure_window()
        self._find_tools()
        self._setup_ui()
        self._log_initial_status()
        self._process_log_queue()

    def _configure_window(self):
        self.title(self.lang_data['window_title'])
        width, height = 1100, 750
        self.geometry(f'{width}x{height}+{self.winfo_screenwidth()//2 - width//2}+{self.winfo_screenheight()//2 - height//2}')
        self.minsize(900, 600)

    def _find_tools(self):
        for root, _, files in os.walk(self.base_path):
            if not self.usmtoolkit_path and "usmtoolkit.exe" in (f.lower() for f in files): self.usmtoolkit_path = Path(root) / "UsmToolkit.exe"
            if not self.vgmstream_path and "test.exe" in (f.lower() for f in files) and "vgmstream" in str(Path(root)).lower(): self.vgmstream_path = Path(root) / "test.exe"

    def _setup_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.video_tab, self.audio_tab = ttk.Frame(self.notebook), ttk.Frame(self.notebook)
        
        self.notebook.add(self.video_tab, text=self.lang_data['video_tab'])
        self.notebook.add(self.audio_tab, text=self.lang_data['audio_tab'])
        
        self._create_tab_content(self.video_tab, 'video')
        self._create_tab_content(self.audio_tab, 'audio')
    
    def _log_initial_status(self):
        d = self.lang_data
        log_lines = [d['env_check_header']]
        
        if self.usmtoolkit_path:
            log_lines.extend([d['env_success'].format(tool_name="UsmToolkit.exe"), d['env_path'].format(path=self.logic._get_relative_path(self.usmtoolkit_path))])
        else:
            log_lines.extend([d['env_error'].format(tool_name="UsmToolkit.exe"), d['env_error_desc_video']])
        
        if self.vgmstream_path:
            log_lines.extend([d['env_success'].format(tool_name="vgmstream(test.exe)"), d['env_path'].format(path=self.logic._get_relative_path(self.vgmstream_path))])
        else:
            log_lines.extend([d['env_error'].format(tool_name="vgmstream(test.exe)"), d['env_error_desc_audio']])
            
        log_lines.append(d['env_check_footer'] + "\n")
        log_text = '\n'.join(log_lines)
        
        self.log_to_gui(log_text, self.video_log_text)
        self.log_to_gui(log_text, self.audio_log_text, clear_first=True)

    def _create_tab_content(self, parent_tab, tab_type):
        d = self.lang_data
        is_audio_tab = (tab_type == 'audio')
        
        tab_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        tab_pane.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(tab_pane, width=450)
        tab_pane.add(controls_frame, weight=2)
        
        log_frame_container = ttk.LabelFrame(tab_pane, text=d['log_section'])
        tab_pane.add(log_frame_container, weight=3)
        
        log_text_widget = scrolledtext.ScrolledText(log_frame_container, wrap=tk.WORD, state='disabled', bg='black', fg='white', font=("Consolas", 9))
        log_text_widget.pack(side='top', fill="both", expand=True, padx=5, pady=(5,0))
        
        status_frame = ttk.Frame(log_frame_container)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=(2,5))

        status_label = ttk.Label(status_frame, text=d['status_idle'])
        status_label.pack(side='left')
        
        progress_bar = ttk.Progressbar(status_frame, orient='horizontal', mode='determinate')
        progress_bar.pack(side='left', fill='x', expand=True, padx=(5,0))

        input_frame = ttk.LabelFrame(controls_frame, text=d['input_section'])
        input_frame.pack(fill='x', pady=5, padx=5)
        
        file_types = [("CRIWARE Audio", "*.acb *.awb")] if is_audio_tab else [("USM Video files", "*.usm")]
        full_paths = self.audio_full_paths if is_audio_tab else self.video_full_paths
        filenames_var = self.audio_filenames_var if is_audio_tab else self.video_filenames_var
        
        add_files_btn = ttk.Button(input_frame, text=d['add_files'], command=lambda: self._add_files(file_types, full_paths, filenames_var, log_text_widget))
        add_files_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')
        add_folder_btn = ttk.Button(input_frame, text=d['add_folder'], command=lambda: self._add_folder(file_types, full_paths, filenames_var, log_text_widget))
        add_folder_btn.pack(side='left', padx=5, pady=5, expand=True, fill='x')

        list_container = ttk.LabelFrame(controls_frame, text=d['file_list_section'])
        list_container.pack(fill='both', expand=True, pady=5, padx=5)
        
        list_frame = ttk.Frame(list_container)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        listbox = Listbox(list_frame, listvariable=filenames_var, selectmode=tk.EXTENDED, height=10)
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
        scrollbar.pack(side='right', fill='y')
        listbox.config(yscrollcommand=scrollbar.set)
        self._create_right_click_menu(listbox, full_paths, filenames_var, log_text_widget)
        
        output_frame = ttk.LabelFrame(controls_frame, text=d['output_section'])
        output_frame.pack(fill='x', pady=5, padx=5)
        output_entry = ttk.Entry(output_frame, state='readonly')
        output_entry.pack(side='left', fill='x', expand=True, padx=5, pady=5)
        ttk.Button(output_frame, text=d['browse'], command=lambda: self._select_output_folder(output_entry)).pack(side='left', padx=5, pady=5)

        action_frame = ttk.LabelFrame(controls_frame, text=d['action_section'])
        action_frame.pack(fill='x', pady=5, padx=5)

        action_button = ttk.Button(action_frame, text=d['start_conversion'])
        
        widgets_dict = {'action_btn': action_button, 'add_files_btn': add_files_btn, 'add_folder_btn': add_folder_btn,
                        'output_entry': output_entry, 'progress': progress_bar, 'status_label': status_label}
                        
        if is_audio_tab:
            action_button.pack(side='left', pady=5, padx=5)
            overwrite_check = ttk.Checkbutton(action_frame, text=d['overwrite_option'], variable=self.audio_overwrite_var)
            overwrite_check.pack(side='left', pady=5, padx=10)
            action_button.config(command=lambda: self.start_audio_conversion(output_entry.get(), self.audio_overwrite_var.get()))
            widgets_dict['overwrite_check'] = overwrite_check
            self.audio_widgets = widgets_dict
            self.audio_log_text = log_text_widget
        else:
            action_button.pack(fill='x', pady=5, padx=5)
            action_button.config(command=lambda: self.start_video_conversion(output_entry.get()))
            self.video_widgets = widgets_dict
            self.video_log_text = log_text_widget
        
    def _create_right_click_menu(self, listbox, full_paths, filenames_var, log_widget):
        d = self.lang_data
        menu = Menu(listbox, tearoff=0)
        
        # 메뉴에 항목 추가
        menu.add_command(label=d['remove_selected'], command=lambda: self._remove_selected_from_list(listbox, full_paths, filenames_var, log_widget))
        menu.add_separator()
        menu.add_command(label=d['remove_all'], command=lambda: self._clear_list(full_paths, filenames_var, log_widget))
        
        # [MODIFIED] 메뉴를 보여주는 함수 수정
        def show_menu(event):
            # '선택 항목 제거'는 항목이 선택되었을 때만 활성화
            menu.entryconfig(d['remove_selected'], state="normal" if listbox.curselection() else "disabled")
            
            # '전체 항목 제거'는 목록에 항목이 하나라도 있을 때만 활성화
            menu.entryconfig(d['remove_all'], state="normal" if listbox.size() > 0 else "disabled")
            
            menu.post(event.x_root, event.y_root)

        listbox.bind("<Button-3>", show_menu)
        listbox.bind("<Delete>", lambda e: self._remove_selected_from_list(listbox, full_paths, filenames_var, log_widget))

    def _set_ui_state(self, widgets, state):
        for widget_name, widget in widgets.items():
            if widget_name in ['action_btn', 'progress', 'status_label']: continue
            if isinstance(widget, ttk.Entry) and state == 'disabled': widget.config(state='readonly')
            else: widget.config(state=state)

    def _reset_video_ui_state(self):
        d = self.lang_data
        self._set_ui_state(self.video_widgets, 'normal')
        self.video_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_video_conversion(self.video_widgets['output_entry'].get()))
        self.video_widgets['status_label'].config(text=d['status_idle'])
        self.video_widgets['progress']['value'] = 0

    def _reset_audio_ui_state(self):
        d = self.lang_data
        self._set_ui_state(self.audio_widgets, 'normal')
        self.audio_widgets['action_btn'].config(text=d['start_conversion'], state='normal', command=lambda: self.start_audio_conversion(self.audio_widgets['output_entry'].get(), self.audio_overwrite_var.get()))
        self.audio_widgets['status_label'].config(text=d['status_idle'])
        self.audio_widgets['progress']['value'] = 0

    def _select_files(self, ft): return list(filedialog.askopenfilenames(title="파일을 선택하세요", filetypes=ft) or [])
    def _select_folder_and_search(self, ft):
        folder = filedialog.askdirectory(title="폴더를 선택하세요")
        if not folder: return []
        exts = [ext.strip('*.') for _, p in ft for ext in p.split()]
        return [str(Path(r) / f) for r, _, fs in os.walk(folder) for f in fs if any(f.lower().endswith(f".{ext}") for ext in exts)]
    
    def _select_output_folder(self, entry_widget):
        folder = filedialog.askdirectory(title="저장할 폴더를 선택하세요")
        if folder:
            entry_widget.config(state='normal'); entry_widget.delete(0, tk.END); entry_widget.insert(0, folder); entry_widget.config(state='readonly')

    def _update_listbox(self, fp, fv): fv.set([os.path.basename(p) for p in fp])
    def _add_paths_to_list(self, new_paths, full_paths, filenames_var, log_widget):
        if not new_paths: return
        d = self.lang_data
        unique_new_paths = [p for p in new_paths if p not in set(full_paths)]
        if not unique_new_paths: self.log_to_gui(f"\n{d['alert_files_exist']}\n", log_widget); return
        full_paths.extend(unique_new_paths)
        self._update_listbox(full_paths, filenames_var)
        self.log_to_gui(f"\n{d['log_files_added'].format(count=len(unique_new_paths))}\n{d['log_total_files'].format(total=len(full_paths))}\n", log_widget)
        
    def _add_files(self, ft, fp, fv, lw): self._add_paths_to_list(self._select_files(ft), fp, fv, lw)
    def _add_folder(self, ft, fp, fv, lw): self._add_paths_to_list(self._select_folder_and_search(ft), fp, fv, lw)
        
    def _remove_selected_from_list(self, lb, fp, fv, lw):
        sel_idx = lb.curselection()
        if not sel_idx: return
        for i in sorted(sel_idx, reverse=True): del fp[i]
        self._update_listbox(fp, fv)
        self.log_to_gui(f"\n{self.lang_data['log_files_removed'].format(count=len(sel_idx))}\n", lw)
        
    def _clear_list(self, fp, fv, lw):
        if not fp: return
        count = len(fp)
        fp.clear()
        self._update_listbox(fp, fv)
        self.log_to_gui(f"\n{self.lang_data['log_all_files_removed'].format(count=count)}\n", lw)

    def start_video_conversion(self, output_dir):
        d = self.lang_data
        if not self.video_full_paths: self.log_to_gui(f"\n{d['error_no_files']}\n", self.video_log_text); return
        if not output_dir: self.log_to_gui(f"\n{d['error_no_output_video']}\n", self.video_log_text); return
        
        self.video_cancel_event.clear()
        self._set_ui_state(self.video_widgets, 'disabled')
        self.video_widgets['action_btn'].config(text=d['cancel_conversion'], command=self.cancel_video_conversion)
        threading.Thread(target=self.logic.run_video_conversion, daemon=True, args=(self.video_full_paths[:], output_dir, self.usmtoolkit_path, self.video_cancel_event)).start()

    def cancel_video_conversion(self):
        self.video_widgets['action_btn'].config(state='disabled'); self.video_cancel_event.set()

    def start_audio_conversion(self, output_dir, overwrite):
        d = self.lang_data
        if not self.audio_full_paths: self.log_to_gui(f"\n{d['error_no_files']}\n", self.audio_log_text); return
        if not output_dir: self.log_to_gui(f"\n{d['error_no_output_audio']}\n", self.audio_log_text); return

        self.audio_cancel_event.clear()
        self._set_ui_state(self.audio_widgets, 'disabled')
        self.audio_widgets['action_btn'].config(text=d['cancel_conversion'], command=self.cancel_audio_conversion)
        threading.Thread(target=self.logic.run_audio_conversion, daemon=True, args=(self.audio_full_paths[:], output_dir, self.vgmstream_path, overwrite, self.audio_cancel_event)).start()

    def cancel_audio_conversion(self):
        self.audio_widgets['action_btn'].config(state='disabled'); self.audio_cancel_event.set()

    def log_to_gui(self, message, log_widget, clear_first=False):
        log_widget.config(state='normal')
        if clear_first: log_widget.delete('1.0', tk.END)
        log_widget.insert(tk.END, message)
        log_widget.config(state='disabled')
        log_widget.see(tk.END)

    def _process_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                msg_type, *args = msg
                
                if msg_type.startswith('__'): 
                    was_cancelled = args[0]
                    d = self.lang_data
                    if msg_type == '__VIDEO_DONE__':
                        widgets, total = self.video_widgets, self.video_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_video_ui_state()
                    else: 
                        widgets, total = self.audio_widgets, self.audio_total_files
                        current = widgets['progress']['value']
                        status_key = 'status_cancelled' if was_cancelled else 'status_complete'
                        widgets['status_label'].config(text=d[status_key].format(current=current, total=total))
                        self._reset_audio_ui_state()
                
                elif msg_type == 'log':
                    target_tab, text = args
                    log_widget = self.video_log_text if target_tab == 'video' else self.audio_log_text
                    self.log_to_gui(text + '\n', log_widget)
                
                elif msg_type == 'progress_start':
                    target_tab, total = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    if target_tab == 'video': self.video_total_files = total
                    else: self.audio_total_files = total
                    
                    widgets['progress'].config(maximum=total, value=0)
                    widgets['status_label'].config(text=self.lang_data['status_starting'].format(total=total))
                
                elif msg_type == 'progress_update':
                    target_tab, value = args
                    widgets = self.video_widgets if target_tab == 'video' else self.audio_widgets
                    total = self.video_total_files if target_tab == 'video' else self.audio_total_files
                    
                    widgets['progress']['value'] = value
                    widgets['status_label'].config(text=self.lang_data['status_processing'].format(current=value, total=total))
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()