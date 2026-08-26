import QtQuick
import QtQuick.Controls

Item {
    SystemPalette { id: palette }

    property string textSource: "clipboard"
    property string textractorUrl: "ws://localhost:6677"
    property string lunaUrl: "ws://localhost:2333/api/ws/text/origin"
    property bool saved: false
    // "" means no preference: layer-shell passes a null output and the
    // compositor picks, generally the display last interacted with.
    property string startupOutput: ""
    property bool legacyWindows: false

    function load() {
        var s = JSON.parse(bridge.get_settings())
        textSource = s.text_source || "clipboard"
        textractorUrl = s.textractor_ws_url || "ws://localhost:6677"
        lunaUrl = s.lunatranslator_ws_url || "ws://localhost:2333/api/ws/text/origin"
        sourceCombo.currentIndex = ["clipboard", "textractor", "lunatranslator"].indexOf(textSource)

        legacyWindows = s.legacy_windows === true
        legacyCheck.checked = legacyWindows
        startupOutput = s.startup_output || ""
        var outputs = [""].concat(bridge.available_outputs())
        outputCombo.model = outputs
        var idx = outputs.indexOf(startupOutput)
        // A monitor named in settings but not currently connected still shows,
        // so unplugging a screen does not silently wipe the preference.
        if (idx < 0 && startupOutput !== "") {
            outputs.push(startupOutput)
            outputCombo.model = outputs
            idx = outputs.length - 1
        }
        outputCombo.currentIndex = Math.max(0, idx)
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

        CheckBox {
            id: legacyCheck
            text: "Use ordinary windows (no layer-shell)"
            onCheckedChanged: legacyWindows = checked
            contentItem: Text {
                text: legacyCheck.text
                color: palette.windowText
                leftPadding: legacyCheck.indicator.width + 6
                verticalAlignment: Text.AlignVCenter
            }
        }
        Text {
            text: "The window manager handles moving and placing Fuwari, as it " +
                  "did before layer-shell. Fuwari will no longer float above " +
                  "fullscreen games. Takes effect on restart."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        Text { text: "Open on monitor"; color: palette.windowText; visible: !legacyWindows }
        ComboBox {
            id: outputCombo
            width: parent.width
            visible: !legacyWindows
            model: [""]
            // Blank reads as automatic; the raw "" would look like a glitch.
            displayText: currentText === "" ? "Automatic (compositor decides)" : currentText
            onCurrentTextChanged: startupOutput = currentText
            contentItem: Text {
                text: outputCombo.displayText
                color: palette.windowText
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
        }
        Text {
            text: "Takes effect next time Fuwari starts. Wayland does not let an " +
                  "application move itself between monitors once open."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
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
                s.startup_output = startupOutput
                s.legacy_windows = legacyWindows
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
