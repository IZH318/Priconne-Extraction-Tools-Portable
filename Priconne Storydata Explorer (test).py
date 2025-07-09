import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import os
import re

# --------------------------------------------------------------------------
# 스크립트 파싱 로직 (이전과 동일)
# --------------------------------------------------------------------------
def parse_script_to_readable_flow(script_text, show_original_code=False):
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
                if show_original_code:
                    output += f"  - 원본 코드: {line}\n"
                output += "───────────────\n"
        elif line.startswith('choice'):
            parts = line.split('"')
            output += f"\n▶─── [플레이어 선택지] ───\n"
            output += f"  \"{parts[1]}\" (→ tag {parts[2].strip()})\n"
            if show_original_code:
                output += f"  - 원본 코드: {line}\n"
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
        self.root.title("게임 스크립트 분석기 v3.1 (폴더 구조 지원)")
        self.root.geometry("800x600")
        self.file_list_map = {}

        main_pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        list_frame = tk.Frame(main_pane, bd=2, relief=tk.SUNKEN)
        list_frame.pack(fill=tk.BOTH, expand=True)
        main_pane.add(list_frame, width=240)

        tk.Label(list_frame, text="파일 목록").pack(pady=5)
        self.listbox = tk.Listbox(list_frame, font=("Arial", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        scrollbar.config(command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.bind('<<ListboxSelect>>', self.on_file_select)

        self.notebook = ttk.Notebook(main_pane)
        self.notebook.pack(fill=tk.BOTH, expand=True)
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
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        
        button_frame = tk.Frame(bottom_frame)
        button_frame.pack(side=tk.LEFT)
        tk.Button(button_frame, text="폴더 열기", command=self.open_folder).pack(side=tk.LEFT, padx=5)
        
        option_frame = tk.Frame(bottom_frame)
        option_frame.pack(side=tk.RIGHT)
        self.show_original_var = tk.BooleanVar(value=False)
        tk.Checkbutton(option_frame, text="원본 코드 표시", variable=self.show_original_var, command=self.update_conversion).pack(side=tk.LEFT, padx=10)

    def open_folder(self):
        """
        사용자가 선택한 폴더와 그 하위에서 특정 구조를 가진 스크립트 파일을 찾습니다.
        구조: storydata_storydata_#######/storydata_#######.bin
        """
        folder_path = filedialog.askdirectory(title="스크립트가 포함된 상위 폴더를 선택하세요")
        if not folder_path: return

        self.listbox.delete(0, tk.END)
        self.file_list_map.clear()
        
        # 1. 상위 폴더 이름 패턴: storydata_storydata_숫자7자리
        parent_folder_pattern = re.compile(r'storydata_storydata_(\d{7})')
        
        found_files = []
        for root_dir, dirs, _ in os.walk(folder_path):
            for d in dirs:
                match = parent_folder_pattern.match(d)
                if match:
                    # 2. 하위 파일 이름 패턴: storydata_숫자7자리.bin
                    story_id = match.group(1) # 폴더 이름에서 숫자 7자리를 추출
                    target_filename = f"storydata_{story_id}.bin"
                    target_filepath = os.path.join(root_dir, d, target_filename)
                    
                    # 3. 실제 파일이 존재하는지 확인
                    if os.path.exists(target_filepath):
                        # 리스트에 표시할 이름은 상위 폴더 이름으로 함 (더 구별하기 쉬움)
                        display_name = d 
                        found_files.append((display_name, target_filepath))
        
        if not found_files:
            messagebox.showinfo("결과", "해당 패턴의 폴더/파일 구조를 찾을 수 없습니다.")
            return

        # 찾은 파일들을 이름순으로 정렬
        found_files.sort()
        for display_name, fullpath in found_files:
            self.listbox.insert(tk.END, display_name)
            self.file_list_map[display_name] = fullpath

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

        show_original = self.show_original_var.get()
        flow_text_result = parse_script_to_readable_flow(script_content, show_original_code=show_original)
        
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', flow_text_result)
        self.output_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = ScriptAnalyzerApp(root)
    root.mainloop()
