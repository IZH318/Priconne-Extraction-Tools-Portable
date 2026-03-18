# src/resource_remover/logic.py
import os
from pathlib import Path
from datetime import datetime
import json
from send2trash import send2trash

class ResourceRemoverLogic:
    def __init__(self, base_path="."):
        self.base_path = Path(base_path).resolve()

    def count_resources(self, extensions_to_remove):
        """
        Counts the number of files matching the given extensions without deleting them.
        Returns a list of Path objects for the matching files.
        """
        found_files = []
        target_exts = tuple(extensions_to_remove)
        search_path = self.base_path

        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.lower().endswith(target_exts):
                    found_files.append(Path(root) / file)
        return found_files

    def remove_resources(self, target_files, extensions_to_remove, use_trash=True):
        """
        Removes the provided resource files and returns the number of deleted files.
        Raises an Exception if a critical error occurs.
        """
        
        deleted_files = []
        errors = []
        for file_path in target_files:
            try:
                if use_trash:
                    send2trash(file_path)
                else:
                    os.remove(file_path)
                deleted_files.append(str(file_path)) # Store as string for logging
            except Exception as e:
                errors.append(f"{file_path}: {e}")
                
        # 로그 파일 생성
        log_filename = ""
        if deleted_files or errors:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Ensure log file is created in the target_path or a sensible location
            log_dir = self.base_path
            log_filename = log_dir / f"deletion_log_{timestamp}.txt"
            try:
                with open(log_filename, 'w', encoding='utf-8') as f:
                    f.write(f"Resource Deletion Log - {timestamp}\n")
                    f.write(f"Target Path: {self.base_path}\n")
                    f.write(f"Extensions: {extensions_to_remove}\n")
                    f.write(f"Use Trash: {use_trash}\n")
                    f.write("-" * 50 + "\n")
                    f.write(f"Successfully processed: {len(deleted_files)} files\n")
                    for p in deleted_files:
                        f.write(f"[SUCCESS] {p}\n")
                    if errors:
                        f.write("-" * 50 + "\n")
                        f.write(f"Errors: {len(errors)} files\n")
                        for e in errors:
                            f.write(f"[ERROR] {e}\n")
            except Exception as e:
                # Handle error during log file creation
                print(f"Failed to create log file {log_filename}: {e}")
                log_filename = "" # Indicate log file creation failed
                
        return len(deleted_files), errors, str(log_filename)
