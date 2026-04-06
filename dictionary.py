import os
import json
from fugashi import Tagger
import unidic
import sqlite3


tagger = Tagger('-d ' + unidic.DICDIR)

DB_PATH = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Looks up dictionary entries with jmdict
def lookup_jmdict(text):
    cursor.execute('SELECT entry_json FROM jmdict WHERE text = ?', (text,))
    rows = cursor.fetchall()
    return [json.loads(row[0]) for row in rows]

# Looks up name entries with jmnedit
def lookup_jmnedict(text):
    cursor.execute('SELECT entry_json FROM jmnedict WHERE text = ?', (text,))
    row = cursor.fetchone()
    return json.loads(row[0]) if row else None

# Looks up frequency of entries with jpdb_freq
def lookup_frequency(text):
    cursor.execute('SELECT rank FROM frequency WHERE word = ?', (text,))
    row = cursor.fetchone()
    return row[0] if row else None

# Looks up kanji with KANJIDIC
def lookup_kanji(text):
    cursor.execute('SELECT entry_json FROM kanji WHERE literal = ?', (text,))
    row = cursor.fetchone()
    return json.loads(row[0]) if row else None


# Return each of the functions as an easy to read variable
dictionary = lookup_jmdict
names = lookup_jmnedict
frequency = lookup_frequency
kanji_dict = lookup_kanji

def tokenize(sentence):
    words = []
    for word in tagger(sentence):
        if word.feature.pos1 == '名詞':
            words.append({'surface': word.surface, 'lemma': word.surface})
        else:
            words.append({'surface': word.surface, 'lemma': word.feature.lemma or word.surface})

    return words
