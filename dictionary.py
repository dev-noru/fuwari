import os
import pickle
import json
from fugashi import Tagger
import unidic


tagger = Tagger('-d ' + unidic.DICDIR)





CACHE_DIR = os.path.expanduser('~/.cache/jp_popup')
DATA_DIR = os.path.expanduser('~/.local/share/jp_popup')
def load_dictionary():
    cache_path = f'{CACHE_DIR}/dictionary.pkl'
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    dictionary = {}
    with open(os.path.join(DATA_DIR, 'jmdict-eng.json')) as f:
        data = json.load(f)
        for word in data['words']:
            for kanji in word.get('kanji', []):
                text = kanji['text']
                if text not in dictionary:
                    dictionary[text] = []
                dictionary[text].append(word)
            for kana in word.get('kana', []):
                text = kana['text']
                if text not in dictionary:
                    dictionary[text] = []
                dictionary[text].append(word)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(dictionary, f)
    return dictionary

dictionary = load_dictionary()

def load_names():
    cache_path = f'{CACHE_DIR}/names.pkl'
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    names = {}
    with open(os.path.join(DATA_DIR, 'jmnedict-all.json')) as f:
        data = json.load(f)
        for word in data['words']:
            for kanji in word.get('kanji', []):
                text = kanji['text']
                names[text] = word
            for kana in word.get('kana', []):
                text = kana['text']
                names[text] = word
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(names, f)
    return names

names = load_names()

def load_frequency():
    cache_path = f'{CACHE_DIR}/frequency.pkl'
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    frequency = {}
    with open(os.path.join(DATA_DIR, 'jpdb_freq', 'term_meta_bank_1.json')) as f:
        data = json.load(f)
        for entry in data:
            word = entry[0]
            meta = entry[2]
            if 'value' in meta:
                rank = meta['value']
            elif 'frequency' in meta:
                rank = meta['frequency']['value']
            else:
                continue
            frequency[word] = rank
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(frequency, f)
    return frequency

frequency = load_frequency()
            
def load_kanji():
    cache_path = f'{CACHE_DIR}/kanji.pkl'
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    kanji_dict = {}
    with open(os.path.join(DATA_DIR, 'kanjidic2-en.json')) as f:
        data = json.load(f)
        for character in data['characters']:
            kanji_dict[character['literal']] = character
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(kanji_dict, f)

    return kanji_dict

kanji_dict = load_kanji()



def tokenize(sentence):
    words = []
    for word in tagger(sentence):
        if word.feature.pos1 == '名詞':
            words.append({'surface': word.surface, 'lemma': word.surface})
        else:
            words.append({'surface': word.surface, 'lemma': word.feature.lemma or word.surface})

    return words
