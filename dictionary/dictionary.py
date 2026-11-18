import os
import json
import re
from fugashi import GenericTagger, create_feature_wrapper
import sqlite3
import threading
from dictionary.unidic_setup import mecab_args

_local = threading.local()


# UniDic 3.1's 29 feature columns, by name, so word.feature.lemma and the
# rest work. GenericTagger rather than Tagger: Tagger goes looking for a
# pip-installed `unidic` on its own, even when told which dictionary to use,
# and a half-removed one made it crash on every sentence.
UnidicFeatures = create_feature_wrapper('UnidicFeatures', (
    'pos1 pos2 pos3 pos4 cType cForm lForm lemma orth pron orthBase '
    'pronBase goshu iType iForm fType fForm iConType fConType type kana '
    'kanaBase form formBase aType aConType aModType lid lemma_id').split())
# Created on first use, not at import: on a fresh install UniDic has not been
# downloaded yet when Fuwari starts, and a tagger built without it fails.
_tagger = None
_tagger_lock = threading.Lock()


def _get_tagger():
    """The shared tagger, or None while UniDic is still missing."""
    global _tagger
    if _tagger is None:
        with _tagger_lock:
            if _tagger is None:
                args = mecab_args()
                if args is None:
                    return None
                _tagger = GenericTagger(args, wrapper=UnidicFeatures)
    return _tagger

DB_PATH = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def _cursor():
    """A cursor owned by the calling thread.

    SQLite objects cannot cross threads, and the module-level cursor belongs
    to whichever thread imported this module. tokenize() runs on the clipboard
    watcher, so it needs its own -- sharing one would also race on fetch,
    since execute and fetchall are not atomic together.
    """
    if not hasattr(_local, 'conn'):
        _local.conn = sqlite3.connect(DB_PATH)
    return _local.conn.cursor()

# Looks up dictionary entries from the database
def lookup_term(term):
    cursor.execute("""
        SELECT terms.term, terms.reading, terms.definitions, terms.def_tags, dictionaries.title FROM terms JOIN dictionaries ON terms.dictionary_id = dictionaries.id WHERE terms.term = ? AND dictionaries.enabled = 1 ORDER BY dictionaries.priority ASC
    """, (term,))
    rows = cursor.fetchall()
    print(f"lookup_term({term}): {len(rows)} rows")
    return [{'term': row[0], 'reading': row[1], 'definitions': json.loads(row[2]), 'def_tags': row[3], 'title': row[4]} for row in rows]


# MeCab's part of speech -> the JMdict tag codes that agree with it. def_tags
# holds raw codes ('v1', 'n', 'prt'), not the readable labels the popup shows,
# so these are prefixes tested against each whitespace-separated code. An
# unlisted part of speech simply expresses no opinion.
_POS_HINT = {
    '動詞': ('v',),
    '名詞': ('n', 'vs'),      # vs nouns take suru and are still nouns
    '助詞': ('prt',),
    '助動詞': ('aux', 'cop'),
    '副詞': ('adv',),
    '形容詞': ('adj-i',),
    '形状詞': ('adj-na', 'adj-no'),
    '接尾辞': ('suf', 'n-suf'),
    '接頭辞': ('pref', 'n-pref'),
    '代名詞': ('pn',),
    '接続詞': ('conj',),
    '感動詞': ('int',),
    '連体詞': ('adj-pn',),
}


def _pos_matches(row, hints):
    if not hints:
        return False
    codes = (row.get('def_tags') or '').split()
    return any(c == h or c.startswith(h) for c in codes for h in hints)


def lookup_best(candidates, reading='', pos=''):
    """Entries for whichever candidate form gives the most plausible word.

    Part of speech decides it first. 気 read as a noun must not resolve to the
    げ suffix, and 感じます must not land on the noun 感じ, even though both
    share their spelling with the right answer. Where the part of speech
    cannot separate them, the commoner form wins, which is what picks 感じる
    over 感ずる, やっぱり over 矢張り, and の over ん.
    """
    hint = _POS_HINT.get(pos, ())
    best = None
    for cand in candidates:
        rows = lookup_term(cand)
        if not rows:
            continue
        # Stable, so better entries rise without disturbing dictionary
        # priority among equals.
        if hint:
            rows.sort(key=lambda r: 0 if _pos_matches(r, hint) else 1)
        if reading:
            rows.sort(key=lambda r: 0 if r['reading'] == reading else 1)
        agrees = any(_pos_matches(r, hint) for r in rows)
        freq = lookup_frequency(cand)
        score = (0 if agrees else 1, freq if freq is not None else float('inf'))
        if best is None or score < best[0]:
            best = (score, rows)
    return best[1] if best else []


def _freq_number(value):
    """A frequency as a number, from either plain shape Yomitan allows.

    Dictionaries store it as a bare number, a string such as "1234" or
    "1234㋕", or {"value": 1234, "displayValue": "..."}. None if there is
    no number to be had.
    """
    if isinstance(value, dict):
        value = value.get('value')
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = re.match(r'\s*(\d+)', value)
        return int(match.group(1)) if match else None
    return None

# Looks up frequency of entries from the database
def lookup_frequency(text, reading=None):
    """Frequency rank of a term, from the highest-priority dictionary that has one.

    Entries can also be tied to one reading: {"reading": ..., "frequency": ...}.
    Those only count when they match the reading given, the way Yomitan
    filters them, so 打 read だ never gets the rank of 打 read ダース. With no
    reading given, any entry counts.
    """
    cursor.execute('''
        SELECT tm.data FROM term_meta tm
        JOIN dictionaries d ON tm.dictionary_id = d.id
        WHERE tm.term = ? AND tm.type = 'freq' AND d.enabled = 1
        ORDER BY d.priority ASC
    ''', (text,))
    for (raw,) in cursor.fetchall():
        data = json.loads(raw)
        if isinstance(data, dict) and 'reading' in data:
            if reading is not None and data['reading'] != reading:
                continue
            data = data.get('frequency')
        number = _freq_number(data)
        if number is not None:
            return number
    return None

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
_KATA_TO_HIRA = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})


def _candidates(word):
    """Forms worth looking up, best guess first.

    UniDic's `lemma` is the lexeme, which is often an archaic orthography the
    text never used: 矢張り for やっぱり, 只 for ただ, 其の for その. Its
    `orthBase` is the base form as written, which is usually what a dictionary
    indexes -- but not always, since it turns んだ's ん into ん rather than の.
    Neither wins outright, so both are offered and the caller picks by how
    common the result is.
    """
    f = word.feature
    surface = word.surface
    lemma = f.lemma or surface
    # UniDic tags loanwords as "キャンプ-camp", which cannot match anything.
    if '-' in lemma:
        lemma = lemma.split('-', 1)[0]
    orth = f.orthBase or surface

    # Nouns keep the written form first: their lemma is often a katakana
    # reading (篠崎 -> シノザキ) that no dictionary indexes.
    order = (surface, orth, lemma) if f.pos1 == '名詞' else (orth, lemma, surface)
    out = []
    for c in order:
        if c and c not in out:
            out.append(c)
    # UniDic normalises the じる verbs to their ずる form: 感じる -> 感ずる,
    # which is a real word but orders of magnitude rarer.
    for c in list(out):
        if c.endswith('ずる'):
            alt = c[:-2] + 'じる'
            if alt not in out:
                out.append(alt)
    return out

# Longest merge to attempt. 5 covers 図書館情報学科 and どうしようもない
# without checking combinations nobody would look up.
MAX_MERGE = 5


def _terms_exist(surfaces):
    """Surface -> its dictionary reading, for the surfaces that exist."""
    if not surfaces:
        return {}
    q = ','.join('?' * len(surfaces))
    cur = _cursor()
    cur.execute(f'SELECT term, reading FROM terms WHERE term IN ({q})', surfaces)
    return {row[0]: row[1] for row in cur.fetchall()}


def _merge(words, sentence):
    """Fold adjacent short-unit tokens into the longest form the dictionary
    knows. UniDic splits at morpheme boundaries, which is finer than what a
    dictionary lookup wants: 学生証 arrives as 学生 + 証, and looking up
    either half separately is not what the reader asked about.
    """
    out = []
    i = 0
    while i < len(words):
        # Every merge starting here, longest first.
        cands = []
        for n in range(min(MAX_MERGE, len(words) - i), 1, -1):
            # Never end a merge on the particle の. Some dictionaries have
            # entries like 水の or てるの, but the reader hovering 水 wants 水.
            last = words[i + n - 1]
            if last['surface'] == 'の' and last.get('pos') == '助詞':
                continue
            cands.append((n, sentence[words[i]['start']:words[i + n - 1]['end']]))
        found = _terms_exist([c[1] for c in cands])
        for n, surface in cands:
            if surface in found:
                out.append({
                    'surface': surface,
                    'lemma': surface,
                    'candidates': [surface],
                    'reading': found.get(surface, ''),
                    'pos': '',
                    'start': words[i]['start'],
                    'end': words[i + n - 1]['end'],
                })
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out

def tokenize(sentence):
    tagger = _get_tagger()
    if tagger is None:
        # No UniDic yet: nothing can be split into words until the
        # first-run download is done.
        return []
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
        cands = _candidates(word)
        kana = word.feature.kana
        words.append({
            'surface': surface,
            'lemma': cands[0],
            'candidates': cands,
            'reading': kana.translate(_KATA_TO_HIRA) if kana else '',
            'pos': word.feature.pos1 or '',
            'start': start,
            'end': end,
        })
    try:
        return _merge(words, sentence)
    except Exception as e:
        import traceback; traceback.print_exc()
        return words
