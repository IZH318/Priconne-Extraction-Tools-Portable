import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import os
import json
import re

class SearchWindow(tk.Toplevel):
    """고급 검색 기능을 위한 별도의 창 (LabelFrame 적용)"""
    def __init__(self, app, all_files_dict, character_map, search_callback, search_data):
        super().__init__(app.master)
        self.title("storydata 고급 검색")
        
        self.app = app
        self.all_files_dict = all_files_dict
        self.character_map = character_map
        self.search_callback = search_callback
        self.search_data = search_data

        self.search_vars = {
            'filename': tk.StringVar(),
            'char_name': tk.StringVar(),
            'char_type': tk.StringVar(value='화자'),
            'content': tk.StringVar(),
            'bgm': tk.StringVar(),
            'background': tk.StringVar()
        }
        self.transient(app.master)
        self.grab_set()
        
        self._setup_ui()
        self._center_window(480, 240)

    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
    def _setup_ui(self):
        self.geometry("480x240")
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        criteria_frame = ttk.LabelFrame(main_frame, text="검색 조건", padding="10")
        criteria_frame.pack(fill="x", expand=True, anchor="n")
        criteria_frame.columnconfigure(1, weight=1)

        ttk.Label(criteria_frame, text="파일 이름:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['filename'], values=self.search_data.get('filenames', [])).grid(row=0, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="캐릭터 이름:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['char_name'], values=self.search_data.get('character_names', [])).grid(row=1, column=1, sticky="ew")
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['char_type'], values=['화자', '피호명자(대사)'], width=12, state='readonly').grid(row=1, column=2, sticky="e", padx=(5,0))

        ttk.Label(criteria_frame, text="내용(대사):").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(criteria_frame, textvariable=self.search_vars['content']).grid(row=2, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="BGM 파일명:").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['bgm'], values=self.search_data.get('bgms', [])).grid(row=3, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="배경 파일명:").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['background'], values=self.search_data.get('backgrounds', [])).grid(row=4, column=1, columnspan=2, sticky="ew")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="검색", command=self._search).pack(side="right")
        ttk.Button(button_frame, text="초기화", command=self._reset).pack(side="right", padx=(0, 5))

    def _get_char_name(self, char_id):
        char_id_str = str(char_id)
        return self.character_map.get(char_id_str, char_id_str)

    def _search(self):
        self.app.status_bar.config(text="검색 중...")
        self.app.master.update_idletasks()

        criteria = {key: var.get().lower() for key, var in self.search_vars.items() if var.get()}
        if not criteria:
            self._reset()
            return
        
        matched_files = []
        for filename, path in self.all_files_dict.items():
            if not criteria.get('filename') or criteria['filename'] in filename.lower():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if self._check_file_content(data, criteria):
                        matched_files.append(filename)
                except Exception: continue

        self.search_callback(matched_files)
        self.destroy()

    def _check_file_content(self, data, criteria):
        content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
        if not content_criteria:
            return True

        for scene in data.values():
            match = True
            if 'content' in content_criteria and not ('print' in scene and content_criteria['content'] in scene['print'].get('text', '').lower()):
                match = False
            
            if 'bgm' in content_criteria and not ('bgm' in scene and content_criteria['bgm'] in str(scene.get('bgm', '')).lower()):
                match = False

            if 'background' in content_criteria and not ('background' in scene and content_criteria['background'] in str(scene.get('background', '')).lower()):
                match = False

            if 'char_name' in content_criteria:
                char_name_crit = content_criteria['char_name']
                char_type = self.search_vars['char_type'].get()
                
                char_found = False
                if 'print' in scene:
                    if char_type == '화자' and char_name_crit in self._get_char_name(scene['print'].get('name', '')).lower():
                        char_found = True
                    if char_type == '피호명자(대사)' and char_name_crit in scene['print'].get('text', '').lower():
                        char_found = True
                
                if not char_found:
                    match = False
            
            if match:
                return True

        return False

    def _reset(self):
        for var in self.search_vars.values(): var.set('')
        self.search_callback(list(self.all_files_dict.keys()))
        self.destroy()

class StoryViewerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("storydata Viewer")

        self.all_files = {}
        self.search_data = {}
        self.file_titles = {}
        self.display_name_to_filename = {}
        self.current_filenames_in_list = []
        self.current_file_path = None
        
        self.display_mode_var = tk.StringVar(value="원본 파일 이름으로 표시")
        self.view_mode_var = tk.StringVar(value="간단히 표시")

        self.character_map = self.load_json_file("character_map.json")
        
        self.field_order = [
            # {0} 그룹의 모든 데이터 (중복 제외)
            'title', 'outline', 'bgm', 'place', 'situation', 'movie', 'black_out', 
            'transition', 'background_color', 'background', 'jingle', 'env', 'ui_visible',

            # {1} ~ {n} 그룹의 모든 데이터 (원본 순서 기준)
            'vo', 'face', 'print', 'nod', 'wait', 'window_visible', 'change', 'jump', 
            'eye_open', 'se', 'pop', 'shake', 'sway', 'fadeout', 'fadeout_all', 
            'white_out', 'chara_full', 'fadein', 'voice_effect', 'focus', 'pan', 
            'camera_zoom', 'emotion', 'effect', 'choice', 'tag', 'goto', 'still', 
            'still_unit', 'still_move', 'still_normalize', 'out_l', 'in_r', 
            'effect_delete', 'se_pause', 'ignore_bgm', 'env_stop', 'unknown', 
            'multi_lipsync', 'change_window', 'text_size', 'bright_change', 
            'character_up_down', 'background_blur', 'event_adv_move_horizontal'
        ]
        
        self.setup_ui()
        self.setup_text_tags()
        self._center_window(800, 600)

    def _center_window(self, width, height):
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def setup_ui(self):
        self.master.geometry("800x600")
        self.create_menu()
        self.master.grid_rowconfigure(1, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        
        options_group = ttk.LabelFrame(self.master, text="옵션")
        options_group.grid(row=0, column=0, sticky="ew", padx=10, pady=(5,0))
        options_group.columnconfigure(0, weight=1)
        options_group.columnconfigure(1, weight=1)

        file_options_group = ttk.LabelFrame(options_group, text="스토리 파일 목록 옵션", padding=5)
        file_options_group.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        ttk.Radiobutton(file_options_group, text="원본 파일 이름으로 표시", variable=self.display_mode_var, value="원본 파일 이름으로 표시", command=self._on_display_mode_change).grid(row=0, column=0, padx=5)
        ttk.Radiobutton(file_options_group, text="title 정보로 표시", variable=self.display_mode_var, value="title 정보로 표시", command=self._on_display_mode_change).grid(row=0, column=1, padx=5)

        detail_options_group = ttk.LabelFrame(options_group, text="스토리 상세 정보 옵션", padding=5)
        detail_options_group.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Radiobutton(detail_options_group, text="간단히 표시 (title, outline, vo, print)", variable=self.view_mode_var, value="간단히 표시", command=self._on_view_mode_change).grid(row=0, column=0, padx=5)
        ttk.Radiobutton(detail_options_group, text="자세히 표시", variable=self.view_mode_var, value="자세히 표시", command=self._on_view_mode_change).grid(row=0, column=1, padx=5)

        main_frame = ttk.Frame(self.master, padding=(10, 5, 10, 0))
        main_frame.grid(row=1, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True)

        left_weight = 1
        right_weight = 2

        left_group = ttk.LabelFrame(self.paned_window, text="스토리 파일 목록", padding=5)
        self.paned_window.add(left_group, weight=left_weight) 
        left_group.grid_rowconfigure(1, weight=1)
        left_group.grid_columnconfigure(0, weight=1)

        ttk.Button(left_group, text="storydata 고급 검색", command=self.open_search_window).grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        list_frame_inner = ttk.Frame(left_group)
        list_frame_inner.grid(row=1, column=0, sticky="nsew")
        list_frame_inner.grid_rowconfigure(0, weight=1)
        list_frame_inner.grid_columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame_inner, selectmode=tk.SINGLE)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        list_scrollbar = ttk.Scrollbar(list_frame_inner, orient=tk.VERTICAL, command=self.file_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=list_scrollbar.set)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        
        right_group = ttk.LabelFrame(self.paned_window, text="스토리 상세 정보", padding=5)
        self.paned_window.add(right_group, weight=right_weight)
        right_group.grid_rowconfigure(0, weight=1)
        right_group.grid_columnconfigure(0, weight=1)
        
        text_frame_inner = ttk.Frame(right_group)
        text_frame_inner.grid(row=0, column=0, sticky="nsew")
        text_frame_inner.grid_rowconfigure(0, weight=1)
        text_frame_inner.grid_columnconfigure(0, weight=1)
        
        self.story_text = tk.Text(text_frame_inner, wrap=tk.WORD, state=tk.DISABLED, spacing1=2, padx=10, pady=10)
        self.story_text.grid(row=0, column=0, sticky="nsew")
        text_scrollbar = ttk.Scrollbar(text_frame_inner, orient=tk.VERTICAL, command=self.story_text.yview)
        text_scrollbar.grid(row=0, column=1, sticky="ns")
        self.story_text.config(yscrollcommand=text_scrollbar.set)

        self.status_bar = ttk.Label(self.master, text="폴더를 열어주세요.", anchor=tk.W, padding=5)
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        def reapply_weights(event=None):
            total_width = self.paned_window.winfo_width()
            sash_position = int(total_width * left_weight / (left_weight + right_weight))
            self.paned_window.sashpos(0, sash_position)
            self.paned_window.unbind("<Configure>")

        self.paned_window.bind("<Configure>", reapply_weights)

    def setup_text_tags(self):
        default_font_family = font.nametofont("TkDefaultFont").cget("family")

        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A', lmargin1=20)
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080')
    
    def create_menu(self):
        menu_bar = tk.Menu(self.master)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="파일 열기...", command=self.open_files)
        file_menu.add_command(label="폴더 열기...", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.master.quit)
        menu_bar.add_cascade(label="파일", menu=file_menu)
        self.master.config(menu=menu_bar)

    def load_json_file(self, file_path, file_desc="JSON"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError: return {}
        except json.JSONDecodeError:
            messagebox.showerror("오류", f"{file_desc} 파일({file_path})의 형식이 잘못되었습니다.")
            return {}
            
    def _clear_workspace(self):
        self.update_story_text([])
        self.all_files.clear()
        self.search_data.clear()
        self.file_listbox.delete(0, tk.END)
        self.file_titles.clear()
        self.display_name_to_filename.clear()
        self.current_filenames_in_list = []
        self.current_file_path = None

    def _is_valid_storydata(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data:
                return False
            return all(k.isdigit() and isinstance(v, dict) for k, v in data.items())
        except Exception:
            return False

    def open_files(self):
        file_paths = filedialog.askopenfilenames(
            title="storydata 파일을 선택하세요",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")]
        )
        if not file_paths: return

        self._clear_workspace()
        self.status_bar.config(text="선택한 파일 검증 중...")
        self.master.update_idletasks()

        for path in file_paths:
            if self._is_valid_storydata(path):
                filename = os.path.basename(path)
                self.all_files[filename] = path
            
        if not self.all_files:
            messagebox.showwarning("알림", "선택한 파일 중 유효한 storydata 파일이 없습니다.")
            self.status_bar.config(text="준비")
            return

        self._analyze_and_update_ui()

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="storydata 파일이 있는 폴더를 선택하세요")
        if not folder_path: return

        self._clear_workspace()
        self.status_bar.config(text="폴더에서 파일 검색 중...")
        self.master.update_idletasks()
        
        pattern = re.compile(r'^storydata_\d{7}\.json$')
        for dirpath, _, filenames in os.walk(folder_path):
            for filename in sorted(filenames):
                if pattern.match(filename):
                    self.all_files[filename] = os.path.join(dirpath, filename)
        
        if not self.all_files:
            messagebox.showwarning("알림", "선택한 폴더에 storydata 파일이 없습니다.")
            self.status_bar.config(text="준비")
            return

        self._analyze_and_update_ui()

    def _analyze_and_update_ui(self):
        self.status_bar.config(text=f"총 {len(self.all_files)}개 파일 분석 중...")
        self.master.update_idletasks()
        
        unique_chars, unique_bgms, unique_bgs = set(), set(), set()
        
        def _extract_asset_name(value):
            if isinstance(value, str): return value
            if isinstance(value, list) and value and isinstance(value[0], str): return value[0]
            return None

        for filename, path in self.all_files.items():
            try:
                with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
                
                title = data.get('0', {}).get('title', '').strip()
                self.file_titles[filename] = title if title else filename

                for scene in data.values():
                    if 'bgm' in scene:
                        bgm_name = _extract_asset_name(scene['bgm'])
                        if bgm_name: unique_bgms.add(bgm_name)
                    if 'background' in scene:
                        bg_name = _extract_asset_name(scene['background'])
                        if bg_name: unique_bgs.add(bg_name)
                    if 'print' in scene and 'name' in scene['print']:
                        unique_chars.add(self.get_char_name(scene['print']['name']))
            except Exception: continue
        
        self.search_data = {
            'filenames': sorted(list(self.all_files.keys())),
            'character_names': sorted(list(unique_chars)),
            'bgms': sorted(list(unique_bgms)),
            'backgrounds': sorted(list(unique_bgs)),
        }
        
        self.update_file_list(list(self.all_files.keys()))
        self.status_bar.config(text=f"총 {len(self.all_files)}개 파일 로드 및 분석 완료.")

    def open_search_window(self):
        if not self.all_files:
            messagebox.showinfo("알림", "먼저 파일이나 폴더를 열어주세요.")
            return
        SearchWindow(self, self.all_files, self.character_map, self.update_file_list, self.search_data)

    def update_file_list(self, filenames):
        self.update_story_text([])
        self.current_file_path = None

        self.current_filenames_in_list = sorted(filenames)
        self.file_listbox.delete(0, tk.END)
        self.display_name_to_filename.clear()

        display_mode = self.display_mode_var.get()
        
        for filename in self.current_filenames_in_list:
            display_name = filename
            if display_mode == "title 정보로 표시":
                title = self.file_titles.get(filename, filename)
                if title != filename:
                    display_name = f"{title}"

            self.file_listbox.insert(tk.END, display_name)
            self.display_name_to_filename[display_name] = filename
            
        self.status_bar.config(text=f"{len(filenames)}개의 파일이 목록에 표시됩니다.")

    def on_file_select(self, event):
        sel_indices = self.file_listbox.curselection()
        if not sel_indices: return
        
        display_name = self.file_listbox.get(sel_indices[0])
        filename = self.display_name_to_filename.get(display_name)
        
        if filename:
            path = self.all_files.get(filename)
            if path:
                self.current_file_path = path
                self.load_and_display_story(path)

    def load_and_display_story(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            content_list = self.format_story_data(data)
            self.update_story_text(content_list)
            self.status_bar.config(text=f"'{os.path.basename(file_path)}' 로드 완료.")
        except Exception as e:
            messagebox.showerror("오류", f"파일 처리 중 오류 발생: {e}")

    def get_char_name(self, char_id):
        char_id_str = str(char_id)
        return self.character_map.get(char_id_str, char_id_str)

    def _on_display_mode_change(self):
        self.update_file_list(self.current_filenames_in_list)

    def _on_view_mode_change(self):
        if self.current_file_path:
            self.load_and_display_story(self.current_file_path)

    def format_story_data(self, data):
        content_list = []
        view_mode = self.view_mode_var.get()
        
        for key in sorted(data.keys(), key=int):
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            
            keys_to_display = []
            if view_mode == "간단히 표시":
                simple_keys = ['title', 'outline', 'vo', 'print']
                keys_to_display = [k for k in simple_keys if k in scene]
            else:
                keys_to_display = sorted(scene.keys(), key=self._sort_key_func)
            
            for field in keys_to_display:
                value = scene[field]
                content_list.append((f"{field}\n", 'key'))
                formatter = getattr(self, f'_format_{field}', self._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append(("-"*60 + "\n\n", None))
        return content_list

    def _sort_key_func(self, field_name):
        if field_name in self.field_order:
            return (0, self.field_order.index(field_name))
        return (1, field_name)

    def _format_print(self, value, content_list):
        name = self.get_char_name(value.get('name', '???'))
        text = value.get('text', '').replace('\n', '\n' + ' ' * 9)
        content_list.append((f"- name: {name}\n", 'print_sub_key'))
        content_list.append((f"- text: “{text}”\n", 'print_sub_key'))

    def _format_chara_full(self, value, content_list): self._format_generic_char_list(value, content_list)
    def _format_fadein(self, value, content_list): self._format_generic_char_list(value, content_list)
    def _format_fadeout(self, value, content_list): self._format_generic_char_list(value, content_list)
    def _format_face(self, value, content_list): self._format_generic_char_list(value, content_list)
    def _format_nod(self, value, content_list): self._format_simple_char_list(value, content_list)
    def _format_shake(self, value, content_list): self._format_simple_char_list(value, content_list)
    def _format_focus(self, value, content_list): self._format_simple_char_list(value, content_list)

    def _format_choice(self, value, content_list):
        for i, choice_item in enumerate(value, 1):
            content_list.append((f"{i}. {choice_item['text']}", 'choice'))
            content_list.append((f" (→ S# {choice_item['tag']})\n", 'choice_tag'))

    def _format_default(self, value, content_list):
        content_list.append((f"{str(value)}\n", 'value'))
    
    def _format_generic_char_list(self, value, content_list):
        for item in value:
            if isinstance(item, list) and item:
                char_name = self.get_char_name(item[0])
                details = ", ".join(map(str, item[1:]))
                content_list.append((f"- {char_name}", 'value'))
                content_list.append((f" ({details})\n" if details else "\n", 'value'))

    def _format_simple_char_list(self, value, content_list):
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((f"- {self.get_char_name(item)}\n", 'value'))

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = StoryViewerApp(root)
    root.mainloop()