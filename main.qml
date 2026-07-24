import QtQuick
import QtQuick.Window
import QtQuick.Controls
import org.kde.layershell 1.0 as LayerShell

Window {
  id: mainWindow
  color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
  flags: Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
  width: 400
  height: 100
  minimumHeight: 50
  minimumWidth: 300
  visible: true

  Component.onCompleted: console.log(
    "screen:", Screen.width, "x", Screen.height,
    "| avail:", Screen.desktopAvailableWidth, "x", Screen.desktopAvailableHeight,
    "| crate:", bridge.screenWidth, "x", bridge.screenHeight,
    "| win:", mainWindow.width, "x", mainWindow.height,
    "| dpr:", Screen.devicePixelRatio)

  property int posX: 0
  property int posY: 0
  // On Wayland we own the position, so posX/posY are authoritative. On X11 the
  // WM can move us without telling QML, so ask Qt where we actually ended up.
  readonly property int winX: mainWindow.wayland ? mainWindow.posX : mainWindow.x
  readonly property int winY: mainWindow.wayland ? mainWindow.posY : mainWindow.y

  // Compositor logical pixels per Qt logical pixel. Derived at runtime rather
  // than hardcoded, so it holds for any display scaling. Falls back to 1 until
  // the Wayland thread has reported an output.
  property real dragScale: (bridge && bridge.screenWidth > 0 && Screen.width > 0)
                           ? bridge.screenWidth / Screen.width
                           : 1.0

  // Margins are in compositor pixels, not Qt pixels, so every position in this
  // file lives in compositor units and anything Qt-sized is multiplied by
  // dragScale to get there.
  property int screenW: (bridge && bridge.screenWidth > 0) ? bridge.screenWidth : Screen.width
  property int screenH: (bridge && bridge.screenHeight > 0) ? bridge.screenHeight : Screen.height

  // the window's size in compositor pixels
  property int ghostW: Math.round(mainWindow.width * mainWindow.dragScale)
  property int ghostH: Math.round(mainWindow.height * mainWindow.dragScale)

  property bool dragging: false
  property bool wayland: bridge ? bridge.isWayland : true

  x: mainWindow.posX
  y: mainWindow.posY

  // Ghost appearance, in Qt units; scaled on the way to the crate.
  // Tune ghostRadius to match your compositor's corner rounding.
  property int ghostBorder: 2
  property int ghostRadius: 12
  property int ghostFillPct: 14

  LayerShell.Window.layer: LayerShell.Window.LayerOverlay
  LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
  LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
  LayerShell.Window.margins: Qt.rect(mainWindow.posX, mainWindow.posY, 0, 0)
  // Measure margins from the output edge rather than the usable area, so these
  // coordinates share an origin with the crate's overlay.
  LayerShell.Window.exclusionZone: -1

  property bool ocrActive: false

  Rectangle {
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    height: gearIcon.height + 5
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
    z: 1

    MouseArea {
      id: dragArea
      anchors.fill: parent
      cursorShape: Qt.OpenHandCursor
      // The compositor pins pointer focus to this surface until the button is
      // released (implicit grab), so motion cannot be tracked here. Hand the
      // drag to the crate, which owns a stationary full-screen overlay and
      // therefore sees real screen coordinates.
      onPressed: (mouse) => {
        if (mainWindow.dragging) return
        mainWindow.dragging = true
        var s = mainWindow.dragScale
        console.log("DRAG start | scale:", s,
                    "| pos:", mainWindow.posX, mainWindow.posY,
                    "| size:", mainWindow.width, mainWindow.height,
                    "| crate:", bridge.screenWidth, bridge.screenHeight)
        bridge.set_drag_style(palette.highlight.toString(),
                              Math.max(1, Math.round(mainWindow.ghostBorder * s)),
                              Math.round(mainWindow.ghostRadius * s),
                              mainWindow.ghostFillPct)
        bridge.start_window_drag(mainWindow.posX, mainWindow.posY,
                                 mainWindow.ghostW, mainWindow.ghostH,
                                 Math.round(mouse.x * s),
                                 Math.round(mouse.y * s))
      }
    }

    Text {
      id: closeIcon
      text: "✕"
      font.pointSize: 11
      color: closeMouse.containsMouse ? "#e06c75" : palette.windowText
      anchors.top: parent.top
      anchors.right: ocrIcon.left
      anchors.margins: 5
      z: 1

      MouseArea {
        id: closeMouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: Qt.quit()
        cursorShape: Qt.PointingHandCursor
      }
    }

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
      sentenceEdit.pendingIndex = -1
    }
    // final position from the crate, in compositor pixels, applied once
    function onWindowMoved(x, y) {
      console.log("DRAG end | crate returned:", x, y)
      var s = mainWindow.dragScale
      var nx = Math.round(x / s)
      var ny = Math.round(y / s)
      mainWindow.posX = Math.max(0, Math.min(mainWindow.screenW - mainWindow.ghostW, x))
      mainWindow.posY = Math.max(0, Math.min(mainWindow.screenH - mainWindow.ghostH, y))
      mainWindow.dragging = false
      bridge.nudge()
    }
    function onWindowDragCancelled() {
      mainWindow.dragging = false
    }
  }

  MouseArea {
    anchors.fill: parent
    z: -1
  }

  Flickable {
    id: sentenceFlick
    anchors.fill: parent
    contentHeight: sentenceArea.height
    clip: true
    ScrollBar.vertical: ScrollBar {
      policy: sentenceArea.height > sentenceFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
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
        property real lastMx: -1
        property real lastMy: -1

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
              sentenceEdit.showLookup(sel, sentenceEdit.selectionStart, sentenceEdit.selectionEnd)
            }
          }
        }
        Timer {
          id: transitTimer
          interval: 120
          onTriggered: sentenceEdit.resolveHover(sentenceEdit.lastMx, sentenceEdit.lastMy)
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

          var dx = mx - lastMx
          var dy = my - lastMy
          lastMx = mx
          lastMy = my

          // Heading toward the popup? Then tokens under the cursor are transit,
          // not intent — leave the popup showing what is actually being read.
          // The timer still resolves it if the cursor stops here.
          if (definitionWindow.visible && Math.abs(dy) > Math.abs(dx)) {
            var popupAbove = definitionWindow.posY < mainWindow.winY
            if (popupAbove ? (dy < 0) : (dy > 0)) {
              transitTimer.restart()
              return
            }
          }

          transitTimer.stop()
          resolveHover(mx, my)
        }

        function resolveHover(mx, my) {
          var idx = tokenAt(charAt(mx, my))
          if (idx === hoverIndex) return
          hoverIndex = idx
          if (idx < 0) {
            hideTimer.restart()
            return
          }
          var tok = bridge.words[idx]
          showLookup(tok.lemma, tok.start, tok.end)
        }

        function leave() {
          transitTimer.stop()
          lastMx = -1
          lastMy = -1
          hoverIndex = -1
          if (definitionWindow.visible) hideTimer.restart()
        }

        function showLookup(term, start, end) {
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

          if (start >= 0) {
            var r = positionToRectangle(start)
            // scene coords handle the Flickable offset and nesting for us
            var p = mapToItem(null, r.x, r.y + r.height)
            console.log("POPUP | win:", mainWindow.posX, mainWindow.posY,
                        "| p.x:", p.x,
                        "| defW/H:", definitionWindow.width, definitionWindow.height,
                        "| screenW/H:", mainWindow.screenW, mainWindow.screenH,
                        "| scale:", mainWindow.dragScale)
            var ds = mainWindow.dragScale
            var defW = Math.round(definitionWindow.width * ds)
            var defH = Math.round(definitionWindow.height * ds)
            var sx = mainWindow.winX + Math.round(p.x * ds)
            if (sx + defW > mainWindow.screenW)
              sx = mainWindow.screenW - defW - 8
            if (sx < 0)
              sx = 0
            // prefer above the window; fall below only when there is no room
            var sy = mainWindow.winY - defH - 4
            if (sy < 0) {
              sy = mainWindow.winY + mainWindow.ghostH + 4
              if (sy + defH > mainWindow.screenH)
                sy = Math.max(0, mainWindow.screenH - defH - 8)
            }
            definitionWindow.posX = sx
            definitionWindow.posY = sy
          
          }

          hideTimer.stop()
          definitionWindow.visible = true
        }
      }
    }
  }

  Rectangle {
    anchors.fill: parent
    z: 1000
    visible: bridge && bridge.ocrLoading
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.85)

    Column {
      anchors.centerIn: parent
      spacing: 12
      BusyIndicator {
        running: bridge && bridge.ocrLoading
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
