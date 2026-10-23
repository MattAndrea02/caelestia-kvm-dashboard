// Run with tests/run-kubernetes-smoke.py; all settings and API responses are isolated.
import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import qs.services
import qs.modules.nexus
import qs.modules.dashboard.vms

ShellRoot {
    id: root
    property int stage: 0
    property var firstCard
    property real firstTimestamp: 0
    property real deadline: Date.now() + 45000

    function require(value: bool, message: string): void {
        if (!value)
            throw new Error(message);
    }

    FloatingWindow {
        id: dashboardWindow
        visible: true
        implicitWidth: 880
        implicitHeight: 520
        color: Colours.palette.m3surface
        KubeTab {
            id: tab
            anchors.centerIn: parent
            width: implicitWidth
            height: implicitHeight
            active: dashboardWindow.visible
        }
    }
    FloatingWindow {
        id: settingsWindow
        visible: true
        implicitWidth: 1080
        implicitHeight: 850
        color: Colours.palette.m3surface
        Nexus {
            id: nexus
            anchors.fill: parent
            nState.screen: settingsWindow.screen
            nState.isWindow: true
            nState.currentPageIdx: PageRegistry.pages.findIndex(page => page.label === "Kubernetes")
        }
    }
    FileView { id: mode; path: Quickshell.env("KUBE_TEST_MODE_FILE") }
    Timer {
        id: poll
        interval: 100
        running: true
        repeat: true
        onTriggered: {
            try {
                root.require(Date.now() < root.deadline, "Timed out at stage " + root.stage);
                const page = CUtils.findChild(nexus, "kubeSettingsPage");
                if (root.stage === 0 && KubeMonitor.summary.state === "ok" && page?.contextNames.length === 2) {
                    root.require(KubeMonitor.consumers.length === 2, "Tab and settings did not share the monitor");
                    const cards = CUtils.findChildren(tab, "kubeCard");
                    root.require(cards.length > 0, "No resource cards rendered");
                    root.firstCard = cards[0];
                    root.firstCard.expanded = true;
                    root.firstTimestamp = KubeMonitor.snapshot.timestamp;
                    root.stage = 1;
                } else if (root.stage === 1 && KubeMonitor.snapshot.timestamp > root.firstTimestamp) {
                    root.require(CUtils.findChildren(tab, "kubeCard").includes(root.firstCard), "Polling replaced a resource delegate");
                    root.require(root.firstCard.expanded, "Polling collapsed details");
                    mode.setText("degraded");
                    root.stage = 2;
                } else if (root.stage === 2 && KubeMonitor.summary.state === "attention") {
                    root.require(KubeMonitor.summary.nodes_ready === 1, "NotReady node was not counted");
                    root.require(KubeMonitor.keys.some(key => KubeMonitor.byId[key].reason.includes("CrashLoopBackOff")), "Crash loop was not rendered");
                    tab.grabToImage(result => result.saveToFile(Quickshell.env("KUBE_TEST_PREVIEW") + "/cluster.png"));
                    nexus.grabToImage(result => result.saveToFile(Quickshell.env("KUBE_TEST_PREVIEW") + "/settings.png"));
                    mode.setText("partial");
                    root.stage = 3;
                } else if (root.stage === 3 && KubeMonitor.snapshot.sources?.pods?.code === "forbidden") {
                    root.require(KubeMonitor.summary.state === "incomplete", "Partial permissions showed healthy status");
                    root.require(KubeMonitor.keys.some(key => KubeMonitor.byId[key].kind === "Pod" && KubeMonitor.byId[key].stale), "Failed reads did not mark cached rows stale");
                    root.require(KubeMonitor.metric("system_ready", "system_total", ["pods"]) === "—", "A stale metric was shown as current");
                    mode.setText("offline");
                    root.stage = 4;
                } else if (root.stage === 4 && KubeMonitor.summary.api === "unreachable") {
                    const context = CUtils.findChild(nexus, "kubeContext");
                    context.selected(context.menuItems.find(item => item.value === "other"));
                    root.require(KubeMonitor.keys.length === 0, "Context switch retained the previous cluster");
                    CUtils.findChild(nexus, "kubeInterval").moved(6);
                    root.stage = 5;
                } else if (root.stage === 5 && KubeMonitor.snapshot.selection?.context === "other" && !VmPreferences.saving) {
                    root.require(!KubeMonitor.keys.length, "Unavailable new context inherited previous rows");
                    settingsWindow.visible = false;
                    dashboardWindow.visible = false;
                    root.stage = 6;
                } else if (root.stage === 6 && !KubeMonitor.running) {
                    root.require(KubeMonitor.consumers.length === 0, "Hidden views still consume the monitor");
                    console.log("KUBERNETES_SMOKE_PASSED");
                    poll.stop();
                    Qt.quit();
                }
            } catch (error) {
                console.error("KUBERNETES_SMOKE_FAILED", error);
                poll.stop();
                Qt.quit();
            }
        }
    }
}
