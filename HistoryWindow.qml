import QtQuick
import QtQuick.Window
import QtQuick.Controls

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

    Connections {
      target: bridge
      function onHistoryChanged() {
        historyData = JSON.parse(bridge.get_history())
      }
    }
    onVisibleChanged: {
        if (visible) {
            historyData = JSON.parse(bridge.get_history())
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
            width: parent.width 
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
                          width: wordText.width + 6
                          height: wordText.height + 4
                          color: "transparent"
                          border.color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.3)
                          border.width: 1
                          radius: 3
                          MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onExited: {

                              parent.color = "transparent"
                            }
                            onEntered: {
                              currentDefinition = bridge.lookup(modelData.lemma)
                              parent.color = Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)
                              if (currentDefinition === "") {
                                  return
                                  }
                            var results = JSON.parse(currentDefinition)
                            var first = results[0]

                            var pos = parent.mapToGlobal(mouseX, mouseY)

                            var popupX = pos.x
                            var popupY = pos.y + 20

                            if (popupX + definitionWindow.width > Screen.width)
                            popupX = pos.x - definitionWindow.width

                            if (popupY + definitionWindow.height > Screen.height)
                            popupY = pos.y - definitionWindow.height

                            definitionWindow.word = first.Kanji
                            definitionWindow.reading = first.Reading
                            definitionWindow.pos = first["Part of Speech"].join(", ")
                            definitionWindow.freq = first.Frequency ? "JPDB: " + first.Frequency : ""
                            definitionWindow.currentResults = results
                            Qt.callLater(function() {
                                definitionWindow.x = popupX
                                definitionWindow.y = popupY
                                definitionWindow.visible = true
                            })
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
