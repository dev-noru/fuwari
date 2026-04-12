import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Settings Window 
Window {
    id: root
    color: palette.base
    title: "Settings"
    width: 450
    height: 550
    visible: false
    flags: Qt.Window | Qt.WindowStaysOnTopHint

    // Added SystemPalette
    SystemPalette { id: palette }

    property var decks: []
    property var noteTypes: []
    property var fields: []
    property string ankiUrl: "http://127.0.0.1:8765"
    property string selectedDeck: ""
    property string selectedNoteType: ""


    onVisibleChanged: {
        if (visible) {
            var s = JSON.parse(bridge.get_settings())
            root.decks = JSON.parse(bridge.get_decks())
            root.noteTypes = JSON.parse(bridge.get_note_types())
            deckCombo.currentIndex = root.decks.indexOf(s.deck)
            noteTypeCombo.currentIndex = root.noteTypes.indexOf(s.note_type)
            root.fields = JSON.parse(bridge.get_fields(s.note_type))
            dictItem.dictList = JSON.parse(bridge.get_dictionaries())
            Qt.callLater (function(){
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
      }


    TabBar{
          id: tabBar
          width: parent.width
          // Added TabBar background
          background: Rectangle { color: palette.base }
              TabButton {
                id: anki
                text: "Anki"
                // Added tab styling with top highlight line
                contentItem: Text {
                    text: parent.text
                    color: palette.windowText
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: palette.base
                    Rectangle {
                        width: parent.width
                        height: 2
                        anchors.top: parent.top
                        color: tabBar.currentIndex === 0 ? palette.highlight : "transparent"
                    }
                }
              }
              TabButton {
                id: dictionaries
                text: "Dictionaries"
                // Added tab styling with top highlight line
                contentItem: Text {
                    text: parent.text
                    color: palette.windowText
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: palette.base
                    Rectangle {
                        width: parent.width
                        height: 2
                        anchors.top: parent.top
                        color: tabBar.currentIndex === 1 ? palette.highlight : "transparent"
                    }
                }
              }
        }

        StackLayout {
          width: parent.width
          anchors.top: tabBar.bottom
          anchors.bottom: parent.bottom
          currentIndex: tabBar.currentIndex
          Layout.fillHeight: true



          Item {
            width: parent.width
            height: parent.height
            Flickable {
              anchors.fill: parent
              contentHeight: settingsCol.implicitHeight
              clip: true
              ScrollBar.vertical: ScrollBar {
                  policy: settingsCol.implicitHeight > root.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
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
                  text: root.ankiUrl
                  color: palette.windowText
                  // Added background styling
                  background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                  onTextChanged: root.ankiUrl = text
                }
                Button {
                  text: "Refresh"
                  onClicked: {
                      root.decks = JSON.parse(bridge.get_decks())
                      root.noteTypes = JSON.parse(bridge.get_note_types())
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
                    model: root.decks
                    onCurrentTextChanged: root.selectedDeck = currentText
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
                    model: root.noteTypes
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
                        var noteType = root.noteTypes[noteTypeCombo.currentIndex]
                        root.fields = JSON.parse(bridge.get_fields(noteType))
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
                    model: root.fields.length > 0 ? ["Word", "Reading", "Furigana", "Sentence", "Sentence Furigana", "Sentence Audio", "Definitions", "Images", "Frequency", "Audio"] : []
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
                            model: ["(none)"].concat(root.fields)
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
                          var s = {
                              anki_url: root.ankiUrl,
                              deck: deckCombo.currentText,
                              note_type: noteTypeCombo.currentText,
                              field_map: fieldMap
                          }
                          bridge.save_settings_slot(JSON.stringify(s))
                          root.visible = false
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
        // Dictionaries Tab
        Item {
            id: dictItem
            width: parent.width
            height: parent.height
            property var dictList: []
            property string searchText: ""
            property bool importing: false
            property string importStatus: ""

            Connections {
                target: bridge
                function onDictionaryImported(success) {
                    dictItem.importing = false
                    dictItem.importStatus = success ? "✓ Imported!" : "✗ Import failed"
                    dictItem.dictList = JSON.parse(bridge.get_dictionaries())
                }
            }

            Column {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 10
                topPadding: 15

                TextField {
                    width: parent.width
                    color: palette.windowText
                    placeholderText: "Search dictionaries..."
                    // Updated background colour
                    background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                    onTextChanged: dictItem.searchText = text
                }

                BusyIndicator {
                    running: dictItem.importing
                    visible: dictItem.importing
                    width: parent.width
                }

                Text {
                    text: dictItem.importStatus
                    color: dictItem.importStatus.startsWith("✓") ? "green" : "red"
                    visible: dictItem.importStatus !== ""
                }

                ListView {
                    width: parent.width
                    height: parent.height - 80
                    model: dictItem.dictList
                    clip: true
                    delegate: Row {
                        width: dictItem.width - 40
                        spacing: 10
                        Text {
                            text: modelData.title
                            color: palette.windowText
                            width: parent.width - 150
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                        }
                        Switch {
                            // Fixed enabled check
                            checked: modelData.enabled == 1
                            onCheckedChanged: bridge.toggle_dictionary(modelData.id, checked)
                        }
                        Button {
                            text: "Delete"
                            height: -60
                            onClicked: {
                                bridge.delete_dictionary(modelData.id)
                                dictItem.dictList = JSON.parse(bridge.get_dictionaries())
                            }
                            contentItem: Text {
                                text: parent.text
                                color: palette.windowText
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            // Updated button colour
                            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                        }
                        Column {
                            Button {
                                text: "▲"
                                width: 30
                                height: 20
                                onClicked: {
                                    bridge.reorder_dictionary(modelData.id, modelData.priority - 1)
                                    dictItem.dictList = JSON.parse(bridge.get_dictionaries())
                                }
                                contentItem: Text {
                                    text: parent.text
                                    color: palette.windowText
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                // Updated button colour
                                background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                            }
                            Button {
                                text: "▼"
                                width: 30
                                height: 20
                                onClicked: {
                                    bridge.reorder_dictionary(modelData.id, modelData.priority + 1)
                                    dictItem.dictList = JSON.parse(bridge.get_dictionaries())
                                }
                                contentItem: Text {
                                    text: parent.text
                                    color: palette.windowText
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                // Updated button colour
                                background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                            }
                        }
                    }
                }

                Button {
                    text: "Install Dictionary"
                    onClicked: fileDialog.open()
                    contentItem: Text {
                        text: parent.text
                        color: palette.windowText
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    // Updated button colour
                    background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
                }
            }

            FileDialog {
                id: fileDialog
                nameFilters: ["Zip files (*.zip)"]
                onAccepted: {
                    dictItem.importing = true
                    dictItem.importStatus = ""
                    bridge.install_dictionary(selectedFile.toString().replace("file://", ""))
                }
            }
          }        
      }
      
}
