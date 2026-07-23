import QtQuick
import QtQuick.Window
import QtQuick.Controls

Window {
  id: mainWindow
  color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
  flags: Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
  width: 400
  height: 100
  minimumHeight: 50
  minimumWidth: 300
  visible: true

  property bool ocrActive: false

  Rectangle {
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    height: gearIcon.height + 5
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
    z: 1

    Text {
      id: gearIcon
      text: "⚙"
      font.pointSize: 11
      color: gearMouse.containsMouse ? Qt.hsva(palette.highlight.hsvHue, 0.8, palette.highlight.hsvValue, 1.0) : palette.windowText
      anchors.top: parent.top
      anchors.left: parent.left
      anchors.margins: 5
      z: 1

      MouseArea {
        id: gearMouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: settingsWindow.visible = !settingsWindow.visible
        cursorShape: Qt.PointingHandCursor
      }
    }

    Text {
      id: historyIcon
      text: "☰"
      font.pointSize: 11
      color: historyMouse.containsMouse ? Qt.hsva(palette.highlight.hsvHue, 0.8, palette.highlight.hsvValue, 1.0) : palette.windowText
      anchors.top: parent.top
      anchors.right: parent.right
      anchors.margins: 5
      z: 1

      MouseArea {
        id: historyMouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: historyWindow.visible = !historyWindow.visible
        cursorShape: Qt.PointingHandCursor
      }
    }

    Text {
      id: ocrIcon
      text: "👁"
      font.pointSize: 11
      color: mainWindow.ocrActive
        ? Qt.hsva(palette.highlight.hsvHue, 0.8, palette.highlight.hsvValue, 1.0)
        : ocrMouse.containsMouse
          ? Qt.hsva(palette.highlight.hsvHue, 0.8, palette.highlight.hsvValue, 1.0)
          : palette.windowText
      anchors.top: parent.top
      anchors.right: historyIcon.left
      anchors.margins: 5
      z: 1

      MouseArea {
        id: ocrMouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: {
          bridge.toggle_ocr()
          mainWindow.ocrActive = !mainWindow.ocrActive
        }
        cursorShape: Qt.PointingHandCursor
      }
    }
  }

  SystemPalette { id: palette }

  SettingsWindow { id: settingsWindow }
  DefinitionWindow { id: definitionWindow }
  HistoryWindow { id: historyWindow }
  CardPreviewWindow { id: cardPreviewWindow }

  FirstRunWindow {
    id: firstWindow
    Component.onCompleted: {
      if (!bridge.has_dictionaries()) {
        firstWindow.visible = false
      }
    }
  }

  // grace period so the cursor can travel from the word onto the popup
  Timer {
    id: hideTimer
    interval: 250
    onTriggered: definitionWindow.visible = false
  }

  Connections {
    target: definitionWindow
    function onPopupHoveredChanged() {
      if (definitionWindow.popupHovered)
        hideTimer.stop()
      else if (definitionWindow.visible)
        hideTimer.restart()
    }
  }

  Connections {
    target: bridge
    function onWordsChanged() {
      sentenceEdit.hoverIndex = -1
    }
  }

  MouseArea {
    anchors.fill: parent
    z: -1
  }

  Flickable {
    anchors.fill: parent
    contentHeight: sentenceArea.height
    clip: true
    ScrollBar.vertical: ScrollBar {
      policy: sentenceArea.height > mainWindow.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
      background: Rectangle { color: palette.base }
      contentItem: Rectangle {
        implicitWidth: 6
        color: palette.light
        radius: 3
      }
    }

    Item {
      id: sentenceArea
      width: mainWindow.width
      height: sentenceEdit.implicitHeight + 35

      TextEdit {
        id: sentenceEdit
        x: 10
        y: 25
        width: parent.width - 20
        textFormat: TextEdit.RichText
        text: sentenceEdit.buildHtml(bridge ? bridge.sentence : "", sentenceEdit.hoverIndex)
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: palette.windowText
        font.family: "Noto Sans CJK JP"
        font.pointSize: 11

        property bool shiftHeld: false
        property int hoverIndex: -1

        selectionColor: {
          var light = palette.window.hsvValue >= 0.5
          var c = Qt.darker(palette.highlight, light ? 2.2 : 1.5)
          return Qt.rgba(c.r, c.g, c.b, light ? 0.6 : 0.9)
        }

        MouseArea {
          anchors.fill: parent
          acceptedButtons: Qt.NoButton
          hoverEnabled: true
          cursorShape: sentenceEdit.shiftHeld ? Qt.IBeamCursor : Qt.ArrowCursor
          onPositionChanged: (mouse) => {
            sentenceEdit.shiftHeld = (mouse.modifiers & Qt.ShiftModifier) !== 0
            sentenceEdit.updateHover(mouse.x, mouse.y, mouse.modifiers)
          }
          onExited: {
            sentenceEdit.shiftHeld = false
            sentenceEdit.leave()
          }
        }

        onSelectedTextChanged: selectionTimer.restart()

        Timer {
          id: selectionTimer
          interval: 300
          onTriggered: {
            var sel = sentenceEdit.selectedText.trim()
            if (sel.length > 0) {
              sentenceEdit.showLookup(sel)
            }
          }
        }

        function esc(s) {
          return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        }

        // colour just the hovered token, like the old per-word Text did
        function buildHtml(sentence, idx) {
          if (!sentence) return ""
          var ws = bridge ? bridge.words : []
          if (idx < 0 || idx >= ws.length) return esc(sentence)
          var t = ws[idx]
          return esc(sentence.substring(0, t.start))
               + '<span style="color:' + palette.highlight + '">'
               + esc(sentence.substring(t.start, t.end))
               + '</span>'
               + esc(sentence.substring(t.end))
        }

        // positionAt gives the nearest caret boundary, not the character under
        // the cursor — convert by checking which side of the caret we're on
        function charAt(mx, my) {
          var p = positionAt(mx, my)
          var r = positionToRectangle(p)
          return (mx < r.x) ? p - 1 : p
        }

        function tokenAt(pos) {
          var ws = bridge ? bridge.words : []
          for (var i = 0; i < ws.length; i++)
            if (pos >= ws[i].start && pos < ws[i].end) return i
          return -1
        }

        function updateHover(mx, my, mods) {
          if (mods & Qt.ShiftModifier) return   // selecting: don't touch the text
          if (selectedText.length > 0) return
          var p = charAt(mx, my)
          var idx = tokenAt(p)
          console.log("pos:", p, "-> token:", idx,
                      idx >= 0 ? bridge.words[idx].surface + " [" + bridge.words[idx].start + "," + bridge.words[idx].end + ")" : "none")
          if (idx === hoverIndex) return
          hoverIndex = idx
          if (idx < 0) {
            hideTimer.restart()
            return
          }
          showLookup(bridge.words[idx].lemma)
        }

        function leave() {
          hoverIndex = -1
          if (definitionWindow.visible) hideTimer.restart()
        }

        function showLookup(term) {
          var res = bridge.lookup(term)
          if (res === "") {
            hideTimer.restart()
            return
          }
          var results = JSON.parse(res)
          var first = results[0]
          definitionWindow.word = first.Kanji
          definitionWindow.reading = first.Reading
          definitionWindow.pos = first["Part of Speech"].join(", ")
          definitionWindow.freq = first.Frequency ? "JPDB: " + first.Frequency : ""
          definitionWindow.currentResults = results
          hideTimer.stop()
          definitionWindow.visible = true
        }
      }
    }
  }

  Rectangle {
    anchors.fill: parent
    z: 1000
    visible: bridge.ocrLoading
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.85)

    Column {
      anchors.centerIn: parent
      spacing: 12
      BusyIndicator {
        running: bridge.ocrLoading
        anchors.horizontalCenter: parent.horizontalCenter
      }
      Text {
        text: "Loading OCR model…"
        color: palette.windowText
        font.family: "Noto Sans CJK JP"
        anchors.horizontalCenter: parent.horizontalCenter
      }
    }
  }
}
