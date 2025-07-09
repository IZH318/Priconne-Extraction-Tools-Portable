import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import os
import re
import threading
import queue
import multiprocessing

# --------------------------------------------------------------------------
# 스크립트 파싱 로직
# --------------------------------------------------------------------------
def parse_script_to_readable_flow(script_text, lang_data):
    lines = script_text.strip().split('\n')
    output = ""
    scene_count = 0
    action_buffer = []

    def get_line_label(line):
        if re.match(r'^(chara_full|fade|in_|out_|change|change_window)', line): return f"[{lang_data['parser_char']}]"
        if re.match(r'^(bgm|amb|se|vo_effect)', line): return f"[{lang_data['parser_sound']}]"
        if re.match(r'^(background|transition|white_|black_)', line): return f"[{lang_data['parser_scene_eff']}]"
        if re.match(r'^(window_visible|bright_change|effect)', line): return f"[{lang_data['parser_ui']}]"
        return f"[{lang_data['parser_etc']}]"

    def flush_action_buffer():
        nonlocal output, action_buffer
        if not action_buffer:
            return
        output += f"\n--- [{lang_data['parser_directing']}] ---\n"
        for action in action_buffer:
            output += f"  {get_line_label(action):<10} {action}\n"
        output += "-----------------\n"
        action_buffer = []

    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith(('print', 'choice', 'tag', 'goto', 'background')):
            flush_action_buffer()
        if line.startswith('title'):
            output += f"■ {lang_data['parser_title']}: {line.split(' ', 1)[1].strip().replace('\"', '')}\n\n"
        elif line.startswith('outline'):
            output += f"■ {lang_data['parser_outline']}:\n{line.split(' ', 1)[1].strip().replace('\"', '')}\n"
        elif line.startswith('background'):
            scene_count += 1
            output += f"\n\n\n{'='*20} {lang_data['parser_scene']} {scene_count} {'='*20}\n"
            output += f"{get_line_label(line):<10} {line}\n"
        elif line.startswith('print'):
            match = re.match(r'print "([^"]*)" "(.*)"', line)
            if match:
                char_name, content_with_end_quote = match.groups()
                content = content_with_end_quote.rstrip('"')
                text = re.sub(r'<[^>]+>', '', content).replace('\\n', ' ')
                output += f"\n▶─── {char_name} ───\n"
                output += f"  \"{text}\"\n"
                tags = re.findall(r'<([^>]+)>', content)
                if tags:
                    output += f"  - {lang_data['parser_details']}:\n"
                    for tag in tags:
                        output += f"      - {tag}\n"
                output += "───────────────\n"
        elif line.startswith('choice'):
            parts = line.split('"')
            output += f"\n▶─── [{lang_data['parser_choice']}] ───\n"
            output += f"  \"{parts[1]}\" (→ tag {parts[2].strip()})\n"
            output += "───────────────\n"
        elif line.startswith('tag'):
            output += f"\n--- [{lang_data['parser_branch']}: tag {line.split(' ')[1]}] ---\n"
        elif line.startswith('goto'):
            output += f"\n→ (tag {line.split(' ')[1]} {lang_data['parser_merge']})\n"
        elif line != "end":
            action_buffer.append(line)
    flush_action_buffer()
    return output

def worker_process_file(args):
    """(별도 프로세스) 파일을 읽고 지정된 언어로 변환합니다."""
    filepath, lang_data = args
    file_content = None
    encodings_to_try = ['utf-8', 'cp949', 'euc-kr']
    for encoding in encodings_to_try:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                file_content = f.read()
            break
        except Exception:
            continue
    
    if file_content:
        converted_text = parse_script_to_readable_flow(file_content, lang_data)
        original_basename = os.path.basename(filepath)
        new_filename = f"{os.path.splitext(original_basename)[0]}_Export.txt"
        return (new_filename, converted_text)
    return None

# --------------------------------------------------------------------------
# GUI 애플리케이션 클래스
# --------------------------------------------------------------------------
class ScriptAnalyzerApp:
    def __init__(self, root):
        self.root = root
        
        self.LANGUAGES = {
            'ko': {
                'title': "Priconne Storydata Explorer", 'file_list': "파일 목록", 'tab_original': "원본 스크립트", 'tab_converted': "변환 결과",
                'progress_idle': "대기 중...", 'menu_main': "메뉴(Menu)", 'menu_file_open': "파일 열기...", 'menu_folder_open': "폴더 열기...",
                'menu_save': "변환 결과 저장...", 'menu_lang': "언어(Language)", 'menu_exit': "종료", 'save_option_title': "저장 옵션",
                'save_option_msg': "현재 선택된 파일만 저장하시겠습니까?\n\n- 예(Y): 현재 선택한 파일 1개만 저장\n- 아니요(N): 목록의 모든 파일 저장",
                'open_folder_title': "스크립트가 포함된 상위 폴더를 선택하세요", 'open_file_title': "스크립트 파일 선택",
                'save_folder_title': "결과를 저장할 폴더를 선택하세요", 'search_start': "검색 시작...", 'search_progress': "검색 중... ({}/{})",
                'search_done': "완료! ({}개 파일)", 'search_none': "해당 패턴의 파일을 찾을 수 없습니다.", 'save_prep': "변환 작업 준비 중... (총 {}개)",
                'save_progress': "저장 중... ({}/{})", 'save_done': "총 {}개의 파일이 저장되었습니다.", 'save_complete': "저장 완료!",
                'error_file_read': "{} 파일을 읽을 수 없습니다.", 'error_no_selection': "선택된 파일이 없습니다.", 'error_no_files_to_save': "저장할 파일이 목록에 없습니다.",
                'parser_title': "제목", 'parser_outline': "줄거리", 'parser_scene': "장면", 'parser_directing': "연출", 'parser_details': "연출 상세",
                'parser_choice': "플레이어 선택지", 'parser_branch': "분기 시작", 'parser_merge': "으로 합류", 'parser_char': "캐릭터",
                'parser_sound': "사운드", 'parser_scene_eff': "장면", 'parser_ui': "효과/UI", 'parser_etc': "기타"
            },
            'en': {
                'title': "Priconne Storydata Explorer", 'file_list': "File List", 'tab_original': "Original Script", 'tab_converted': "Converted Result",
                'progress_idle': "Idle...", 'menu_main': "Menu", 'menu_file_open': "Open File...", 'menu_folder_open': "Open Folder...",
                'menu_save': "Save Converted Result...", 'menu_lang': "Language", 'menu_exit': "Exit", 'save_option_title': "Save Option",
                'save_option_msg': "Save only the currently selected file?\n\n- Yes: Save only the selected file.\n- No: Save all files in the list.",
                'open_folder_title': "Select the parent folder containing scripts", 'open_file_title': "Select a script file",
                'save_folder_title': "Select a folder to save results", 'search_start': "Searching...", 'search_progress': "Searching... ({}/{})",
                'search_done': "Complete! ({} files found)", 'search_none': "Could not find files with the specified pattern.", 'save_prep': "Preparing to convert... (Total {} files)",
                'save_progress': "Saving... ({}/{})", 'save_done': "{} files have been saved.", 'save_complete': "Save Complete!",
                'error_file_read': "Could not read file: {}", 'error_no_selection': "No file selected.", 'error_no_files_to_save': "There are no files in the list to save.",
                'parser_title': "Title", 'parser_outline': "Outline", 'parser_scene': "Scene", 'parser_directing': "Directing", 'parser_details': "Details",
                'parser_choice': "Player Choice", 'parser_branch': "Branch Start", 'parser_merge': "Merge to", 'parser_char': "Character",
                'parser_sound': "Sound", 'parser_scene_eff': "Scene", 'parser_ui': "Effect/UI", 'parser_etc': "Etc"
            },
            'ja': {
                'title': "Priconne Storydata Explorer", 'file_list': "ファイルリスト", 'tab_original': "元のスクリプト", 'tab_converted': "変換結果",
                'progress_idle': "待機中...", 'menu_main': "メニュー", 'menu_file_open': "ファイルを開く...", 'menu_folder_open': "フォルダを開く...",
                'menu_save': "変換結果を保存...", 'menu_lang': "言語", 'menu_exit': "終了", 'save_option_title': "保存オプション",
                'save_option_msg': "現在選択されているファイルのみを保存しますか？\n\n- はい(Y): 選択したファイル1つだけを保存\n- いいえ(N): リスト内のすべてのファイルを保存",
                'open_folder_title': "スクリプトが含まれている親フォルダを選択してください", 'open_file_title': "スクリプトファイルを選択",
                'save_folder_title': "結果を保存するフォルダを選択してください", 'search_start': "検索開始...", 'search_progress': "検索中... ({}/{})",
                'search_done': "完了！ ({}個のファイル)", 'search_none': "指定されたパターンのファイルが見つかりませんでした。", 'save_prep': "変換準備中... (合計 {}個)",
                'save_progress': "保存中... ({}/{})", 'save_done': "{}個のファイルが保存されました。", 'save_complete': "保存完了！",
                'error_file_read': "{} ファイルを読み込めません。", 'error_no_selection': "ファイルが選択されていません。", 'error_no_files_to_save': "保存するファイルがリストにありません。",
                'parser_title': "タイトル", 'parser_outline': "概要", 'parser_scene': "シーン", 'parser_directing': "演出", 'parser_details': "演出詳細",
                'parser_choice': "プレイヤー選択肢", 'parser_branch': "分岐開始", 'parser_merge': "へ合流", 'parser_char': "キャラクター",
                'parser_sound': "サウンド", 'parser_scene_eff': "シーン", 'parser_ui': "効果/UI", 'parser_etc': "その他"
            }
        }
        self.lang = 'ko'
        
        window_width = 800
        window_height = 600
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        self.file_list_map = {}
        self.data_queue = queue.Queue()

        self.create_widgets()
        self.change_language(self.lang)

    def create_widgets(self):
        self.create_menu()
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        list_frame = tk.Frame(main_pane, bd=2, relief=tk.SUNKEN)
        main_pane.add(list_frame, width=240)
        self.list_label = tk.Label(list_frame)
        self.list_label.pack(pady=5)
        self.listbox = tk.Listbox(list_frame, font=("Arial", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.listbox.bind('<<ListboxSelect>>', self.on_file_select)
        self.notebook = ttk.Notebook(main_pane)
        main_pane.add(self.notebook)
        self.tab1 = tk.Frame(self.notebook)
        self.notebook.add(self.tab1)
        self.input_text = scrolledtext.ScrolledText(self.tab1, wrap=tk.WORD, font=("Consolas", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tab2 = tk.Frame(self.notebook)
        self.notebook.add(self.tab2)
        self.output_text = scrolledtext.ScrolledText(self.tab2, wrap=tk.WORD, font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        self.style = ttk.Style(self.root)
        self.style.layout('text.Horizontal.TProgressbar', [('Horizontal.Progressbar.trough', {'children': [('Horizontal.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})], 'sticky': 'nswe'}), ('Horizontal.Progressbar.label', {'sticky': ''})])
        self.style.configure('text.Horizontal.TProgressbar', anchor='center')
        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100, style='text.Horizontal.TProgressbar')
        self.progressbar.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def create_menu(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.lang_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(menu=self.file_menu)
        self.menubar.add_cascade(menu=self.lang_menu)
        self.file_menu.add_command(command=self.open_file)
        self.file_menu.add_command(command=self.open_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(command=self.save_results)
        self.file_menu.add_separator()
        self.file_menu.add_command(command=self.root.destroy)
        self.lang_menu.add_command(label="한국어", command=lambda: self.change_language('ko'))
        self.lang_menu.add_command(label="English", command=lambda: self.change_language('en'))
        self.lang_menu.add_command(label="日本語", command=lambda: self.change_language('ja'))

    def change_language(self, lang_code):
        self.lang = lang_code
        lang_data = self.LANGUAGES[self.lang]
        self.root.title(lang_data['title'])
        self.list_label.config(text=lang_data['file_list'])
        self.notebook.tab(self.tab1, text=lang_data['tab_original'])
        self.notebook.tab(self.tab2, text=lang_data['tab_converted'])
        self.menubar.entryconfig(1, label=lang_data['menu_main'])
        self.menubar.entryconfig(2, label=lang_data['menu_lang'])
        self.file_menu.entryconfig(0, label=lang_data['menu_file_open'])
        self.file_menu.entryconfig(1, label=lang_data['menu_folder_open'])
        self.file_menu.entryconfig(3, label=lang_data['menu_save'])
        self.file_menu.entryconfig(5, label=lang_data['menu_exit'])
        self.update_progressbar_text(lang_data['progress_idle'])
        # 언어 변경 시, 현재 열려있는 파일의 변환 결과도 갱신
        self.update_conversion()

    def update_conversion(self):
        script_content = self.input_text.get('1.0', tk.END)
        if not script_content.strip():
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete('1.0', tk.END)
            self.output_text.config(state=tk.DISABLED)
            return
        
        # 현재 언어 데이터를 파서에 전달
        lang_data = self.LANGUAGES[self.lang]
        flow_text_result = parse_script_to_readable_flow(script_content, lang_data)
        
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', flow_text_result)
        self.output_text.config(state=tk.DISABLED)

    def save_results_multiprocess(self, filepaths, save_folder):
        try:
            lang_data = self.LANGUAGES[self.lang]
            # 각 프로세스에 언어 데이터도 함께 전달
            tasks = [(fp, lang_data) for fp in filepaths]
            
            pool_size = min(multiprocessing.cpu_count(), 4)
            with multiprocessing.Pool(processes=pool_size) as pool:
                # 여러 인자를 전달하기 위해 starmap_async 대신 map_async 사용
                async_result = pool.map_async(worker_process_file, tasks)
                results = async_result.get()

            self.data_queue.put(('save_start', len(results)))
            total_files = len(results)
            for i, result in enumerate(filter(None, results)):
                new_filename, converted_text = result
                save_path = os.path.join(save_folder, new_filename)
                try:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(converted_text)
                except Exception as e:
                    self.data_queue.put(('error', f"{new_filename} saving error:\n{e}"))
                progress = ((i + 1) / total_files) * 100
                lang_data_progress = self.LANGUAGES[self.lang]
                self.data_queue.put(('progress', (progress, lang_data_progress['save_progress'].format(i+1, total_files))))
            self.data_queue.put(('done', total_files))
        except Exception as e:
            self.data_queue.put(('error', f"Multiprocessing error:\n{e}"))

    def open_file(self, *args): # 이벤트 핸들러는 event 인자를 받을 수 있으므로 *args 추가
        filepath = filedialog.askopenfilename(
            title=self.LANGUAGES[self.lang]['open_file_title'],
            filetypes=(("BIN", "*.bin"), ("All files", "*.*"))
        )
        if not filepath: return
        filename = os.path.basename(filepath)
        self.listbox.delete(0, tk.END)
        self.file_list_map.clear()
        self.listbox.insert(tk.END, filename)
        self.file_list_map[filename] = filepath
        self.listbox.selection_set(0)
        self.on_file_select(None)
        self.update_progressbar_text(f"'{filename}' loaded.")

    def open_folder(self, *args):
        folder_path = filedialog.askdirectory(title=self.LANGUAGES[self.lang]['open_folder_title'])
        if not folder_path: return
        self.listbox.delete(0, tk.END)
        self.file_list_map.clear()
        self.progressbar.config(mode='determinate')
        self.progress_var.set(0)
        self.update_progressbar_text(self.LANGUAGES[self.lang]['search_start'])
        threading.Thread(target=self.search_files_thread, args=(folder_path,), daemon=True).start()
        self.process_queue('search')

    def save_results(self, *args):
        if not self.file_list_map:
            messagebox.showwarning("Error", self.LANGUAGES[self.lang]['error_no_files_to_save'])
            return
        choice = messagebox.askyesnocancel(self.LANGUAGES[self.lang]['save_option_title'], self.LANGUAGES[self.lang]['save_option_msg'])
        if choice is None: return
        
        files_to_save_names = []
        if choice:
            selected_indices = self.listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("Error", self.LANGUAGES[self.lang]['error_no_selection'])
                return
            files_to_save_names.append(self.listbox.get(selected_indices[0]))
        else:
            files_to_save_names = list(self.file_list_map.keys())
            
        save_folder = filedialog.askdirectory(title=self.LANGUAGES[self.lang]['save_folder_title'])
        if not save_folder: return
        
        filepaths_to_process = [self.file_list_map[name] for name in files_to_save_names]
        
        self.progress_var.set(0)
        self.progressbar.config(mode='indeterminate')
        self.update_progressbar_text(self.LANGUAGES[self.lang]['save_prep'].format(len(filepaths_to_process)))
        self.root.update_idletasks()
        threading.Thread(target=self.save_results_multiprocess, args=(filepaths_to_process, save_folder), daemon=True).start()
        self.process_queue('save')

    def search_files_thread(self, folder_path):
        parent_folder_pattern = re.compile(r'storydata_storydata_(\d{7})')
        try:
            dir_list = [d for _, dirs, _ in os.walk(folder_path) for d in dirs]
            total_dirs = len(dir_list)
        except Exception:
            total_dirs = 1
        processed_dirs = 0
        lang_data_progress = self.LANGUAGES[self.lang]
        for root_dir, dirs, _ in os.walk(folder_path):
            for d in dirs:
                processed_dirs += 1
                match = parent_folder_pattern.match(d)
                if match:
                    story_id = match.group(1)
                    target_filename = f"storydata_{story_id}.bin"
                    target_filepath = os.path.join(root_dir, d, target_filename)
                    if os.path.exists(target_filepath):
                        self.data_queue.put(('file_found', (d, target_filepath)))
                progress = (processed_dirs / total_dirs) * 100 if total_dirs > 0 else 0
                self.data_queue.put(('progress', (progress, lang_data_progress['search_progress'].format(processed_dirs, total_dirs))))
        self.data_queue.put(('search_done', None))
    
    def process_queue(self, task_type):
        try:
            while True:
                msg_type, data = self.data_queue.get_nowait()
                if msg_type == 'progress':
                    progress, text = data
                    self.progress_var.set(progress)
                    self.update_progressbar_text(text)
                
                if task_type == 'search':
                    if msg_type == 'file_found':
                        display_name, fullpath = data
                        self.file_list_map[display_name] = fullpath
                    elif msg_type == 'search_done':
                        self.finalize_loading()
                        return
                
                elif task_type == 'save':
                    if msg_type == 'save_start':
                        self.progressbar.config(mode='determinate')
                        self.update_progressbar_text(self.LANGUAGES[self.lang]['save_prep'].format(data))
                    elif msg_type == 'done':
                        messagebox.showinfo("Complete", self.LANGUAGES[self.lang]['save_done'].format(data))
                        self.update_progressbar_text(self.LANGUAGES[self.lang]['save_complete'])
                        self.root.after(2000, lambda: self.update_progressbar_text(self.LANGUAGES[self.lang]['progress_idle']))
                        return
                    elif msg_type == 'error':
                        messagebox.showerror("Error", data)
                        self.update_progressbar_text("Error")
                        return
        except queue.Empty:
            self.root.after(100, lambda: self.process_queue(task_type))

    def finalize_loading(self):
        lang_data = self.LANGUAGES[self.lang]
        if not self.file_list_map:
            messagebox.showinfo("Result", lang_data['search_none'])
            self.update_progressbar_text("No files")
        else:
            sorted_files = sorted(self.file_list_map.keys())
            for display_name in sorted_files:
                self.listbox.insert(tk.END, display_name)
            num_files = len(self.file_list_map)
            self.update_progressbar_text(lang_data['search_done'].format(num_files))
        self.progress_var.set(100)
        self.root.after(2000, lambda: self.update_progressbar_text(lang_data['progress_idle']))
        
    def update_progressbar_text(self, text):
        self.style.configure('text.Horizontal.TProgressbar', text=text)

    def on_file_select(self, event):
        selected_indices = self.listbox.curselection()
        if not selected_indices: return
        selected_display_name = self.listbox.get(selected_indices[0])
        filepath = self.file_list_map.get(selected_display_name)
        if not filepath: return
        encodings_to_try = ['utf-8', 'cp949', 'euc-kr']
        file_content = None
        for encoding in encodings_to_try:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    file_content = f.read()
                break
            except Exception:
                continue
        if file_content is not None:
            self.input_text.delete('1.0', tk.END)
            self.input_text.insert('1.0', file_content)
            self.update_conversion()
        else:
            messagebox.showerror("Error", self.LANGUAGES[self.lang]['error_file_read'].format(selected_display_name))
            
if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = ScriptAnalyzerApp(root)
    root.mainloop()
