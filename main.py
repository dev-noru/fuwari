from bridge import Bridge
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


app = QGuiApplication(sys.argv)
app.setDesktopFileName("fuwari")
bridge = Bridge()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("bridge", bridge)
engine.load('Projects/Coding/fuwari/main.qml')
sys.exit(app.exec())


