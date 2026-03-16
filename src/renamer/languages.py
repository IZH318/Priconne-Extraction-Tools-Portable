import json
import os

_json_path = os.path.join(os.path.dirname(__file__), 'languages.json')
with open(_json_path, 'r', encoding='utf-8') as _f:
    LANGUAGES = json.load(_f)
