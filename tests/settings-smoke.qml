// Run from a temporary overlay with XDG_CONFIG_HOME pointing to a test directory.
import QtQuick
import Quickshell
import Quickshell.Io
import Caelestia
import qs.services
import qs.modules.nexus
import qs.modules.dashboard.vms

ShellRoot {
    FloatingWindow {
        id: window
        visible: true
        implicitWidth: 1080
        implicitHeight: 760
        color: Colours.palette.m3surface
        Nexus {
            id: nexus
            anchors.fill: parent
            nState.screen: window.screen
            nState.isWindow: true
            nState.currentPageIdx: PageRegistry.pages.findIndex(page => page.icon === "dns")
        }
    }
    Timer {
        interval: 2500
        running: true
        onTriggered: {
            const username = CUtils.findChild(nexus, "vmSshDefaultUser");
            const port = CUtils.findChild(nexus, "vmSshDefaultPort");
            if (!VmPreferences.ready || !username || !port)
                throw new Error("Native VM settings page did not load");
            username.editingFinished("master");
            port.moved(2222);
        }
    }
    Timer {
        interval: 4500
        running: true
        onTriggered: probe.running = true
    }
    Process {
        id: probe
        command: VmCommands.python("vm_config.py", ["get"])
        stdout: StdioCollector {
            onStreamFinished: {
                const reply = JSON.parse(text);
                if (reply.config?.ssh.port !== 2222 || reply.config?.ssh.username !== "master")
                    throw new Error("Native settings did not persist the edited SSH values");
                if (!CUtils.findChildren(nexus, "vmSshProfileUser").length)
                    throw new Error("Per-VM connection settings were not created");
                nexus.grabToImage(result => {
                    result.saveToFile("/tmp/caelestia-vm-settings-preview.png");
                    console.log("VM_SETTINGS_SMOKE_PASSED");
                    finish.start();
                });
            }
        }
    }
    Timer {
        id: finish
        interval: 500
        onTriggered: Qt.quit()
    }
}
