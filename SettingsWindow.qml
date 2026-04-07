import QtQuick
import QtQuick.Window
import QtQuick.Controls

// Settings Window 
Window {
    id: root
    color: palette.base
    title: "Settings"
    width: 450
    height: 550
    visible: false
    flags: Qt.Window | Qt.WindowStaysOnTopHint

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
          onTextChanged: root.ankiUrl = text
        }
        Button {
          text: "Refresh"
          onClicked: {
              root.decks = JSON.parse(bridge.get_decks())
              root.noteTypes = JSON.parse(bridge.get_note_types())
          }
        }

        Text { text: "Deck"; color: palette.windowText }
        ComboBox {
            id: deckCombo
            width: parent.width
            model: root.decks
            onCurrentTextChanged: root.selectedDeck = currentText
        }
        
        Text { text: "Note Type"; color: palette.windowText }
        ComboBox {
            id: noteTypeCombo
            width: parent.width
            model: root.noteTypes
        }
        Button {
            text: "Load Fields"
            onClicked: {
                var noteType = root.noteTypes[noteTypeCombo.currentIndex]
                root.fields = JSON.parse(bridge.get_fields(noteType))
            }
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
          }

      }
  }
}


