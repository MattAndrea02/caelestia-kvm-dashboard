pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import Quickshell
import Quickshell.Io
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services
import qs.modules.nexus.common

PageBase {
    id: root
    title: "Kubernetes"
    objectName: "kubeSettingsPage"
    property var contextNames: []
    property string contextError: ""
    property string requestedPath: ""
    readonly property string kubeconfigPath: VmPreferences.data.kubernetes?.kubeconfig || ""
    readonly property var options: VmPreferences.data.kubernetes || ({})
    readonly property bool shown: visible && !!Window.window?.visible

    function reloadContexts(): void {
        if (!root.shown || !VmPreferences.ready)
            return;
        if (contextReader.running) {
            refreshDelay.restart();
            return;
        }
        root.requestedPath = root.kubeconfigPath;
        contextReader.command = VmCommands.python("kube_monitor.py", ["--contexts", "--kubeconfig=" + root.requestedPath]);
        contextReader.running = true;
    }
    onKubeconfigPathChanged: {
        contextNames = [];
        contextError = "";
        refreshDelay.restart();
    }
    onShownChanged: {
        if (shown)
            refreshDelay.restart();
        else
            contextReader.running = false;
    }
    Component.onCompleted: refreshDelay.restart()

    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: root.cappedWidth
        spacing: Tokens.spacing.extraSmall / 2
        KubeActivity { active: root.shown }
        Timer { id: refreshDelay; interval: 400; onTriggered: root.reloadContexts() }
        Connections {
            target: VmPreferences
            function onReadyChanged(): void { refreshDelay.restart(); }
        }
        Process {
            id: contextReader
            stdout: StdioCollector {
                onStreamFinished: {
                    if (root.requestedPath !== root.kubeconfigPath || !root.shown)
                        return;
                    try {
                        const result = JSON.parse(text);
                        root.contextNames = result.contexts || [];
                        root.contextError = result.error || (root.contextNames.length ? "" : "No contexts found. Configure a kubeconfig on this computer.");
                    } catch (error) {
                        root.contextError = "Could not list Kubernetes contexts.";
                    }
                }
            }
        }
        Variants {
            id: contextItems
            model: root.contextNames
            delegate: MenuItem {
                required property string modelData
                text: modelData
                value: modelData
                icon: "cloud"
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: !!VmPreferences.error
            text: VmPreferences.error
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colours.palette.m3error
        }
        SectionHeader { first: true; text: "Cluster connection" }
        ToggleRow {
            objectName: "kubeEnabled"
            first: true
            text: "Monitor Kubernetes"
            subtext: "Read cluster and application health while visible"
            enabled: VmPreferences.ready
            checked: root.options.enabled ?? false
            onToggled: VmPreferences.setKubernetes("enabled", checked)
        }
        TextFieldRow {
            objectName: "kubeConfigPath"
            label: "Kubeconfig"
            subtext: "Empty uses KUBECONFIG or ~/.kube/config"
            placeholderText: "Default kubeconfig"
            enabled: VmPreferences.ready
            value: root.kubeconfigPath
            maximumLength: 4096
            onEditingFinished: value => VmPreferences.setKubernetes("kubeconfig", value.trim())
        }
        SelectRow {
            objectName: "kubeContext"
            label: "Context"
            subtext: "Only this context is monitored; kubectl's current context is unchanged"
            enabled: VmPreferences.ready && root.contextNames.length > 0
            menuItems: contextItems.instances
            active: menuItems.find(item => item.value === root.options.context) ?? null
            fallbackText: root.options.context || "Select a context"
            fallbackIcon: "cloud"
            onSelected: item => VmPreferences.setKubernetes("context", item.value)
        }
        RowButton {
            last: true
            text: "Refresh contexts"
            icon: "refresh"
            disabled: contextReader.running || !VmPreferences.ready
            onClicked: root.reloadContexts()
        }
        StyledText {
            Layout.fillWidth: true
            visible: !!root.contextError
            text: root.contextError
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colours.palette.m3error
            font: Tokens.font.body.small
        }
        SectionHeader { text: "Monitoring" }
        StepperRow {
            objectName: "kubeInterval"
            first: true
            last: true
            label: "Refresh interval"
            subtext: "Seconds between readings while visible"
            enabled: VmPreferences.ready
            value: root.options.interval ?? 10
            from: 5
            to: 60
            onMoved: value => VmPreferences.setKubernetes("interval", Math.round(value))
        }
        SectionHeader { text: "Connection status" }
        InfoRow {
            first: true
            last: true
            label: "Cluster health"
            subtext: root.options.context || "Select a context above"
            value: KubeMonitor.stateLabel
        }
        StyledText {
            Layout.fillWidth: true
            text: [KubeMonitor.error, ...Object.entries(KubeMonitor.snapshot.sources || {}).filter(pair => !pair[1].ok).map(pair => pair[0] + ": " + pair[1].error)].filter(Boolean).join("\n")
            visible: !!text
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colours.palette.m3error
            font: Tokens.font.body.small
        }
        StyledText {
            Layout.fillWidth: true
            text: "Requires kubectl and a kubeconfig for a reachable cluster. Access must allow reading nodes, pods, Deployments, StatefulSets and DaemonSets across namespaces. Credentials remain in your kubeconfig."
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.small
        }
    }
}
