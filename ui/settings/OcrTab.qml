import QtQuick
import QtQuick.Controls

Item {
    id: root
    SystemPalette { id: palette }

    property bool showAdvanced: false
    property bool joinLines: true
    property bool portalReset: false
    property bool saved: false

    // Scan speed and sensitivity used to be saved as preset names. Kept so
    // a choice saved by an older version still loads as the same number.
    readonly property var legacyScan: ({ fast: 0.25, normal: 0.5, slow: 1.0 })
    readonly property var legacyStale: ({ sensitive: 1.0, normal: 2.0, relaxed: 4.0 })

    function _num(v, fallback) {
        return (typeof v === "number" && isFinite(v)) ? v : fallback
    }

    function load() {
        var s = JSON.parse(bridge.get_settings())
        scanSetting.value = _num(s.ocr_scan_interval, legacyScan[s.ocr_scan_speed] || 0.5)
        staleSetting.value = _num(s.ocr_stale_epsilon, legacyStale[s.ocr_stale_sensitivity] || 2.0)
        confSetting.value = _num(s.ocr_char_confidence, 0.25)
        // Assigning a value equal to the current one fires no change, so the
        // controls are brought into line explicitly.
        scanSetting.sync()
        staleSetting.sync()
        confSetting.sync()
        joinLines = s.ocr_join_lines !== false
        joinCheck.checked = joinLines
        showAdvanced = s.ocr_show_advanced === true
        portalReset = false
        saved = false
    }

    // One tunable number: a preset dropdown always, and in advanced mode a
    // slider and a number box as well, all kept in step. A new advanced
    // setting is one more TunableSetting.
    component TunableSetting: Column {
        id: ts
        property string title
        property string help
        property string advancedHelp
        property var presetLabels: []
        property var presetValues: []
        property real from: 0
        property real to: 1
        property real stepSize: 0.01
        property int decimals: 2
        property real value: 0
        property bool advanced: false
        // The user picked "Custom", which only means something with the
        // slider and number box showing.
        signal customRequested()

        width: parent ? parent.width : 0
        spacing: 6

        SystemPalette { id: pal }

        function presetIndex(v) {
            for (var i = 0; i < presetValues.length; i++)
                if (Math.abs(presetValues[i] - v) < 0.0005)
                    return i
            return presetValues.length          // Custom
        }

        function setValue(v) {
            v = Math.min(to, Math.max(from, v))
            v = Math.round(v / stepSize) * stepSize
            value = Number(v.toFixed(decimals))
        }

        // Pushes value out to every control. Controls only ever write back
        // from the user's own actions (onActivated, onMoved,
        // onEditingFinished), so this cannot loop.
        function sync() {
            combo.currentIndex = presetIndex(value)
            slider.value = value
            box.text = value.toFixed(decimals)
        }

        onValueChanged: sync()
        Component.onCompleted: sync()

        Text { text: ts.title; color: pal.windowText }

        ComboBox {
            id: combo
            width: parent.width
            model: ts.presetLabels.concat(["Custom"])
            onActivated: (index) => {
                if (index < ts.presetValues.length)
                    ts.value = ts.presetValues[index]
                else
                    ts.customRequested()
            }
            contentItem: Text {
                text: combo.displayText
                color: pal.windowText
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
            }
            background: Rectangle { color: pal.dark; border.color: pal.mid; radius: 2 }
        }

        Row {
            id: row
            width: parent.width
            spacing: 10
            visible: ts.advanced

            Slider {
                id: slider
                width: row.width - box.width - row.spacing
                anchors.verticalCenter: parent.verticalCenter
                from: ts.from
                to: ts.to
                stepSize: ts.stepSize
                snapMode: Slider.SnapAlways
                onMoved: ts.setValue(value)
            }

            TextField {
                id: box
                width: 72
                horizontalAlignment: Text.AlignRight
                color: pal.windowText
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                // "C" so a decimal point is accepted whatever the system
                // locale, and a comma is never mistaken for one.
                validator: DoubleValidator {
                    bottom: ts.from
                    top: ts.to
                    decimals: ts.decimals
                    notation: DoubleValidator.StandardNotation
                    locale: "C"
                }
                onEditingFinished: {
                    var v = parseFloat(text)
                    if (isNaN(v))
                        ts.sync()               // put back the last good value
                    else
                        ts.setValue(v)
                }
                background: Rectangle { color: pal.dark; border.color: pal.mid; radius: 2 }
            }
        }

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            font.pixelSize: 11
            color: Qt.rgba(pal.windowText.r, pal.windowText.g, pal.windowText.b, 0.6)
            text: (ts.advanced && ts.advancedHelp !== "") ? ts.advancedHelp : ts.help
        }
    }

    Flickable {
        id: flick
        anchors.fill: parent
        contentHeight: column.implicitHeight
        clip: true
        // Vertical only, so dragging a slider sideways moves the slider
        // rather than trying to scroll the page.
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar {
            policy: column.implicitHeight > flick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            background: Rectangle { color: palette.base }
            contentItem: Rectangle {
                implicitWidth: 6
                color: palette.light
                radius: 3
            }
        }

        Column {
            id: column
            x: 20
            // Room for the 20px margins on both sides, plus the scroll bar.
            width: flick.width - 40 - 8
            spacing: 15
            topPadding: 20
            bottomPadding: 20

            TunableSetting {
                id: scanSetting
                title: "Scan speed"
                help: "How often Fuwari checks the screen for new text."
                advancedHelp: "Seconds between scans. Lower picks up new lines sooner " +
                              "but uses more CPU; higher is easier on battery."
                presetLabels: ["Fast", "Normal", "Slow"]
                presetValues: [0.25, 0.5, 1.0]
                from: 0.1
                to: 2.0
                stepSize: 0.05
                decimals: 2
                advanced: root.showAdvanced
                onCustomRequested: root.showAdvanced = true
            }

            TunableSetting {
                id: staleSetting
                title: "End hover when the screen changes"
                help: "How readily a hover is dropped when the game moves on."
                advancedHelp: "How much the screen around the hovered word must change " +
                              "(average brightness difference) before the hover counts " +
                              "as stale. Raise it if hovers end on their own in animated " +
                              "scenes; lower it if old highlights linger."
                presetLabels: ["Sensitive", "Normal", "Relaxed"]
                presetValues: [1.0, 2.0, 4.0]
                from: 0.5
                to: 10
                stepSize: 0.1
                decimals: 1
                advanced: root.showAdvanced
                onCustomRequested: root.showAdvanced = true
            }

            TunableSetting {
                id: confSetting
                title: "Character filtering"
                help: "How sure OCR must be before it keeps a character."
                advancedHelp: "Minimum recognition confidence. Lower keeps more of small " +
                              "or thin text, like web pages, at the cost of the odd " +
                              "misread; higher drops more, which can split words apart. " +
                              "meikipop uses 0.10."
                presetLabels: ["Lenient", "Standard", "Strict"]
                presetValues: [0.10, 0.25, 0.40]
                from: 0.05
                to: 0.6
                stepSize: 0.01
                decimals: 2
                advanced: root.showAdvanced
                onCustomRequested: root.showAdvanced = true
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
                text: root.showAdvanced
                      ? "Lets words that wrap onto the next line be looked up whole. " +
                        "Turn it off if separate menu entries get merged together."
                      : "Look up words that wrap onto the next line as one word."
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.6)
                wrapMode: Text.WordWrap
                width: parent.width
                font.pixelSize: 11
            }

            Rectangle {
                visible: bridge !== null && bridge.usesPortal
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
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
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.6)
                wrapMode: Text.WordWrap
                width: parent.width
                font.pixelSize: 11
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
            }

            CheckBox {
                id: advancedCheck
                text: "Show advanced settings"
                checked: root.showAdvanced
                onToggled: root.showAdvanced = checked
                contentItem: Text {
                    text: advancedCheck.text
                    color: palette.windowText
                    leftPadding: advancedCheck.indicator.width + 6
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                text: "Save"
                onClicked: {
                    var s = JSON.parse(bridge.get_settings())
                    s.ocr_scan_interval = scanSetting.value
                    s.ocr_stale_epsilon = staleSetting.value
                    s.ocr_char_confidence = confSetting.value
                    s.ocr_join_lines = root.joinLines
                    s.ocr_show_advanced = root.showAdvanced
                    // The numbers above now say everything the old preset
                    // names did.
                    delete s.ocr_scan_speed
                    delete s.ocr_stale_sensitivity
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
}
