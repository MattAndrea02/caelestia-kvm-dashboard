#!/usr/bin/env python3
"""Install a reversible, user-owned Caelestia overlay. Never requires sudo."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
MARKER = ".vm-dashboard-install.json"
CONTENT = Path("modules/dashboard/Content.qml")
PAGE_REGISTRY = Path("modules/nexus/PageRegistry.qml")
PAGE_COMPONENTS = Path("modules/nexus/PageCompRegistry.qml")


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{name}: expected integration point not found exactly once; this Caelestia version needs an updated adapter")
    return text.replace(old, new, 1)


def patches(source: Path) -> dict[Path, str]:
    """Keep the upstream adaptation in one place; never ship a fork of the shell."""
    content = (source / CONTENT).read_text()
    if "vmComponent" in content:
        raise ValueError("The source already includes a VM tab; use an unmodified Caelestia source")
    content = replace_once(content, 'import QtQuick\n', 'import "vms"\nimport QtQuick\n', str(CONTENT))
    content = replace_once(content,
        '                enabled: Config.dashboard.showWeather\n            }',
        '                enabled: Config.dashboard.showWeather\n            },\n'
        '            {\n'
        '                component: vmComponent,\n'
        '                iconName: "dns",\n'
        '                text: "VMs",\n'
        '                enabled: true\n'
        '            }', str(CONTENT))
    content = replace_once(content, '            Behavior on contentX {',
        '            Component {\n'
        '                id: vmComponent\n\n'
        '                VmTab {\n'
        '                    active: root.screenState.dashboard && root.dashboardTabs[root.screenState.dashboardTab]?.component === vmComponent\n'
        '                }\n'
        '            }\n\n'
        '            Behavior on contentX {', str(CONTENT))
    pages = replace_once((source / PAGE_REGISTRY).read_text(), '        // About\n',
        '        {\n'
        '            label: "Virtual machines",\n'
        '            icon: "dns",\n'
        '            description: "Libvirt connections, SSH, monitoring",\n'
        '            category: "shell"\n'
        '        },\n\n'
        '        // About\n', str(PAGE_REGISTRY))
    components = replace_once((source / PAGE_COMPONENTS).read_text(), 'import QtQuick\n',
        'import qs.modules.dashboard.vms\nimport QtQuick\n', str(PAGE_COMPONENTS))
    components = replace_once(components, '        // About\n',
        '        Component {\n'
        '            StackPage {\n'
        '                Component { VmSettingsPage {} }\n'
        '            }\n'
        '        },\n\n'
        '        // About\n', str(PAGE_COMPONENTS))
    return {CONTENT: content, PAGE_REGISTRY: pages, PAGE_COMPONENTS: components}


def fingerprint(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.name == MARKER:
            continue
        if path.is_symlink():
            result[str(path.relative_to(root))] = "link:" + os.readlink(path)
        elif path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify_owned(target: Path) -> None:
    if target.is_symlink() or not (target / MARKER).is_file():
        raise ValueError(f"Refusing to replace an unmanaged configuration: {target}. Choose a different --target or move your existing override aside first")
    expected = json.loads((target / MARKER).read_text())["files"]
    actual = fingerprint(target)
    changed = sorted(key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key))
    if changed:
        raise ValueError("Installed files have local changes; preserve them before updating/removing:\n  " + "\n  ".join(changed))


def check(source: Path, target: Path) -> dict[Path, str]:
    if source.resolve() == target.resolve() or source.resolve() in target.resolve().parents or target.resolve() in source.resolve().parents:
        raise ValueError("Source and target must be separate, non-nested directories")
    for executable in ("qs", "ssh"):
        if not shutil.which(executable):
            raise ValueError(f"Missing existing dependency: {executable}. No packages were installed")
    if importlib.util.find_spec("libvirt") is None:
        raise ValueError("Missing Python libvirt bindings. No packages were installed")
    if not (source / "shell.qml").is_file():
        raise ValueError(f"Caelestia shell.qml not found in {source}")
    if target.exists() or target.is_symlink():
        verify_owned(target)
    return patches(source)


def install(source: Path, target: Path) -> None:
    changed = check(source, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".caelestia-vm-stage-", dir=target.parent))
    old = None
    try:
        # Real directories keep Quickshell's qs.* imports rooted in the overlay.
        # Unchanged files link to the package, so source/assets aren't duplicated.
        for directory, dirs, files in os.walk(source, followlinks=True):
            dirs[:] = [name for name in dirs if name not in (".git", "__pycache__")]
            relative = Path(directory).relative_to(source)
            (stage / relative).mkdir(parents=True, exist_ok=True)
            for name in files:
                if name != MARKER:
                    (stage / relative / name).symlink_to(source / relative / name)
        # shell.qml must be a real file: qs canonicalizes a symlinked entry point.
        changed[Path("shell.qml")] = (source / "shell.qml").read_text()
        for relative, text in changed.items():
            destination = stage / relative
            destination.unlink(missing_ok=True)
            destination.write_text(text)
        payload = stage / "modules/dashboard/vms"
        payload.mkdir()
        for path in (REPO / "qml").iterdir():
            if path.is_file():
                shutil.copy2(path, payload / path.name)
        for path in (REPO / "backend").glob("*.py"):
            shutil.copy2(path, payload / path.name)
        (stage / MARKER).write_text(json.dumps({"version": 1, "source": str(source), "files": fingerprint(stage)}, indent=2) + "\n")
        if target.exists():
            old = Path(tempfile.mkdtemp(prefix=".caelestia-vm-old-", dir=target.parent))
            old.rmdir()
            target.rename(old)
        try:
            stage.rename(target)
        except OSError:
            if old:
                old.rename(target)
                old = None
            raise
        if old:
            shutil.rmtree(old)
        print(f"Installed user overlay: {target}")
        print(f"VM code: {target / 'modules/dashboard/vms'}")
        print("Adapted: " + ", ".join(str(path) for path in (CONTENT, PAGE_REGISTRY, PAGE_COMPONENTS)))
        print("Existing services, VM definitions, shell.json and system package files were not changed.")
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def instances(source: Path, target: Path) -> list[dict]:
    result = subprocess.run(["qs", "list", "--all", "-j"], text=True, capture_output=True, check=True)
    if result.stdout.strip().startswith("No running instances"):
        return []
    paths = {str((path / "shell.qml").resolve()) for path in (source, target)}
    return [entry for entry in json.loads(result.stdout) if entry["config_path"] in paths]


def restart(previous: list[dict], launch: Path) -> None:
    for entry in previous:
        print(f"Restarting Caelestia shell instance {entry['pid']} (no VM services are restarted)")
        subprocess.run(["qs", "-p", entry["config_path"], "kill", "--pid", str(entry["pid"])], check=True)
    deadline = time.monotonic() + 5
    terminated = False
    while any(Path(f"/proc/{entry['pid']}").exists() for entry in previous):
        if time.monotonic() > deadline:
            if terminated:
                raise RuntimeError("Caelestia did not exit; restart the desktop shell manually")
            # Some Quickshell builds keep pending jobs alive after IPC quit.
            for entry in previous:
                try:
                    os.kill(entry["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
            terminated = True
            deadline = time.monotonic() + 3
        time.sleep(0.1)
    subprocess.run(["qs", "-p", str(launch), "-d", "-n"], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "install", "uninstall"), nargs="?", default="install")
    parser.add_argument("--source", type=Path, default=Path("/etc/xdg/quickshell/caelestia"))
    parser.add_argument("--target", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "quickshell/caelestia")
    parser.add_argument("--restart", action="store_true", help="restart only the desktop shell after install/uninstall")
    args = parser.parse_args()
    source, target = args.source.expanduser().absolute(), args.target.expanduser().absolute()
    try:
        if os.geteuid() == 0:
            raise ValueError("Run this as your normal desktop user, without sudo")
        previous = instances(source, target) if args.restart else []
        if args.action == "check":
            check(source, target)
            print(f"Compatible Caelestia source: {source}\nTarget: {target}\nExisting dependencies available. No changes made.")
        elif args.action == "install":
            install(source, target)
        else:
            verify_owned(target)
            shutil.rmtree(target)
            print(f"Removed managed override: {target}")
        if args.restart and args.action != "check":
            restart(previous, target if args.action == "install" else source)
        elif args.action != "check":
            print("Restart Caelestia to activate this change, or use --restart.")
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"setup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
