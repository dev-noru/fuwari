import sqlite3
import os
import json

def main():
    DATA_DIR = os.path.expanduser('~/.local/share/jp_popup')
    SQL_DIR = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
    conn = sqlite3.connect(SQL_DIR)
    cursor = conn.cursor()

    # Jmdict Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jmdict (
            entry_id TEXT,
            text TEXT,
            entry_json TEXT
        )
    ''')

    # Jmnedict table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jmnedict (
            text TEXT PRIMARY KEY,
            entry_json TEXT
        )
    ''')

    # frequency table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frequency (
            word TEXT,
            rank INTEGER
        )
    ''')

    # KANJIDIC table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kanji (
            literal TEXT PRIMARY KEY,
            entry_json TEXT
        )
    ''')

    # User edit table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_edits (
            source TEXT,
            entry_id TEXT,
            field TEXT,
            value TEXT
        )
    ''')

    # History and timestamp table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lookup_history (
            text TEXT,
            timestamp INTEGER,
            mined INTEGER

        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_jmdict_text ON jmdict(text)
    ''')

    def migrate_jmdict():
        with open(os.path.join(DATA_DIR, 'jmdict-eng.json')) as f:
            data = json.load(f)
            for word in data['words']:
                # Iterate and insert row with kanji['text']
                for kanji in word['kanji']:
                    cursor.execute(
                        'INSERT INTO jmdict (entry_id, text, entry_json) VALUES (?, ?, ?)',
                        (word['id'], kanji['text'], json.dumps(word))
                        )
                # Iterate and insert row with kana['text']
                for kana in word['kana']:
                    cursor.execute(
                        'INSERT INTO jmdict (entry_id, text, entry_json) VALUES (?, ?, ?)',
                        (word['id'], kana['text'], json.dumps(word))
                        )

    def migrate_jmnedict():
        with open(os.path.join(DATA_DIR, 'jmnedict-all.json')) as f:
            data = json.load(f)
            for word in data['words']:
                # Iterate and insert row with kanji['text']
                for kanji in word['kanji']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO jmnedict (text, entry_json) VALUES (?, ?)',
                        (kanji['text'], json.dumps(word))
                        )
                # Iterate and insert row with kana['text']
                for kana in word['kana']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO jmnedict (text, entry_json) VALUES (?, ?)',
                        (kana['text'], json.dumps(word))
                        )


    def migrate_frequency():
        with open(os.path.join(DATA_DIR, 'jpdb_freq', 'term_meta_bank_1.json')) as f:
            data = json.load(f)
            for entry in data:
                word = entry[0]
                meta = entry[2]
                # Iterate and insert row with kanji['text']
                if 'value' in meta:
                    rank = meta['value']
                elif 'frequency' in meta:
                    rank = meta['frequency']['value']
                else:
                    continue
                cursor.execute(
                    'INSERT OR IGNORE INTO frequency (word, rank) VALUES (?, ?)',
                    (word, rank)
                    )

    def migrate_kanji():
        with open(os.path.join(DATA_DIR, 'kanjidic2-en.json')) as f:
            data = json.load(f)
            for character in data['characters']:
                cursor.execute(
                     'INSERT OR IGNORE INTO kanji (literal, entry_json) VALUES (?, ?)',
                    (character['literal'], json.dumps(character))

                        )

    migrate_jmdict()
    migrate_jmnedict()
    migrate_frequency()
    migrate_kanji()
    conn.commit()
    conn.close()

if __name__ == '__main__':
    main()
