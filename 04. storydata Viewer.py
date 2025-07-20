import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import re

class StoryViewerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("storydata Viewer")
        self.master.geometry("800x600")

        self.found_files = {}
        self.character_map = self.load_character_map()
        self.setup_ui()
        self.setup_text_tags()
        
        self._center_window()

    def _center_window(self):
        """프로그램 창을 화면 정가운데에 위치시킵니다."""
        self.master.update_idletasks()  # 창 크기 정보 업데이트
        
        # 창의 너비와 높이
        window_width = self.master.winfo_width()
        window_height = self.master.winfo_height()
        
        # 화면의 너비와 높이
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        
        # 화면 중앙 좌표 계산
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        
        # 창 위치 설정
        self.master.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")


    def setup_ui(self):
        """UI 위젯을 생성하고 grid 레이아웃을 사용하여 배치합니다."""
        self.create_menu()

        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        main_frame = ttk.Frame(self.master)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(5, 0))
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.paned_window.grid(row=0, column=0, sticky="nsew")

        left_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(left_frame, weight=1)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(left_frame, text="스토리 파일 목록").grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        list_frame_inner = ttk.Frame(left_frame)
        list_frame_inner.grid(row=1, column=0, sticky="nsew")
        list_frame_inner.grid_rowconfigure(0, weight=1)
        list_frame_inner.grid_columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame_inner, selectmode=tk.SINGLE, font=("Malgun Gothic", 10))
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        list_scrollbar = ttk.Scrollbar(list_frame_inner, orient=tk.VERTICAL, command=self.file_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=list_scrollbar.set)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

        right_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(right_frame, weight=3)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(right_frame, text="스토리 상세 정보").grid(row=0, column=0, sticky="ew", pady=(0, 5))

        text_frame_inner = ttk.Frame(right_frame)
        text_frame_inner.grid(row=1, column=0, sticky="nsew")
        text_frame_inner.grid_rowconfigure(0, weight=1)
        text_frame_inner.grid_columnconfigure(0, weight=1)

        self.story_text = tk.Text(text_frame_inner, wrap=tk.WORD, state=tk.DISABLED, font=("Malgun Gothic", 10), spacing1=2, padx=10, pady=10)
        self.story_text.grid(row=0, column=0, sticky="nsew")
        text_scrollbar = ttk.Scrollbar(text_frame_inner, orient=tk.VERTICAL, command=self.story_text.yview)
        text_scrollbar.grid(row=0, column=1, sticky="ns")
        self.story_text.config(yscrollcommand=text_scrollbar.set)

        self._bind_scroll_events(self.file_listbox)
        self._bind_scroll_events(self.story_text)

        self.status_bar = ttk.Label(self.master, text="폴더를 열어주세요.", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 5))

    def _bind_scroll_events(self, widget):
        widget.bind("<MouseWheel>", lambda event, w=widget: self._on_mouse_scroll(event, w), add="+")
        widget.bind("<Button-4>", lambda event, w=widget: self._on_mouse_scroll(event, w), add="+")
        widget.bind("<Button-5>", lambda event, w=widget: self._on_mouse_scroll(event, w), add="+")

    def _on_mouse_scroll(self, event, widget):
        scroll_speed = 5
        if event.num == 4 or event.delta > 0:
            widget.yview_scroll(-scroll_speed, "units")
        elif event.num == 5 or event.delta < 0:
            widget.yview_scroll(scroll_speed, "units")
        return "break"

    def setup_text_tags(self):
        """텍스트 위젯에 사용할 색상 및 스타일 태그를 설정합니다. (폰트 크기 10으로 통일)"""
        base_font = ("Malgun Gothic", 10)
        base_font_bold = (base_font[0], base_font[1], 'bold')
        base_font_italic = (base_font[0], base_font[1], 'italic')
        
        self.story_text.tag_configure('scene_header', font=('Malgun Gothic', 14, 'bold'), foreground='#00008B')
        self.story_text.tag_configure('key', font=base_font_bold, foreground='#4A4A4A', lmargin1=20)
        self.story_text.tag_configure('value', font=("Consolas", 10), foreground='#333333', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('print_sub_key', font=("Consolas", 10), foreground='#333333', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('choice', font=base_font_bold, foreground='#8B0000', lmargin1=40, lmargin2=40)
        self.story_text.tag_configure('choice_tag', font=base_font_italic, foreground='#808080')
    
    def create_menu(self):
        menu_bar = tk.Menu(self.master)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="폴더 열기", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.master.quit)
        menu_bar.add_cascade(label="파일", menu=file_menu)
        self.master.config(menu=menu_bar)

    def load_character_map(self):
        try:
            with open("character_map.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError: return {}
        except json.JSONDecodeError: return {}

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="스토리 데이터가 있는 폴더를 선택하세요")
        if not folder_path: return
        self.file_listbox.delete(0, tk.END)
        self.update_story_text([])
        self.found_files.clear()
        self.status_bar.config(text="파일 검색 중...")
        self.master.update_idletasks()
        self.find_story_files(folder_path)
        self.status_bar.config(text=f"총 {len(self.found_files)}개 파일 찾음.")

    def find_story_files(self, root_folder):
        pattern = re.compile(r'^storydata_\d{7}\.json$')
        for dirpath, _, filenames in os.walk(root_folder):
            for filename in sorted(filenames):
                if pattern.match(filename):
                    self.found_files[filename] = os.path.join(dirpath, filename)
                    self.file_listbox.insert(tk.END, filename)

    def on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if not sel: return
        path = self.found_files.get(self.file_listbox.get(sel[0]))
        if path: self.load_and_display_story(path)

    def load_and_display_story(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            content_list = self.format_consistent_data(data)
            self.update_story_text(content_list)
            self.status_bar.config(text=f"'{os.path.basename(file_path)}' 로드 완료.")
        except Exception as e:
            messagebox.showerror("오류", f"파일 처리 중 오류 발생: {e}")

    def get_char_name(self, char_id):
        if not isinstance(char_id, str):
            char_id = str(char_id)
        if not char_id.isdigit():
            return char_id
        return self.character_map.get(char_id, f"ID:{char_id}")

    def format_consistent_data(self, data):
        content_list = []
        
        field_order = [
            'title', 'outline', 'situation', 'tag', 'background', 'bg_pan', 'bg_pan_x', 'bgm', 'se',
            'effect', 'movie', 'still', 'chara_full', 'face', 'focus', 'nod', 'shake', 'pop',
            'sway', 'scale', 'change', 'character_up_down', 'multi_lipsync', 'fadein',
            'fadeout', 'fadein_all', 'fadeout_all', 'white_out', 'black_out', 'eye_open',
            'effect_delete', 'se_pause', 'env_stop', 'ignore_bgm', 'window_visible', 'ui_visible', 
            'text_size', 'change_window', 'event_adv_move_horizontal', 'wait', 'vo', 
            'voice_effect', 'print', 'choice'
        ]

        for key in sorted(data.keys(), key=int):
            scene = data[key]
            content_list.append((f" S# {key} \n", 'scene_header'))
            
            def sort_key_func(field_name):
                if field_name in field_order:
                    return (0, field_order.index(field_name))
                else:
                    return (1, field_name)

            sorted_scene_keys = sorted(scene.keys(), key=sort_key_func)

            for field in sorted_scene_keys:
                value = scene[field]
                content_list.append((f"{field}\n", 'key'))

                if field == 'print':
                    name = self.get_char_name(value.get('name', '???'))
                    text = value.get('text', '')
                    indent_space = ' ' * 9 
                    formatted_text = text.replace('\n', '\n' + indent_space)
                    content_list.append((f"- name: {name}\n", 'print_sub_key'))
                    content_list.append((f"- text: “{formatted_text}”\n", 'print_sub_key'))
                
                elif field in ['chara_full', 'fadein', 'fadeout', 'face']:
                    for item in value:
                        if isinstance(item, list) and item:
                            char_name = self.get_char_name(item[0])
                            details = ", ".join(map(str, item[1:]))
                            content_list.append((f"- {char_name}", 'value'))
                            if details: content_list.append((f" ({details})\n", 'value'))
                            else: content_list.append(("\n", 'value'))
                elif field in ['nod', 'shake', 'focus']:
                    if not isinstance(value, list): value = [value]
                    for item in value:
                        content_list.append((f"- {self.get_char_name(item)}\n", 'value'))
                elif field == 'choice':
                    for i, choice_item in enumerate(value, 1):
                        content_list.append((f"{i}. {choice_item['text']}", 'choice'))
                        content_list.append((f" (→ S# {choice_item['tag']})\n", 'choice_tag'))
                else:
                    content_list.append((f"{str(value)}\n", 'value'))
                
                content_list.append(("\n", None))
            
            content_list.append(("-"*60 + "\n\n", None))

        return content_list

    def update_story_text(self, content_list):
        self.story_text.config(state=tk.NORMAL)
        self.story_text.delete('1.0', tk.END)
        for content, tag in content_list:
            if tag:
                self.story_text.insert(tk.END, content, tag)
            else:
                self.story_text.insert(tk.END, content)
        self.story_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = StoryViewerApp(root)
    root.mainloop()