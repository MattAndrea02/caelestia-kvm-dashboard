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

Item {
    id: root
    property bool active: false
    implicitWidth: 840
    implicitHeight: 370

    VmMonitor {
        id: monitor
        active: root.active
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Tokens.spacing.medium

        RowLayout {
            Layout.fillWidth: true
            spacing: Tokens.spacing.medium
            Metric {
                Layout.fillWidth: true
                icon: "dns"
                label: "Up"
                value: monitor.ready ? monitor.summary.up + " / " + monitor.summary.total : "—"
            }
            Metric {
                Layout.fillWidth: true
                icon: "memory"
                label: "vCPU allocated"
                value: monitor.ready ? String(monitor.summary.vcpus) : "—"
            }
            Metric {
                Layout.fillWidth: true
                icon: "memory_alt"
                label: "vRAM allocated"
                value: monitor.ready ? Format.memory(monitor.summary.memory_kib) : "—"
            }
        }

        StyledText {
            Layout.fillWidth: true
            Layout.maximumHeight: 60
            visible: !!monitor.error
            text: monitor.error
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            maximumLineCount: 3
            color: Colours.palette.m3error
            font: Tokens.font.label.small
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: list
                anchors.fill: parent
                clip: true
                spacing: Tokens.spacing.medium
                boundsBehavior: Flickable.StopAtBounds
                model: ScriptModel {
                    values: monitor.keys
                }
                delegate: VmCard {
                    required property string modelData
                    width: list.width - Tokens.padding.medium
                    vm: monitor.byId[modelData] || ({})
                    fresh: !monitor.stale
                }
                ScrollBar.vertical: StyledScrollBar {
                    flickable: list
                }
            }

            ColumnLayout {
                anchors.centerIn: parent
                visible: monitor.keys.length === 0
                spacing: Tokens.spacing.medium
                MaterialIcon {
                    Layout.alignment: Qt.AlignHCenter
                    text: "dns"
                    fontStyle: Tokens.font.icon.extraLarge
                    color: Colours.palette.m3onSurfaceVariant
                }
                StyledText {
                    Layout.alignment: Qt.AlignHCenter
                    text: !monitor.ready ? "Waiting for libvirt…" : monitor.stale ? "VM information unavailable" : "No virtual machines found"
                    font: Tokens.font.title.medium
                }
            }
        }

    }
}
