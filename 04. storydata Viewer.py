import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import os
import json
import re
import sqlite3

class SearchWindow(tk.Toplevel):
    """고급 검색 기능을 위한 별도의 창 (LabelFrame 적용)"""
    def __init__(self, app, all_files_dict, search_callback, search_data):
        super().__init__(app.master)
        self.title("storydata 고급 검색")
        
        self.app = app
        self.all_files_dict = all_files_dict
        
        self.search_callback = search_callback
        self.search_data = search_data

        self.search_vars = {
            'filename': tk.StringVar(),
            'title': tk.StringVar(),
            'outline': tk.StringVar(),
            'char_name': tk.StringVar(),
            'char_type': tk.StringVar(value='화자'),
            'content': tk.StringVar(),
            'bgm': tk.StringVar(),
            'background': tk.StringVar(),
            'event_name': tk.StringVar()
        }
        self.server_var = tk.StringVar(value='JP')

        # 각 서버별 DB 파일 경로 및 테이블/컬럼 정보 정의
        self.server_db_info = {
            'JP': {
                'db_path': 'master_jp.db',
                'event_list_table': 'v1_8931e2893a2d2290dbf498046bc66faafeebc40b6764dd69334ad51f5aca2e9f',
                'event_name_col_list': 'e3f0f79d746654f52125f3c28eb487d9e102f02077fe104d1423f08e80e056e3', # 이벤트 목록 테이블의 이벤트 이름 컬럼 (2번째)
                'event_details_table': 'v1_04d08b8c6bf704241326eca45b6d63cc1a6dd38d03ff256df15b8ec8d4cd2649',
                'event_info_col_details': '20d0bf56a9ca7d14b3172ac4dd383fee10c010d4ecd30c9854302d10390d774e', # 이벤트 상세 테이블의 이벤트 이름+정보 컬럼 (11번째)
                'event_id_col_details': '69d3bbead1844607ef41ecb520a4d5385cae02eddca377aa13721ec7fd01e0ec' # 이벤트 상세 테이블의 이벤트 고유 ID 컬럼 (12번째)
            },
            'KR': {
                'db_path': 'master_kr.db',
                'event_list_table': 'v1_4e380b72af2e31867844884ba838095ad9ea8f02bf83037a3c8ed47b8943f164',
                'event_name_col_list': 'abb720eaefdc23b376dc5b817b683e633eb66fe9a3941025ae27413c56d56fad', # 이벤트 목록 테이블의 이벤트 이름 컬럼 (4번째)
                'event_details_table': 'v1_ebabad5e41c1f71b3e5d705a8fe81411012e124827b4cbde3dfb2469674f598f',
                'event_info_col_details': '45d39837db60a2b9aca5a03c3c17a9999201e08e97c3cff92bb95786dd344355', # 이벤트 상세 테이블의 이벤트 이름+정보 컬럼 (3번째)
                'event_id_col_details': '6db6c11bbfa308b726f5f24bdee2bc75a2f805e2ae94ed4908aaa7444ce3e2eb' # 이벤트 상세 테이블의 이벤트 고유 ID 컬럼 (7번째)
            }
        }
        
        self.transient(app.master)
        self.grab_set()
        
        self._setup_ui()
        self._center_window(420, 420)

        self._on_server_selection_change()

    def _center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
    def _setup_ui(self):
        self.geometry("420x420")
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        criteria_frame = ttk.LabelFrame(main_frame, text="기본 검색 조건", padding="5")
        criteria_frame.pack(fill="x", expand=False, anchor="n", pady=(0, 10))
        criteria_frame.columnconfigure(1, weight=1)

        ttk.Label(criteria_frame, text="파일 이름:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['filename'], values=self.search_data.get('filenames', [])).grid(row=0, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="제목:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(criteria_frame, textvariable=self.search_vars['title']).grid(row=1, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="개요:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(criteria_frame, textvariable=self.search_vars['outline']).grid(row=2, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="캐릭터 이름:").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['char_name'], values=self.search_data.get('character_names', [])).grid(row=3, column=1, sticky="ew")
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['char_type'], values=['화자', '피호명자(대사)'], width=12, state='readonly').grid(row=3, column=2, sticky="e", padx=(5,0))

        ttk.Label(criteria_frame, text="내용(대사):").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(criteria_frame, textvariable=self.search_vars['content']).grid(row=4, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="BGM 파일명:").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['bgm'], values=self.search_data.get('bgms', [])).grid(row=5, column=1, columnspan=2, sticky="ew")

        ttk.Label(criteria_frame, text="배경 파일명:").grid(row=6, column=0, sticky="w", pady=3)
        ttk.Combobox(criteria_frame, textvariable=self.search_vars['background'], values=self.search_data.get('backgrounds', [])).grid(row=6, column=1, columnspan=2, sticky="ew")


        event_search_frame = ttk.LabelFrame(main_frame, text="이벤트 스토리 검색", padding="5")
        event_search_frame.pack(fill="x", expand=True, anchor="n")
        event_search_frame.columnconfigure(1, weight=1)

        server_frame = ttk.LabelFrame(event_search_frame, text="서버", padding="5")
        server_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0,5))
        server_frame.columnconfigure(0, weight=1)
        server_frame.columnconfigure(1, weight=1)

        ttk.Radiobutton(server_frame, text="일본 서버 (JP)", variable=self.server_var, value="JP", command=self._on_server_selection_change).grid(row=0, column=0, padx=5, sticky="w")
        ttk.Radiobutton(server_frame, text="한국 서버 (KR)", variable=self.server_var, value="KR", command=self._on_server_selection_change).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(event_search_frame, text="이벤트 목록:").grid(row=1, column=0, sticky="w", pady=3)
        self.event_combobox = ttk.Combobox(event_search_frame, textvariable=self.search_vars['event_name'])
        self.event_combobox.grid(row=1, column=1, columnspan=2, sticky="ew")

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side="bottom", fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="검색", command=self._search).pack(side="right")
        ttk.Button(button_frame, text="초기화", command=self._reset).pack(side="right", padx=(0, 5))

    def _on_server_selection_change(self):
        selected_server = self.server_var.get()
        db_info = self.server_db_info.get(selected_server)

        if not db_info:
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            self.app.status_bar.config(text="서버 정보 로드 실패.")
            return

        script_dir = os.path.dirname(__file__)
        db_path = os.path.join(script_dir, db_info['db_path'])
        
        if not os.path.exists(db_path):
            messagebox.showwarning("데이터베이스 오류", f"{db_path} 파일을 찾을 수 없습니다.\n\n해당 서버의 이벤트 목록을 로드할 수 없습니다.")
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            self.app.status_bar.config(text=f"'{db_info['db_path']}' 파일 없음.")
            return

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            event_names = []
            query_event_list = f"SELECT DISTINCT \"{db_info['event_name_col_list']}\" FROM \"{db_info['event_list_table']}\""
            cursor.execute(query_event_list)
            
            event_names = [row[0].replace('\\n', '') for row in cursor.fetchall() if row[0]]

            self.event_combobox['values'] = event_names
            self.search_vars['event_name'].set('')
            self.app.status_bar.config(text=f"'{selected_server}' 서버 이벤트 목록 로드 완료 ({len(event_names)}개).")

        except sqlite3.OperationalError as e:
            messagebox.showerror("데이터베이스 오류", f"데이터베이스 연결 또는 쿼리 오류 ({db_path}):\n{e}")
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            self.app.status_bar.config(text=f"데이터베이스 오류: {e}")
        except Exception as e:
            messagebox.showerror("오류", f"이벤트 목록 로드 중 알 수 없는 오류 발생:\n{e}")
            self.event_combobox['values'] = []
            self.search_vars['event_name'].set('')
            self.app.status_bar.config(text=f"이벤트 목록 로드 오류: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    def _search(self):
        self.app.status_bar.config(text="검색 중...")
        self.app.master.update_idletasks()

        criteria = {key: var.get().lower() for key, var in self.search_vars.items() if var.get()}
        
        event_name_from_combo = self.search_vars['event_name'].get()
        if event_name_from_combo:
            event_name_for_db_query = event_name_from_combo.replace(' ', '\\n')
        else:
            event_name_for_db_query = ""

        if 'event_name' in criteria:
            del criteria['event_name']


        if not criteria and not event_name_for_db_query:
            self._reset()
            return
        
        initial_matched_files = set(self.all_files_dict.keys())

        if event_name_for_db_query:
            selected_server = self.server_var.get()
            db_info = self.server_db_info.get(selected_server)

            if not db_info:
                messagebox.showerror("검색 오류", "선택된 서버 정보가 유효하지 않습니다.")
                self.search_callback([])
                self.destroy()
                return

            script_dir = os.path.dirname(__file__)
            db_path = os.path.join(script_dir, db_info['db_path'])

            if not os.path.exists(db_path):
                messagebox.showwarning("검색 오류", f"{db_path} 파일을 찾을 수 없어 이벤트 검색을 수행할 수 없습니다.")
                pass 
            else:
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()

                    query_event_ids = f"SELECT \"{db_info['event_id_col_details']}\" FROM \"{db_info['event_details_table']}\" WHERE \"{db_info['event_info_col_details']}\" LIKE ?"
                    cursor.execute(query_event_ids, (f"{event_name_for_db_query}%",))
                    
                    event_story_ids = {f"storydata_{row[0]}.json" for row in cursor.fetchall()}
                    
                    initial_matched_files = initial_matched_files.intersection(event_story_ids)
                    if not initial_matched_files:
                        self.search_callback([])
                        self.destroy()
                        return

                except sqlite3.OperationalError as e:
                    messagebox.showerror("데이터베이스 오류", f"이벤트 ID 조회 중 오류 발생:\n{e}")
                    self.search_callback([])
                    self.destroy()
                    return
                finally:
                    if conn: conn.close()
            
        final_matched_files = []

        for filename in initial_matched_files:
            file_path = self.all_files_dict.get(filename)
            if not file_path: continue

            if 'filename' in criteria and criteria['filename'] not in filename.lower():
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                content_criteria = {k: v for k, v in criteria.items() if k != 'filename'}
                if self._check_file_content(data, content_criteria):
                    final_matched_files.append(filename)
            except Exception:
                continue
        
        final_matched_files = sorted(list(set(final_matched_files)))

        self.search_callback(final_matched_files)
        self.destroy()

    def _check_file_content(self, data, criteria):
        scene_0 = data.get('0', {})
        if 'title' in criteria and criteria['title'] not in scene_0.get('title', '').lower():
            return False
        if 'outline' in criteria and criteria['outline'] not in scene_0.get('outline', '').lower():
            return False

        scene_level_criteria_keys = ['char_name', 'content', 'bgm', 'background']
        has_scene_level_criteria = any(key in criteria for key in scene_level_criteria_keys)

        if not has_scene_level_criteria:
            return True

        for scene in data.values():
            match = True
            
            if 'content' in criteria and not ('print' in scene and criteria['content'] in scene['print'].get('text', '').lower()):
                match = False
            
            if 'bgm' in criteria and not ('bgm' in scene and criteria['bgm'] in str(scene.get('bgm', '')).lower()):
                match = False

            if 'background' in criteria and not ('background' in scene and criteria['background'] in str(scene.get('background', '')).lower()):
                match = False

            if 'char_name' in criteria:
                char_name_crit = criteria['char_name']
                char_type = self.search_vars['char_type'].get()
                
                char_found = False
                if 'print' in scene:
                    if char_type == '화자' and char_name_crit in str(scene['print'].get('name', '')).lower():
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
        self.server_var.set('JP')
        self._on_server_selection_change()
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

        self.field_order = [
            # 20250722 storydata 기준
            # 파트 1: {0} 그룹의 모든 데이터 (중복 제외)
            'title', 'outline', 'movie', 'shake_anime', 'place',

            # 파트 2: {1} ~ {n} 그룹의 모든 데이터 (원본 순서 기준)
            'vo', 'face', 'print', 'nod', 'wait', 'window_visible', 'change', 'chara_full', 
            'fadein', 'focus', 'jump', 'fadeout_all', 'fadeout', 'pop', 'voice_effect', 
            'change_window', 'ignore_bgm', 'eye_open', 'emotion', 'se', 'fadein_all', 
            'effect', 'effect_delete', 'se_pause', 'multi_lipsync', 'bgm', 'tag', 
            'choice', 'goto', 'text_size', 'ui_visible', 'black_out', 'bright_change', 
            'background', 'situation', 'bg_pan', 'env_stop', 'env', 'background_color', 
            'shake', 'sway', 'out_l', 'in_r', 'character_up_down', 'pan', 'camera_zoom', 
            'still', 'still_unit', 'still_move', 'still_normalize', 'background_blur', 
            'unknown'
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

        # GUI 표시용 태그 설정 (텍스트 내용에 직접 공백을 추가했으므로 마진은 줄임)
        self.story_text.tag_configure('scene_header', font=(default_font_family, 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=(default_font_family, 10, 'bold'), foreground='#4A4A4A') # Removed lmargin1 as spaces are added to string
        self.story_text.tag_configure('value', font=(default_font_family, 10), foreground='#333333') # Removed lmargin as spaces are added to string
        self.story_text.tag_configure('print_sub_key', font=(default_font_family, 10), foreground='#333333') # Removed lmargin as spaces are added to string
        self.story_text.tag_configure('choice', font=(default_font_family, 10, 'bold'), foreground='#8B0000') # Removed lmargin as spaces are added to string
        self.story_text.tag_configure('choice_tag', font=(default_font_family, 10, 'italic'), foreground='#808080') # Removed lmargin as spaces are added to string
    
    def create_menu(self):
        menu_bar = tk.Menu(self.master)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="파일 열기", command=self.open_files)
        file_menu.add_command(label="폴더 열기", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="내보내기", command=self.export_stories)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.master.quit)
        menu_bar.add_cascade(label="메뉴(Menu)", menu=file_menu)
        self.master.config(menu=menu_bar)
            
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
        
        pattern = re.compile(r'^storydata_\d+\.json$')
        for dirpath, _, filenames in os.walk(folder_path):
            for filename in sorted(filenames):
                if pattern.match(filename):
                    full_path = os.path.join(dirpath, filename)
                    if self._is_valid_storydata(full_path):
                        self.all_files[filename] = full_path
        
        if not self.all_files:
            messagebox.showwarning("알림", "선택한 폴더에 유효한 storydata 파일이 없습니다.")
            self.status_bar.config(text="준비")
            return

        self._analyze_and_update_ui()

    def _analyze_and_update_ui(self):
        self.status_bar.config(text=f"총 {len(self.all_files)}개 파일 분석 중...")
        self.master.update_idletasks()
        
        unique_char_names, unique_bgms, unique_bgs = set(), set(), set()
        
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
                    if 'print' in scene and 'name' in scene['print']:
                        char_name = str(scene['print']['name']).strip()
                        if char_name:
                            unique_char_names.add(char_name)

                    if 'bgm' in scene:
                        bgm_name = _extract_asset_name(scene['bgm'])
                        if bgm_name: unique_bgms.add(bgm_name)
                    if 'background' in scene:
                        bg_name = _extract_asset_name(scene['background'])
                        if bg_name: unique_bgs.add(bg_name)
            except Exception:
                continue
        
        self.search_data = {
            'filenames': sorted(list(self.all_files.keys())),
            'character_names': sorted(list(unique_char_names)),
            'bgms': sorted(list(unique_bgms)),
            'backgrounds': sorted(list(unique_bgs)),
        }
        
        self.update_file_list(list(self.all_files.keys()))
        self.status_bar.config(text=f"총 {len(self.all_files)}개 파일 로드 및 분석 완료.")

    def open_search_window(self):
        if not self.all_files:
            messagebox.showinfo("알림", "먼저 storydata 파일이나 폴더를 열어주세요.")
            return
        SearchWindow(self, self.all_files, self.update_file_list, self.search_data)

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
        if len(filenames) > 0:
            self.file_listbox.selection_set(0)
            self.file_listbox.event_generate("<<ListboxSelect>>")

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
            # format_story_data는 (텍스트, 태그) 튜플 리스트를 반환합니다.
            content_list = self.format_story_data(data) 
            self.update_story_text(content_list)
            self.status_bar.config(text=f"'{os.path.basename(file_path)}' 로드 완료.")
        except Exception as e:
            messagebox.showerror("오류", f"파일 처리 중 오류 발생: {e}")
            self.status_bar.config(text=f"오류: '{os.path.basename(file_path)}' 로드 실패.")

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
            else: # 자세히 표시
                keys_to_display = sorted(scene.keys(), key=self._sort_key_func)
            
            for field in keys_to_display:
                value = scene[field]
                # 각 필드 이름 앞에 4칸의 공백을 추가하여 들여쓰기
                content_list.append(("    " + f"{field}\n", 'key'))
                # 각 포매터 메소드는 content_list에 직접 (텍스트, 태그) 튜플을 추가합니다.
                formatter = getattr(self, f'_format_{field}', self._format_default)
                formatter(value, content_list)
                content_list.append(("\n", None))
            content_list.append(("-"*60 + "\n\n", None))
        return content_list

    def _sort_key_func(self, field_name):
        if field_name in self.field_order:
            return (0, self.field_order.index(field_name))
        return (1, field_name)

    # 포매터 메소드들은 전달받은 content_list에 직접 내용을 추가하도록 구현되어 있습니다.
    # 각 값 앞에 8칸의 공백을 추가하여 들여쓰기를 반영합니다.
    def _format_print(self, value, content_list):
        indent = "        " # 8 spaces for value-level content
        name = str(value.get('name', '???')) 
        text = value.get('text', '')
        # 대사 내용 내의 줄바꿈 시에도 들여쓰기 유지
        formatted_text = text.replace('\n', '\n' + indent)

        content_list.append((indent + f"- name: {name}\n", 'print_sub_key'))
        content_list.append((indent + f"- text: “{formatted_text}”\n", 'print_sub_key'))

    def _format_chara_full(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_fadein(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_fadeout(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_face(self, value, content_list): self._format_generic_id_list(value, content_list)
    def _format_nod(self, value, content_list): self._format_simple_id_list(value, content_list)
    def _format_shake(self, value, content_list): self._format_simple_id_list(value, content_list)
    def _format_focus(self, value, content_list): self._format_simple_id_list(value, content_list)

    def _format_choice(self, value, content_list):
        indent = "        " # 8 spaces for value-level content
        for i, choice_item in enumerate(value, 1):
            # 선택지 텍스트 앞에 들여쓰기 추가
            content_list.append((indent + f"{i}. {choice_item['text']}", 'choice'))
            # 태그는 같은 줄에 이어붙이므로 들여쓰기 추가 안 함
            content_list.append((f" (→ S# {choice_item['tag']})\n", 'choice_tag'))

    def _format_default(self, value, content_list):
        indent = "        " # 8 spaces for value-level content
        # 기본값 앞에 8칸의 공백을 추가하여 들여쓰기
        content_list.append((indent + f"{str(value)}\n", 'value'))
    
    def _format_generic_id_list(self, value, content_list):
        indent = "        " # 8 spaces for value-level content
        if not isinstance(value, list):
            self._format_default(value, content_list) # 이 함수가 이미 들여쓰기를 추가함
            return

        for item in value:
            if isinstance(item, list) and item:
                char_id = str(item[0])
                details = ", ".join(map(str, item[1:]))
                # 리스트 항목 앞에 8칸의 공백을 추가하여 들여쓰기
                content_list.append((indent + f"- {char_id}", 'value'))
                # 세부 정보는 같은 줄에 이어붙이므로 들여쓰기 추가 안 함
                content_list.append((f" ({details})\n" if details else "\n", 'value'))
            else:
                content_list.append((indent + f"- {str(item)}\n", 'value'))

    def _format_simple_id_list(self, value, content_list):
        indent = "        " # 8 spaces for value-level content
        if not isinstance(value, list): value = [value]
        for item in value:
            content_list.append((indent + f"- {str(item)}\n", 'value'))

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            # content 문자열에 이미 들여쓰기 공백이 포함되어 있으므로,
            # Tkinter 태그의 lmargin 옵션은 제거하거나 0으로 설정해도 무방합니다.
            self.story_text.insert(tk.END, content, (tag,) if tag else ())
        self.story_text.config(state=tk.DISABLED)

    def export_stories(self):
        if not self.all_files:
            messagebox.showinfo("알림", "먼저 storydata 파일이나 폴더를 열어주세요.")
            return

        # 내보내기 범위 선택 메시지 박스
        response = messagebox.askyesno(
            "내보내기 옵션",
            "현재 목록에 반환 된 파일만 저장하시겠습니까?\n\n"
            "- 예(Y): 현재 목록에 반환 된 파일만 저장\n"
            "- 아니요(N): 불러왔던 모든 파일 저장"
        )

        if response is None: # 사용자가 메시지 박스를 닫았을 경우
            return

        if response: # 예(Y) 선택: 현재 리스트에 있는 파일만 내보내기
            filenames_to_export = self.current_filenames_in_list
        else: # 아니요(N) 선택: 모든 불러온 파일 내보내기
            filenames_to_export = sorted(list(self.all_files.keys()))
        
        if not filenames_to_export:
            messagebox.showinfo("알림", "내보낼 파일이 없습니다.")
            return

        # 저장할 폴더 선택 대화 상자
        output_folder = filedialog.askdirectory(title="스토리 파일을 저장할 폴더를 선택하세요")
        if not output_folder:
            self.status_bar.config(text="내보내기 취소.")
            return

        self.status_bar.config(text=f"{len(filenames_to_export)}개 파일 내보내기 중...")
        self.master.update_idletasks() # UI 업데이트 강제

        exported_count = 0
        failed_count = 0
        failed_files = []

        for filename in filenames_to_export:
            source_file_path = self.all_files.get(filename)
            if not source_file_path:
                failed_count += 1
                failed_files.append(filename)
                continue

            # 파일 이름은 원본 그대로, 확장자는 txt로 변경
            output_filename = os.path.splitext(filename)[0] + ".txt"
            output_file_path = os.path.join(output_folder, output_filename)

            try:
                with open(source_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 현재 선택된 뷰 모드(간단히/자세히)에 따라 데이터 포맷
                # format_story_data는 (텍스트, 태그) 튜플 리스트를 반환합니다.
                formatted_content_list = self.format_story_data(data)
                
                # 텍스트 부분만 추출하여 하나의 문자열로 결합 (이미 들여쓰기 공백이 포함됨)
                text_to_write = "".join([text for text, _ in formatted_content_list])

                with open(output_file_path, 'w', encoding='utf-8') as outfile:
                    outfile.write(text_to_write)
                
                exported_count += 1

            except Exception as e:
                failed_count += 1
                failed_files.append(f"{filename} (오류: {e})")
                continue
        
        # 내보내기 결과 메시지
        if exported_count > 0:
            messagebox.showinfo("내보내기 완료", f"{exported_count}개의 파일을 성공적으로 내보냈습니다.")
            self.status_bar.config(text=f"{exported_count}개 파일 내보내기 완료. ({failed_count}개 실패)")
        else:
            messagebox.showwarning("내보내기 실패", f"내보낸 파일이 없습니다. {failed_count}개의 파일에서 오류가 발생했습니다.")
            self.status_bar.config(text=f"모든 파일 내보내기 실패. ({failed_count}개 실패)")
        
        if failed_files:
            # 실패한 파일이 많을 경우 일부만 표시
            error_msg_detail = "\n".join(failed_files[:10])
            if len(failed_files) > 10:
                error_msg_detail += "\n..."
            messagebox.showerror("내보내기 오류 상세", "다음 파일 내보내기 중 오류가 발생했습니다:\n" + error_msg_detail)


if __name__ == "__main__":
    root = tk.Tk()
    app = StoryViewerApp(root)
    root.mainloop()