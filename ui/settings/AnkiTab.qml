import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Item {
    SystemPalette { id: palette }

    property var decks: []
    property var noteTypes: []
    property var fields: []
    property string ankiUrl: ""
    property string selectedDeck: ""

    function load() {
        var s = JSON.parse(bridge.get_settings())
        decks = JSON.parse(bridge.get_decks())
        noteTypes = JSON.parse(bridge.get_note_types())
        deckCombo.currentIndex = decks.indexOf(s.deck)
        noteTypeCombo.currentIndex = noteTypes.indexOf(s.note_type)
        fields = JSON.parse(bridge.get_fields(s.note_type))
        ankiUrl = s.anki_url || "http://127.0.0.1:8765"
        audioBufferCheck.checked = s.sentence_audio_buffer === true
        audioSecondsSlider.value = s.sentence_audio_seconds || 20
        Qt.callLater(function() {
            for (var i = 0; i < fieldRepeater.count; i++) {
                var row = fieldRepeater.itemAt(i)
                var label = row.children[0].text
                var combo = row.children[1]
                if (s.field_map[label]) {
                    combo.currentIndex = combo.model.indexOf(s.field_map[label])
                }
            }
        })
    }
            Flickable {
              anchors.fill: parent
              contentHeight: settingsCol.implicitHeight
              clip: true
              ScrollBar.vertical: ScrollBar {
                  policy: settingsCol.implicitHeight > height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
              }

              Column {
                id: settingsCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 20
                spacing: 15
                topPadding: 20
                bottomPadding: 20
                Text { text: "AnkiConnect URL"; color: palette.windowText }
                TextField {
                  id: ankiUrlField
                  width: parent.width
                  text: ankiUrl
                  color: palette.windowText
                  // Added background styling
                  background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                  onTextChanged: ankiUrl = text
                }
                Button {
                  text: "Refresh"
                  onClicked: {
                      decks = JSON.parse(bridge.get_decks())
                      noteTypes = JSON.parse(bridge.get_note_types())
                  }
                  // Added button styling
                  contentItem: Text {
                      text: parent.text
                      color: palette.windowText
                      horizontalAlignment: Text.AlignHCenter
                      verticalAlignment: Text.AlignVCenter
                  }
                  background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                }

                Text { text: "Deck"; color: palette.windowText }
                ComboBox {
                    id: deckCombo
                    width: parent.width
                    model: decks
                    onCurrentTextChanged: selectedDeck = currentText
                    // Added combobox styling
                    contentItem: Text {
                        text: deckCombo.displayText
                        color: palette.windowText
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 8
                    }
                    background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                }
                
                Text { text: "Note Type"; color: palette.windowText }
                ComboBox {
                    id: noteTypeCombo
                    width: parent.width
                    model: noteTypes
                    // Added combobox styling
                    contentItem: Text {
                        text: noteTypeCombo.displayText
                        color: palette.windowText
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 8
                    }
                    background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                }
                Button {
                    text: "Load Fields"
                    onClicked: {
                        var noteType = noteTypes[noteTypeCombo.currentIndex]
                        fields = JSON.parse(bridge.get_fields(noteType))
                    }
                    // Added button styling
                    contentItem: Text {
                        text: parent.text
                        color: palette.windowText
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                }

                Repeater {
                    id: fieldRepeater
                    model: fields.length > 0 ? ["Word", "Reading", "Furigana", "Sentence", "Sentence Furigana", "Sentence Audio", "Definitions", "Images", "Frequency", "Audio"] : []
                    Row {
                        spacing: 10
                        width: parent.width
                        Text {
                            text: modelData
                            color: palette.windowText
                            width: 170
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            width: parent.width - 190
                            model: ["(none)"].concat(fields)
                            popup.height: 200
                            // Added combobox styling
                            contentItem: Text {
                                text: parent.displayText
                                color: palette.windowText
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                        }
                    }
                  }
                  Text {
                      text: "Sentence Audio"
                      color: palette.windowText
                      font.bold: true
                      topPadding: 10
                  }
                  CheckBox {
                      id: audioBufferCheck
                      text: "Keep the last few seconds of desktop audio for cards"
                      contentItem: Text {
                          text: audioBufferCheck.text
                          color: palette.windowText
                          leftPadding: audioBufferCheck.indicator.width + 6
                          verticalAlignment: Text.AlignVCenter
                          wrapMode: Text.Wrap
                      }
                  }
                  Text {
                      text: "Buffer length: " + Math.round(audioSecondsSlider.value) + " seconds"
                      color: palette.windowText
                      opacity: audioBufferCheck.checked ? 1 : 0.5
                  }
                  Slider {
                      id: audioSecondsSlider
                      width: parent.width
                      from: 5; to: 60
                      stepSize: 1
                      snapMode: Slider.SnapAlways
                      value: 20
                      enabled: audioBufferCheck.checked
                  }
                  Text {
                      width: parent.width
                      // 48 kHz mono 16-bit is 96 KB per second of buffer.
                      text: "Uses about " + (Math.round(audioSecondsSlider.value) * 0.096).toFixed(1) +
                            " MB of memory while on. Needs PipeWire; clips are saved as Opus " +
                            "if ffmpeg is installed, otherwise WAV."
                      color: palette.windowText
                      opacity: 0.6
                      font.pointSize: 8
                      wrapMode: Text.Wrap
                  }

                  Button {
                      text: "Save"
                      onClicked: {
                          var fieldMap = {}
                          for (var i = 0; i < fieldRepeater.count; i++) {
                              var row = fieldRepeater.itemAt(i)
                              var label = row.children[0].text
                              var combo = row.children[1]
                              if (combo.currentText !== "(none)") {
                                  fieldMap[label] = combo.currentText
                              }
                          }
                          var s = JSON.parse(bridge.get_settings())
                          s.anki_url = ankiUrl
                          s.deck = deckCombo.currentText
                          s.note_type = noteTypeCombo.currentText
                          s.field_map = fieldMap
                          s.sentence_audio_buffer = audioBufferCheck.checked
                          s.sentence_audio_seconds = Math.round(audioSecondsSlider.value)
                          bridge.save_settings_slot(JSON.stringify(s))
                          Window.window.visible = false
                      }
                      // Added button styling
                      contentItem: Text {
                          text: parent.text
                          color: palette.windowText
                          horizontalAlignment: Text.AlignHCenter
                          verticalAlignment: Text.AlignVCenter
                      }
                      background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                  }

              }
            }
          }
