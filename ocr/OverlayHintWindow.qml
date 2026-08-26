import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell

Window {
    id: root
    flags: Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    transientParent: null
    visible: false

    property int posX: 0
    property int posY: 0
    property real s: bridge ? bridge.uiScale : 1.0

    readonly property bool expanded: dotArea.containsMouse || exitArea.containsMouse
    readonly property int dotMargin: Math.round(5 * root.s)
    property bool introducing: false

    signal dismissed()
    signal dragStarted(real mx, real my)

    readonly property int expandedWidth: Math.round(150 * root.s)
    readonly property int capsuleHeight: Math.round(28 * root.s)
    width: expanded ? expandedWidth : Math.round(52 * root.s)
    height: Math.round(52 * root.s)

    readonly property bool legacy: bridge ? bridge.legacyWindows : false

    Component.onCompleted: {
        if (root.legacy) return
        LayerShell.Window.layer = LayerShell.Window.LayerOverlay
        LayerShell.Window.screen = bridge ? bridge.startupScreen : null
        LayerShell.Window.anchors = LayerShell.Window.AnchorTop | LayerShell.Window.AnchorLeft
        LayerShell.Window.keyboardInteractivity = LayerShell.Window.KeyboardInteractivityNone
        LayerShell.Window.exclusionZone = -1
    }

    onPosXChanged: if (!root.legacy) LayerShell.Window.margins = Qt.rect(root.posX, root.posY, 0, 0)
    onPosYChanged: if (!root.legacy) LayerShell.Window.margins = Qt.rect(root.posX, root.posY, 0, 0)

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
        width: Math.round(14 * root.s)
        height: Math.round(14 * root.s)
        radius: width / 2
        anchors.left: parent.left
        anchors.leftMargin: Math.round(19 * root.s)
        anchors.verticalCenter: parent.verticalCenter
        color: palette.highlight
        opacity: root.expanded ? 1.0 : (root.introducing ? 1.0 : 0.7)
        Behavior on opacity { NumberAnimation { duration: 500 } }

        border.color: palette.window
        border.width: 2

        MouseArea {
            id: dotArea
            anchors.fill: parent
            anchors.margins: -root.dotMargin
            hoverEnabled: true
            cursorShape: Qt.OpenHandCursor
            onPressed: (mouse) => root.dragStarted(mouse.x + dot.x - root.dotMargin,
                                                   mouse.y + dot.y - root.dotMargin)
        }
    }

    Text {
        id: exitLabel
        visible: root.expanded
        anchors.left: dot.right
        anchors.leftMargin: Math.round(9 * root.s)
        anchors.verticalCenter: parent.verticalCenter
        text: "✕  Exit overlay"
        font.pointSize: 9 * root.s
        font.family: "Noto Sans CJK JP"
        color: exitArea.containsMouse ? palette.highlight : palette.windowText

        MouseArea {
            id: exitArea
            anchors.fill: parent
            anchors.margins: Math.round(-4 * root.s)
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.dismissed()
        }
    }
}
