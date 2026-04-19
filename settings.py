import os
import json


SETTINGS_PATH = os.path.expanduser('~/.config/jp_popup/settings.json')

DEFAULT_SETTINGS = {
    "anki_url": "http://localhost:8765",
    "deck": "",
    "note_type": "",
    "field_map": {},
    "main_width": 400,
    "main_height": 100,
    "def_width": 300,
    "def_height": 200,
    'text_source': 'clipboard',
    'textractor_ws_url': 'ws://localhost:6677',
    'lunatranslator_ws_url': 'ws://localhost:2333/api/ws/text/origin'
}

def load_settings():
    try:
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    except:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2)

settings = load_settings()
