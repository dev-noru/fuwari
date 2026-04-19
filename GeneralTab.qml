import QtQuick
import QtQuick.Controls

Item {
    SystemPalette { id: palette }

    property string textSource: "clipboard"
    property string textractorUrl: "ws://localhost:6677"
    property string lunaUrl: "ws://localhost:2333/api/ws/text/origin"
    property bool saved: false

    function load() {
        var s = JSON.parse(bridge.get_settings())
        textSource = s.text_source || "clipboard"
        textractorUrl = s.textractor_ws_url || "ws://localhost:6677"
        lunaUrl = s.lunatranslator_ws_url || "ws://localhost:2333/api/ws/text/origin"
        sourceCombo.currentIndex = ["clipboard", "textractor", "lunatranslator"].indexOf(textSource)
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15
        topPadding: 20

        Text { text: "Text Source"; color: palette.windowText }
        ComboBox {
            id: sourceCombo
            width: parent.width
            model: ["clipboard", "textractor", "lunatranslator"]
            onCurrentTextChanged: textSource = currentText
            contentItem: Text {
                text: sourceCombo.displayText
                color: palette.windowText
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
        }

        Text { text: "Textractor WebSocket URL"; color: palette.windowText; visible: textSource === "textractor" }
        TextField {
            width: parent.width
            visible: textSource === "textractor"
            text: textractorUrl
            color: palette.windowText
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
            onTextChanged: textractorUrl = text
        }

        Text { text: "LunaTranslator WebSocket URL"; color: palette.windowText; visible: textSource === "lunatranslator" }
        TextField {
            width: parent.width
            visible: textSource === "lunatranslator"
            text: lunaUrl
            color: palette.windowText
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
            onTextChanged: lunaUrl = text
        }

        Button {
            text: "Save"
            onClicked: {
                var s = JSON.parse(bridge.get_settings())
                s.text_source = textSource
                s.textractor_ws_url = textractorUrl
                s.lunatranslator_ws_url = lunaUrl
                bridge.save_settings_slot(JSON.stringify(s))
                saved = true
            }
            contentItem: Text {
                text: parent.text
                color: palette.windowText
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
          }
          Text {
              visible: saved
              text: "⚠ Restart Fuwari to apply changes."
              color: "orange"
          }
    }
}
