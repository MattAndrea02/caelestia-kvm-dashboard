#!/usr/bin/env python3
"""Read-only libvirt snapshots, streamed as JSON lines for the Caelestia tab."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
import vm_config

# Never spawn a session daemon on behalf of the dashboard.
os.environ["LIBVIRT_AUTOSTART"] = "0"

try:
    import libvirt
except ImportError:
    libvirt = None

DEFAULT_URIS = vm_config.URIS
STATES = {0: "Unknown", 1: "Up", 2: "Up", 3: "Paused", 4: "Shutting down",
          5: "Down", 6: "Crashed", 7: "Suspended"}


def settings(path: Path) -> dict:
    """An optional user config changes the monitor only, never libvirt."""
    return vm_config.load(path)


def guest_memory_used(stats: dict, now: float) -> int | None:
    """Guest MemTotal - MemAvailable; old/missing balloon stats are unknown."""
    if not {"available", "usable", "last_update"} <= stats.keys():
        return None
    if not 0 <= now - stats["last_update"] <= 60:
        return None
    total, available = stats["available"], stats["usable"]
    return total - available if 0 <= available <= total else None


def addresses(domain, arp_fallback: bool = True) -> list[str]:
    """Use existing DHCP/ARP data. No guest agent or guest configuration needed."""
    found = set()
    sources = [libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE]
    if arp_fallback:
        sources.append(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_ARP)
    for source in sources:
        try:
            interfaces = domain.interfaceAddresses(source)
        except libvirt.libvirtError:
            continue
        for interface in interfaces.values():
            for entry in interface.get("addrs") or []:
                try:
                    address = ipaddress.ip_address(entry["addr"])
                except (ValueError, KeyError):
                    continue
                if not (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast):
                    found.add(address)
        if found:
            break
    return [str(address) for address in sorted(found, key=lambda ip: (ip.version, int(ip)))]


class Monitor:
    """Own connections and CPU baselines for one visible dashboard instance."""

    def __init__(self, uris: list[str]):
        self.uris = uris
        self.connections = {}
        self.previous = {}
        self.lifecycle = {}
        self.seen_connections = set()
        self.startup_seconds = vm_config.DEFAULTS["startup_seconds"]
        self.arp_fallback = vm_config.DEFAULTS["arp_fallback"]

    def close(self):
        for connection in self.connections.values():
            connection.close()
        self.connections.clear()

    def domain_snapshot(self, domain, uri: str) -> dict:
        key = f"{uri}#{domain.UUIDString()}"
        state, _maximum, memory, vcpus, cpu_ns = domain.info()
        active = bool(domain.isActive())
        now = time.monotonic()
        identity = domain.ID()
        old = self.lifecycle.get(key)
        newly_started = active and ((old and (not old[0] or old[1] != identity)) or (old is None and uri in self.seen_connections))
        starting_until = now + self.startup_seconds if newly_started else old[2] if old else 0
        self.lifecycle[key] = (active, identity, starting_until)
        display_state = STATES.get(state, "Unknown")
        if active and state in (0, 1, 2) and (now < starting_until or state == 0):
            display_state = "Starting up"
        previous = self.previous.get(key)
        cores = None
        if active and previous:
            old_time, old_cpu, old_id = previous
            elapsed = now - old_time
            if elapsed > 0 and cpu_ns >= old_cpu and identity == old_id:
                cores = min(vcpus, (cpu_ns - old_cpu) / (elapsed * 1_000_000_000))
        if active:
            self.previous[key] = (now, cpu_ns, identity)
        else:
            self.previous.pop(key, None)
            cores = 0.0

        stats = {}
        if active:
            try:
                stats = domain.memoryStats()
            except libvirt.libvirtError:
                pass  # Optional statistics must not hide an otherwise healthy VM.
        ips = addresses(domain, self.arp_fallback) if active else []
        return {
            "key": key, "name": domain.name(), "uri": uri,
            "state": display_state, "active": active,
            "up": active and display_state == "Up", "can_ssh": active and state in (1, 2),
            "vcpus": vcpus, "cpu_cores": cores,
            "cpu_percent": None if cores is None or not vcpus else cores / vcpus * 100,
            "memory_kib": memory,
            "guest_used_kib": guest_memory_used(stats, time.time()) if active else None,
            "rss_kib": stats.get("rss") if active else None,
            "addresses": ips, "address": ips[0] if ips else "",
        }

    def snapshot(self) -> dict:
        machines, connections, errors = [], [], []
        for uri in self.uris:
            try:
                if uri not in self.connections:
                    self.connections[uri] = libvirt.openReadOnly(uri)
                domains = self.connections[uri].listAllDomains(0)
                connections.append({"uri": uri, "ok": True})
                for domain in domains:
                    try:
                        machines.append(self.domain_snapshot(domain, uri))
                    except libvirt.libvirtError as error:
                        # A VM can disappear between enumeration and collection.
                        errors.append(f"{uri}: {error}")
                self.seen_connections.add(uri)
            except libvirt.libvirtError as error:
                connection = self.connections.pop(uri, None)
                if connection:
                    connection.close()
                connections.append({"uri": uri, "ok": False})
                errors.append(f"{uri}: {error}")

        machines.sort(key=lambda vm: (not vm["active"], vm["name"].casefold(), vm["key"]))
        live_keys = {vm["key"] for vm in machines}
        self.previous = {key: value for key, value in self.previous.items() if key in live_keys}
        self.lifecycle = {key: value for key, value in self.lifecycle.items() if key in live_keys}
        active = [vm for vm in machines if vm["active"]]
        return {
            "machines": machines, "connections": connections, "errors": errors,
            "timestamp": time.time(),
            "summary": {
                "total": len(machines), "up": sum(vm["up"] for vm in machines),
                "inactive": len(machines) - len(active),
                "other_active": sum(not vm["up"] for vm in active),
                "vcpus": sum(vm["vcpus"] for vm in active),
                "memory_kib": sum(vm["memory_kib"] for vm in active),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="stream snapshots until the tab closes")
    parser.add_argument("--uri", action="append", help="override connections (repeatable; test:///default is useful for tests)")
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "caelestia/vm-dashboard.json")
    args = parser.parse_args()
    try:
        if libvirt is None:
            raise RuntimeError("Python libvirt bindings are not available in this Python environment")
        libvirt.registerErrorHandler(lambda _context, _error: None, None)
        config = settings(args.config)
        monitor = Monitor(args.uri or config["uris"])
        try:
            while True:
                config = settings(args.config)
                monitor.uris = args.uri or config["uris"]
                for uri in set(monitor.connections) - set(monitor.uris):
                    monitor.connections.pop(uri).close()
                    monitor.seen_connections.discard(uri)
                monitor.startup_seconds = config["startup_seconds"]
                monitor.arp_fallback = config["arp_fallback"]
                print(json.dumps(monitor.snapshot(), separators=(",", ":")), flush=True)
                if not args.watch:
                    break
                time.sleep(config["interval"])
        finally:
            monitor.close()
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"fatal": str(error)}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
