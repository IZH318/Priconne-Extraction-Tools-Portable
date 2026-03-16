# src/resource_remover/logic.py
import os
from pathlib import Path

class ResourceRemoverLogic:
    def __init__(self, base_path="."):
        self.base_path = Path(base_path).resolve()

    def count_resources(self, extensions):
        """
        Counts the number of files matching the given extensions without deleting them.
        Returns a tuple of (count, base_path_str) for display purposes.
        """
        count = 0
        target_exts = tuple(extensions)
        for root, dirs, files in os.walk(self.base_path):
            for file in files:
                if file.lower().endswith(target_exts):
                    count += 1
        return count, str(self.base_path)

    def remove_resources(self, extensions):
        """
        Removes the matching resource files and returns the number of deleted files.
        Raises an Exception if a critical error occurs.
        """
        deleted_count = 0
        target_exts = tuple(extensions)
        for root, dirs, files in os.walk(self.base_path):
            for file in files:
                if file.lower().endswith(target_exts):
                    file_path = Path(root) / file
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except OSError as e:
                        print(f"Failed to delete {file_path}: {e}")
        return deleted_count
