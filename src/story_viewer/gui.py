# src/story_viewer/gui.py
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
from datetime import datetime

from .languages import LANGUAGES, ABOUT_INFO
from .windows_search import SearchWindow
from .windows_export import ExportWindow
from .logic import StoryDataLoader, StoryFormatter

class StoryViewerApp(ttk.Frame):
    def __init__(self, master, app_lang_var=None):
        super().__init__(master)
        self.pack(fill=tk.BOTH, expand=True)

        self.master = master
        self.all_files = {}
        self.story_data_cache = {}
        self.search_data = {}
        self.file_titles = {}
        self.display_name_to_filename = {}
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.is_loading = False
        self.task_queue = queue.Queue()

        if app_lang_var:
            self.lang_var = app_lang_var
        else:
            self.lang_var = tk.StringVar(value='ko')
            
        self.lang_var.trace_add('write', self._on_language_change_event)
        
        self.display_mode_var = tk.StringVar(value="original")
        self.view_mode_var = tk.StringVar(value="simple")

        self.db_status = {}
        self.db_check_done = False
        self.db_warning_shown = False

        self.server_db_info = {
            'JP': {
                'db_path': 'master_jp.db',
                'event_list_table': 'v1_8931e2893a2d2290dbf498046bc66faafeebc40b6764dd69334ad51f5aca2e9f',
                'event_name_col_list': 'e3f0f79d746654f52125f3c28eb487d9e102f02077fe104d1423f08e80e056e3',
                'event_details_table': 'v1_04d08b8c6bf704241326eca45b6d63cc1a6dd38d03ff256df15b8ec8d4cd2649',
                'event_info_col_details': '20d0bf56a9ca7d14b3172ac4dd383fee10c010d4ecd30c9854302d10390d774e',
                'event_id_col_details': '69d3bbead1844607ef41ecb520a4d5385cae02eddca377aa13721ec7fd01e0ec'
            },
            'KR': {
                'db_path': 'master_kr.db',
                'event_list_table': 'v1_4e380b72af2e31867844884ba838095ad9ea8f02bf83037a3c8ed47b8943f164',
                'event_name_col_list': 'abb720eaefdc23b376dc5b817b683e633eb66fe9a3941025ae27413c56d56fad',
                'event_details_table': 'v1_ebabad5e41c1f71b3e5d705a8fe81411012e124827b4cbde3dfb2469674f598f',
                'event_info_col_details': '45d39837db60a2b9aca5a03c3c17a9999201e08e97c3cff92bb95786dd344355',
                'event_id_col_details': '9a0ef39c5ee7f28590676ed2b6b857c10aad6d01983252fa6b978b0cb3991880'
            }
        }

        self.setup_ui()
        self.setup_text_tags()
        self.master.after(100, self._process_queue)
        self._update_ui_text()
        self._update_status_bar('status_bar_initial')

    def _on_language_change_event(self, *args):
        try:
            self._update_ui_text()
            self._on_display_mode_change(force_update=True)
            self._on_view_mode_change(force_update=True)
        except tk.TclError:
            pass

    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # 메인 레이아웃 (좌/우 분할)
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        
        left_weight, right_weight = 35, 65

        # 좌측 패널 구성
        left_pane = ttk.Frame(self.paned_window)
        self.paned_window.add(left_pane, weight=left_weight)

        # 오픈 프레임 (파일/폴더 열기, 내보내기 버튼)
        self.open_frame = ttk.LabelFrame(left_pane, text="")
        self.open_frame.pack(fill=tk.X, pady=(0, 5))
        self.btn_open_file = ttk.Button(self.open_frame, text="", command=self.open_files)
        self.btn_open_file.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 2), pady=5)
        self.btn_open_folder = ttk.Button(self.open_frame, text="", command=self.open_folder)
        self.btn_open_folder.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 2), pady=5)
        self.btn_export = ttk.Button(self.open_frame, text="", command=self.open_export_window, state="disabled")
        self.btn_export.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 5), pady=5)

        # 파일 목록 옵션 프레임
        self.file_options_group = ttk.LabelFrame(left_pane, text="", padding=5)
        self.file_options_group.pack(fill=tk.X, pady=(0, 5))
        self.display_orig_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="original", command=self._on_display_mode_change)
        self.display_orig_radio.pack(side=tk.LEFT, padx=(5, 10))
        self.display_title_radio = ttk.Radiobutton(self.file_options_group, text="", variable=self.display_mode_var, value="title", command=self._on_display_mode_change)
        self.display_title_radio.pack(side=tk.LEFT, padx=5)

        # 리스트 프레임 (검색창 + 리스트박스)
        self.left_group = ttk.LabelFrame(left_pane, text="")
        self.left_group.pack(fill=tk.BOTH, expand=True)
        self.search_button = ttk.Button(self.left_group, text="", command=self.open_search_window, state="disabled")
        self.search_button.pack(fill=tk.X, padx=5, pady=(5, 5))
        
        list_scrollbar = ttk.Scrollbar(self.left_group, orient=tk.VERTICAL)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
        self.file_listbox = tk.Listbox(self.left_group, selectmode=tk.SINGLE, yscrollcommand=list_scrollbar.set)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=(0, 5))
        list_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        
        # 우측 패널 구성
        right_pane = ttk.Frame(self.paned_window)
        self.paned_window.add(right_pane, weight=right_weight)
        
        # 상세 옵션 프레임
        self.detail_options_group = ttk.LabelFrame(right_pane, text="", padding=5)
        self.detail_options_group.pack(fill=tk.X, pady=(0, 5))
        self.view_simple_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="simple", command=self._on_view_mode_change)
        self.view_simple_radio.pack(side=tk.LEFT, padx=(5, 10))
        self.view_detailed_radio = ttk.Radiobutton(self.detail_options_group, text="", variable=self.view_mode_var, value="detailed", command=self._on_view_mode_change)
        self.view_detailed_radio.pack(side=tk.LEFT, padx=5)
        
        # 텍스트 출력 프레임
        self.right_group = ttk.LabelFrame(right_pane, text="")
        self.right_group.pack(fill=tk.BOTH, expand=True)
        text_scrollbar = ttk.Scrollbar(self.right_group, orient=tk.VERTICAL)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        self.story_text = tk.Text(self.right_group, wrap=tk.WORD, state=tk.DISABLED, spacing1=2, padx=10, pady=10, yscrollcommand=text_scrollbar.set)
        self.story_text.pack(fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        text_scrollbar.config(command=self.story_text.yview)

        # 상태 표시줄
        self.status_bar = ttk.Label(self, text="", anchor=tk.W, padding=5)
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        
        # PanedWindow 초기 분할 비율 설정
        def reapply_weights(event=None):
            try:
                total_width = self.paned_window.winfo_width()
                sash_position = int(total_width * left_weight / (left_weight + right_weight))
                self.paned_window.sashpos(0, sash_position)
                self.paned_window.unbind("<Configure>")
            except tk.TclError: pass
        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self):
        default_font_family = font.nametofont("TkDefaultFont").cget("family")
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A')
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333')
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000')
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')
    
    def _update_ui_text(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        self.btn_open_file.config(text=lang_dict['file_open'])
        self.btn_open_folder.config(text=lang_dict['folder_open'])
        self.btn_export.config(text=lang_dict['export'])

        self.open_frame.config(text=lang_dict.get('open_frame_title', '파일 선택'))
        self.file_options_group.config(text=lang_dict['file_options_group'])
        self.detail_options_group.config(text=lang_dict['detail_options_group'])
        self.display_orig_radio.config(text=lang_dict['display_original_filename'])
        self.display_title_radio.config(text=lang_dict['display_title'])
        self.view_simple_radio.config(text=lang_dict['view_simple'])
        self.view_detailed_radio.config(text=lang_dict['view_detailed'])
        self.left_group.config(text=lang_dict['list_group_title'])
        self.right_group.config(text=lang_dict['detail_group_title'])
        self.search_button.config(text=lang_dict['search_button_text'])
        
        self.update_file_list(self.current_filenames_in_list)

    def _update_status_bar(self, key, **kwargs):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
        message = lang_dict.get(key, "...")
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError:
                pass
        self.status_bar.config(text=message)
        
    def _show_about_dialog(self):
        lang_dict = LANGUAGES[self.lang_var.get()]
        title = lang_dict['about_header']
        
        info_lines = []
        for key, value in ABOUT_INFO.items():
            label_key = f'about_label_{key}'
            label_text = lang_dict.get(label_key, key.capitalize())
            info_lines.append(f"{label_text}: {value}")
            
        message = "\n".join(info_lines)
        messagebox.showinfo(title, message, parent=self.master)

    def _process_queue(self):
        try:
            while True:
                task = self.task_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self._process_queue)

    def _clear_workspace(self):
        self.update_story_text([])
        self.all_files.clear()
        self.story_data_cache.clear()
        self.search_data.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.loaded_filenames = []
        self.current_file_path = None
        self.search_button.config(state="disabled")
        self.btn_export.config(state="disabled")
        self.db_status.clear()
        self.db_check_done = False
        self.db_warning_shown = False

    def _start_loading_task(self, paths=None, folder_path=None):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self)
            return
        self._clear_workspace()
        self.is_loading = True
        self._update_status_bar('status_bar_loading_start')
        self.btn_open_file.config(state="disabled")
        self.btn_open_folder.config(state="disabled")
        
        thread = threading.Thread(target=self._load_and_analyze_thread, args=(paths, folder_path))
        thread.daemon = True
        thread.start()

    def open_files(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        file_paths = filedialog.askopenfilenames(
            title=lang_dict.get('dialog_title_open_files', "Select storydata file(s)"),
            filetypes=[(lang_dict.get('filetype_json', "JSON Files"), "*.json"), (lang_dict.get('filetype_all', "All Files"), "*.*")]
        )
        if file_paths:
            self._start_loading_task(paths=file_paths)

    def open_folder(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        folder_path = filedialog.askdirectory(title=lang_dict.get('dialog_title_open_folder', "Select the folder with storydata files"))
        if folder_path:
            self._start_loading_task(folder_path=folder_path)

    def _load_and_analyze_thread(self, paths, folder_path):
        import re
        temp_all_files, temp_story_cache, invalid_files = {}, {}, []
        
        file_candidates = {}
        pattern = re.compile(r'^storydata_\d{7}\.json$')

        if paths:
            for path in paths:
                filename = os.path.basename(path)
                if pattern.match(filename):
                    if filename not in file_candidates:
                        file_candidates[filename] = []
                    file_candidates[filename].append(path)

        if folder_path:
            for dirpath, _, filenames in os.walk(folder_path):
                for filename in filenames:
                    if pattern.match(filename):
                        full_path = os.path.join(dirpath, filename)
                        if filename not in file_candidates:
                            file_candidates[filename] = []
                        file_candidates[filename].append(full_path)
        
        file_list_to_process = []
        for filename, path_list in file_candidates.items():
            if len(path_list) > 1:
                try:
                    winner_path = max(path_list, key=os.path.getsize)
                    file_list_to_process.append(winner_path)
                except FileNotFoundError:
                    pass 
            elif path_list:
                file_list_to_process.append(path_list[0])
        
        file_list_to_process.sort()
        
        total_files = len(file_list_to_process)
        for i, path in enumerate(file_list_to_process):
            self.task_queue.put(lambda i=i, t=total_files: self._update_status_bar('status_bar_analyzing', i=i+1, t=t))
            is_valid, data, error_reason = StoryDataLoader.is_valid_storydata(path)
            
            if is_valid:
                filename = os.path.basename(path)
                temp_all_files[filename] = path
                temp_story_cache[filename] = data
            else:
                invalid_files.append((path, error_reason))
        
        if not temp_all_files:
            self.task_queue.put(lambda: self._finish_loading(None, invalid_files))
            return

        unique_char_names, unique_bgms, unique_bgs, temp_file_titles = set(), set(), set(), {}

        for filename, data in temp_story_cache.items():
            title = data.get('0', {}).get('title', '').strip()
            temp_file_titles[filename] = title if title else filename
            for scene in data.values():
                if 'print' in scene and 'name' in scene['print'] and (name := str(scene['print']['name']).strip()): unique_char_names.add(name)
                if 'bgm' in scene and (bgm_name := StoryDataLoader.extract_asset_name(scene['bgm'])): unique_bgms.add(bgm_name)
                if 'background' in scene and (bg_name := StoryDataLoader.extract_asset_name(scene['background'])): unique_bgs.add(bg_name)

        temp_search_data = {
            'filenames': sorted(list(temp_all_files.keys())), 
            'character_names': sorted(list(unique_char_names)), 
            'bgms': sorted(list(unique_bgms)), 
            'backgrounds': sorted(list(unique_bgs))
        }
        results = {"all_files": temp_all_files, "cache": temp_story_cache, "titles": temp_file_titles, "search_data": temp_search_data}
        self.task_queue.put(lambda: self._finish_loading(results, invalid_files))

    def _finish_loading(self, results, invalid_files):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        self.is_loading = False
        self.btn_open_file.config(state="normal")
        self.btn_open_folder.config(state="normal")
        if not results:
            self._update_status_bar('status_bar_loading_done', loaded=0, failed=len(invalid_files))
            messagebox.showwarning(lang_dict['msgbox_no_valid_files_title'], lang_dict['msgbox_no_valid_files_msg'], parent=self)
        else:
            self.all_files, self.story_data_cache, self.file_titles, self.search_data = results['all_files'], results['cache'], results['titles'], results['search_data']
            self.loaded_filenames = sorted(list(self.all_files.keys()))
            self._update_status_bar('status_bar_loading_done', loaded=len(self.all_files), failed=len(invalid_files))
            self.search_button.config(state="normal")
            self.btn_export.config(state="normal")
            self.update_file_list(list(self.all_files.keys()))
        
        if invalid_files:
            msg = lang_dict['msgbox_load_fail_msg'].format(count=len(invalid_files))
            if messagebox.askyesno(lang_dict['msgbox_load_fail_title'], msg):
                log_filename = "invalid_storydata_log.txt"
                try:
                    with open(log_filename, 'w', encoding='utf-8') as f:
                        f.write(lang_dict['log_header'].format(timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                        f.write(lang_dict['log_total_failed'].format(count=len(invalid_files)))
                        f.write("-" * 50 + "\n\n")
                        for path, reason in invalid_files:
                            f.write(f"{lang_dict['log_file_label']}: {path}\n")
                            f.write(f"{lang_dict['log_reason_label']}: {reason}\n")
                            f.write("-" * 30 + "\n")
                    messagebox.showinfo(lang_dict['msgbox_log_saved_title'], lang_dict['msgbox_log_saved_msg'].format(filename=log_filename))
                except Exception as e:
                    messagebox.showerror(lang_dict['msgbox_log_save_error_title'], lang_dict['msgbox_log_save_error_msg'].format(e=e))

    def _check_and_cache_db_status(self):
        if self.db_check_done: return
        
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        missing_db_paths = []
        
        for server, info in self.server_db_info.items():
            db_path = os.path.join(script_dir, info['db_path'])
            exists = os.path.exists(db_path)
            self.db_status[server] = exists
            if not exists:
                missing_db_paths.append(info['db_path'])

        if missing_db_paths and not self.db_warning_shown:
            paths_str = "\n".join(missing_db_paths)
            messagebox.showwarning(
                lang_dict['db_not_found_title'], 
                lang_dict['db_not_found_msg'].format(paths=paths_str),
                parent=self.master
            )
            self.db_warning_shown = True

        self.db_check_done = True

    def open_search_window(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_search_before_load_title'], lang_dict['msgbox_search_before_load_msg'], parent=self)
            return
        
        self._check_and_cache_db_status()
        
        SearchWindow(app=self, all_files_dict=self.all_files, story_data_cache=self.story_data_cache, search_callback=self.update_file_list, search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)

    def open_export_window(self):
        try:
            lang_dict = LANGUAGES[self.lang_var.get()]
        except KeyError:
            lang_dict = LANGUAGES['ko']
            
        if self.is_loading:
            messagebox.showwarning(lang_dict['msgbox_loading_title'], lang_dict['msgbox_loading_msg'], parent=self)
            return
        if not self.all_files:
            messagebox.showinfo(lang_dict['msgbox_no_export_files_title'], lang_dict['msgbox_no_export_files_msg'], parent=self)
            return
            
        self._check_and_cache_db_status()
        
        ExportWindow(app=self, all_files_dict=self.all_files, story_data_cache=self.story_data_cache, search_data=self.search_data, db_status=self.db_status, server_db_info=self.server_db_info)

    def update_file_list(self, filenames):
        self.update_story_text([])
        self.current_file_path = None
        self.current_filenames_in_list = sorted(filenames)
        self.display_name_to_filename.clear()
        self.file_listbox.delete(0, tk.END)
        total, chunk_size = len(self.current_filenames_in_list), 200
        
        def _populate_list(index=0):
            if index >= total:
                self._update_status_bar('status_bar_list_updated', count=total)
                if total > 0:
                    self.file_listbox.selection_set(0)
                    self.file_listbox.event_generate("<<ListboxSelect>>")
                else:
                    self._update_status_bar('status_bar_ready')
                return
            self._update_status_bar('status_bar_list_updating', i=index + 1, t=total)
            end_index = min(index + chunk_size, total)
            display_mode = self.display_mode_var.get()
            display_chunk = []
            for i in range(index, end_index):
                filename = self.current_filenames_in_list[i]
                display_name = filename
                if display_mode == 'title':
                    if title := self.file_titles.get(filename, filename):
                        display_name = f"{title}"
                display_chunk.append(display_name)
                self.display_name_to_filename[display_name] = filename
            self.file_listbox.insert(tk.END, *display_chunk)
            self.master.after(1, lambda: _populate_list(end_index))
        _populate_list()

    def on_file_select(self, event):
        if not self.file_listbox.curselection(): return
        try:
            display_name = self.file_listbox.get(self.file_listbox.curselection()[0])
        except tk.TclError: return
        if filename := self.display_name_to_filename.get(display_name):
            self.current_file_path = self.all_files.get(filename)
            if data := self.story_data_cache.get(filename):
                formatter = StoryFormatter()
                self.update_story_text(formatter.format_story_data(data, self.view_mode_var.get()))
                self._update_status_bar('status_bar_displaying', filename=filename)
            else:
                self._update_status_bar('status_bar_cache_error', filename=filename)

    def _on_display_mode_change(self, force_update=False):
        if not force_update and self.is_loading: return
        self.update_file_list(self.current_filenames_in_list)

    def _on_view_mode_change(self, force_update=False):
        if not force_update and self.is_loading: return
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            if data := self.story_data_cache.get(filename):
                formatter = StoryFormatter()
                self.update_story_text(formatter.format_story_data(data, self.view_mode_var.get()))

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)

    # Export functionality helper methods
    def _save_list_to_file(self, data_list, filename_suffix, output_folder, header_text):
        output_path = os.path.join(output_folder, f"{filename_suffix}.txt")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                if data_list:
                    for item in data_list:
                        f.write(f"{item}\n")
                else:
                    f.write(f"(No data found for {filename_suffix})\n")
            return True, None
        except Exception as e:
            return False, e

    def _export_master_thread(self, selected_options, output_folder):
        lang_dict = LANGUAGES[self.lang_var.get()]
        export_results = {}
        total_exported_count = 0
        total_failed_count = 0
        all_failed_details = []

        if selected_options['story_data']:
            story_data_scope = selected_options['story_data_scope']
            filenames_to_export = []
            if story_data_scope == 'current_list':
                filenames_to_export = self.current_filenames_in_list
            elif story_data_scope == 'all_loaded':
                filenames_to_export = self.loaded_filenames
            
            if not filenames_to_export:
                export_results['story_data'] = {'success': 0, 'failed': 0, 'details': ["No story data files selected for export."]}
            else:
                type_name = lang_dict.get('export_type_story_data', 'Story Data')
                success_count = 0
                fail_count = 0
                current_failed_details = []

                for i, filename in enumerate(filenames_to_export):
                    self.task_queue.put(lambda tn=type_name, s=success_count, f=fail_count, i=i, tf=len(filenames_to_export): self._update_status_bar('status_bar_exporting_type', type_name=tn, success=s, failed=f, i=i+1, t=tf))
                    data = self.story_data_cache.get(filename)
                    if not data:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Cache Miss)")
                        continue
                    output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".txt")
                    try:
                        formatter = StoryFormatter()
                        text_to_write = "".join([text for text, _ in formatter.format_story_data(data, self.view_mode_var.get())])
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(text_to_write)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        current_failed_details.append(f"{filename} (Error: {e})")
                
                export_results['story_data'] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        other_export_types = [
            {'type': 'filenames', 'name_key': 'export_type_filenames', 'data_func': lambda: sorted(list(self.loaded_filenames)), 'file_suffix': 'filenames', 'header_key': 'export_type_filenames'},
            {'type': 'character_names', 'name_key': 'export_type_character_names', 'data_func': lambda: sorted(self.search_data.get('character_names', [])), 'file_suffix': 'character_names', 'header_key': 'export_type_character_names'},
            {'type': 'bgm_names', 'name_key': 'export_type_bgm_names', 'data_func': lambda: sorted(self.search_data.get('bgms', [])), 'file_suffix': 'bgm_names', 'header_key': 'export_type_bgm_names'},
            {'type': 'background_names', 'name_key': 'export_type_background_names', 'data_func': lambda: sorted(self.search_data.get('backgrounds', [])), 'file_suffix': 'background_names', 'header_key': 'export_type_background_names'},
        ]
        
        for task in other_export_types:
            task_type = task['type']
            if not selected_options[task_type]:
                continue

            type_name = lang_dict.get(task['name_key'], task_type)
            success_count = 0
            fail_count = 0
            current_failed_details = []

            self.task_queue.put(lambda tn=type_name: self._update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0))
            try:
                data_list = task['data_func']()
                if not data_list:
                    export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                    continue

                success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                if success:
                    success_count = 1
                else:
                    fail_count = 1
                    current_failed_details.append(f"{type_name} (Error: {error})")
            except Exception as e:
                fail_count += 1
                current_failed_details.append(f"{type_name} (Unexpected Error: {e})")

            export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
            total_exported_count += success_count
            total_failed_count += fail_count
            all_failed_details.extend(current_failed_details)

        if selected_options['event_list_master']:
            def get_event_list(server_key):
                db_info = self.server_db_info.get(server_key)
                if not db_info or not self.db_status.get(server_key): return []
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(script_dir, db_info['db_path'])
                try:
                    import sqlite3
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\"")
                        return sorted([row[0].replace('\\n', ' ').strip() for row in cursor.fetchall() if row[0]])
                except: return []

            event_list_tasks = [
                {'type': 'event_list_jp', 'name_key': 'export_type_event_list_jp', 'data_func': lambda: get_event_list('JP'), 'file_suffix': 'event_list_jp', 'header_key': 'export_type_event_list_jp'},
                {'type': 'event_list_kr', 'name_key': 'export_type_event_list_kr', 'data_func': lambda: get_event_list('KR'), 'file_suffix': 'event_list_kr', 'header_key': 'export_type_event_list_kr'}
            ]
            for task in event_list_tasks:
                task_type = task['type']
                if not selected_options[task_type]:
                    continue
                type_name = lang_dict.get(task['name_key'], task_type)
                success_count = 0
                fail_count = 0
                current_failed_details = []

                self.task_queue.put(lambda tn=type_name: self._update_status_bar('status_bar_exporting_type', type_name=tn, success=0, failed=0))
                try:
                    data_list = task['data_func']()
                    if not data_list:
                        export_results[task_type] = {'success': 0, 'failed': 0, 'details': [f"No data found for {type_name}."]}
                        continue

                    success, error = self._save_list_to_file(data_list, task['file_suffix'], output_folder, lang_dict.get(task['header_key'], type_name))
                    if success:
                        success_count = 1
                    else:
                        fail_count = 1
                        current_failed_details.append(f"{type_name} (Error: {error})")
                except Exception as e:
                    fail_count += 1
                    current_failed_details.append(f"{type_name} (Unexpected Error: {e})")
                
                export_results[task_type] = {'success': success_count, 'failed': fail_count, 'details': current_failed_details}
                total_exported_count += success_count
                total_failed_count += fail_count
                all_failed_details.extend(current_failed_details)

        self.task_queue.put(lambda: self._finish_export(total_exported_count, total_failed_count, all_failed_details))

    def _finish_export(self, exported_count, failed_count, failed_list):
        lang_dict = LANGUAGES[self.lang_var.get()]

        if exported_count > 0:
            messagebox.showinfo(lang_dict['msgbox_export_complete_title'], lang_dict['msgbox_export_complete_msg'].format(exported_count=exported_count), parent=self.master)
            self._update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        else:
            messagebox.showwarning(lang_dict['msgbox_export_failed_title'], lang_dict['msgbox_export_failed_msg'].format(failed_count=failed_count), parent=self.master)
            self._update_status_bar('status_bar_export_summary', success_total=exported_count, failed_total=failed_count)
        
        if failed_list:
            error_msg = "\n".join(failed_list[:10]) + ("\n..." if len(failed_list) > 10 else "")
            messagebox.showerror(lang_dict['msgbox_export_error_details_title'], lang_dict['msgbox_export_error_details_msg'].format(errors=error_msg), parent=self.master)
