import QtQuick
import QtQuick.Window
import QtQuick.Controls

Window {
    id: firstWindow
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
    flags: Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    width: 450
    height: 500
    minimumHeight: 400
    minimumWidth: 350
    visible: false

    SystemPalette { id: palette }

    Flickable {
        anchors.fill: parent
        contentHeight: column.implicitHeight
        clip: true

        ScrollBar.vertical: ScrollBar {
            policy: column.implicitHeight > firstWindow.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            background: Rectangle {
                color: palette.base
            }
            contentItem: Rectangle {
                implicitWidth: 6
                color: palette.light
                radius: 3
            }
        }

        Column {
            id: column
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: firstWindow.width - 40
            spacing: 16
            topPadding: 16
            bottomPadding: 16

            Rectangle {
                width: parent.width
                height: 60
                radius: 8
                color: Qt.rgba(palette.highlight.r, palette.highlight.g, palette.highlight.b, 0.15)
                border.color: palette.highlight
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    horizontalAlignment: Text.AlignHCenter
                    color: palette.highlight
                    font.bold: true
                    font.pointSize: 16
                    text: "ふわり Fuwari v1.2"
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: palette.windowText
                font.bold: true
                font.pointSize: 11
                text: "No dictionaries were found."
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: palette.windowText
                text: "Fuwari now supports Yomitan-format dictionaries. Download your favourites, drop the .zip files into ~/.local/share/fuwari/dictionaries/ and restart."
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
            }

            Text {
                width: parent.width
                color: palette.windowText
                font.bold: true
                text: "What's new in v1.2"
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: palette.windowText
                text: "• Full Yomitan dictionary format support\n• Import any Yomitan dictionary zip\n• Multiple dictionaries with priority ordering\n• JPDB frequency data support\n• Significantly faster lookups"
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
            }

            Text {
                width: parent.width
                color: palette.windowText
                font.bold: true
                text: "Coming in v1.3"
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: palette.windowText
                text: "• Dictionary manager UI\n• Enable/disable and reorder dictionaries"
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                color: palette.windowText
                font.bold: true
                text: "Get dictionaries"
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: palette.highlight
                text: "MarvNC's Yomitan Dictionary Collection"
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.openUrlExternally("https://github.com/MarvNC/yomitan-dictionaries")
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: palette.highlight
                text: "Yomitan Dictionary Page"
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.openUrlExternally("https://yomitan.wiki/dictionaries/")
                }
            }
        }
    }
}
