import json
import os

_json_path = os.path.join(os.path.dirname(__file__), 'languages.json')
with open(_json_path, 'r', encoding='utf-8') as _f:
    LANGUAGES = json.load(_f)

ABOUT_INFO = {'program': 'storydata Viewer', 'version': '1.0.0', 'updated': '2025-07-26', 'license': 'GNU General Public License v3.0', 'developer': '(Github) IZH318', 'website': 'https://github.com/IZH318'}
