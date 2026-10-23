#!/usr/bin/env python3
"""Render the native UI with fake kubectl, isolated settings and a temporary overlay."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from support import config, REPO, setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path, help="optional directory for preview images and the QML log")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="kubernetes-smoke-") as directory:
        root = Path(directory)
        target = root / "overlay"
        setup.install(Path("/etc/xdg/quickshell/caelestia"), target)
        shutil.copyfile(REPO / "tests/kubernetes-smoke.qml", target / "smoke.qml")
        binary = root / "bin"
        binary.mkdir()
        shutil.copyfile(REPO / "tests/fake_kubectl.py", binary / "kubectl")
        (binary / "kubectl").chmod(0o755)
        config_file = root / "config/caelestia/vm-dashboard.json"
        config.save({"kubernetes": {"enabled": True, "context": "lab", "interval": 5}}, config_file)
        mode = root / "mode"
        mode.write_text("healthy")
        preview = args.preview_dir or root / "preview"
        preview.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                       "XDG_CONFIG_HOME": str(root / "config"), "XDG_CACHE_HOME": str(root / "cache"),
                       "XDG_STATE_HOME": str(root / "state"), "KUBE_TEST_MODE_FILE": str(mode),
                       "KUBE_TEST_PREVIEW": str(preview), "KUBE_TEST_CALLS": str(root / "calls")}
        result = subprocess.run(["qs", "-p", str(target / "smoke.qml"), "--no-color"], env=environment,
                                capture_output=True, text=True, timeout=55)
        output = result.stdout + result.stderr
        (preview / "qml.log").write_text(output)
        if result.returncode or "KUBERNETES_SMOKE_PASSED" not in output or "KUBERNETES_SMOKE_FAILED" in output:
            print(output)
            return 1
        saved = config.load(config_file)["kubernetes"]
        if saved["context"] != "other" or saved["interval"] != 6:
            raise AssertionError("Settings were not persisted")
        calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
        if any("use-context" in call or "apply" in call for call in calls):
            raise AssertionError("Monitoring changed Kubernetes configuration")
        print("Kubernetes GUI smoke passed: health, partial access, stale data, context switching, settings and process lifetime.")
        if args.preview_dir:
            print(f"Previews: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
