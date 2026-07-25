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
    // The window is sized for the ping, which QML clips to the window bounds.
    // The visible capsule is drawn smaller inside it, so the pill stays slim
    // while the ring still has room to expand -- the two used to be the same
    // rectangle, which forced a fat pill to get a large ring.
    readonly property int capsuleHeight: 28
    width: expanded ? expandedWidth : 52
    height: 52

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
        interval: 5000
        onTriggered: root.introducing = false
    }

    Rectangle {
        // The pill. Deliberately not filling the window; see capsuleHeight.
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: root.capsuleHeight
        radius: height / 2
        color: palette.window
        border.color: palette.highlight
        border.width: 1
        opacity: root.expanded ? 0.96 : 0.0
        Behavior on opacity { NumberAnimation { duration: 130 } }
    }

    // Expanding ring, like a sonar ping. Motion outwards from a fixed point
    // catches peripheral vision far better than a dot changing size, which is
    // what makes it findable without having to be permanently bright.
    Rectangle {
        id: ping
        anchors.centerIn: dot
        width: dot.width
        height: dot.height
        radius: width / 2
        color: "transparent"
        border.color: palette.highlight
        border.width: 2
        visible: root.introducing
        opacity: 0

        SequentialAnimation {
            running: root.introducing
            loops: Animation.Infinite
            ParallelAnimation {
                NumberAnimation { target: ping; property: "width";   from: dot.width;  to: dot.width * 3.2;  duration: 1100; easing.type: Easing.OutQuad }
                NumberAnimation { target: ping; property: "height";  from: dot.height; to: dot.height * 3.2; duration: 1100; easing.type: Easing.OutQuad }
                NumberAnimation { target: ping; property: "opacity"; from: 0.85;       to: 0.0;              duration: 1100; easing.type: Easing.OutQuad }
            }
            PauseAnimation { duration: 250 }
        }
    }

    Rectangle {
        id: dot
        width: 14
        height: 14
        radius: width / 2
        anchors.left: parent.left
        // Centred in the collapsed window so the ping expands evenly instead
        // of being cut off against one edge.
        anchors.leftMargin: 19
        anchors.verticalCenter: parent.verticalCenter
        color: palette.highlight
        // Bright enough to spot on a dark game, dim enough not to nag.
        opacity: root.expanded ? 1.0 : (root.introducing ? 1.0 : 0.7)
        Behavior on opacity { NumberAnimation { duration: 500 } }

        // A soft ring at rest so it reads as a control rather than a stray
        // pixel, and stays visible against a background its own colour.
        border.color: palette.window
        border.width: 2

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
