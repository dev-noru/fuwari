import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

Item {
    id: dictItem
    SystemPalette { id: palette }

    property var dictList: []
    property string searchText: ""
    property bool importing: false
    property string importStatus: ""

    function load() {
        dictList = JSON.parse(bridge.get_dictionaries())
    }

            Connections {
                target: bridge
                function onDictionaryImported(success) {
                    importing = false
                    importStatus = success ? "✓ Imported!" : "✗ Import failed"
                    dictList = JSON.parse(bridge.get_dictionaries())
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
                    onTextChanged: searchText = text
                }

                BusyIndicator {
                    running: importing
                    visible: importing
                    width: parent.width
                }

                Text {
                    text: importStatus
                    color: importStatus.startsWith("✓") ? "green" : "red"
                    visible: importStatus !== ""
                }

                ListView {
                    width: parent.width
                    height: parent.height - 80
                    model: dictList
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
                    importing = true
                    importStatus = ""
                    bridge.install_dictionary(selectedFile.toString().replace("file://", ""))
                }
            }
          }        
      

