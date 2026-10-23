pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services

StyledRect {
    id: root
    required property var record
    property bool stale: false
    property bool expanded: false
    objectName: "kubeCard"
    readonly property color accent: stale || record.stale ? Colours.palette.m3outline : record.severity === "error" ? Colours.palette.m3error : record.severity === "attention" || record.severity === "unknown" ? Colours.palette.m3tertiary : Colours.palette.m3primary

    implicitHeight: layout.implicitHeight + Tokens.padding.medium * 2
    color: Colours.tPalette.m3surfaceContainer
    radius: Tokens.rounding.medium

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Tokens.padding.medium
        spacing: Tokens.spacing.small
        RowLayout {
            Layout.fillWidth: true
            MaterialIcon {
                text: root.record.kind === "Node" ? "dns" : root.record.severity === "error" ? "error" : "deployed_code"
                color: root.accent
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                StyledText {
                    Layout.fillWidth: true
                    text: root.record.name || ""
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font: Tokens.font.title.small
                }
                StyledText {
                    Layout.fillWidth: true
                    text: [root.record.kind, root.record.namespace].filter(Boolean).join(" · ")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Colours.palette.m3onSurfaceVariant
                    font: Tokens.font.label.small
                }
            }
            StyledText {
                Layout.maximumWidth: 230
                text: (root.stale || root.record.stale ? "Stale · " : "") + (root.record.status || "Unknown")
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: root.accent
                font: Tokens.font.label.medium
            }
            IconButton {
                objectName: "kubeDetailsButton"
                icon: root.expanded ? "expand_less" : "expand_more"
                type: IconButton.Tonal
                onClicked: root.expanded = !root.expanded
                Accessible.name: root.expanded ? "Hide details" : "Show details"
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: !!root.record.reason
            text: root.record.reason || ""
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: root.expanded ? 100 : 2
            elide: Text.ElideRight
            font: Tokens.font.body.small
        }
        StyledText {
            Layout.fillWidth: true
            visible: root.expanded
            text: (root.record.details || []).join("\n") || "No additional conditions reported."
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.small
        }
    }
}
