import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import os
import re
import threading
import queue

# --------------------------------------------------------------------------
# 스크립트 파싱 로직 (이전과 동일)
# --------------------------------------------------------------------------
def parse_script_to_readable_flow(script_text):
    lines = script_text.strip().split('\n')
    output = ""
    scene_count = 0
    action_buffer = []

    def get_line_label(line):
        if re.match(r'^(chara_full|fade|in_|out_|change|change_window)', line): return "[캐릭터]"
        if re.match(r'^(bgm|amb|se|vo_effect)', line): return "[사운드]"
        if re.match(r'^(background|transition|white_|black_)', line): return "[장면]"
        if re.match(r'^(window_visible|bright_change|effect)', line): return "[효과/UI]"
        return "[기타]"

    def flush_action_buffer():
        nonlocal output, action_buffer
        if not action_buffer:
            return
        output += "\n--- [연출] ---\n"
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
            output += f"■ 제목: {line.split(' ', 1)[1].strip().replace('\"', '')}\n\n"
        elif line.startswith('outline'):
            output += f"■ 줄거리:\n{line.split(' ', 1)[1].strip().replace('\"', '')}\n"
        elif line.startswith('background'):
            scene_count += 1
            output += f"\n\n\n{'='*20} 장면 {scene_count} {'='*20}\n"
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
                    output += f"  - 연출 상세:\n"
                    for tag in tags:
                        output += f"      - {tag}\n"
                output += "───────────────\n"
        elif line.startswith('choice'):
            parts = line.split('"')
            output += f"\n▶─── [플레이어 선택지] ───\n"
            output += f"  \"{parts[1]}\" (→ tag {parts[2].strip()})\n"
            output += "───────────────\n"
        elif line.startswith('tag'):
            output += f"\n--- [분기 시작: tag {line.split(' ')[1]}] ---\n"
        elif line.startswith('goto'):
            output += f"\n→ (tag {line.split(' ')[1]} 으로 합류)\n"
        elif line != "end":
            action_buffer.append(line)
    flush_action_buffer()
    return output

# --------------------------------------------------------------------------
# GUI 애플리케이션 클래스
# --------------------------------------------------------------------------
class ScriptAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("게임 스크립트 분석기 v6.1 (Final)")
        
        window_width = 800
        window_height = 600
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')

        self.file_list_map = {}
        self.file_queue = queue.Queue()

        self.create_menu()

        main_pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        list_frame = tk.Frame(main_pane, bd=2, relief=tk.SUNKEN)
        main_pane.add(list_frame, width=240)

        tk.Label(list_frame, text="파일 목록").pack(pady=5)
        self.listbox = tk.Listbox(list_frame, font=("Arial", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.listbox.bind('<<ListboxSelect>>', self.on_file_select)

        self.notebook = ttk.Notebook(main_pane)
        main_pane.add(self.notebook)

        tab1 = tk.Frame(self.notebook)
        self.notebook.add(tab1, text='원본 스크립트')
        self.input_text = scrolledtext.ScrolledText(tab1, wrap=tk.WORD, font=("Consolas", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tab2 = tk.Frame(self.notebook)
        self.notebook.add(tab2, text='변환 결과')
        self.output_text = scrolledtext.ScrolledText(tab2, wrap=tk.WORD, font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.output_text.config(state=tk.DISABLED)

        bottom_frame = tk.Frame(root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        
        self.style = ttk.Style(root)
        self.style.layout('text.Horizontal.TProgressbar',
                         [('Horizontal.Progressbar.trough',
                           {'children': [('Horizontal.Progressbar.pbar',
                                          {'side': 'left', 'sticky': 'ns'})],
                            'sticky': 'nswe'}),
                          ('Horizontal.Progressbar.label',
                           {'sticky': ''})])
        self.style.configure('text.Horizontal.TProgressbar', text='대기 중...', anchor='center')

        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100, style='text.Horizontal.TProgressbar')
        self.progressbar.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="메뉴(Menu)", menu=file_menu)
        file_menu.add_command(label="파일 열기...", command=self.open_file)
        file_menu.add_command(label="폴더 열기...", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="변환 결과 저장...", command=self.save_results)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.root.destroy)

    def open_file(self):
        filepath = filedialog.askopenfilename(
            title="스크립트 파일 선택",
            filetypes=(("BIN 파일", "*.bin"), ("모든 파일", "*.*"))
        )
        if not filepath: return
        filename = os.path.basename(filepath)
        self.listbox.delete(0, tk.END)
        self.file_list_map.clear()
        self.listbox.insert(tk.END, filename)
        self.file_list_map[filename] = filepath
        self.listbox.selection_set(0)
        self.on_file_select(None)
        self.update_progressbar_text(f"'{filename}' 파일 로드 완료")

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="스크립트가 포함된 상위 폴더를 선택하세요")
        if not folder_path: return
        self.listbox.delete(0, tk.END)
        self.file_list_map.clear()
        self.progressbar.config(mode='determinate')
        self.progress_var.set(0)
        self.update_progressbar_text("검색 시작...")
        threading.Thread(target=self.search_files_thread, args=(folder_path,), daemon=True).start()
        self.process_queue()
        
    def save_results(self):
        if not self.file_list_map:
            messagebox.showwarning("저장 오류", "저장할 파일이 목록에 없습니다.")
            return
        choice = messagebox.askyesnocancel("저장 옵션",
                                           "현재 선택된 파일만 저장하시겠습니까?\n\n"
                                           "- 예(Y): 현재 선택한 파일 1개만 저장\n"
                                           "- 아니요(N): 목록의 모든 파일 저장")
        if choice is None: return
        
        files_to_save_names = []
        if choice:
            selected_indices = self.listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("저장 오류", "선택된 파일이 없습니다.")
                return
            files_to_save_names.append(self.listbox.get(selected_indices[0]))
        else:
            files_to_save_names = list(self.file_list_map.keys())
            
        save_folder = filedialog.askdirectory(title="결과를 저장할 폴더를 선택하세요")
        if not save_folder: return
        
        self.progress_var.set(0)
        self.update_progressbar_text("저장 준비 중...")
        # [수정된 부분] 저장 작업을 별도 스레드에서 실행
        threading.Thread(target=self.save_results_thread, args=(files_to_save_names, save_folder), daemon=True).start()
        self.process_queue()

    def save_results_thread(self, files_to_save_names, save_folder):
        """(백그라운드 스레드) 파일을 읽고, 변환하고, 저장하는 작업"""
        total_files = len(files_to_save_names)
        for i, display_name in enumerate(files_to_save_names):
            filepath = self.file_list_map[display_name]
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
                converted_text = parse_script_to_readable_flow(file_content)
                original_basename = os.path.basename(filepath)
                new_filename = f"{os.path.splitext(original_basename)[0]}_Export.txt"
                save_path = os.path.join(save_folder, new_filename)
                
                try:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(converted_text)
                except Exception as e:
                    self.file_queue.put(('save_error', f"{new_filename} 저장 중 오류:\n{e}"))
                    return # 오류 발생 시 스레드 중단
            
            progress = ((i + 1) / total_files) * 100
            self.file_queue.put(('progress', (progress, f"저장 중... ({i+1}/{total_files})")))

        self.file_queue.put(('save_done', total_files))

    def search_files_thread(self, folder_path):
        parent_folder_pattern = re.compile(r'storydata_storydata_(\d{7})')
        try: total_dirs = sum(1 for _, dirs, _ in os.walk(folder_path) for _ in dirs)
        except Exception: total_dirs = 1
        processed_dirs = 0
        for root_dir, dirs, _ in os.walk(folder_path):
            for d in dirs:
                processed_dirs += 1
                match = parent_folder_pattern.match(d)
                if match:
                    story_id = match.group(1)
                    target_filename = f"storydata_{story_id}.bin"
                    target_filepath = os.path.join(root_dir, d, target_filename)
                    if os.path.exists(target_filepath):
                        self.file_queue.put(('file', (d, target_filepath)))
                progress = (processed_dirs / total_dirs) * 100 if total_dirs > 0 else 0
                self.file_queue.put(('progress', (progress, f"검색 중... ({processed_dirs}/{total_dirs})")))
        self.file_queue.put(('done', None))

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.file_queue.get_nowait()
                if msg_type == 'file':
                    display_name, fullpath = data
                    self.file_list_map[display_name] = fullpath
                elif msg_type == 'progress':
                    progress, text = data
                    self.progress_var.set(progress)
                    self.update_progressbar_text(text)
                elif msg_type == 'done':
                    self.finalize_loading()
                    return
                # [수정된 부분] 저장 관련 메시지 처리
                elif msg_type == 'save_done':
                    messagebox.showinfo("저장 완료", f"총 {data}개의 파일이 저장되었습니다.")
                    self.update_progressbar_text("저장 완료!")
                    self.root.after(2000, lambda: self.update_progressbar_text("대기 중..."))
                    return
                elif msg_type == 'save_error':
                    messagebox.showerror("저장 실패", data)
                    self.update_progressbar_text("저장 중단")
                    return
        except queue.Empty:
            self.root.after(100, self.process_queue)
            
    def finalize_loading(self):
        if not self.file_list_map:
            messagebox.showinfo("결과", "해당 패턴의 폴더/파일 구조를 찾을 수 없습니다.")
            self.update_progressbar_text("파일 없음")
        else:
            sorted_files = sorted(self.file_list_map.keys())
            for display_name in sorted_files:
                self.listbox.insert(tk.END, display_name)
            num_files = len(self.file_list_map)
            self.update_progressbar_text(f"완료! ({num_files}개 파일)")
        self.progress_var.set(100)
        self.root.after(2000, lambda: self.update_progressbar_text("대기 중..."))
        
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
            messagebox.showerror("파일 읽기 오류", f"{selected_display_name} 파일을 읽을 수 없습니다.")
            
    def update_conversion(self):
        script_content = self.input_text.get('1.0', tk.END)
        if not script_content.strip():
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete('1.0', tk.END)
            self.output_text.config(state=tk.DISABLED)
            return
        flow_text_result = parse_script_to_readable_flow(script_content)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', flow_text_result)
        self.output_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScriptAnalyzerApp(root)
    root.mainloop()
