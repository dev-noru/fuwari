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
