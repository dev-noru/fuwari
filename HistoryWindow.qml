import QtQuick
import QtQuick.Window
import QtQuick.Controls
import org.kde.layershell 1.0 as LayerShell

Window {
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint | Qt.WindowDoesNotAcceptFocus
    id: root
    width: 400
    height: 200
    minimumHeight: 150
    minimumWidth: 150
    visible: false
    color: palette.base
    property var historyData: []
    property int posX: 0
    property int posY: 0

    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.margins: Qt.rect(root.posX, root.posY, 0, 0)
    LayerShell.Window.exclusionZone: -1

    x: root.posX
    y: root.posY

    SystemPalette { id: palette; colorGroup: SystemPalette.Active }

    // Opens under the main window. Positions are compositor pixels, same as
    // everywhere else that sets margins.
    function placeNear() {
        var ds = mainWindow.dragScale
        var w = Math.round(root.width * ds)
        var h = Math.round(root.height * ds)
        var px = mainWindow.winX
        var py = mainWindow.winY + mainWindow.ghostH + 8
        if (px + w > mainWindow.screenW) px = mainWindow.screenW - w - 8
        if (px < 0) px = 0
        if (py + h > mainWindow.screenH) py = Math.max(0, mainWindow.winY - h - 8)
        root.posX = px
        root.posY = py
    }

    Connections {
      target: bridge
      function onHistoryChanged() {
        historyData = JSON.parse(bridge.get_history())
      }
    }

    onVisibleChanged: {
        if (visible) {
            historyData = JSON.parse(bridge.get_history())
            placeNear()
        }
    }

    Flickable {
    anchors.fill: parent
    contentHeight: contentCol.implicitHeight
    clip: true
    rightMargin: 8
    ScrollBar.vertical: ScrollBar {
        policy: contentCol.implicitHeight > root.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
        background: Rectangle { color: palette.base }
        contentItem: Rectangle {
            implicitWidth: 6
            color: palette.light
            radius: 3
        }
      }
      Column {
          id: contentCol
          width: parent.width
          spacing: 8
          padding: 10
          topPadding: 15

          Repeater {
              model: root.historyData
              Rectangle {
                  width: contentCol.width - 20
                  height: sentenceFlow.implicitHeight + 12
                  color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.05)
                  border.color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
                  border.width: 1
                  radius: 4
              Text {
                  text: (index + 1) + "."
                  anchors.left: parent.left
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.margins: 6
                  width: 20
                  color: palette.windowText
                  font.family: "Noto Sans CJK JP"
                  font.pointSize: 11
              }
              Flow {
                  id: sentenceFlow
                  anchors.left: parent.left
                  anchors.leftMargin: 26
                  anchors.right: parent.right
                  anchors.rightMargin: 6
                  anchors.top: parent.top
                  anchors.topMargin: 6
                  spacing: 2
                  Repeater {
                      model: modelData.words
                      Rectangle {
                          id: wordChip
                          width: wordText.width + 6
                          height: wordText.height + 4
                          color: "transparent"
                          border.color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.3)
                          border.width: 1
                          radius: 3
                          MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onExited: wordChip.color = "transparent"
                            onEntered: {
                              wordChip.color = Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)

                              var res = bridge.lookup(modelData.lemma)
                              if (res === "") return
                              var results = JSON.parse(res)
                              var first = results[0]

                              definitionWindow.word = first.Kanji
                              definitionWindow.reading = first.Reading
                              definitionWindow.pos = first["Part of Speech"].join(", ")
                              definitionWindow.freq = first.Frequency ? "JPDB: " + first.Frequency : ""
                              definitionWindow.currentResults = results

                              // scene coords inside this window, then offset by
                              // where the window itself sits
                              var ds = mainWindow.dragScale
                              var defW = Math.round(definitionWindow.width * ds)
                              var defH = Math.round(definitionWindow.height * ds)
                              var p = wordChip.mapToItem(null, 0, wordChip.height)
                              var px = root.posX + Math.round(p.x * ds)
                              var py = root.posY + Math.round(p.y * ds) + 4
                              if (px + defW > mainWindow.screenW)
                                px = mainWindow.screenW - defW - 8
                              if (px < 0) px = 0
                              if (py + defH > mainWindow.screenH)
                                py = Math.max(0, root.posY + Math.round(p.y * ds) - wordChip.height - defH - 4)

                              definitionWindow.posX = px
                              definitionWindow.posY = py
                              definitionWindow.visible = true
                            }
                          }
                          Text {
                              id: wordText
                              anchors.centerIn: parent
                              text: modelData.surface
                              color: palette.windowText
                              font.family: "Noto Sans CJK JP"
                              font.pointSize: 10
                          }
                      }
                  }
              }

          }
        }
      }
    }
  }
