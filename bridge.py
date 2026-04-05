import urllib.request
import urllib.parse
import subprocess
import os
import base64
import threading
import json
from PySide6.QtCore import QObject, Signal, Property, Slot
from dictionary import tokenize, dictionary, names, frequency, kanji_dict
from anki import ankiconnect_request
from settings import settings, save_settings

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

    # Class initialization
    def __init__(self):
        super().__init__()
        self._words = []
        self._sentence = ""
        # Below we Thread the UI so it runs at the same time.
        thread = threading.Thread(target=self.clipboard_watcher, daemon=True)
        thread.start()
    
    # Processes the clipboard and tokenizes the sentence into separate words.
    def process_clipboard(self, sentence):
        self.set_sentence(sentence.strip())
        words = tokenize(sentence)
        self.set_words(words)
        self.clipboardUpdated.emit()
        
    # Watches the clipboard to grab.
    def clipboard_watcher(self):
        is_wayland = bool(os.getenv('WAYLAND_DISPLAY'))
        clipboard_cmd = ['wl-paste', '--watch', 'sh', '-c', 'cat; echo; echo "---END---"'] if is_wayland else ['xclip', '-selection', 'clipboard', '-o']
        print(f"Using clipboard command: {clipboard_cmd}")
        result_check = ""
        try:
            # Activates the clipboard for the wayland display server.
            if is_wayland == True:
                result = subprocess.Popen(clipboard_cmd, stdout=subprocess.PIPE, text=True)
                assert result.stdout is not None
                while True:
                    clipboard_check = result.stdout.readline()
                    write_clipboard = ""

                    while clipboard_check.strip() != '---END---':

                        write_clipboard += clipboard_check
                        clipboard_check = result.stdout.readline()

                    self.process_clipboard(write_clipboard)

            # Activates the clipboard for the xorg display server.
            else:
                while True:
                        result = subprocess.run(clipboard_cmd, capture_output=True, text=True)
                        if result_check != result.stdout:
                            self.process_clipboard(result.stdout)
                            result_check = result.stdout
        except Exception as e:
            print(f"Error: {e}")

 


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

    @Slot(str)
    def save_settings_slot(self, settings_json):
        global settings
        settings = json.loads(settings_json)
        save_settings(settings)

    @Slot(str, result=str)
    def lookup(self, word):
        try:
            word = word.split('-')[0]
            hiragana = katakana_to_hiragana(word)
        
            # Find the entry
            results = []

            # JMdict
            entries = dictionary.get(word) or dictionary.get(hiragana)
            if entries:
                # sort common entries first
                entries = sorted(entries, key=lambda e: e['kana'][0].get('common', False), reverse=True)
                for entry in entries:
                    reading = entry['kana'][0]['text']
                    kanji = entry['kanji'][0]['text'] if entry['kanji'] else entry['kana'][0]['text']
                    freq_rank = frequency.get(kanji) or frequency.get(reading) or None
                    pos = [POS_LABELS.get(p, p) for p in entry['sense'][0]['partOfSpeech']]
                    definitions = []
                    for sense in entry['sense']:
                        for gloss in sense['gloss']:
                            definitions.append(f"{len(definitions) + 1}.) {gloss['text']}")
                    results.append({'source': 'JMdict', 'Kanji': kanji, 'Reading': reading, 'Part of Speech': pos,
                                    'Frequency': freq_rank, 'Definitions': definitions})

            # JMnedict
            entry = names.get(word) or names.get(hiragana)
            if entry:
                reading = entry['kana'][0]['text']
                kanji = entry['kanji'][0]['text'] if entry['kanji'] else entry['kana'][0]['text']
                translation_type = entry['translation'][0]['type'][0] if entry['translation'][0]['type'] else 'name'
                definitions = []
                for t in entry['translation']:
                    for trans in t['translation']:
                        definitions.append(f"{len(definitions) + 1}.) {trans['text']}")
                results.append({'source': 'JMnedict', 'Kanji': kanji, 'Reading': reading, 
                                'Part of Speech': [translation_type], 'Frequency': None, 'Definitions': definitions})

            # KANJIDIC
            if len(word) == 1 and word in kanji_dict:
                entry = kanji_dict[word]
                readings = entry['readingMeaning']['groups'][0]['readings']
                on_readings = [r['value'] for r in readings if r['type'] == 'ja_on']
                kun_readings = [r['value'] for r in readings if r['type'] == 'ja_kun']
                meanings = [m['value'] for m in entry['readingMeaning']['groups'][0]['meanings'] if m['lang'] == 'en']
                results.append({'source': 'KANJIDIC', 'Kanji': entry['literal'], 'Reading': '、'.join(on_readings) + ' / ' + '、'.join(kun_readings), 
                                'Part of Speech': ['Kanji'], 'Frequency': entry['misc'].get('frequency'), 
                                'Definitions': [f"{i+1}.) {m}" for i, m in enumerate(meanings)]})

            if not results:
                return ""
            return json.dumps(results, ensure_ascii=False)                 
        except KeyError:
            print("Text not found")
            return ""
    words = Property(list, get_words, set_words, notify=wordsChanged)


