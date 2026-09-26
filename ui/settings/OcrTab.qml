import QtQuick
import QtQuick.Controls

Item {
    id: root
    SystemPalette { id: palette }

    // Saved as preset names rather than numbers, so settings.json stays
    // readable and the numbers behind them can be retuned in bridge.py
    // without breaking anyone's saved choice.
    readonly property var speedKeys: ["fast", "normal", "slow"]
    readonly property var speedLabels: ["Fast (uses more CPU)", "Normal", "Slow (uses less CPU)"]
    readonly property var staleKeys: ["sensitive", "normal", "relaxed"]
    readonly property var staleLabels: ["Sensitive", "Normal", "Relaxed"]

    property string scanSpeed: "normal"
    property string staleSensitivity: "normal"
    property bool joinLines: true
    property bool portalReset: false
    property bool saved: false

    // An unknown or missing key falls back to "normal", not to whatever
    // happens to be first in the list.
    function _index(keys, key) {
        var i = keys.indexOf(key)
        return i < 0 ? keys.indexOf("normal") : i
    }

    function load() {
        var s = JSON.parse(bridge.get_settings())
        scanSpeed = s.ocr_scan_speed || "normal"
        staleSensitivity = s.ocr_stale_sensitivity || "normal"
        joinLines = s.ocr_join_lines !== false
        speedCombo.currentIndex = _index(speedKeys, scanSpeed)
        staleCombo.currentIndex = _index(staleKeys, staleSensitivity)
        joinCheck.checked = joinLines
        portalReset = false
        saved = false
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15
        topPadding: 20

        Text { text: "Scan speed"; color: palette.windowText }
        ComboBox {
            id: speedCombo
            width: parent.width
            model: root.speedLabels
            onCurrentIndexChanged: root.scanSpeed = root.speedKeys[currentIndex]
            contentItem: Text {
                text: speedCombo.displayText
                color: palette.windowText
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
        }
        Text {
            text: "How often Fuwari checks the screen for new text. Faster picks " +
                  "up new lines sooner; slower is easier on CPU and battery."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        Text { text: "End hover when the screen changes"; color: palette.windowText }
        ComboBox {
            id: staleCombo
            width: parent.width
            model: root.staleLabels
            onCurrentIndexChanged: root.staleSensitivity = root.staleKeys[currentIndex]
            contentItem: Text {
                text: staleCombo.displayText
                color: palette.windowText
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
        }
        Text {
            text: "If the game moves on while you're hovering a word, Fuwari drops " +
                  "the old highlight and reads the new screen. Choose Relaxed if " +
                  "hovers end on their own in scenes with a lot of animation."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        CheckBox {
            id: joinCheck
            text: "Join wrapped lines into one sentence"
            onCheckedChanged: root.joinLines = checked
            contentItem: Text {
                text: joinCheck.text
                color: palette.windowText
                leftPadding: joinCheck.indicator.width + 6
                verticalAlignment: Text.AlignVCenter
            }
        }
        Text {
            text: "Lets words that wrap onto the next line be looked up whole. " +
                  "Turn it off if separate menu entries get merged together."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        Text {
            text: "Screen share"
            color: palette.windowText
            visible: bridge !== null && bridge.usesPortal
        }
        Button {
            visible: bridge !== null && bridge.usesPortal
            text: "Reset screen share selection"
            onClicked: {
                bridge.reset_portal_selection()
                root.portalReset = true
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
            visible: bridge !== null && bridge.usesPortal
            text: root.portalReset
                  ? "Done. You'll be asked which screen to share next time OCR starts."
                  : "Fuwari remembers which screen you shared for OCR. Reset it " +
                    "if you shared the wrong one or your monitors have changed."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        Button {
            text: "Save"
            onClicked: {
                var s = JSON.parse(bridge.get_settings())
                s.ocr_scan_speed = root.scanSpeed
                s.ocr_stale_sensitivity = root.staleSensitivity
                s.ocr_join_lines = root.joinLines
                bridge.save_settings_slot(JSON.stringify(s))
                root.saved = true
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
            visible: root.saved
            text: "Saved. Takes effect the next time OCR starts."
            color: "orange"
        }
    }
}
