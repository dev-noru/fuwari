import urllib.request
import urllib.parse
import subprocess
import time
import os
import base64
import threading
import json
import sqlite3
from PySide6.QtCore import QObject, Signal, Property, Slot
from dictionary import get_dictionaries, toggle_dictionary, reorder_dictionary, delete_dictionary, tokenize, dictionary, frequency, kanji_dict, parse_structured_content, DB_PATH
from anki import ankiconnect_request
from settings import settings, save_settings
from migrate import import_dictionary
from collections import deque
from dictionary import cursor

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

class Bridge(QObject):
    wordsChanged = Signal()
    clipboardUpdated = Signal()
    sentenceChanged = Signal()
    historyChanged = Signal()
    dictionaryImported = Signal(bool)

    # Class initialization
    def __init__(self):
        super().__init__()
        self._words = []
        self._sentence = ""
        self._history = deque(maxlen=100)
        # Below we Thread the UI so it runs at the same time.
        thread = threading.Thread(target=self.clipboard_watcher, daemon=True)
        thread.start()
    
    # Processes the clipboard and tokenizes the sentence into separate words.
    def process_clipboard(self, sentence):
        self.set_sentence(sentence.strip())
        words = tokenize(sentence)
        self._history.append({'sentence': sentence.strip(), 'words': words})
        self.set_words(words)
        self.clipboardUpdated.emit()
        self.historyChanged.emit()
        
    # Watches the clipboard to grab.
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

    #Dictionary Management UI    
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

    #Dictionary install
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

    # Checking if the user has any dictionaries
    @Slot(result=bool)
    def has_dictionaries(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM dictionaries')
        count = c.fetchone()[0]
        conn.close()
        print(f"has_dictionaries: {count}")
        return count > 0

    # Adding history to texts
    @Slot(result=str)
    def get_history(self):
        return json.dumps(list(self._history))

    # Grabbing audio of the definition.
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
    # Plays the grabbed audio from above ^
    @Slot(str)
    def play_audio(self, url):
        try:
            subprocess.Popen(['mpv', '--no-video', url])
        except Exception as e:
            print(f"Playback error: {e}")
    # Saves the audio for anki card creation
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

    # Getting anki decks
    @Slot(result=str)
    def get_decks(self):
        try:
            decks = ankiconnect_request('deckNames')
            return json.dumps(decks)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]"
    # Getting note types from anki
    @Slot(result=str)
    def get_note_types(self):
        try:
            note_types = ankiconnect_request('modelNames')
            return json.dumps(note_types)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]"
    # Getting the fields populating the note type
    @Slot(str, result=str)
    def get_fields(self, note_type):
        try:
            fields = ankiconnect_request('modelFieldNames', modelName=note_type)
            print(f"Fields for {note_type}: {fields}")
            return json.dumps(fields)
        except Exception as e:
            print(f"AnkiConnect error: {e}")
            return "[]" 

    # The making of the anki cards
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

    # Moving files from the users dir to the anki server for fetching of media in cards.
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
    
    # Save and loading of the user set anki fields
    @Slot(str)
    def save_settings_slot(self, settings_json):
        global settings
        settings = json.loads(settings_json)
        save_settings(settings)

    # Creation of the lookups
    @Slot(str, result=str)
    def lookup(self, word):
        print(word)
        try:
            word = word.split('-')[0]
            hiragana = katakana_to_hiragana(word)
        
            # Find the entry
            results = []

            # JMdict
            entries = dictionary(word) or dictionary(hiragana)
            if entries:
                # sort common entries first
                for entry in entries:
                    reading = entry['reading']
                    kanji = entry['term']
                    freq_rank = frequency(kanji) or frequency(reading) or None
                    pos = [POS_LABELS.get(p, p) for p in entry['def_tags'].split() if not p.isdigit()]
                    definitions = []
                    for definition in entry['definitions']:
                        text = parse_structured_content(definition)
                        if text:
                            definitions.append(f"{len(definitions) + 1}.) {text}")
                    results.append({'source': entry['title'], 'Kanji': kanji, 'Reading': reading, 'Part of Speech': pos,
                                    'Frequency': freq_rank, 'Definitions': definitions})

            # KANJIDIC
            entry = kanji_dict(word)
            if len(word) == 1 and entry:
                on_readings = entry['onyomi'].split()
                kun_readings = entry['kunyomi'].split()
                meanings = entry['meanings']
                results.append({'source': 'KANJIDIC', 'Kanji': entry['character'], 'Reading': '、'.join(on_readings) + ' / ' + '、'.join(kun_readings), 
                                'Part of Speech': ['Kanji'], 'Frequency': entry['stats'].get('freq'), 
                                'Definitions': [f"{i+1}.) {m}" for i, m in enumerate(meanings)]})
                
            if not results:
                for char in word:
                    entry = kanji_dict(char)
                    if entry:
                        on_readings = entry['onyomi'].split()
                        kun_readings = entry['kunyomi'].split()
                        meanings = entry['meanings']
                        results.append({'source': 'KANJIDIC', 'Kanji': entry['character'], 'Reading': '、'.join(on_readings) + ' / ' + '、'.join(kun_readings), 
                                        'Part of Speech': ['Kanji'], 'Frequency': entry['stats'].get('freq'), 
                                        'Definitions': [f"{i+1}.) {m}" for i, m in enumerate(meanings)]})

            if not results:
                return ""
            return json.dumps(results, ensure_ascii=False)                 
        except Exception as e:
            print(e)
            return ""
    words = Property(list, get_words, set_words, notify=wordsChanged)


