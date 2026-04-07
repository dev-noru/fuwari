import QtQuick
import QtQuick.Window
import QtQuick.Controls

// Card Preview Window creation on adding cards.

Window {
  flags: Qt.Tool | Qt.WindowStaysOnTopHint 
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
                        }

                        Text {
                            visible: modelData.type === "audio" || modelData.type === "sentence_audio"
                            text: "▶ Play"
                            color: palette.highlight
                            font.pointSize: 9
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.type === "sentence_audio") {
                                        bridge.play_audio("file://" + root.fields[index].value)
                                    } 
                                    else {
                                        var url = bridge.get_audio(root.fields[0].value, root.fields[1].value)
                                        if (url !== "") bridge.play_audio(url)
                                    }
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
                          var fname = bridge.store_media_file(f.value)
                          flatFields[f.name] = fname ? "[sound:" + fname + "]" : ""
                      } else if (f.type === "image") {
                          var fname = bridge.store_media_file(f.value)
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
  
