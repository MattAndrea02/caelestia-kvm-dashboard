// Run from the root of a temporary setup.sh overlay in a Wayland session.
import QtQuick
import Quickshell
import Caelestia
import qs.services
import qs.modules.dashboard.vms

ShellRoot {
    property var initialCard

    FloatingWindow {
        id: window
        visible: true
        implicitWidth: 890
        implicitHeight: 420
        color: Colours.palette.m3surface
        VmTab {
            id: tab
            anchors.centerIn: parent
            width: implicitWidth
            height: implicitHeight
            active: true
        }
    }

    Timer {
        interval: 1500
        running: true
        onTriggered: {
            const cards = CUtils.findChildren(tab, "vmCard");
            if (!cards.length)
                throw new Error("Smoke test needs at least one VM in the existing libvirt services");
            initialCard = cards[0];
            console.log("VM_SMOKE_FOUND", cards.length);
        }
    }
    Timer {
        interval: 5500
        running: true
        onTriggered: {
            const cards = CUtils.findChildren(tab, "vmCard");
            if (!initialCard || cards[0] !== initialCard)
                throw new Error("Polling replaced the VM delegate");
            if (initialCard.vm.cpu_percent === null)
                throw new Error("CPU sampling never became available");
            const component = Qt.createComponent("modules/dashboard/vms/VmCard.qml");
            const card = component.createObject(window.contentItem, {vm: initialCard.vm, fresh: false, visible: false});
            if (!card || card.canConnect)
                throw new Error("Stale statistics must disable SSH");
            card.fresh = true;
            card.vm = Object.assign({}, card.vm, {can_ssh: false});
            if (card.canConnect)
                throw new Error("Stopped VMs must disable SSH");
            card.destroy();
            if (Quickshell.env("VM_SMOKE_LAUNCH_SSH") === "1")
                initialCard.connect();
            tab.grabToImage(result => {
                result.saveToFile(Quickshell.env("VM_SCREENSHOT") || "/tmp/caelestia-vm-preview.png");
                tab.active = false;
                finish.start();
                console.log("VM_SMOKE_PASSED");
            });
        }
    }
    Timer {
        id: finish
        interval: 500
        onTriggered: Qt.quit()
    }
}
