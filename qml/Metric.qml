import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.services

StyledRect {
    id: root
    required property string label
    required property string value
    required property string icon

    implicitHeight: row.implicitHeight + Tokens.padding.medium * 2
    implicitWidth: 220
    color: Colours.tPalette.m3surfaceContainer
    radius: Tokens.rounding.medium

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Tokens.padding.medium
        spacing: Tokens.spacing.medium
        MaterialIcon {
            text: root.icon
            color: Colours.palette.m3primary
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            StyledText {
                text: root.label
                color: Colours.palette.m3onSurfaceVariant
                font: Tokens.font.label.small
            }
            StyledText {
                text: root.value
                font: Tokens.font.title.large
            }
        }
    }
}
