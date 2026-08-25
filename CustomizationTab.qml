import QtQuick
import QtQuick.Controls

Item {
    SystemPalette { id: palette }
    
    property real uiScale: 1.0
    property int mainWidth: 400
    property int mainHeight: 100
    property int defWidth: 300
    property int defHeight: 200
    property string popupFont: "Noto Sans CJK JP"
    property int popupFontSize: 11
    property string clipboardFont: "Noto Sans CJK JP"
    property int clipboardFontSize: 12
    property bool loadingFonts: false
    property bool saved: false

  function load() {
      loadingFonts = true
      var s = JSON.parse(bridge.get_settings())
        uiScale = s.ui_scale || 1.0
        uiScaleSlider.value = uiScale
        mainWidth = s.main_width || 400
        mainHeight = s.main_height || 100
        defWidth = s.def_width || 300
        defHeight = s.def_height || 200
        mainWidthSpin.value = mainWidth
        mainHeightSpin.value = mainHeight
        defWidthSpin.value = defWidth
        defHeightSpin.value = defHeight
        popupFont = s.popup_font || "Noto Sans CJK JP"
        popupFontSize = s.popup_font_size || 11
        clipboardFont = s.clipboard_font || "Noto Sans CJK JP"
        clipboardFontSize = s.clipboard_font_size || 12
        var fonts = bridge.available_fonts()
        popupFontCombo.model = fonts
        popupFontCombo.currentIndex = fonts.indexOf(popupFont)
        clipboardFontCombo.model = fonts
        clipboardFontCombo.currentIndex = fonts.indexOf(clipboardFont)
        popupFontSizeSpin.value = popupFontSize
        clipboardFontSizeSpin.value = clipboardFontSize
        loadingFonts = false
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15
        topPadding: 20

        Text { text: "Popup Font"; color: palette.windowText }
        Row {
            spacing: 10
            ComboBox {
                id: popupFontCombo
                width: 220
                onCurrentTextChanged: if (!loadingFonts) popupFont = currentText
                contentItem: Text {
                    text: popupFontCombo.displayText
                    color: palette.windowText
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 8
                }
                background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
            }
            SpinBox {
                id: popupFontSizeSpin
                from: 6; to: 32
                value: popupFontSize
                onValueChanged: popupFontSize = value
            }
        }

        Text { text: "Main Text Font "; color: palette.windowText }
        Row {
            spacing: 10
            ComboBox {
                id: clipboardFontCombo
                width: 220
                onCurrentTextChanged: if (!loadingFonts) clipboardFont = currentText
                contentItem: Text {
                    text: clipboardFontCombo.displayText
                    color: palette.windowText
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 8
                }
                background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
            }
            SpinBox {
                id: clipboardFontSizeSpin
                from: 6; to: 32
                value: clipboardFontSize
                onValueChanged: clipboardFontSize = value
            }
        }

        Text { text: "UI Scale (" + uiScaleSlider.value.toFixed(2) + "x)"; color: palette.windowText }
        Slider {
            id: uiScaleSlider
            width: parent.width
            from: 0.5; to: 3.0
            stepSize: 0.05
            value: uiScale
            onValueChanged: uiScale = value
        }

        Text { text: "Main Window Size"; color: palette.windowText }
        Row {
            spacing: 10
            SpinBox {
                id: mainWidthSpin
                from: 300; to: 2000
                value: mainWidth
                onValueChanged: mainWidth = value
            }
            SpinBox {
                id: mainHeightSpin
                from: 50; to: 1000
                value: mainHeight
                onValueChanged: mainHeight = value
            }
        }

        Text { text: "Definition Popup Size"; color: palette.windowText }
        Row {
            spacing: 10
            SpinBox {
                id: defWidthSpin
                from: 150; to: 2000
                value: defWidth
                onValueChanged: defWidth = value
            }
            SpinBox {
                id: defHeightSpin
                from: 150; to: 1000
                value: defHeight
                onValueChanged: defHeight = value
            }
        }
        Text {
            text: "Takes effect next time Fuwari starts."
            color: palette.mid
            wrapMode: Text.WordWrap
            width: parent.width
            font.pixelSize: 11
        }

        Button {
            text: "Save"
            onClicked: {
                var s = JSON.parse(bridge.get_settings())
                s.ui_scale = uiScale
                s.main_width = mainWidth
                s.main_height = mainHeight
                s.def_width = defWidth
                s.def_height = defHeight
                s.popup_font = popupFont
                s.popup_font_size = popupFontSize
                s.clipboard_font = clipboardFont
                s.clipboard_font_size = clipboardFontSize
                bridge.save_settings_slot(JSON.stringify(s))
                saved = true
            }
            contentItem: Text {
                text: parent.text
                color: palette.windowText
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { color: palette.dark; border.color: palette.mid; radius: 2 }
        }
        Text {
            visible: saved
            text: "⚠ Restart Fuwari to apply changes."
            color: "orange"
        }
    }
}
