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


def _inline(content):
    """Flatten inline content (li children, links, spans) into one string."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _inline(content.get('content', ''))
    if isinstance(content, list):
        return ''.join(p for p in (_inline(i) for i in content) if p)
    return ''


def _ul_items(block):
    """The li items of a ul block, as strings."""
    inner = block.get('content', '')
    items = inner if isinstance(inner, list) else [inner]
    return [t for t in (_inline(i) for i in items) if t]


def parse_sense(definition):
    """
    Parse one definition into {'glosses': [...], 'notes': [...], 'refs': [...]}.
    Yomitan labels each top-level ul via data.content
    ('glossary' / 'notes' / 'references'); unlabelled is treated as a gloss.
    """
    sense = {'glosses': [], 'notes': [], 'refs': []}

    if isinstance(definition, str):          # plain-string dictionaries
        sense['glosses'].append(definition)
        return sense
    if not isinstance(definition, dict):
        return sense

    blocks = definition.get('content', '')
    if isinstance(blocks, str):
        sense['glosses'].append(blocks)
        return sense
    if isinstance(blocks, dict):
        blocks = [blocks]

    for block in blocks:
        if not isinstance(block, dict):
            text = _inline(block)
            if text:
                sense['glosses'].append(text)
            continue
        category = (block.get('data') or {}).get('content', '')
        items = _ul_items(block)
        if category == 'notes':
            sense['notes'].extend(items)
        elif category == 'references':
            sense['refs'].extend(items)
        else:
            sense['glosses'].extend(items)
    return sense


def parse_structured_content(content):
    """Flat-string version, kept for any caller that just wants text."""
    s = parse_sense(content)
    return '\n'.join(p for p in ['; '.join(s['glosses']), *s['notes'], *s['refs']] if p)

# Return each of the functions as an easy to read variable
dictionary = lookup_term
frequency = lookup_frequency
kanji_dict = lookup_kanji

#Code for getting dictionaries
def get_dictionaries():
    cursor.execute('SELECT id, title, enabled, priority FROM dictionaries ORDER BY priority ASC')
    rows = cursor.fetchall()
    return [{'id': row[0], 'title': row[1], 'enabled': row[2], 'priority': row[3]} for row in rows]

#Code for toggling dictionaries
def toggle_dictionary(dict_id, enabled):
    cursor.execute('UPDATE dictionaries SET enabled = ? WHERE id = ?',
                   (enabled, dict_id))
    conn.commit()

#Code for reordering dictionaries
def reorder_dictionary(dict_id, new_priority):
    cursor.execute('UPDATE dictionaries SET priority = ? WHERE id = ?',
                   (new_priority, dict_id))
    conn.commit()


#Code for deleting dictionaries
def delete_dictionary(dict_id):
    cursor.execute('SELECT title FROM dictionaries WHERE id = ?',
                   (dict_id,))
    title = cursor.fetchone()[0] 
    delete = os.path.join(os.path.expanduser('~/.local/share/fuwari/dictionaries'), title + '.zip')

    if os.path.exists(delete):
        os.remove(delete)

    cursor.execute('DELETE FROM dictionaries WHERE id = ?',
                   (dict_id,))
    conn.commit()


# Tokenizes the text so it is searchable.
def tokenize(sentence):
    words = []
    cursor = 0
    for word in tagger(sentence):
        surface = word.surface
        # find the real offset; MeCab doesn't always emit whitespace as a token
        start = sentence.find(surface, cursor)
        if start == -1:
            start = cursor
        end = start + len(surface)
        cursor = end
        if word.feature.pos1 == '名詞':
            lemma = surface
        else:
            lemma = word.feature.lemma or surface
        words.append({'surface': surface, 'lemma': lemma, 'start': start, 'end': end})
    return words
