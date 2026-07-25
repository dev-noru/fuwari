import os
import signal
import sys
import sqlite3
import tracemalloc

# FUWARI_MEMTRACE=1 reports, every 15s, which lines are holding the most
# memory and how that has changed since the previous report. Off by default:
# tracing every allocation slows the interpreter noticeably.
if os.getenv('FUWARI_MEMTRACE') == '1':
    tracemalloc.start(12)

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

from bridge import Bridge
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

app = QGuiApplication(sys.argv)
app.setDesktopFileName("fuwari")

# Qt swallows exceptions raised inside a slot, so a KeyboardInterrupt landing in
# a QTimer callback prints a traceback and the loop carries on. Restoring the C
# default handler makes Ctrl+C terminate the process, which matters when the
# main window is hidden behind the overlay and there is nothing to click.
signal.signal(signal.SIGINT, signal.SIG_DFL)

bridge = Bridge()

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("bridge", bridge)

script_dir = os.path.dirname(os.path.abspath(__file__))
engine.load(os.path.join(script_dir, 'main.qml'))

if not engine.rootObjects():
    sys.exit("Failed to load main.qml — see the QML errors above")

# The window is needed to force a wl_surface commit after moving: layer-shell
# margins are double-buffered and do not apply until the next frame.
bridge.set_window(engine.rootObjects()[0])

if os.getenv('FUWARI_MEMTRACE') == '1':
    from PySide6.QtCore import QTimer as _QTimer
    _mem_state = {'prev': None, 'n': 0}

    def _report_memory():
        snap = tracemalloc.take_snapshot().filter_traces((
            tracemalloc.Filter(False, tracemalloc.__file__),
        ))
        cur, peak = tracemalloc.get_traced_memory()
        _mem_state['n'] += 1
        print(f"\n--- memtrace #{_mem_state['n']}  traced={cur/1e6:.0f}MB "
              f"peak={peak/1e6:.0f}MB ---")
        if _mem_state['prev'] is not None:
            print("  biggest growth since last report:")
            for st in snap.compare_to(_mem_state['prev'], 'lineno')[:6]:
                if st.size_diff <= 0:
                    continue
                print(f"    +{st.size_diff/1e6:7.1f}MB  {st.traceback[0]}")
        print("  largest totals:")
        for st in snap.statistics('lineno')[:6]:
            print(f"    {st.size/1e6:8.1f}MB  {st.count:>7} blocks  {st.traceback[0]}")
        _mem_state['prev'] = snap

    _mem_timer = _QTimer()
    _mem_timer.setInterval(15000)
    _mem_timer.timeout.connect(_report_memory)
    _mem_timer.start()

sys.exit(app.exec())
