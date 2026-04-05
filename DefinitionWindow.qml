import QtQuick
import QtQuick.Window
import QtQuick.Controls

// This is the definition window where the
// definitions of the words are displayed.
Window {
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.X11BypassWindowManagerHint | Qt.WindowDoesNotAcceptFocus
    id: root
    width: 300
    height: 200 
    minimumHeight: 150
    minimumWidth: 150
    visible: false
    color: palette.base
    property var currentResults: []
    property string word: ""
    property string reading: ""
    property string pos: ""
    property string freq: ""

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

            Row {
                width: parent.width
                spacing: 8
                Text {
                    id: wordText2
                    text: root.word
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
                            var fields = {}
                            var audio = bridge.store_audio(wordText2.text, readingText.text)
                            var data = {
                                "Word": wordText2.text,
                                "Reading": readingText.text,
                                "Furigana": wordText2.text + "[" + readingText.text + "]",
                                "Sentence": bridge.sentence,
                                "Sentence Furigana": bridge.sentence,
                                "Definitions": root.currentResults[0].Definitions.join("\n"),
                                "Frequency": freqText.text,
                                "Audio": audio
                            }
                            for (var key in fieldMap) {
                                fields[fieldMap[key]] = data[key] || ""
                            }
                            var result = bridge.add_note(s.deck, s.note_type, JSON.stringify(fields))
                            if (result !== "") {
                                mineIcon.color = "green"
                                Qt.callLater(function() {
                                    mineIcon.color = palette.highlight
                                })
                            }
                        }
                    }
                }
            }

            Text {
                id: readingText
                text: root.reading
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
                                text: modelData.source
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
                                        var url = bridge.get_audio(modelData.Kanji, modelData.Reading)
                                        if (url !== "") bridge.play_audio(url)
                                    }
                                }
                            }
                        }
                        Text {
                            text: modelData.Reading
                            color: palette.windowText
                            font.pointSize: 8
                            font.family: "Noto Sans CJK JP"
                            visible: index > 0
                        }
                        Text {
                            width: parent.width
                            text: modelData.Definitions.join("\n")
                            wrapMode: Text.Wrap
                            color: palette.windowText
                            font.pointSize: 8
                            font.family: "Noto Sans CJK JP"
                        }
                    }
                }
            }
        }
    }
  }  


