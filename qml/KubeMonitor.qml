pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property var consumers: []
    property var snapshot: ({})
    property var byId: ({})
    property var keys: []
    property bool stale: true
    property string error: ""
    readonly property var options: VmPreferences.data.kubernetes || ({})
    readonly property bool requested: consumers.length > 0 && VmPreferences.ready && !!options.enabled && !!options.context
    readonly property bool running: process.running
    readonly property string selection: JSON.stringify([!!options.enabled, options.kubeconfig || "", options.context || ""])
    readonly property string signature: selection + ":" + (options.interval || 10)
    readonly property var summary: snapshot.summary || ({})
    readonly property string stateLabel: stale && requested ? "Verification incomplete" : ({ok: "No problems detected", attention: "Needs attention", progressing: "Update in progress", incomplete: "Verification incomplete"})[summary.state] || "Not configured"

    function subscribe(owner: var, enabled: bool): void {
        const next = consumers.filter(item => item !== owner);
        if (enabled)
            next.push(owner);
        consumers = next;
    }

    function accept(data: string): void {
        try {
            const next = JSON.parse(data);
            if (next.fatal)
                throw new Error(next.fatal);
            const chosen = next.selection || {};
            if (JSON.stringify([!!chosen.enabled, chosen.kubeconfig || "", chosen.context || ""]) !== selection)
                return;
            if (!next.summary || !Array.isArray(next.records) || !next.sources)
                throw new Error("Invalid snapshot");
            const records = {};
            for (const row of next.records)
                records[row.key] = row;
            snapshot = next;
            byId = records;
            keys = next.records.map(row => row.key);
            error = next.setup || "";
            stale = false;
            watchdog.restart();
        } catch (failure) {
            error = "Could not read Kubernetes status: " + failure;
            stale = true;
        }
    }

    function sourceFresh(source: string): bool {
        return !stale && !!snapshot.sources?.[source]?.ok;
    }

    function metric(ready: string, total: string, sources: var): string {
        return sources.every(source => sourceFresh(source)) ? summary[ready] + " / " + summary[total] : "—";
    }

    onSelectionChanged: {
        snapshot = {};
        byId = {};
        keys = [];
        error = "";
    }
    onSignatureChanged: {
        stale = true;
        process.running = false;
        if (requested)
            retry.restart();
    }
    onRequestedChanged: {
        stale = true;
        if (requested) {
            retry.restart();
        } else {
            retry.stop();
            watchdog.stop();
            process.running = false;
        }
    }

    Process {
        id: process
        command: VmCommands.python("kube_monitor.py", ["--watch"])
        stdout: SplitParser { onRead: data => root.accept(data) }
        onExited: (exitCode, exitStatus) => {
            root.stale = true;
            if (root.requested) {
                if (!root.error)
                    root.error = "Kubernetes monitor stopped. Retrying…";
                retry.restart();
            }
        }
    }
    Timer {
        id: retry
        interval: 500
        onTriggered: {
            if (!root.requested)
                return;
            if (VmPreferences.saving || process.running) {
                restart();
                return;
            }
            process.running = true;
            watchdog.restart();
        }
    }
    Timer {
        id: watchdog
        interval: ((root.options.interval || 10) + 12) * 1000
        onTriggered: {
            root.stale = true;
            root.error = "Kubernetes collection timed out. Retrying…";
            process.running = false;
            if (root.requested)
                retry.restart();
        }
    }
}
