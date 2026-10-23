"""Shared defaults, validation and atomic persistence for widget connections."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import tempfile

USERNAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.-]*\$?")
HOST = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.:%_-]*")
URIS = ["qemu:///system", "qemu:///session"]
DEFAULTS = {
    "uris": URIS, "interval": 3, "startup_seconds": 10, "arp_fallback": True,
    "ssh": {"username": "", "port": 22, "timeout": 10, "identity_file": ""},
    "machines": {},
    "kubernetes": {"enabled": False, "kubeconfig": "", "context": "", "interval": 10},
}


def config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "caelestia/vm-dashboard.json"


def number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}")


def validate_ssh(options: dict, profile: bool = False) -> None:
    if not isinstance(options, dict):
        raise ValueError("SSH settings must be an object")
    allowed = set(DEFAULTS["ssh"]) | ({"host"} if profile else set())
    if options.keys() - allowed:
        raise ValueError("Unknown SSH setting: " + ", ".join(options.keys() - allowed))
    for key, value in options.items():
        if key in ("port", "timeout"):
            number(value, key, 0 if profile else 1, 65535 if key == "port" else 120)
            if int(value) != value:
                raise ValueError(f"{key} must be an integer")
        else:
            if not isinstance(value, str) or any(ord(c) < 32 for c in value):
                raise ValueError(f"Invalid {key}")
            if value and key in ("username", "host") and not (USERNAME if key == "username" else HOST).fullmatch(value):
                raise ValueError(f"Invalid SSH {key}")


def normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("The monitor configuration must be a JSON object")
    if data.keys() - DEFAULTS.keys():
        raise ValueError("Unknown setting: " + ", ".join(data.keys() - DEFAULTS.keys()))
    config = copy.deepcopy(DEFAULTS)
    config.update(data)
    if not isinstance(config["uris"], list) or not config["uris"] or any(uri not in URIS for uri in config["uris"]):
        raise ValueError("Enable at least one local libvirt connection")
    config["uris"] = list(dict.fromkeys(config["uris"]))
    number(config["interval"], "Refresh interval", 1, 60)
    number(config["startup_seconds"], "Startup indicator", 0, 120)
    if not isinstance(config["arp_fallback"], bool):
        raise ValueError("ARP fallback must be true or false")
    validate_ssh(config["ssh"])
    config["ssh"] = {**DEFAULTS["ssh"], **config["ssh"]}
    if not isinstance(config["machines"], dict):
        raise ValueError("VM connection profiles must be an object")
    for profile in config["machines"].values():
        validate_ssh(profile, profile=True)
    options = config["kubernetes"]
    if not isinstance(options, dict) or options.keys() - DEFAULTS["kubernetes"].keys():
        raise ValueError("Invalid Kubernetes settings")
    options = {**DEFAULTS["kubernetes"], **options}
    if not isinstance(options["enabled"], bool):
        raise ValueError("Kubernetes monitoring must be true or false")
    for key in ("kubeconfig", "context"):
        if not isinstance(options[key], str) or any(ord(c) < 32 for c in options[key]):
            raise ValueError(f"Invalid Kubernetes {key}")
    number(options["interval"], "Kubernetes refresh interval", 5, 60)
    if int(options["interval"]) != options["interval"]:
        raise ValueError("Kubernetes refresh interval must be an integer")
    config["kubernetes"] = options
    return config


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    return normalize(json.loads(path.read_text()) if path.exists() else {})


def save(data: dict, path: Path | None = None) -> None:
    path = path or config_path()
    data = normalize(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".vm-dashboard-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def ssh_options(config: dict, key: str, host: str) -> dict:
    options = {**config["ssh"], "host": host}
    # Empty/zero profile values inherit global defaults or the detected address.
    options.update({name: value for name, value in config["machines"].get(key, {}).items() if value})
    return options


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("get", "save"))
    parser.add_argument("data", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "save":
            save(json.loads(args.data))
            print(json.dumps({"ok": True}))
        else:
            print(json.dumps({"config": load()}))
    except (ValueError, TypeError, OSError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
