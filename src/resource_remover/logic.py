# src/resource_remover/logic.py
import os
from pathlib import Path

class ResourceRemoverLogic:
    def __init__(self, base_path="."):
        self.base_path = Path(base_path).resolve()
        self.extensions_to_remove = ['.unity3d', '.awb', '.acb', '.usm']

    def remove_resources(self):
        """
        Removes the matching resource files and returns the number of deleted files.
        Raises an Exception if an error occurs.
        """
        deleted_count = 0
        try:
            for root, dirs, files in os.walk(self.base_path):
                for file in files:
                    if file.lower().endswith(tuple(self.extensions_to_remove)):
                        file_path = Path(root) / file
                        try:
                            file_path.unlink()
                            deleted_count += 1
                        except OSError as e:
                            print(f"Failed to delete {file_path}: {e}")
            return deleted_count
        except Exception as e:
            raise e
