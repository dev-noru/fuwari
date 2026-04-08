import os
import sqlite3

DB_PATH = os.path.expanduser('~/.local/share/fuwari/fuwari.db')
def old_schema_exists():
    if not os.path.exists(DB_PATH):
        print("Running migration...")
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jmdict'")
    result = cursor.fetchone()
    conn.close()
    return result is not None

if not os.path.exists(DB_PATH) or old_schema_exists():
    from migrate import main as migrate
    migrate()

from dictionary import DB_PATH
from bridge import Bridge
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine



app = QGuiApplication(sys.argv)
app.setDesktopFileName("fuwari")
bridge = Bridge()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("bridge", bridge)
script_dir = os.path.dirname(os.path.abspath(__file__))
engine.load(os.path.join(script_dir, 'main.qml'))
sys.exit(app.exec())


