import tkinter as tk
from tkinter import filedialog, messagebox
import UnityPy
import os
import threading
from PIL import Image
import json
import re

# UnityPy가 파일에서 버전을 감지하지 못할 경우를 대비하여 대체 버전을 설정합니다.
# 사용자가 요청한 '2021.3.20f1' 버전으로 하드코딩합니다.
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"

# 직접적인 파일로 변환이 용이한, 특별 처리할 에셋 타입 목록입니다.
# 각 타입에 맞는 폴더 이름을 지정합니다.
SPECIAL_TYPES = {
    "Texture2D": "Textures",
    "Sprite": "Sprites",
    "TextAsset": "TextAssets",
    "AudioClip": "Audio",
    "Mesh": "Meshes",
    "Shader": "Shaders",
    "Font": "Fonts",
    "VideoClip": "Videos",
    "MovieTexture": "Videos",
}

class AssetExtractorApp:
    """
    Tkinter를 사용하여 Unity 에셋 추출을 위한 GUI 애플리케이션 클래스입니다.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Unity 에셋 추출기 (AssetStudio 호환)")
        self.root.geometry("500x250")
        self.root.configure(bg="#f0f0f0")
        self.setup_ui()

    def setup_ui(self):
        """GUI의 레이아웃과 위젯을 설정합니다."""
        main_frame = tk.Frame(self.root, padx=20, pady=20, bg="#f0f0f0")
        main_frame.pack(expand=True, fill=tk.BOTH)

        self.select_button = tk.Button(
            main_frame, text="Unity 파일 선택", command=self.browse_file,
            font=("Helvetica", 12, "bold"), bg="#4a90e2", fg="white",
            relief=tk.FLAT, padx=10, pady=10
        )
        self.select_button.pack(pady=10, fill=tk.X)
        
        self.status_label = tk.Label(
            main_frame, text="추출할 파일을 선택하세요.", font=("Helvetica", 10),
            bg="#f0f0f0", wraplength=460
        )
        self.status_label.pack(pady=20)

        self.progress_label = tk.Label(
            main_frame, text="", font=("Helvetica", 10, "italic"), bg="#f0f0f0"
        )
        self.progress_label.pack(pady=5)

    def browse_file(self):
        """파일 탐색기를 열어 사용자가 파일을 선택하도록 합니다."""
        file_path = filedialog.askopenfilename(
            title="Unity3d, assets, AssetBundle 파일을 선택하세요",
            filetypes=(
                ("모든 지원 파일", "*.unity3d *.assets *.bundle *.*"),
                ("Unity3D 파일", "*.unity3d"),
                ("Assets 파일", "*.assets"),
                ("AssetBundle 파일", "*.*"),
            )
        )
        if file_path:
            self.status_label.config(text=f"선택된 파일: {os.path.basename(file_path)}")
            self.progress_label.config(text="에셋 추출을 시작합니다...")
            self.select_button.config(state=tk.DISABLED)
            
            thread = threading.Thread(target=self.extract_assets, args=(file_path,))
            thread.start()

    def extract_assets(self, file_path):
        """선택된 파일에서 모든 에셋을 추출하는 메인 로직입니다."""
        output_dir = os.path.join(os.path.dirname(file_path), f"{os.path.basename(file_path)}_extracted")
        os.makedirs(output_dir, exist_ok=True)
        
        extracted_count = 0
        env = None
        try:
            env = UnityPy.load(file_path)
            total_assets = len(env.objects)
            
            if total_assets == 0:
                self.update_status("파일에서 에셋을 찾을 수 없습니다.", error=True)
                return

            for i, obj in enumerate(env.objects):
                self.root.after(0, self.update_progress, i + 1, total_assets)
                
                try:
                    # 모든 에셋을 타입에 따라 맞는 함수로 추출합니다.
                    if self.export_asset(obj, output_dir):
                        extracted_count += 1
                except Exception as e:
                    print(f"에셋 추출 중 오류 발생 (PathID: {obj.path_id}, Type: {obj.type.name}): {e}")

            self.update_status(f"추출 완료! 총 {total_assets}개의 에셋 중 {extracted_count}개를 추출하여\n'{output_dir}'에 저장했습니다.", success=True)

        except Exception as e:
            self.update_status(f"오류 발생: {e}", error=True)
        finally:
            self.root.after(0, lambda: self.select_button.config(state=tk.NORMAL))
            if env:
                del env


    def update_status(self, message, error=False, success=False):
        """GUI의 상태 레이블을 업데이트합니다."""
        color = "red" if error else "green" if success else "black"
        self.status_label.config(text=message, fg=color)
        self.progress_label.config(text="")

    def update_progress(self, current, total):
        """GUI의 진행률 레이블을 업데이트합니다."""
        self.progress_label.config(text=f"처리 중... ({current}/{total})")

    def sanitize_filename(self, name):
        """AssetStudio와 동일하게 파일 이름으로 사용할 수 없는 문자를 제거합니다."""
        # \ / : * ? " < > |
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def get_unique_path(self, path, obj):
        """파일 이름 중복 시, '이름 (#PathID).확장자' 형식으로 고유 경로를 생성합니다."""
        if not os.path.exists(path):
            return path
        
        # 파일이 이미 존재하면, PathID를 이름에 추가하여 고유성을 보장합니다.
        directory, filename = os.path.split(path)
        name, ext = os.path.splitext(filename)
        
        # 사용자가 요청한 'name (#pathid)' 형식을 사용합니다.
        new_name = f"{name} (#{obj.path_id}){ext}"
        new_path = os.path.join(directory, new_name)

        # PathID를 추가했음에도 불구하고 파일이 여전히 존재할 경우 (매우 드문 경우),
        # 기존처럼 숫자 카운터를 추가합니다.
        if not os.path.exists(new_path):
            return new_path
        else:
            count = 1
            base_name_for_counting = f"{name} (#{obj.path_id})"
            while True:
                final_name = f"{base_name_for_counting} ({count}){ext}"
                final_path = os.path.join(directory, final_name)
                if not os.path.exists(final_path):
                    return final_path
                count += 1

    def get_export_path(self, obj, output_dir, extension):
        """AssetStudio의 명명 규칙에 따라 최종 저장 경로를 생성합니다."""
        data = obj.read()
        
        # 1. 기본 이름 결정
        base_name = ""
        if hasattr(data, 'name') and data.name:
            base_name = data.name
        elif hasattr(data, 'm_Name') and data.m_Name:
            base_name = data.m_Name

        # 2. 이름이 없으면 타입과 PathID로 대체
        if not base_name:
            base_name = f"{obj.type.name} #{obj.path_id}"
        
        # 3. 폴더 경로 결정
        folder_name = SPECIAL_TYPES.get(obj.type.name, obj.type.name)
        dest_folder = os.path.join(output_dir, folder_name)
        os.makedirs(dest_folder, exist_ok=True)
        
        # 4. 파일 이름 정리 및 확장자 추가
        sanitized_name = self.sanitize_filename(base_name)
        initial_path = os.path.join(dest_folder, f"{sanitized_name}{extension}")
        
        # 5. 중복 처리하여 최종 경로 반환
        return self.get_unique_path(initial_path, obj)

    # =========================================================================
    # 에셋 추출 로직
    # =========================================================================

    def export_asset(self, obj, output_dir):
        """에셋 타입에 따라 적절한 방법으로 추출을 위임합니다."""
        obj_type = obj.type.name

        if obj_type in ["Texture2D", "Sprite"]:
            data = obj.read()
            
            # 실제 이미지 데이터가 있는지 확인합니다.
            has_image_data = False
            try:
                # .image는 디코딩을 시도하며, 성공 시에만 PIL Image 객체를 반환합니다.
                if data.image is not None:
                    has_image_data = True
            except Exception:
                # 디코딩 불가능한 포맷 등에서 오류가 발생할 수 있습니다.
                has_image_data = False
            
            if has_image_data:
                # 이미지 데이터가 있으면 PNG로 저장합니다.
                path = self.get_export_path(obj, output_dir, ".png")
                try:
                    data.image.save(path)
                    return True
                except Exception as e:
                    print(f"이미지 저장 실패 ({path}): {e}")
                    # PNG 저장을 시도했으나 실패했으므로, JSON으로 넘어가지 않습니다.
                    return False
            else:
                # 이미지 데이터가 없는 Texture2D/Sprite는 JSON으로 저장하여 메타데이터를 확인합니다.
                path = self.get_export_path(obj, output_dir, ".json")
                try:
                    typetree_data = obj.read_typetree()
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(typetree_data, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                    return True
                except Exception:
                    # TypeTree조차 읽을 수 없으면 저장하지 않습니다.
                    return False

        elif obj_type == "TextAsset":
            data = obj.read()
            content_to_save = None

            # 1. .script 또는 .m_Script에서 데이터를 가져옵니다.
            if hasattr(data, 'script') and data.script is not None:
                content_to_save = data.script
            elif hasattr(data, 'm_Script') and data.m_Script is not None:
                content_to_save = data.m_Script

            if content_to_save is not None:
                path = self.get_export_path(obj, output_dir, ".bin")
                
                final_bytes_to_save = b""

                if isinstance(content_to_save, bytes):
                    # 이상적인 경우: UnityPy가 데이터를 bytes로 올바르게 제공한 경우
                    final_bytes_to_save = content_to_save
                
                elif isinstance(content_to_save, str):
                    # 문제의 경우: UnityPy가 바이너리 데이터를 str로 잘못 해석한 경우
                    # 'surrogateescape'를 사용하여 서로게이트 코드를 원래 바이트로 복원합니다.
                    # 이는 'surrogates not allowed' 오류를 해결합니다.
                    final_bytes_to_save = content_to_save.encode('utf-8', errors='surrogateescape')

                if final_bytes_to_save:
                    with open(path, "wb") as f:
                        f.write(final_bytes_to_save)
                    return True

            return False

        elif obj_type == "AudioClip":
            data = obj.read()
            samples = data.samples
            if not samples: return False
            
            # 여러 오디오 샘플이 있을 수 있습니다.
            for name, audio_data in samples.items():
                # 각 샘플에 맞는 임시 객체를 만들어 이름을 전달합니다.
                temp_obj_for_naming = type('',(object,),{'type':obj.type, 'path_id':obj.path_id})()
                temp_obj_for_naming.read = lambda: type('',(object,),{'m_Name':name})()
                path = self.get_export_path(temp_obj_for_naming, output_dir, ".wav")
                with open(path, "wb") as f:
                    f.write(audio_data)
            return True

        elif obj_type == "Mesh":
            path = self.get_export_path(obj, output_dir, ".obj")
            data = obj.read()
            obj_data = data.export()
            if obj_data:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(obj_data)
                return True
            return False
        
        elif obj_type == "Shader":
            path = self.get_export_path(obj, output_dir, ".txt")
            data = obj.read()
            try:
                shader_text = data.export()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(shader_text)
                return True
            except Exception as e:
                print(f"Shader 저장 실패 ({path}): {e}")
            return False

        elif obj_type == "Font":
            data = obj.read()
            if not data.m_FontData: return False
            ext = ".otf" if data.m_FontData[:4] == b"OTTO" else ".ttf"
            path = self.get_export_path(obj, output_dir, ext)
            with open(path, "wb") as f:
                f.write(data.m_FontData)
            return True

        elif obj_type in ["VideoClip", "MovieTexture"]:
            data = obj.read()
            if not data.m_VideoData: return False
            ext = os.path.splitext(data.m_OriginalPath)[1] if data.m_OriginalPath else ".bin"
            path = self.get_export_path(obj, output_dir, ext)
            with open(path, "wb") as f:
                f.write(data.m_VideoData)
            return True

        else:
            # 그 외 모든 타입은 JSON으로 저장합니다.
            path = self.get_export_path(obj, output_dir, ".json")
            try:
                data = obj.read_typetree()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False, default=lambda o: f"<Unserializable: {type(o).__name__}>")
                return True
            except Exception:
                # TypeTree가 없는 에셋은 저장할 수 없습니다.
                return False

if __name__ == "__main__":
    root = tk.Tk()
    app = AssetExtractorApp(root)
    root.mainloop()
