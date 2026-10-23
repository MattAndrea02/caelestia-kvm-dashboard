pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs.utils

Singleton {
    id: root
    property var data: ({})
    property bool ready: false
    property string error: ""
    property bool queued: false
    readonly property bool saving: queued || writer.running

    function reload(): void {
        if (!reader.running && !writer.running && !queued)
            reader.running = true;
    }

    function update(key: string, value: var): void {
        const next = JSON.parse(JSON.stringify(data));
        next[key] = value;
        commit(next);
    }

    function setSsh(profile: string, key: string, value: var): void {
        const next = JSON.parse(JSON.stringify(data));
        if (profile) {
            if (!next.machines[profile])
                next.machines[profile] = {};
            next.machines[profile][key] = value;
        } else {
            next.ssh[key] = value;
        }
        commit(next);
    }

    function setKubernetes(key: string, value: var): void {
        const next = JSON.parse(JSON.stringify(data));
        next.kubernetes = Object.assign({}, next.kubernetes || {}, {[key]: value});
        // A context belongs to its kubeconfig, not merely to a display name.
        if (key === "kubeconfig" && value !== data.kubernetes?.kubeconfig)
            next.kubernetes.context = "";
        commit(next);
    }

    function commit(next: var): void {
        if (!ready || JSON.stringify(data) === JSON.stringify(next))
            return;
        data = next;
        queued = true;
        saveDelay.restart();
    }

    function setConnection(uri: string, enabled: bool): void {
        let uris = data.uris.filter(value => value !== uri);
        if (enabled)
            uris.push(uri);
        if (!uris.length) {
            error = "Keep at least one libvirt connection enabled.";
            return;
        }
        update("uris", uris);
    }

    Component.onCompleted: reload()

    FileView {
        path: Paths.config + "/vm-dashboard.json"
        watchChanges: true
        printErrors: false
        onFileChanged: root.reload()
    }
    Process {
        id: reader
        command: VmCommands.python("vm_config.py", ["get"])
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const reply = JSON.parse(text);
                    root.error = reply.error || "";
                    if (reply.config && !root.queued) {
                        root.data = reply.config;
                        root.ready = true;
                    }
                } catch (error) {
                    root.error = String(error);
                }
            }
        }
    }
    Timer {
        id: saveDelay
        interval: 250
        onTriggered: {
            if (writer.running) {
                restart();
                return;
            }
            root.queued = false;
            writer.command = VmCommands.python("vm_config.py", ["save", JSON.stringify(root.data)]);
            writer.running = true;
        }
    }
    Process {
        id: writer
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    root.error = JSON.parse(text).error || "";
                } catch (error) {
                    root.error = String(error);
                }
            }
        }
    }
}
