pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services

Item {
    id: root
    property bool active: false
    implicitWidth: 840
    implicitHeight: 480
    readonly property var sourceErrors: Object.entries(KubeMonitor.snapshot.sources || {}).filter(pair => !pair[1].ok).map(pair => pair[0] + ": " + pair[1].error)
    readonly property string setupMessage: !KubeMonitor.options.enabled ? "Enable monitoring in Caelestia Settings → Kubernetes." : !KubeMonitor.options.context ? "Choose a kubeconfig and context in Caelestia Settings → Kubernetes." : ""
    KubeActivity { active: root.active }

    ColumnLayout {
        anchors.fill: parent
        spacing: Tokens.spacing.medium
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                StyledText {
                    objectName: "kubeHealthLabel"
                    Layout.fillWidth: true
                    text: root.setupMessage ? "Kubernetes" : KubeMonitor.stateLabel
                    color: KubeMonitor.summary.state === "attention" ? Colours.palette.m3tertiary : Colours.palette.m3onSurface
                    font: Tokens.font.title.medium
                }
                StyledText {
                    Layout.fillWidth: true
                    text: KubeMonitor.options.context || "No context selected"
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Colours.palette.m3onSurfaceVariant
                    font: Tokens.font.label.small
                }
            }
            StyledText {
                text: KubeMonitor.summary.issues === undefined ? "" : KubeMonitor.summary.issues + (KubeMonitor.summary.issues === 1 ? " finding" : " findings") + (KubeMonitor.stale ? " · stale" : "")
                font: Tokens.font.label.medium
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Tokens.spacing.small
            Metric {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                icon: "cloud"
                label: "API"
                value: KubeMonitor.stale ? "—" : ({reachable: "Reachable", unreachable: "Unreachable", access_error: "Access error", setup_required: "Setup needed"})[KubeMonitor.summary.api] || "Unknown"
            }
            Metric {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                icon: "dns"
                label: "Nodes ready"
                value: KubeMonitor.metric("nodes_ready", "nodes_total", ["nodes"])
            }
            Metric {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                icon: "settings"
                label: "System pods ready"
                value: KubeMonitor.metric("system_ready", "system_total", ["pods"])
            }
            Metric {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                icon: "deployed_code"
                label: "Workloads available"
                value: KubeMonitor.metric("apps_ready", "apps_total", ["deployments.apps", "statefulsets.apps", "daemonsets.apps"])
            }
        }
        StyledText {
            Layout.fillWidth: true
            visible: !!text
            text: root.setupMessage || [KubeMonitor.error, ...root.sourceErrors].filter(Boolean).join("\n")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 7
            elide: Text.ElideRight
            color: root.setupMessage ? Colours.palette.m3onSurfaceVariant : Colours.palette.m3error
            font: Tokens.font.body.small
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ListView {
                id: list
                anchors.fill: parent
                clip: true
                spacing: Tokens.spacing.small
                boundsBehavior: Flickable.StopAtBounds
                model: ScriptModel { values: KubeMonitor.keys }
                delegate: KubeCard {
                    required property string modelData
                    width: list.width - Tokens.padding.medium
                    record: KubeMonitor.byId[modelData] || ({})
                    stale: KubeMonitor.stale
                }
                ScrollBar.vertical: StyledScrollBar { flickable: list }
            }
            StyledText {
                anchors.centerIn: parent
                visible: !KubeMonitor.keys.length && !root.setupMessage
                text: KubeMonitor.stale ? "Waiting for Kubernetes…" : "No resource data available"
                color: Colours.palette.m3onSurfaceVariant
            }
        }
    }
}
