import QtQuick
import Quickshell

Scope {
    id: root
    property bool active: false
    onActiveChanged: KubeMonitor.subscribe(root, active)
    Component.onCompleted: KubeMonitor.subscribe(root, active)
    Component.onDestruction: KubeMonitor.subscribe(root, false)
}
