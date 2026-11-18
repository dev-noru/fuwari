import QtQuick
import QtQuick.Window
import QtQuick.Controls

// Card Preview Window creation on adding cards.

Window {
  flags: Qt.Tool | Qt.WindowStaysOnTopHint
  transientParent: (bridge && bridge.legacyWindows) ? mainWindow : null
    SystemPalette { id: palette }
    id: root
    width: 400
    height: 300 
    minimumHeight: 150
    minimumWidth: 150
    visible: false
    color: palette.base
    property var fields: [
        { name: "Word", type: "text", value: "猫" },
        { name: "Reading", type: "text", value: "ねこ" },
        { name: "Sentence", type: "text", value: "猫が好きです。" },
        { name: "Definitions", type: "text", value: "1.) cat\n2.) gato" },
        { name: "Frequency", type: "text", value: "JPDB: 1234" },
        { name: "Audio", type: "audio", value: "" },
    ]
    property string deck: "Japanese"
    property string noteType: "Mining"
    property string word: ""
    property string reading: ""
    // Sentence audio from the rolling buffer, frozen when the card opened.
    // clipStart/clipEnd are the trim handles as fractions of the clip.
    property bool hasClip: false
    property var peaks: []
    property real clipLength: 0
    property real clipStart: 0
    property real clipEnd: 1

    // Whether the clip and the screenshot go on the card. Turning one off
    // keeps it around, so it can be turned back on before adding.
    property bool useClip: true
    property bool useImage: true

    onVisibleChanged: {
        if (visible) {
            // Fresh for every card, or "off" would carry over to the next one.
            useClip = true
            useImage = true
        }
        if (visible && hasClip) {
            peaks = bridge.sentence_audio_peaks(160)
            clipLength = bridge.sentence_audio_length()
            clipStart = 0
            clipEnd = 1
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
                model: root.fields
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
                        Text {
                            text: modelData.name
                            color: palette.highlight
                            font.pointSize: 8
                        }
                        TextArea {
                            id: fieldInput
                            width: parent.width
                            visible: !(modelData.type === "sentence_audio" && root.hasClip)
                            text: modelData.value
                            wrapMode: Text.Wrap
                            color: palette.windowText
                            font.pointSize: 9
                            font.family: "Noto Sans CJK JP"
                            onTextChanged: {
                                var updated = root.fields
                                updated[index].value = text
                                root.fields = updated
                            }
                        }
                        Image {
                            visible: modelData.type === "image" && fieldInput.text !== ""
                            source: modelData.type === "image" ? fieldInput.text : ""
                            width: parent.width
                            height: 120
                            fillMode: Image.PreserveAspectFit
                            opacity: root.useImage ? 1 : 0.3
                        }

                        // Waveform of the buffered audio. Drag on it to move
                        // whichever trim handle is closer to the pointer.
                        Item {
                            id: waveBox
                            visible: modelData.type === "sentence_audio" && root.hasClip
                            width: parent.width
                            height: visible ? 60 : 0
                            opacity: root.useClip ? 1 : 0.3

                            Rectangle {
                                anchors.fill: parent
                                radius: 3
                                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.04)
                            }

                            Row {
                                anchors.fill: parent
                                Repeater {
                                    model: root.peaks
                                    Rectangle {
                                        property real frac: (index + 0.5) / root.peaks.length
                                        width: waveBox.width / root.peaks.length
                                        height: Math.max(1, modelData * waveBox.height)
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: frac >= root.clipStart && frac <= root.clipEnd
                                               ? palette.highlight : palette.mid
                                    }
                                }
                            }

                            Rectangle {
                                x: root.clipStart * waveBox.width - width / 2
                                width: 3; height: parent.height
                                color: palette.highlight
                            }
                            Rectangle {
                                x: root.clipEnd * waveBox.width - width / 2
                                width: 3; height: parent.height
                                color: palette.highlight
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.SizeHorCursor
                                enabled: root.useClip
                                // Keep the Flickable from taking the drag.
                                preventStealing: true
                                property bool movingStart: true
                                function moveTo(px) {
                                    var f = Math.max(0, Math.min(1, px / width))
                                    if (movingStart)
                                        root.clipStart = Math.min(f, root.clipEnd - 0.01)
                                    else
                                        root.clipEnd = Math.max(f, root.clipStart + 0.01)
                                }
                                onPressed: (mouse) => {
                                    var f = mouse.x / width
                                    movingStart = Math.abs(f - root.clipStart) < Math.abs(f - root.clipEnd)
                                    moveTo(mouse.x)
                                }
                                onPositionChanged: (mouse) => { if (pressed) moveTo(mouse.x) }
                            }
                        }

                        Text {
                            visible: waveBox.visible
                            text: (root.clipStart * root.clipLength).toFixed(1) + "s – "
                                  + (root.clipEnd * root.clipLength).toFixed(1) + "s  ("
                                  + ((root.clipEnd - root.clipStart) * root.clipLength).toFixed(1) + "s)"
                            color: palette.windowText
                            opacity: 0.7
                            font.pointSize: 8
                        }

                        Text {
                            visible: modelData.type === "audio" || modelData.type === "sentence_audio"
                            text: "▶ Play"
                            color: palette.highlight
                            opacity: (modelData.type === "sentence_audio" && root.hasClip && !root.useClip) ? 0.4 : 1
                            font.pointSize: 9
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.type === "sentence_audio" && root.hasClip) {
                                        if (!root.useClip) return
                                        var clipPath = bridge.export_sentence_audio(root.clipStart, root.clipEnd)
                                        if (clipPath !== "") bridge.play_audio("file://" + clipPath)
                                    }
                                    else if (modelData.type === "sentence_audio") {
                                        bridge.play_audio("file://" + root.fields[index].value)
                                    } 
                                    else {
                                        var url = bridge.get_audio(root.fields[0].value, root.fields[1].value)
                                        if (url !== "") bridge.play_audio(url)
                                    }
                                }
                            }
                          }
                        // Leave the recording or screenshot off this card.
                        Text {
                            property bool isClip: modelData.type === "sentence_audio" && root.hasClip
                            property bool isImage: modelData.type === "image" && fieldInput.text !== ""
                            property bool used: isClip ? root.useClip : root.useImage
                            visible: isClip || isImage
                            text: used ? "✕ Don't use" : "↺ Use again"
                            color: palette.highlight
                            font.pointSize: 9
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (parent.isClip) root.useClip = !root.useClip
                                    else root.useImage = !root.useImage
                                }
                            }
                        }
                    }
                }   
              }

          Row {
            spacing: 8
            Button {
              text: "Add"
              onClicked: {
                  var flatFields = {}
                  for (var i = 0; i < root.fields.length; i++) {
                      var f = root.fields[i]
                      if (f.type === "audio") {
                          flatFields[f.name] = f.value
                      } else if (f.type === "sentence_audio") {
                          var audioPath = root.hasClip
                              ? (root.useClip ? bridge.export_sentence_audio(root.clipStart, root.clipEnd) : "")
                              : f.value
                          var fname = audioPath ? bridge.store_media_file(audioPath) : ""
                          flatFields[f.name] = fname ? "[sound:" + fname + "]" : ""
                      } else if (f.type === "image") {
                          var fname = (f.value && root.useImage) ? bridge.store_media_file(f.value) : ""
                          flatFields[f.name] = fname ? "<img src='" + fname + "'>" : ""
                      } else {
                          flatFields[f.name] = f.value
                      }
                  }
              
                  bridge.add_note(root.deck, root.noteType, JSON.stringify(flatFields))
                  root.visible = false
              }
            }
            Button {
              text: "Cancel"
              onClicked: root.visible = false
            }
          }
        }
      }
    }
  
