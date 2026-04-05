from bridge import Bridge
import sys
import os
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


