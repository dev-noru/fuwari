import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: root
    color: palette.base
    title: "Settings"
    width: 450
    height: 550
    visible: false
    flags: Qt.Window | Qt.WindowStaysOnTopHint

    SystemPalette { id: palette }

    onVisibleChanged: {
        if (visible) {
            ankiTab.load()
            dictTab.load()
            generalTab.load()
        }
    }

    TabBar {
        id: tabBar
        width: parent.width
        background: Rectangle { color: palette.base }

        TabButton {
            text: "Anki"
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
            text: "Dictionaries"
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

        TabButton {
            text: "General"
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
                    color: tabBar.currentIndex === 2 ? palette.highlight : "transparent"
                }
            }
        }
    }

    StackLayout {
        width: parent.width
        anchors.top: tabBar.bottom
        anchors.bottom: parent.bottom
        currentIndex: tabBar.currentIndex

        AnkiTab {
            id: ankiTab
            width: parent.width
            height: parent.height
        }

        DictionariesTab {
            id: dictTab
            width: parent.width
            height: parent.height
        }

        GeneralTab {
            id: generalTab
            width: parent.width
            height: parent.height
        }
    }
}
