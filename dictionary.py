import os
import json
from fugashi import Tagger
import unidic
import sqlite3


tagger = Tagger('-d ' + unidic.DICDIR)

DB_PATH = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Looks up dictionary entries from the database
def lookup_term(term):
    cursor.execute("""
        SELECT terms.term, terms.reading, terms.definitions, terms.def_tags, dictionaries.title FROM terms JOIN dictionaries ON terms.dictionary_id = dictionaries.id WHERE terms.term = ? AND dictionaries.enabled = 1 ORDER BY dictionaries.priority ASC
    """, (term,))
    rows = cursor.fetchall()
    print(f"lookup_term({term}): {len(rows)} rows")
    return [{'term': row[0], 'reading': row[1], 'definitions': json.loads(row[2]), 'def_tags': row[3], 'title': row[4]} for row in rows]


# Looks up frequency of entries from the database
def lookup_frequency(text):
    cursor.execute('''
        SELECT tm.data FROM term_meta tm
        JOIN dictionaries d ON tm.dictionary_id = d.id
        WHERE tm.term = ? AND tm.type = 'freq' AND d.enabled = 1
        ORDER BY d.priority ASC
        LIMIT 1
    ''', (text,))
    row = cursor.fetchone()
    if not row:
        return None
    data = json.loads(row[0])
    if isinstance(data, dict):
        return data.get('value')
    return data

# Looks up kanji from the database
def lookup_kanji(character):
    cursor.execute('SELECT kanji.character, kanji.onyomi, kanji.kunyomi, kanji.tags, kanji.meanings, kanji.stats FROM kanji JOIN dictionaries ON kanji.dictionary_id = dictionaries.id WHERE kanji.character = ? AND dictionaries.enabled = 1', (character,))
    row = cursor.fetchone()
    if not row:
        return None
    return {'character': row[0], 'onyomi': row[1], 'kunyomi': row[2], 'tags': row[3], 'meanings': json.loads(row[4]), 'stats': json.loads(row[5])}


# Yomitan style definitons parser
def parse_structured_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(filter(None, [parse_structured_content(item) for item in content]))
    if isinstance(content, dict):
        return parse_structured_content(content.get('content', ''))
    return ''

# Return each of the functions as an easy to read variable
dictionary = lookup_term
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
