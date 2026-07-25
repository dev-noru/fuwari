import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

// Shown while the overlay owns the screen and the main window is hidden.
//
// It stays up rather than timing out, because it is the only way back: the
// main window is gone, and a layer surface with no keyboard interactivity
// cannot be given a shortcut without taking focus from the game. It fades
// down once read so it is not sitting brightly over the text.
Window {
    id: root
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    // Fixed rather than derived from the label: sizing a Window from a child
    // that is anchored to that same Window is a binding loop, and QML settles
    // it at zero, which yields a window that is mapped but invisible.
    width: 280
    height: 34
    visible: false
    color: "transparent"
    // Without this the window inherits the main window as its transient
    // parent, so Qt creates it as a popup rather than a top level and
    // layershellqt cannot give it a layer surface: it maps as far as QML is
    // concerned but never appears. DefinitionWindow does the same.
    transientParent: null

    // compositor logical pixels, like every other position in this app
    property int posX: 0
    property int posY: 0
    property bool faded: false

    signal dismissed()

    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.margins: Qt.rect(root.posX, root.posY, 0, 0)
    LayerShell.Window.exclusionZone: -1

    x: root.posX
    y: root.posY

    SystemPalette { id: palette; colorGroup: SystemPalette.Active }

    onVisibleChanged: {
        if (visible) {
            root.faded = false
            fadeTimer.restart()
        } else {
            fadeTimer.stop()
        }
    }

    Timer {
        id: fadeTimer
        interval: 4000
        onTriggered: root.faded = true
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: palette.window
        border.color: palette.highlight
        border.width: 1
        opacity: hintMouse.containsMouse ? 1.0 : (root.faded ? 0.5 : 0.95)
        Behavior on opacity { NumberAnimation { duration: 200 } }

        Text {
            id: label
            anchors.centerIn: parent
            text: "Overlay on — click here to exit"
            font.pointSize: 10
            font.family: "Noto Sans CJK JP"
            color: hintMouse.containsMouse ? palette.highlight : palette.windowText
        }

        MouseArea {
            id: hintMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.dismissed()
        }
    }
}
