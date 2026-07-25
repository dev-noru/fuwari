import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

// The way back while the overlay owns the screen and the main window is
// hidden. A dot at rest, so it sits over the game without competing with it;
// hovering reveals the exit. The dot itself is the drag grip.
//
// It stays put rather than timing out because it is the only exit: a layer
// surface with no keyboard interactivity cannot take a shortcut without
// stealing focus from the game underneath.
Window {
    id: root
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    // Without this the window inherits the main window as a transient parent,
    // so Qt creates a popup rather than a top level and layershellqt cannot
    // give it a layer surface: visible reads true but nothing ever appears.
    transientParent: null
    visible: false

    // compositor logical pixels, like every other position in this app
    property int posX: 0
    property int posY: 0

    readonly property bool expanded: dotArea.containsMouse || exitArea.containsMouse
    // Bright for a moment after activation so it can be found, then it settles
    // back to being unobtrusive.
    property bool introducing: false

    signal dismissed()
    // Surface-local press position, in Qt pixels. The drag is handed to the
    // crate because a surface cannot measure a drag of itself: the compositor
    // pins pointer focus to it until release.
    signal dragStarted(real mx, real my)

    // Clamping has to reserve room for the expanded capsule, or dragging the
    // dot to the right edge would open the exit off screen.
    readonly property int expandedWidth: 150
    width: expanded ? expandedWidth : 22
    height: 26

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
            root.introducing = true
            introTimer.restart()
        } else {
            introTimer.stop()
            root.introducing = false
        }
    }

    Timer {
        id: introTimer
        interval: 2600
        onTriggered: root.introducing = false
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: palette.window
        border.color: palette.highlight
        border.width: 1
        opacity: root.expanded ? 0.96 : 0.0
        Behavior on opacity { NumberAnimation { duration: 130 } }
    }

    Rectangle {
        id: dot
        width: 12
        height: 12
        radius: width / 2
        anchors.left: parent.left
        anchors.leftMargin: 5
        anchors.verticalCenter: parent.verticalCenter
        color: palette.highlight
        // Dim at rest so it reads as a marker rather than a control.
        opacity: root.expanded ? 1.0 : (root.introducing ? 1.0 : 0.45)
        Behavior on opacity { NumberAnimation { duration: 500 } }

        // A slow pulse while introducing, so the eye catches it even at the
        // edge of vision.
        SequentialAnimation on scale {
            running: root.introducing
            loops: Animation.Infinite
            NumberAnimation { to: 1.45; duration: 650; easing.type: Easing.InOutQuad }
            NumberAnimation { to: 1.0;  duration: 650; easing.type: Easing.InOutQuad }
        }
        onScaleChanged: if (!root.introducing && scale !== 1.0) scale = 1.0

        MouseArea {
            id: dotArea
            anchors.fill: parent
            // Widened to the collapsed window so the dot is easy to grab,
            // without making the target bigger than it looks once expanded.
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.OpenHandCursor
            onPressed: (mouse) => root.dragStarted(mouse.x + dot.x - 5,
                                                   mouse.y + dot.y - 5)
        }
    }

    Text {
        id: exitLabel
        visible: root.expanded
        anchors.left: dot.right
        anchors.leftMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        text: "✕  Exit overlay"
        font.pointSize: 9
        font.family: "Noto Sans CJK JP"
        color: exitArea.containsMouse ? palette.highlight : palette.windowText

        MouseArea {
            id: exitArea
            anchors.fill: parent
            anchors.margins: -4
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.dismissed()
        }
    }
}
