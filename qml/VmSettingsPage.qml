pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import qs.components
import qs.services
import qs.modules.nexus.common

PageBase {
    id: root
    title: "Virtual machines"
    objectName: "vmSettingsPage"

    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: root.cappedWidth
        spacing: Tokens.spacing.extraSmall / 2

        VmMonitor {
            id: monitor
            active: root.visible
        }
        StyledText {
            Layout.fillWidth: true
            visible: !!VmPreferences.error
            text: VmPreferences.error
            wrapMode: Text.Wrap
            color: Colours.palette.m3error
        }
        SectionHeader {
            first: true
            text: "Libvirt connections"
        }
        ToggleRow {
            first: true
            text: "System VMs"
            subtext: "qemu:///system"
            disabled: !VmPreferences.ready || (checked && VmPreferences.data.uris.length === 1)
            checked: VmPreferences.data.uris?.includes("qemu:///system") ?? false
            onToggled: VmPreferences.setConnection("qemu:///system", checked)
        }
        ToggleRow {
            last: true
            text: "User session VMs"
            subtext: "qemu:///session"
            disabled: !VmPreferences.ready || (checked && VmPreferences.data.uris.length === 1)
            checked: VmPreferences.data.uris?.includes("qemu:///session") ?? false
            onToggled: VmPreferences.setConnection("qemu:///session", checked)
        }
        SectionHeader { text: "Monitoring" }
        StepperRow {
            first: true
            label: "Refresh interval"
            subtext: "Seconds between readings while visible"
            value: VmPreferences.data.interval ?? 1
            from: 1
            to: 60
            enabled: VmPreferences.ready
            onMoved: value => VmPreferences.update("interval", value)
        }
        StepperRow {
            label: "Startup indicator"
            subtext: "Seconds shown after an observed VM start"
            value: VmPreferences.data.startup_seconds ?? 0
            from: 0
            to: 120
            stepSize: 5
            enabled: VmPreferences.ready
            onMoved: value => VmPreferences.update("startup_seconds", value)
        }
        ToggleRow {
            last: true
            text: "ARP address fallback"
            subtext: "Look in the host’s ARP table when DHCP has no address"
            enabled: VmPreferences.ready
            checked: VmPreferences.data.arp_fallback ?? false
            onToggled: VmPreferences.update("arp_fallback", checked)
        }
        SectionHeader { text: "SSH defaults" }
        SshFields { Layout.fillWidth: true }
        Repeater {
            model: ScriptModel { values: monitor.keys }
            delegate: ColumnLayout {
                id: profileSection
                required property string modelData
                Layout.fillWidth: true
                spacing: Tokens.spacing.extraSmall / 2
                SectionHeader {
                    text: monitor.byId[profileSection.modelData]?.name || "Virtual machine"
                }
                SshFields {
                    Layout.fillWidth: true
                    profile: profileSection.modelData
                }
            }
        }
    }
}
