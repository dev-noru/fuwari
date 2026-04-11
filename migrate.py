import sqlite3
import os
import json
import zipfile

DICT_DIR = os.path.expanduser('~/.local/share/fuwari/dictionaries/')
SQL_DIR = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
os.makedirs(os.path.dirname(SQL_DIR), exist_ok=True)
os.makedirs(DICT_DIR, exist_ok=True)
conn = sqlite3.connect(SQL_DIR)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jmdict'")
if cursor.fetchone():
    conn.close()
    os.remove(SQL_DIR)
    conn = sqlite3.connect(SQL_DIR)
    cursor = conn.cursor()

# dictionaries
#   id, title, author, version, type, priority, enabled
# Dictionary table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dictionaries (
        id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        version TEXT,
        type TEXT,
        priority INTEGER,
        enabled BOOLEAN
    )
''')

# terms
#   id, dictionary_id (FK -> dictionaries.id), term, reading, def_tags, rules, score, definitions (JSON), sequence, term_tags
# terms table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS terms (
        id INTEGER PRIMARY KEY,
        dictionary_id INTEGER,
        term TEXT,
        reading TEXT,
        def_tags TEXT,
        rules TEXT,
        score INTEGER,
        definitions TEXT,
        sequence INTEGER,
        term_tags TEXT,
        FOREIGN KEY (dictionary_id) REFERENCES dictionaries(id)
    )
''')

# term_meta 
#   id(PK), dictionary_id(FK), term, type, data
# terms meta data table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS term_meta (
        id INTEGER PRIMARY KEY,
        dictionary_id INTEGER,
        term TEXT,
        type TEXT,
        data TEXT,
        FOREIGN KEY (dictionary_id) REFERENCES dictionaries(id)
    )
''')

# kanji
#   id(PK), dictionary_id(FK), character, onyomi, kunyomi, tags, meanings, stats
# kanji table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS kanji (
        id INTEGER PRIMARY KEY,
        dictionary_id INTEGER,
        character TEXT,
        onyomi TEXT,
        kunyomi TEXT,
        tags TEXT,
        meanings TEXT,
        stats TEXT,
        FOREIGN KEY (dictionary_id) REFERENCES dictionaries(id)
    )
''')

# kanji_meta
#   id(PK), dictionary_id(FK), kanji, type, data
# kanji meta data table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS kanji_meta (
        id INTEGER PRIMARY KEY,
        dictionary_id INTEGER,
        kanji TEXT,
        type TEXT,
        data TEXT,
        FOREIGN KEY (dictionary_id) REFERENCES dictionaries(id)
    )
""")

# User edit table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_edits (
        dictionary_id INTEGER,
        sequence INTEGER,
        field TEXT,
        value TEXT,
        FOREIGN KEY (dictionary_id) REFERENCES dictionaries(id)
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
cursor.execute('CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_term_meta_term ON term_meta(term)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_kanji_character ON kanji(character)')

# Function to import yomitan style dictionaries
def import_dictionary(zip_path):
    conn = sqlite3.connect(SQL_DIR)
    cursor = conn.cursor()
    with zipfile.ZipFile(zip_path) as f:
        index = f.open('index.json')
        index_data = json.load(index)
        cursor.execute('SELECT id FROM dictionaries WHERE title = ?', (index_data['title'],))
        if cursor.fetchone():
            return
        cursor.execute('SELECT MAX(priority) FROM dictionaries')
        max_priority = cursor.fetchone()[0] or 0
        priority = max_priority + 1
        cursor.execute(
            'INSERT INTO dictionaries (title, author, version, type, priority, enabled) VALUES (?, ?, ?, ?, ?, 1)',
            (index_data['title'], index_data.get('author', ''), index_data.get('version', ''), index_data.get('type', ''), priority)
            )
        dictionary_id = cursor.lastrowid
        # terms table structure and insert
        for filename in f.namelist():
            if filename.startswith('term_bank_'):
                term_file = f.open(filename)
                term_data = json.load(term_file)
                for entry in term_data:
                    term, reading, def_tags, rules, score, definitions, sequence, term_tags = entry
                    cursor.execute(
                    'INSERT INTO terms (dictionary_id, term, reading, def_tags, rules, score, definitions, sequence, term_tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (dictionary_id, term, reading, def_tags, rules, score, json.dumps(definitions), sequence, term_tags))

        # terms_meta_bank structure and insert
        for filename in f.namelist():
            if filename.startswith('term_meta_bank_'):
                term_meta_file = f.open(filename)
                term_meta_data = json.load(term_meta_file)
                for entry in term_meta_data:
                    term, meta_type, meta_data = entry
                    cursor.execute(
                    'INSERT INTO term_meta (dictionary_id, term, type, data) VALUES (?, ?, ?, ?)',
                    (dictionary_id, term, meta_type, json.dumps(meta_data))
                    )

        # kanji structure and insert
        for filename in f.namelist():
            if filename.startswith('kanji_bank_'):
                kanji_file = f.open(filename)
                kanji_data = json.load(kanji_file)
                for entry in kanji_data:
                    character, onyomi, kunyomi, tags, meanings, stats = entry
                    cursor.execute(
                    'INSERT INTO kanji (dictionary_id, character, onyomi, kunyomi, tags, meanings, stats) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (dictionary_id, character, onyomi, kunyomi, tags, json.dumps(meanings), json.dumps(stats))
                    )

        # kanji_meta structure and insert
        for filename in f.namelist():
            if filename.startswith('kanji_meta_bank_'):
                kanji_meta_file = f.open(filename)
                kanji_meta_data = json.load(kanji_meta_file)
                for entry in kanji_meta_data:
                    character, meta_type, meta_data = entry
                    cursor.execute(
                    'INSERT INTO kanji_meta (dictionary_id, kanji, type, data) VALUES (?, ?, ?, ?)',
                    (dictionary_id, character, meta_type, json.dumps(meta_data))
                    )

    conn.commit()
    conn.close()

# Function to scan the users directory for any yomitan dictionaries.
def scan_dictionary():
    for n in os.listdir(DICT_DIR):
        if n.endswith('.zip'):
            import_dictionary(os.path.join(DICT_DIR, n))

scan_dictionary()




