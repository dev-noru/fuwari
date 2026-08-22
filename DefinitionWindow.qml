import QtQuick
import QtQuick.Window
import QtQuick.Controls
import org.kde.layershell 1.0 as LayerShell

pragma ComponentBehavior: Bound

Window {
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    id: root
    width: 300
    height: 200
    minimumHeight: 150
    minimumWidth: 150
    visible: false
    color: palette.base
    // Layer-shell surfaces cannot be transients, so this must be null there.
    // In legacy mode the opposite is true: being a child of the main window is
    // the only way a plain Wayland window gets placed anywhere sensible -- the
    // compositor puts it beside its parent, which is how the popup behaved
    // before layer-shell was introduced.
    transientParent: (bridge && bridge.legacyWindows) ? mainWindow : null
    property var currentResults: []
    property string word: ""
    property string reading: ""
    property string pos: ""
    property string freq: ""
    property bool popupHovered: popupHover.hovered
    property int posX: 0
    property int posY: 0

    // Report this window's footprint to the OCR loop. It is drawn over the
    // captured region, so without this its pixels trip the change gate and its
    // own definitions get recognised as game text. Sizes are Qt pixels, scaled
    // to compositor pixels to match the space the OCR region lives in.
    function _reportMask() {
        if (!bridge) return
        if (!visible) { bridge.set_popup_mask(0, 0, 0, 0); return }
        var s = mainWindow.dragScale
        bridge.set_popup_mask(root.posX, root.posY,
                              Math.round(root.width * s),
                              Math.round(root.height * s))
    }
    readonly property bool legacy: bridge ? bridge.legacyWindows : false

    // Margins are double-buffered and only apply on the next frame, so they
    // are re-sent on every move. Merged with the mask report because QML
    // allows only one handler per signal.
    function _moved() {
        if (!root.legacy)
            LayerShell.Window.margins = Qt.rect(root.posX, root.posY, 0, 0)
        _reportMask()
    }

    onVisibleChanged: _reportMask()
    onWidthChanged: _reportMask()
    onHeightChanged: _reportMask()
    onPosXChanged: _moved()
    onPosYChanged: _moved()

    // Applied rather than declared: writing any LayerShell property is what
    // makes this a layer surface, and there is no value meaning "off". In
    // legacy mode the popup is an ordinary window the WM places.
    Component.onCompleted: {
        if (root.legacy) return
        LayerShell.Window.layer = LayerShell.Window.LayerOverlay
        LayerShell.Window.screen = bridge ? bridge.startupScreen : null
        LayerShell.Window.anchors = LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
        LayerShell.Window.keyboardInteractivity = LayerShell.Window.KeyboardInteractivityNone
        LayerShell.Window.exclusionZone = -1
    }

    x: root.posX
    y: root.posY

    SystemPalette { id: palette; colorGroup: SystemPalette.Active }

    Flickable {
        anchors.fill: parent
        contentHeight: contentCol.implicitHeight
        clip: true
        rightMargin: 8

        HoverHandler { id: popupHover }

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

            Row {
                width: parent.width
                spacing: 8
                TextEdit {
                    id: wordText2
                    text: root.word
                    readOnly: true
                    selectByMouse: true
                    wrapMode: Text.Wrap
                    color: palette.windowText
                    font.bold: true
                    font.pointSize: 12
                    font.family: "Noto Sans CJK JP"
                    anchors.verticalCenter: parent.verticalCenter
                }
                Rectangle {
                    color: Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)
                    border.color: palette.highlight
                    border.width: 1
                    radius: 4
                    width: 20
                    height: mineIcon.height + 1
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: 2
                    Text {
                        id: mineIcon
                        anchors.centerIn: parent
                        text: "+"
                        font.pointSize: 10
                        font.bold: true
                        color: palette.highlight
                    }
                    MouseArea {
                        id: mineMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            var s = JSON.parse(bridge.get_settings())
                            var fieldMap = s.field_map
                            var audio = bridge.store_audio(wordText2.text, readingText.text)
                            var data = {
                                "Word": wordText2.text,
                                "Reading": readingText.text,
                                "Furigana": wordText2.text + "[" + readingText.text + "]",
                                "Sentence": bridge.sentence,
                                "Sentence Furigana": bridge.sentence,
                                "Definitions": root.currentResults[0].Definitions.join("\n"),
                                "Image": "",
                                "Frequency": freqText.text,
                                "Sentence Audio": "",
                                "Audio": audio
                            }
                            var typedFields = []
                            for (var key in fieldMap) {
                                typedFields.push({
                                    name: fieldMap[key],
                                    type: key === "Audio" ? "audio" : key === "Sentence Audio" ? "sentence_audio" : key === "Images" ? "image" : "text",
                                    value: data[key] || ""
                                })
                            }
                            cardPreviewWindow.deck = s.deck
                            cardPreviewWindow.noteType = s.note_type
                            cardPreviewWindow.word = wordText2.text
                            cardPreviewWindow.reading = readingText.text
                            cardPreviewWindow.fields = typedFields
                            cardPreviewWindow.visible = true
                        }
                    }
                }
            }

            TextEdit {
                id: readingText
                text: root.reading
                readOnly: true
                selectByMouse: true
                width: parent.width
                wrapMode: Text.Wrap
                color: palette.windowText
                font.pointSize: 9
                font.family: "Noto Sans CJK JP"
            }

            Row {
                spacing: 5
                Rectangle {
                    color: Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)
                    border.color: palette.highlight
                    border.width: 1
                    radius: 4
                    width: posText.width + 12
                    height: posText.height + 6
                    Text {
                        id: posText
                        text: root.pos
                        anchors.centerIn: parent
                        color: palette.windowText
                        font.pointSize: 8
                    }
                }
                Rectangle {
                    color: Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)
                    border.color: palette.highlight
                    border.width: 1
                    radius: 4
                    width: freqText.width + 12
                    height: freqText.height + 6
                    Text {
                        id: freqText
                        text: root.freq
                        anchors.centerIn: parent
                        color: palette.windowText
                        font.pointSize: 8
                    }
                }
            }

            Repeater {
                model: root.currentResults
                Rectangle {
                    id: entryCard
                    required property var modelData
                    required property int index
                    property var entry: modelData
                    width: contentCol.width - 20
                    height: entryCol.implicitHeight + 12
                    color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.05)
                    border.color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
                    border.width: 1
                    radius: 4
                    Column {
                        id: entryCol
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 4
                        Row {
                            spacing: 6
                            Text {
                                text: entryCard.entry.source
                                color: palette.highlight
                                font.pointSize: 8
                                font.bold: true
                            }
                            Text {
                                text: "▶"
                                color: audioBtnMouse.containsMouse
                                    ? Qt.hsva(palette.highlight.hsvHue, 1.0, palette.highlight.hsvValue, 1.0)
                                    : palette.windowText
                                font.pointSize: 8
                                MouseArea {
                                    id: audioBtnMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        var url = bridge.get_audio(entryCard.entry.Kanji, entryCard.entry.Reading)
                                        if (url !== "") bridge.play_audio(url)
                                    }
                                }
                            }
                        }
                        TextEdit {
                            text: entryCard.entry.Kanji
                            readOnly: true
                            selectByMouse: true
                            color: palette.windowText
                            font.pointSize: 9
                            font.bold: true
                            font.family: "Noto Sans CJK JP"
                            visible: entryCard.index > 0
                        }
                        TextEdit {
                            text: entryCard.entry.Reading
                            readOnly: true
                            selectByMouse: true
                            color: palette.windowText
                            font.pointSize: 8
                            font.family: "Noto Sans CJK JP"
                            visible: entryCard.index > 0
                        }

                        Column {
                            id: sensesCol
                            width: parent.width
                            spacing: 9
                            Repeater {
                                model: entryCard.entry.Senses
                                Column {
                                    id: senseCol
                                    required property var modelData
                                    property var sense: modelData
                                    width: sensesCol.width
                                    spacing: 3

                                    Row {
                                        id: glossRow
                                        width: parent.width
                                        spacing: 6

                                        Rectangle {
                                            id: numBadge
                                            color: Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.2)
                                            border.color: palette.highlight
                                            border.width: 1
                                            radius: 4
                                            width: numText.implicitWidth + 10
                                            height: numText.implicitHeight + 4
                                            Text {
                                                id: numText
                                                anchors.centerIn: parent
                                                text: senseCol.sense.num
                                                color: palette.highlight
                                                font.pointSize: 7
                                                font.bold: true
                                            }
                                        }

                                        TextEdit {
                                            width: glossRow.width - (numBadge ? numBadge.width : 0) - glossRow.spacing
                                            text: senseCol.sense.glosses
                                            readOnly: true
                                            selectByMouse: true
                                            wrapMode: Text.Wrap
                                            color: palette.windowText
                                            font.pointSize: 8
                                            font.family: "Noto Sans CJK JP"
                                        }
                                    }

                                    Repeater {
                                        model: senseCol.sense.notes
                                        TextEdit {
                                            required property var modelData
                                            x: 22
                                            width: senseCol.width - 22
                                            text: "※ " + modelData
                                            readOnly: true
                                            selectByMouse: true
                                            wrapMode: Text.Wrap
                                            color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.55)
                                            font.pointSize: 7
                                            font.family: "Noto Sans CJK JP"
                                        }
                                    }

                                    Repeater {
                                        model: senseCol.sense.refs
                                        TextEdit {
                                            required property var modelData
                                            x: 22
                                            width: senseCol.width - 22
                                            text: "→ " + modelData
                                            readOnly: true
                                            selectByMouse: true
                                            wrapMode: Text.Wrap
                                            color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.55)
                                            font.pointSize: 7
                                            font.family: "Noto Sans CJK JP"
                                        }
                                    }
                                }
                            }

                            Row {
                                visible: entryCard.entry.Related && entryCard.entry.Related.length > 0
                                spacing: 6
                                Text {
                                    text: "related forms"
                                    color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.45)
                                    font.pointSize: 7
                                }
                                TextEdit {
                                    text: entryCard.entry.Related ? entryCard.entry.Related.join(" · ") : ""
                                    readOnly: true
                                    selectByMouse: true
                                    color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.7)
                                    font.pointSize: 7
                                    font.family: "Noto Sans CJK JP"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
