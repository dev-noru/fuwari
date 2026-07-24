import urllib.request
import urllib.parse
import subprocess
import time
import os
import base64
import threading
import json
import sqlite3
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
from dictionary import get_dictionaries, toggle_dictionary, reorder_dictionary, delete_dictionary, tokenize, dictionary, frequency, kanji_dict, parse_structured_content, parse_sense, DB_PATH
from anki import ankiconnect_request
from settings import settings, save_settings
from migrate import import_dictionary
from collections import deque
import websockets
from dictionary import cursor
import re

# Give up if the crate never answers (e.g. the overlay was killed).
DRAG_TIMEOUT_MS = 30000


POS_LABELS = {
    'v1': 'Ichidan verb',
    'v5': 'Godan verb',
    'v5r': 'Godan verb',
    'v5k': 'Godan verb',
    'v5s': 'Godan verb',
    'v5t': 'Godan verb',
    'v5n': 'Godan verb',
    'v5b': 'Godan verb',
    'v5m': 'Godan verb',
    'v5g': 'Godan verb',
    'v5u': 'Godan verb',
    'vt': 'Transitive',
    'vi': 'Intransitive',
    'vs': 'Suru verb',
    'vk': 'Kuru verb',
    'aux-v': 'Auxiliary verb',
    'n': 'Noun',
    'n-adv': 'Adverbial noun',
    'n-suf': 'Noun suffix',
    'n-pref': 'Noun prefix',
    'adj-i': 'I-adjective',
    'adj-na': 'Na-adjective',
    'adj-no': 'No-adjective',
    'adv': 'Adverb',
    'prt': 'Particle',
    'conj': 'Conjunction',
    'int': 'Interjection',
    'exp': 'Expression',
    'pn': 'Pronoun',
    'suf': 'Suffix',
    'pref': 'Prefix',
    'unc': 'Unclassified',
}

def katakana_to_hiragana(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ン' else c for c in text)

_LATIN = re.compile(r'[A-Za-z]')

def _is_related_form(sense):
    """Bare cross-reference 'senses' that are just a kanji form, e.g. 屋's 6.) 屋."""
    joined = ''.join(sense['glosses'])
    return bool(joined) and not _LATIN.search(joined) and len(joined) <= 4

class Bridge(QObject):
    wordsChanged = Signal()
    clipboardUpdated = Signal()
    sentenceChanged = Signal()
    historyChanged = Signal()
    dictionaryImported = Signal(bool)
    ocrLoadingChanged = Signal()
    windowMoved = Signal(int, int)
    windowDragCancelled = Signal()
    screenSizeChanged = Signal()


    def __init__(self):
        super().__init__()
        self._words = []
        self._sentence = ""
        self._history = deque(maxlen=100)
        self._ocr = None
        self._layershell = None
        self._ocr_loading = False
        self._screen_w = 0
        self._screen_h = 0

        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(16)          # ~60Hz, matches the ghost redraw
        self._drag_timer.timeout.connect(self._poll_drag)
        self._drag_elapsed = 0

        # _ls() is what spawns the Wayland thread, so the size is not available
        # on the first call. Poll until the compositor has told it about an output.
        self._screen_timer = QTimer(self)
        self._screen_timer.setInterval(100)
        self._screen_timer.timeout.connect(self._refresh_screen_size)
        self._screen_attempts = 0
        self._screen_timer.start()

        source = settings.get('text_source', 'clipboard')
        if source == 'clipboard':
            threading.Thread(target=self.clipboard_watcher, daemon=True).start()
        elif source == 'textractor':
            threading.Thread(target=self.websocket_watcher, daemon=True,
                args=(settings.get('textractor_ws_url', 'ws://localhost:6677'),)).start()
        elif source == 'lunatranslator':
            threading.Thread(target=self.websocket_watcher, daemon=True,
                args=(settings.get('lunatranslator_ws_url', 'ws://localhost:2333/api/ws/text/origin'),)).start()


    # --- window drag ---------------------------------------------------------
    #
    # Everything here is in compositor logical pixels. QML owns the conversion
    # from Qt units, because only QML knows Screen.width; keeping the factor in
    # one place is the difference between this working and drifting.

    def _ls(self):
        """The lazily created LayerShell instance, shared with OCR region select."""
        if getattr(self, "_layershell", None) is None:
            from layer_shell import LayerShell
            self._layershell = LayerShell()
        return self._layershell

    def _refresh_screen_size(self):
        self._screen_attempts += 1
        try:
            w, h = self._ls().screen_size()
        except Exception as e:
            print("screen_size failed:", e)
            self._screen_timer.stop()
            return
        if w > 0 and h > 0:
            self._screen_timer.stop()
            if (w, h) != (self._screen_w, self._screen_h):
                self._screen_w = w
                self._screen_h = h
                print(f"crate screen size: {w} x {h}")
                self.screenSizeChanged.emit()
        elif self._screen_attempts > 50:      # ~5s
            print("crate never reported a screen size")
            self._screen_timer.stop()

    @Property(int, notify=screenSizeChanged)
    def screenWidth(self):
        return self._screen_w

    @Property(int, notify=screenSizeChanged)
    def screenHeight(self):
        return self._screen_h

    @Slot(str, int, int, int)
    def set_drag_style(self, color, border, radius, fill_pct):
        """color is a QML colour string, "#rrggbb" or "#aarrggbb"."""
        text = color.lstrip("#")
        if len(text) == 8:      # drop the alpha channel
            text = text[2:]
        try:
            rgb = int(text, 16)
        except ValueError:
            rgb = 0xFFFFFF
        try:
            self._ls().set_drag_style(rgb, border, radius, fill_pct)
        except Exception as e:
            print("set_drag_style failed:", e)

    @Slot(int, int, int, int, int, int)
    def start_window_drag(self, x, y, w, h, grab_x, grab_y):
        """Called from the toolbar's onPressed. Hands the window geometry to the
        crate, which maps a stationary full-screen overlay and draws the ghost."""
        try:
            self._ls().start_drag(x, y, w, h, grab_x, grab_y)
        except Exception as e:
            print("start_window_drag failed:", e)
            self.windowDragCancelled.emit()
            return
        self._drag_elapsed = 0
        self._drag_timer.start()

    def _poll_drag(self):
        self._drag_elapsed += self._drag_timer.interval()
        if self._drag_elapsed > DRAG_TIMEOUT_MS:
            self._drag_timer.stop()
            self._ls().stop_drag()
            self.windowDragCancelled.emit()
            return

        result = self._ls().poll_drag()
        if result is None:
            return

        self._drag_timer.stop()

        if result == "cancel":
            self.windowDragCancelled.emit()
            return

        try:
            xs, ys = result.split(",")
            self.windowMoved.emit(int(xs), int(ys))
        except ValueError:
            self.windowDragCancelled.emit()

        

    # -------------------------------------------------------------------------

    def process_clipboard(self, sentence):
        sentence = sentence.strip()
        self.set_sentence(sentence)
        words = tokenize(sentence)
        self._history.append({'sentence': sentence, 'words': words})
        self.set_words(words)
        self.clipboardUpdated.emit()
        self.historyChanged.emit()

    def clipboard_watcher(self):
        is_wayland = bool(os.getenv('WAYLAND_DISPLAY'))
        clipboard_cmd = ['wl-paste'] if is_wayland else ['xclip', '-selection', 'clipboard', '-o']
        print(f"Using clipboard command: {clipboard_cmd}")
        result_check = ""
        while True:
            try:
                time.sleep(0.1)
                result = subprocess.run(clipboard_cmd, capture_output=True, text=True)
                if result_check != result.stdout:
                    self.process_clipboard(result.stdout)
                    result_check = result.stdout
            except Exception:
                pass

    def websocket_watcher(self, url):
        import asyncio
        async def listen():
            while True:
                try:
                    async with websockets.connect(url) as ws:
                        async for message in ws:
                            self.process_clipboard(message)
                except Exception:
                    await asyncio.sleep(3)
        asyncio.run(listen())

    def get_sentence(self):
        return self._sentence

    def set_sentence(self, sentence):
        self._sentence = sentence
        self.sentenceChanged.emit()

    sentence = Property(str, get_sentence, set_sentence, notify=sentenceChanged)

    def get_words(self):
        return self._words

    def set_words(self, words):
        self._words = words
        self.wordsChanged.emit()
        print(words)

    words = Property(list, get_words, set_words, notify=wordsChanged)

    #OCR loading display
    def _get_ocr_loading(self):
        return self._ocr_loading

    def _set_ocr_loading(self, value):
        self._ocr_loading = value
        self.ocrLoadingChanged.emit()

    ocrLoading = Property(bool, _get_ocr_loading, notify=ocrLoadingChanged)

    @Slot()
    def toggle_ocr(self):
        if self._ocr and self._ocr._running:
            self._ocr.stop()
            self._ocr = None
            return

        def start_ocr():
            layershell = self._ls()
            region = layershell.select_region()
            if not region:
                return
            from ocr import OCRThread, is_pipeline_loaded, ensure_pipeline_loaded
            if not is_pipeline_loaded():
                self._set_ocr_loading(True)
                ensure_pipeline_loaded()
                self._set_ocr_loading(False)
            self._ocr = OCRThread(self.process_clipboard, layershell)
            self._ocr.set_region(region)
            self._ocr.start()

        threading.Thread(target=start_ocr, daemon=True).start()

    @Slot(result=str)
    def get_dictionaries(self):
        return json.dumps(get_dictionaries())

    @Slot(int, bool)
    def toggle_dictionary(self, dict_id, enabled):
        toggle_dictionary(dict_id, enabled)

    @Slot(int, int)
    def reorder_dictionary(self, dict_id, new_priority):
        reorder_dictionary(dict_id, new_priority)

    @Slot(int)
    def delete_dictionary(self, dict_id):
        delete_dictionary(dict_id)

    @Slot(str, result=bool)
    def install_dictionary(self, zip_path):
        try:
            def run():
                try:
                    import_dictionary(zip_path)
                    self.dictionaryImported.emit(True)
                except Exception as e:
                    print(f"Import error: {e}")
                    self.dictionaryImported.emit(False)
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            return True
        except Exception as e:
            return False

    @Slot(result=bool)
    def has_dictionaries(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM dictionaries')
        count = c.fetchone()[0]
        conn.close()
        print(f"has_dictionaries: {count}")
        return count > 0

    @Slot(result=str)
    def get_history(self):
        return json.dumps(list(self._history))

    @Slot(str, str, result=str)
    def get_audio(self, term, reading):
        try:
            encoded_term = urllib.parse.quote(term)
            encoded_reading = urllib.parse.quote(reading)
            url = f'http://localhost:5050?term={encoded_term}&reading={encoded_reading}'
            request = urllib.request.Request(url)
            response = json.loads(urllib.request.urlopen(request).read())
            sources = response.get('audioSources', [])
            if sources:
                return sources[0]['url']
            return ""
        except Exception as e:
            print(f"Audio error: {e}")
            return ""

    @Slot(str)
    def play_audio(self, url):
        try:
            subprocess.Popen(['mpv', '--no-video', url])
        except Exception as e:
            print(f"Playback error: {e}")

    @Slot(str, str, result=str)
    def store_audio(self, term, reading):
        try:
            encoded_term = urllib.parse.quote(term)
            encoded_reading = urllib.parse.quote(reading)
            url = f'http://localhost:5050?term={encoded_term}&reading={encoded_reading}'
            response = json.loads(urllib.request.urlopen(url).read())
            sources = response.get('audioSources', [])
            if not sources:
                return ""
            audio_url = sources[0]['url']
            audio_data = urllib.request.urlopen(audio_url).read()
            filename = f'{term}_{reading}.opus'
            ankiconnect_request('storeMediaFile',
                filename=filename,
                data=base64.b64encode(audio_data).decode('utf-8'))
            return f'[sound:{filename}]'
        except Exception as e:
            print(f"Store audio error: {e}")
            return ""

    @Slot(result=str)
    def get_decks(self):
        try:
            decks = ankiconnect_request('deckNames')
            return json.dumps(decks)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]"

    @Slot(result=str)
    def get_note_types(self):
        try:
            note_types = ankiconnect_request('modelNames')
            return json.dumps(note_types)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]"

    @Slot(str, result=str)
    def get_fields(self, note_type):
        try:
            fields = ankiconnect_request('modelFieldNames', modelName=note_type)
            print(f"Fields for {note_type}: {fields}")
            return json.dumps(fields)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]"

    @Slot(str, str, str, result=str)
    def add_note(self, deck, note_type, fields_json):
        try:
            fields = json.loads(fields_json)
            result = ankiconnect_request('addNote', note={
                'deckName': deck,
                'modelName': note_type,
                'fields': fields,
                'options': {'allowDuplicate': False}
            })
            print(f"Adding note: deck={deck}, note_type={note_type}, fields={fields}")
            print(f"Result: {result}")
            return json.dumps(result)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return ""

    @Slot(result=str)
    def get_settings(self):
        return json.dumps(settings)

    @Slot(str, result=str)
    def store_media_file(self, file_path):
        try:
            clean_path = file_path.replace("file://", "")
            with open(clean_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(clean_path)[1]
            filename = f"{int(time.time())}{ext}"
            ankiconnect_request('storeMediaFile', filename=filename, data=data)
            return filename
        except Exception as e:
            print(f"Store media error: {e}")
            return ""

    @Slot(str)
    def save_settings_slot(self, settings_json):
        global settings
        settings = json.loads(settings_json)
        save_settings(settings)

    @Slot(str, result=str)
    def lookup(self, word):
        print(word)
        try:
            word = word.split('-')[0]
            hiragana = katakana_to_hiragana(word)
            results = []
            entries = dictionary(word) or dictionary(hiragana)
            if entries:
                # group rows by (title, term, reading), preserving first-seen order
                groups = {}
                order = []
                for entry in entries:
                    key = (entry['title'], entry['term'], entry['reading'])
                    if key not in groups:
                        groups[key] = []
                        order.append(key)
                    groups[key].append(entry)

                for key in order:
                    rows = groups[key]
                    title, kanji, reading = key
                    first = rows[0]
                    freq_rank = frequency(kanji) or frequency(reading) or None
                    pos = [POS_LABELS.get(p, p) for p in first['def_tags'].split() if not p.isdigit()]

                    # flatten every sense from every row in this group, numbered continuously
                    senses = []
                    related = []
                    for row in rows:
                        for definition in row['definitions']:
                            sense = parse_sense(definition)
                            if not (sense['glosses'] or sense['notes'] or sense['refs']):
                                continue
                            if _is_related_form(sense):
                                related.extend(sense['glosses'])
                                continue
                            senses.append({
                                'num': len(senses) + 1,
                                'glosses': '; '.join(sense['glosses']),
                                'notes': sense['notes'],
                                'refs': sense['refs'],
                            })

                    results.append({
                        'source': title, 'Kanji': kanji, 'Reading': reading,
                        'Part of Speech': pos, 'Frequency': freq_rank,
                        'Senses': senses, 'Related': related,
                        # flat form kept for Anki mining
                        'Definitions': [f"{s['num']}.) {s['glosses']}" for s in senses],
                    })

            entry = kanji_dict(word)
            if len(word) == 1 and entry:
                on_readings = entry['onyomi'].split()
                kun_readings = entry['kunyomi'].split()
                meanings = entry['meanings']
                results.append({'source': 'KANJIDIC', 'Kanji': entry['character'], 'Reading': '、'.join(on_readings) + ' / ' + '、'.join(kun_readings),
                                'Part of Speech': ['Kanji'], 'Frequency': entry['stats'].get('freq'),
                                'Definitions': [f"{i+1}.) {m}" for i, m in enumerate(meanings)],
                                'Senses': [{'num': i + 1, 'glosses': m, 'notes': [], 'refs': []}
                                           for i, m in enumerate(meanings)],
                                'Related': []})

            if not results:
                for char in word:
                    entry = kanji_dict(char)
                    if entry:
                        on_readings = entry['onyomi'].split()
                        kun_readings = entry['kunyomi'].split()
                        meanings = entry['meanings']
                        results.append({'source': 'KANJIDIC', 'Kanji': entry['character'], 'Reading': '、'.join(on_readings) + ' / ' + '、'.join(kun_readings),
                                        'Part of Speech': ['Kanji'], 'Frequency': entry['stats'].get('freq'),
                                        'Definitions': [f"{i+1}.) {m}" for i, m in enumerate(meanings)],
                                        'Senses': [{'num': i + 1, 'glosses': m, 'notes': [], 'refs': []}
                                                   for i, m in enumerate(meanings)],
                                        'Related': []})

            if not results:
                return ""
            return json.dumps(results, ensure_ascii=False)
        except Exception as e:
            print(e)
            return ""
