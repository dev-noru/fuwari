import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Dialogs

Window {
    id: firstWindow
    color: Qt.rgba(palette.window.r, palette.window.g, palette.window.b, 0.9)
    flags: Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    width: 450
    height: 520
    minimumHeight: 350
    minimumWidth: 350
    visible: false

    SystemPalette { id: palette }

    // "" until an import has been tried, then a line saying how it went.
    property string importStatus: ""
    property bool importing: false
    property bool hasDicts: false

    property bool downloading: false
    property real downloadedMb: 0
    property real totalMb: 0
    property string downloadStatus: ""

    Component.onCompleted: hasDicts = bridge.has_dictionaries()

    FileDialog {
        id: importDialog
        title: "Choose a Yomitan dictionary"
        nameFilters: ["Yomitan dictionaries (*.zip)"]
        onAccepted: {
            // The dialog hands back a file:// URL; the importer wants a path.
            var path = decodeURIComponent(
                selectedFile.toString().replace(/^file:\/\//, ""))
            firstWindow.importing = true
            firstWindow.importStatus = "Importing… this can take a minute for large dictionaries."
            bridge.install_dictionary(path)
        }
    }

    Connections {
        target: bridge
        function onUnidicProgress(doneMb, totalMb) {
            firstWindow.downloadedMb = doneMb
            firstWindow.totalMb = totalMb
        }
        function onUnidicDownloadFinished(ok, error) {
            firstWindow.downloading = false
            firstWindow.downloadStatus = ok
                ? ""
                : "The download didn't finish: " + error + ". Check your connection and try again."
        }
        function onDictionaryImported(ok) {
            firstWindow.importing = false
            if (ok)
                firstWindow.hasDicts = true
            firstWindow.importStatus = ok
                ? "Imported. You can import more, or close this window and start reading."
                : "That file couldn't be imported. Make sure it's a Yomitan dictionary .zip."
        }
    }

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

                // No version number here: this window is about getting set
                // up, and a number in it goes stale with every release.
                Text {
                    anchors.centerIn: parent
                    horizontalAlignment: Text.AlignHCenter
                    color: palette.highlight
                    font.bold: true
                    font.pointSize: 16
                    text: "ふわり Fuwari"
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                color: palette.windowText
                font.bold: true
                font.pointSize: 11
                text: "Welcome! Two quick steps to get set up."
            }

            // --- Step 1: UniDic ---------------------------------------------
            Text {
                width: parent.width
                color: palette.windowText
                font.bold: true
                text: (bridge !== null && bridge.unidicReady) ? "1. Word splitter  ✓" : "1. Word splitter"
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: !(bridge !== null && bridge.unidicReady)
                color: palette.windowText
                text: "Fuwari needs UniDic to split sentences into words. It's a " +
                      "one-time download of a few hundred MB (about 770 MB once " +
                      "unpacked), and it's kept when you update Fuwari."
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: !(bridge !== null && bridge.unidicReady) && !firstWindow.downloading
                text: "Download UniDic"
                onClicked: {
                    firstWindow.downloading = true
                    firstWindow.downloadStatus = ""
                    firstWindow.downloadedMb = 0
                    firstWindow.totalMb = 0
                    bridge.download_unidic()
                }
            }

            ProgressBar {
                width: parent.width
                visible: firstWindow.downloading
                // Indeterminate until the server says how big the file is.
                indeterminate: firstWindow.totalMb <= 0
                from: 0
                to: Math.max(1, firstWindow.totalMb)
                value: firstWindow.downloadedMb
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                visible: firstWindow.downloading
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.75)
                text: firstWindow.totalMb > 0
                      ? Math.round(firstWindow.downloadedMb) + " / " + Math.round(firstWindow.totalMb) + " MB"
                      : Math.round(firstWindow.downloadedMb) + " MB"
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: firstWindow.downloadStatus !== ""
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.75)
                text: firstWindow.downloadStatus
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.2)
            }

            // --- Step 2: a dictionary ---------------------------------------
            Text {
                width: parent.width
                color: palette.windowText
                font.bold: true
                text: firstWindow.hasDicts ? "2. Dictionary  ✓" : "2. Dictionary"
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: palette.windowText
                text: "Fuwari uses Yomitan-format dictionaries. Download one from the " +
                      "links below, then import the .zip here. You can add more later " +
                      "from Settings → Dictionaries."
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: firstWindow.importing ? "Importing…" : "Import dictionary…"
                enabled: !firstWindow.importing
                onClicked: importDialog.open()
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: firstWindow.importStatus !== ""
                color: Qt.rgba(palette.windowText.r, palette.windowText.g, palette.windowText.b, 0.75)
                text: firstWindow.importStatus
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
