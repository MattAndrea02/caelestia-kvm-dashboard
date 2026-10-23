pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    id: root

    property bool active: false
    property bool ready: false
    property bool stale: true
    property var keys: []
    property var byId: ({})
    property var summary: ({total: 0, up: 0, inactive: 0, other_active: 0, vcpus: 0, memory_kib: 0})
    property string error: ""

    function accept(data: string): void {
        try {
            const snapshot = JSON.parse(data);
            if (snapshot.fatal) {
                root.error = snapshot.fatal;
                root.stale = true;
                return;
            }
            const next = {};
            for (const vm of snapshot.machines)
                next[vm.key] = vm;
            root.byId = next;
            root.keys = snapshot.machines.map(vm => vm.key);
            root.summary = snapshot.summary;
            root.error = snapshot.errors.join("\n");
            root.ready = true;
            root.stale = !snapshot.connections.some(c => c.ok);
            watchdog.restart();
        } catch (error) {
            root.error = "Could not read VM statistics: " + error;
            root.stale = true;
        }
    }

    onActiveChanged: {
        retry.stop();
        if (active) {
            root.stale = true;
            process.running = true;
            watchdog.restart();
        } else {
            process.running = false;
            watchdog.stop();
        }
    }

    Component.onCompleted: {
        if (active && !process.running) {
            process.running = true;
            watchdog.restart();
        }
    }

    Component.onDestruction: process.running = false

    Process {
        id: process

        command: VmCommands.python("vm_monitor.py", ["--watch"])
        stdout: SplitParser {
            onRead: data => root.accept(data)
        }
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.trim() && root.active)
                    root.error = text.trim();
            }
        }
        onExited: (exitCode, exitStatus) => {
            if (root.active) {
                root.stale = true;
                if (!root.error)
                    root.error = "VM monitor stopped. Retrying…";
                retry.restart();
            }
        }
    }

    Timer {
        id: retry
        interval: 5000
        onTriggered: {
            if (root.active) {
                process.running = true;
                watchdog.restart();
            }
        }
    }

    Timer {
        id: watchdog
        // Accommodates the maximum configurable 60-second sampling interval.
        interval: 75000
        onTriggered: {
            if (root.active) {
                root.stale = true;
                root.error = "Libvirt is not responding. Retrying…";
                if (process.running)
                    process.signal(9);
                else
                    retry.restart();
            }
        }
    }
}
