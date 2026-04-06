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



  property string currentDefinition: ""
  property string currentSentence: ""
  Rectangle {
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    height: gearIcon.height + 5
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
    z: 1

      // Settings Icon and Button
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

      // History Icon and Button
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
    }


SystemPalette {
  id: palette
}

// Settings Window 
SettingsWindow { id: settingsWindow }

// Definition Window
DefinitionWindow { id: definitionWindow }

// History Window
HistoryWindow { id: historyWindow }


  MouseArea {
    anchors.fill: parent
    z: -1

  }

  Flickable {
      anchors.fill: parent
      contentHeight: mainFlow.implicitHeight
      clip: true
        ScrollBar.vertical: ScrollBar {
            policy: mainFlow.implicitHeight > mainWindow.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            background: Rectangle {
                color: palette.base
            }
            contentItem: Rectangle {
                implicitWidth: 6
                color: palette.light
                radius: 3
            }
      }

  

Flow {
    id: mainFlow
    width: parent.width
    spacing: 0
    topPadding: 25
    leftPadding: 10
    rightPadding: 10
    Repeater { 
        model: bridge ? bridge.words : []
        Rectangle {
            width: wordText.width
            height: wordText.height
            color: "transparent"
            
            Text {
                id: wordText
                text: modelData.surface
                color: palette.windowText
                font.family: "Noto Sans CJK JP"
                font.pointSize: 11
              }

            
            MouseArea {
                hoverEnabled: true
                anchors.fill: parent
                onExited: {

                  parent.color = "transparent"
                  parent.children[0].color = palette.windowText
                }
                onEntered: {
                currentDefinition = bridge.lookup(modelData.lemma)
                if (currentDefinition === "") {

                    parent.color = "transparent"
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
                parent.children[0].color= palette.highlight
                }
            }
        }
    }
  } 
}
}

