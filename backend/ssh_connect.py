#!/usr/bin/env python3
"""Prompt in the existing terminal, then hand authentication to OpenSSH."""

import argparse
from pathlib import Path
import subprocess
import vm_config

USERNAME = vm_config.USERNAME
HOST = vm_config.HOST


def prompt(label: str, pattern) -> str:
    while True:
        value = input(label + ": ").strip()
        if pattern.fullmatch(value):
            return value
        print(f"Please enter a valid {label.lower()}.")


def ssh_command(username: str, host: str, port: int = 22, timeout: int = 10, identity_file: str = "") -> list[str]:
    if not USERNAME.fullmatch(username) or not HOST.fullmatch(host):
        raise ValueError("Invalid SSH username or host")
    # No shell evaluation. Keep SSH config, keys and host-key verification intact.
    vm_config.validate_ssh({"port": port, "timeout": timeout, "identity_file": identity_file})
    command = ["ssh", "-o", f"ConnectTimeout={int(timeout)}", "-p", str(int(port)), "-l", username]
    if identity_file:
        command.extend(["-i", str(Path(identity_file).expanduser())])
    return command + ["--", host]


def connect(name: str, host: str, options: dict | None = None) -> int:
    options = options or {**vm_config.DEFAULTS["ssh"], "host": host}
    host = options.get("host", host)
    print("SSH · " + "".join(char for char in name if char.isprintable()))
    if not HOST.fullmatch(host):
        host = prompt("Host", HOST)
    print("Host: " + host)
    username = options["username"] or prompt("Username", USERNAME)
    result = subprocess.run(ssh_command(username, host, options["port"], options["timeout"], options["identity_file"]), check=False)
    if result.returncode:
        input(f"\nSSH exited with code {result.returncode}. Press Enter to close.")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="")
    parser.add_argument("--name", default="Virtual machine")
    parser.add_argument("--key", default="", help="libvirt URI + UUID connection profile")
    args = parser.parse_args()
    try:
        return connect(args.name, args.host, vm_config.ssh_options(vm_config.load(), args.key, args.host))
    except (EOFError, KeyboardInterrupt):
        return 130
    except (OSError, ValueError) as error:
        input(f"Cannot start SSH: {error}\nPress Enter to close.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
