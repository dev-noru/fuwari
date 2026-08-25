import os
import json


SETTINGS_PATH = os.path.expanduser('~/.config/jp_popup/settings.json')

DEFAULT_SETTINGS = {
    "ui_scale": 1.0,
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
    'lunatranslator_ws_url': 'ws://localhost:2333/api/ws/text/origin',
    # Which monitor to open on, by wl_output name ("eDP-1", "DP-3", ...).
    # Empty means "let the compositor choose", which is what layer-shell does
    # with a null output: generally the display the user most recently
    # interacted with. Wayland gives a client no way to find the pointer's
    # monitor itself, so on a multi-monitor setup this is the only way to make
    # the choice deterministic.
    'startup_output': '',
    # Use ordinary windows instead of layer-shell surfaces. Layer-shell floats
    # above fullscreen games, which is the point of Fuwari, but it also means
    # the app positions itself and the window manager cannot: dragging, monitor
    # placement and popup positioning all become Fuwari's problem. Turning this
    # on gives up floating-above-fullscreen and hands all of that back to the
    # WM, which is how the app behaved before layer-shell was introduced.
    'legacy_windows': False
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
