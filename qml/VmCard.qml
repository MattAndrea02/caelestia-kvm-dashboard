pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services
import "Format.js" as Format

StyledRect {
    id: root

    required property var vm
    required property bool fresh
    objectName: "vmCard"
    readonly property bool canConnect: fresh && !!vm.can_ssh && GlobalConfig.general.apps.terminal.length > 0

    function connect(): void {
        if (canConnect) {
            Quickshell.execDetached([...GlobalConfig.general.apps.terminal,
                ...VmCommands.python("ssh_connect.py", ["--name=" + vm.name,
                    "--host=" + (vm.address || ""), "--key=" + vm.key])]);
        }
    }

    implicitHeight: layout.implicitHeight + Tokens.padding.medium * 2
    color: Colours.tPalette.m3surfaceContainer
    radius: Tokens.rounding.medium

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Tokens.padding.medium
        spacing: Tokens.spacing.medium

        RowLayout {
            Layout.fillWidth: true
            MaterialIcon {
                text: "dns"
                color: root.vm.up ? Colours.palette.m3primary : Colours.palette.m3onSurfaceVariant
            }
            StyledText {
                Layout.fillWidth: true
                text: root.vm.name || ""
                font: Tokens.font.title.medium
                elide: Text.ElideRight
            }
            StyledText {
                text: root.fresh ? root.vm.state || "Unknown" : "Stale"
                color: root.vm.up && root.fresh ? Colours.palette.m3primary : Colours.palette.m3tertiary
                font: Tokens.font.label.large
            }
            IconTextButton {
                objectName: "vmSshConnect"
                icon: "terminal"
                text: "SSH"
                type: ButtonBase.Tonal
                disabled: !root.canConnect
                onClicked: root.connect()
                ToolTip.visible: hovered
                ToolTip.text: root.vm.address || "Enter the address in your terminal"
                ToolTip.delay: 700
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Tokens.spacing.medium
            Resource {
                icon: "memory"
                label: (root.vm.vcpus ?? "—") + " vCPU"
                value: root.vm.cpu_percent === null || root.vm.cpu_percent === undefined ? "—" : root.vm.cpu_percent.toFixed(1) + "%"
                fraction: (root.vm.cpu_percent ?? 0) / 100
                tip: "CPU usage across the VM’s allocated vCPUs"
            }
            Resource {
                icon: "memory_alt"
                label: "RAM"
                value: (root.vm.guest_used_kib === null || root.vm.guest_used_kib === undefined ? "—" : Format.memory(root.vm.guest_used_kib)) + " / " + Format.memory(root.vm.memory_kib)
                fraction: root.vm.memory_kib ? (root.vm.guest_used_kib ?? 0) / root.vm.memory_kib : 0
                tip: "Guest used / allocated RAM · Host RSS: " + Format.memory(root.vm.rss_kib)
                accent: Colours.palette.m3tertiary
            }
        }

    }

    component Resource: ColumnLayout {
        id: resource
        required property string icon
        required property string label
        required property string value
        required property real fraction
        required property string tip
        property color accent: Colours.palette.m3primary
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        spacing: Tokens.spacing.small
        ToolTip.visible: hover.hovered
        ToolTip.text: tip
        ToolTip.delay: 700
        HoverHandler { id: hover }
        RowLayout {
            MaterialIcon {
                text: resource.icon
                color: resource.accent
                fontStyle: Tokens.font.icon.small
            }
            StyledText {
                text: resource.label
                color: Colours.palette.m3onSurfaceVariant
            }
            Item { Layout.fillWidth: true }
            StyledText {
                text: resource.value
                font: Tokens.font.label.medium
            }
        }
        StyledProgressBar {
            Layout.fillWidth: true
            value: resource.fraction
            fgColour: resource.accent
        }
    }
}
