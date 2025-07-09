import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import re

# --------------------------------------------------------------------------
# 스크립트 파싱 및 변환 로직 (장면 간 여백 추가)
# --------------------------------------------------------------------------
def parse_script_to_readable_flow(script_text, show_original_code=False):
    """
    대사 흐름을 중심으로 연출을 재배치하여 가독성을 극대화합니다.
    (로직 안정화 버전)
    """
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
            # [수정된 부분] 장면 전환 제목 앞에 빈 줄 세 개 추가
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
# GUI 애플리케이션 클래스 (이하 코드는 수정할 필요 없음)
# --------------------------------------------------------------------------
class ScriptParserApp:
    def __init__(self, root):
        self.root = root
        self.root.title("게임 스크립트 흐름 분석기")
        self.root.geometry("1200x800")

        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(left_frame, text="원본 스크립트").pack(pady=5)
        self.input_text = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.input_text.pack(fill=tk.BOTH, expand=True)

        right_frame = tk.Frame(main_frame, bd=2, relief=tk.SUNKEN)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(right_frame, text="변환 결과").pack(pady=5)
        self.output_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.output_text.config(state=tk.DISABLED)

        bottom_frame = tk.Frame(root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        
        button_frame = tk.Frame(bottom_frame)
        button_frame.pack(side=tk.LEFT)
        
        tk.Button(button_frame, text="파일 열기", command=self.open_file).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="변환하기", command=self.convert_script, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="결과 복사", command=self.copy_to_clipboard).pack(side=tk.LEFT, padx=5)
        
        option_frame = tk.Frame(bottom_frame)
        option_frame.pack(side=tk.RIGHT)
        
        self.show_original_var = tk.BooleanVar(value=False)
        tk.Checkbutton(option_frame, text="원본 코드 표시", variable=self.show_original_var).pack(side=tk.LEFT, padx=10)
        
        tk.Button(option_frame, text="초기화", command=self.clear_all).pack(side=tk.LEFT, padx=5)

    def open_file(self):
        filepath = filedialog.askopenfilename(filetypes=(("모든 파일", "*.*"),))
        if not filepath: return
        encodings_to_try = ['utf-8', 'cp949', 'euc-kr']
        file_content = None
        for encoding in encodings_to_try:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    file_content = f.read()
                print(f"파일을 '{encoding}' 인코딩으로 읽었습니다.")
                break 
            except (UnicodeDecodeError, IOError): continue
        if file_content is not None:
            self.input_text.delete('1.0', tk.END)
            self.input_text.insert('1.0', file_content)
        else:
            messagebox.showerror("파일 읽기 오류", "파일을 지원되는 인코딩으로 읽을 수 없습니다.")

    def convert_script(self):
        script_content = self.input_text.get('1.0', tk.END)
        if not script_content.strip():
            messagebox.showwarning("입력 오류", "변환할 스크립트 내용이 없습니다.")
            return
        show_original = self.show_original_var.get()
        flow_text_result = parse_script_to_readable_flow(script_content, show_original_code=show_original)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', flow_text_result)
        self.output_text.config(state=tk.DISABLED)

    def copy_to_clipboard(self):
        result = self.output_text.get('1.0', tk.END)
        if result.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
            messagebox.showinfo("복사 완료", "변환 결과가 클립보드에 복사되었습니다.")
        else:
            messagebox.showwarning("복사 오류", "복사할 내용이 없습니다.")
            
    def clear_all(self):
        self.input_text.delete('1.0', tk.END)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete('1.0', tk.END)
        self.output_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScriptParserApp(root)
    root.mainloop()
