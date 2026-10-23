pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.modules.nexus.common

ColumnLayout {
    id: root
    property string profile: ""
    readonly property var options: profile ? (VmPreferences.data.machines?.[profile] || ({})) : (VmPreferences.data.ssh || ({}))
    spacing: Tokens.spacing.extraSmall / 2
    enabled: VmPreferences.ready

    TextFieldRow {
        first: true
        visible: !!root.profile
        label: "SSH host"
        subtext: "Leave empty to use the detected IP"
        placeholderText: "Automatic"
        value: root.options.host || ""
        maximumLength: 253
        onEditingFinished: value => VmPreferences.setSsh(root.profile, "host", value.trim())
    }
    TextFieldRow {
        first: !root.profile
        objectName: root.profile ? "vmSshProfileUser" : "vmSshDefaultUser"
        label: "SSH username"
        subtext: root.profile ? "Leave empty to use the default" : "Leave empty to ask in the terminal"
        placeholderText: root.profile ? "Default" : "Ask each time"
        value: root.options.username || ""
        maximumLength: 64
        onEditingFinished: value => VmPreferences.setSsh(root.profile, "username", value.trim())
    }
    StepperRow {
        objectName: root.profile ? "vmSshProfilePort" : "vmSshDefaultPort"
        label: "SSH port"
        subtext: root.profile ? "0 uses the default port" : "Port used by the SSH client"
        value: root.options.port ?? 0
        from: root.profile ? 0 : 1
        to: 65535
        onMoved: value => VmPreferences.setSsh(root.profile, "port", Math.round(value))
    }
    StepperRow {
        label: "Connection timeout"
        subtext: root.profile ? "Seconds; 0 uses the default" : "Seconds"
        value: root.options.timeout ?? 0
        from: root.profile ? 0 : 1
        to: 120
        onMoved: value => VmPreferences.setSsh(root.profile, "timeout", Math.round(value))
    }
    TextFieldRow {
        last: true
        label: "SSH identity file"
        subtext: "Optional key path; existing SSH config still applies"
        placeholderText: "Default keys"
        value: root.options.identity_file || ""
        maximumLength: 4096
        onEditingFinished: value => VmPreferences.setSsh(root.profile, "identity_file", value.trim())
    }
}
