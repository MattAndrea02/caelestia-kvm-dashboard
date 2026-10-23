#!/usr/bin/env python3
"""Read-only Kubernetes health snapshots. No libvirt or Kubernetes SDK dependency."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import vm_config

RESOURCES = ("nodes", "pods", "deployments.apps", "statefulsets.apps", "daemonsets.apps")
SEVERITY = {"error": 0, "attention": 1, "unknown": 2, "info": 3, "ok": 4}


class CollectionError(Exception):
    def __init__(self, code: str, message: str, reached: bool = False):
        super().__init__(message)
        self.code, self.reached = code, reached


def command_error(stderr: str) -> CollectionError:
    # Credential plugins may write secrets to stderr. Never forward raw diagnostics.
    text = stderr.casefold()
    if "forbidden" in text:
        return CollectionError("forbidden", "Read permission denied for this resource.", True)
    if any(word in text for word in ("unauthorized", "must be logged in", "provide credentials")):
        return CollectionError("authentication", "Kubernetes credentials were rejected.", True)
    if any(word in text for word in ("x509", "certificate", "tls handshake")):
        return CollectionError("tls", "Could not verify the API connection. Check certificates and endpoint.")
    if any(word in text for word in ("context", "kubeconfig", "config file", "no configuration", "no such file")):
        return CollectionError("configuration", "Check the kubeconfig path and selected context.")
    if any(word in text for word in ("exec:", "credential", "getting token", "interactive")):
        return CollectionError("authentication", "Authentication failed. Refresh credentials with kubectl in a terminal.")
    if any(word in text for word in ("timeout", "deadline exceeded", "timed out")):
        return CollectionError("timeout", "The API request timed out.")
    return CollectionError("unavailable", "Could not read the API. Check connectivity and credentials with kubectl.")


class Kubectl:
    """Bound requests and cancel their process groups, including credential helpers."""

    def __init__(self):
        self.children = set()
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    @staticmethod
    def kill(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self):
        self.stopped.set()
        with self.lock:
            for process in self.children:
                self.kill(process)

    def run(self, options: dict, args: list[str], use_context: bool = True) -> str:
        command = ["kubectl"]
        if options.get("kubeconfig"):
            command.append("--kubeconfig=" + str(Path(options["kubeconfig"]).expanduser()))
        if use_context:
            command.extend(["--context=" + options["context"], "--request-timeout=5s"])
        command.extend(args)
        with self.lock:
            if self.stopped.is_set():
                raise CollectionError("cancelled", "Collection stopped.")
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True, errors="replace",
                                           start_new_session=True)
            except FileNotFoundError:
                raise CollectionError("missing_kubectl", "Install kubectl on this computer to enable Kubernetes monitoring.") from None
            except OSError:
                raise CollectionError("configuration", "Could not start kubectl. Check the local installation.") from None
            self.children.add(process)
        try:
            try:
                stdout, stderr = process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                self.kill(process)
                process.communicate()
                raise CollectionError("timeout", "kubectl did not finish within eight seconds.") from None
            if process.returncode:
                raise command_error(stderr)
            return stdout
        finally:
            # A helper must not outlive the request, even if kubectl has exited.
            self.kill(process)
            with self.lock:
                self.children.discard(process)

    def fetch(self, options: dict, resource: str) -> list[dict]:
        args = ["get", resource, "-o", "json"]
        if resource != "nodes":
            args.append("--all-namespaces")
        try:
            data = json.loads(self.run(options, args))
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError()
            if any(not isinstance(item, dict) or not isinstance(item.get("metadata"), dict)
                   or not item["metadata"].get("name") for item in data["items"]):
                raise ValueError()
            return data["items"]
        except (ValueError, TypeError):
            raise CollectionError("invalid_response", "kubectl returned an invalid resource list.", True) from None

    def contexts(self, kubeconfig: str) -> list[str]:
        result = self.run({"kubeconfig": kubeconfig}, ["config", "get-contexts", "-o", "name"], False)
        return sorted(set(line.strip() for line in result.splitlines() if line.strip()))


def clean(value) -> str:
    return " ".join(str(value or "").split())[:1200]


def conditions(item: dict) -> dict:
    return {condition["type"]: condition for condition in item.get("status", {}).get("conditions", [])
            if isinstance(condition, dict) and "type" in condition}


def condition_details(item: dict) -> list[str]:
    return [clean(f"{kind}: {value.get('status', 'Unknown')} · {value.get('reason', '')} {value.get('message', '')}")
            for kind, value in conditions(item).items()]


def record(item: dict, source: str, kind: str) -> dict:
    meta = item["metadata"]
    return {"key": f"{source}/{meta.get('namespace', '')}/{meta.get('uid') or meta['name']}",
            "source": source, "kind": kind, "name": clean(meta["name"]),
            "namespace": clean(meta.get("namespace", "")), "severity": "ok",
            "status": "Ready", "reason": "", "details": condition_details(item),
            "stale": False, "progressing": False}


def node_record(item: dict) -> dict:
    row = record(item, "nodes", "Node")
    checks = conditions(item)
    ready = checks.get("Ready", {}).get("status", "Unknown")
    row["ready"] = ready == "True"
    row["status"] = {"True": "Ready", "False": "NotReady"}.get(ready, "Unknown")
    reasons = []
    if ready != "True":
        reasons.append("Node readiness is " + row["status"])
    for name in ("MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable"):
        if checks.get(name, {}).get("status") == "True":
            reasons.append(name)
    if reasons:
        row.update(severity="error", reason=" · ".join(reasons))
    else:
        unknown = [name for name in ("MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable")
                   if checks.get(name, {}).get("status") == "Unknown"]
        if unknown:
            row.update(severity="unknown", reason="Unknown conditions: " + ", ".join(unknown))
    if item.get("spec", {}).get("unschedulable"):
        row["status"] += " · Scheduling disabled"
    row["details"].extend([
        "Kubelet: " + clean(item.get("status", {}).get("nodeInfo", {}).get("kubeletVersion", "Unknown")),
        "Addresses: " + ", ".join(clean(a.get("address")) for a in item.get("status", {}).get("addresses", [])),
    ])
    return row


def pod_record(item: dict) -> dict:
    row = record(item, "pods", "Pod")
    status = item.get("status", {})
    phase = status.get("phase", "Unknown")
    ready = conditions(item).get("Ready", {}).get("status") == "True"
    containers = status.get("initContainerStatuses", []) + status.get("containerStatuses", [])
    row.update(ready=ready, active=phase not in ("Succeeded", "Failed") and not item["metadata"].get("deletionTimestamp"),
               restarts=sum(container.get("restartCount", 0) for container in containers))
    row["details"].extend(["Node: " + clean(item.get("spec", {}).get("nodeName", "Not scheduled")),
                           f"Phase: {phase} · Restarts: {row['restarts']}"])
    failures = []
    for container in containers:
        state = container.get("state", {})
        current = state.get("waiting") or state.get("terminated") or {}
        reason = current.get("reason", "")
        row["details"].append(clean(f"{container.get('name', '')}: {'Ready' if container.get('ready') else 'Not ready'} · {reason} {current.get('message', '')}"))
        if reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError", "CreateContainerError", "InvalidImageName", "RunContainerError"):
            failures.append(reason)
    if item["metadata"].get("deletionTimestamp"):
        row.update(status="Terminating", severity="info")
    elif phase == "Succeeded":
        row.update(status="Completed", severity="info")
    elif failures or phase == "Failed":
        reason = " · ".join(sorted(set(failures))) or clean(status.get("reason")) or "Pod failed"
        row.update(status="Problem", severity="error", reason=reason)
    elif not ready or phase != "Running":
        row.update(status=phase if phase != "Running" else "Not ready", severity="attention",
                   reason=clean(status.get("reason")) or ("Waiting for scheduling or startup" if phase == "Pending" else "Pod is not ready"))
    return row


def workload_record(item: dict, source: str) -> dict:
    kind = {"deployments.apps": "Deployment", "statefulsets.apps": "StatefulSet", "daemonsets.apps": "DaemonSet"}[source]
    row = record(item, source, kind)
    spec, status = item.get("spec", {}), item.get("status", {})
    daemon = source == "daemonsets.apps"
    desired = status.get("desiredNumberScheduled") if daemon else spec.get("replicas", 1)
    available = status.get("numberAvailable", 0) if daemon else status.get("availableReplicas", 0)
    if source == "statefulsets.apps" and "availableReplicas" not in status and not spec.get("minReadySeconds", 0):
        available = status.get("readyReplicas", 0)
    ready = status.get("numberReady" if daemon else "readyReplicas", 0)
    observed = status.get("observedGeneration", 0) >= item["metadata"].get("generation", 1)
    row.update(desired=desired, available=available, ready=False)
    row["details"].append(f"Available: {available} / {desired if desired is not None else 'unknown'} · Ready: {ready}")
    if not observed:
        row.update(status="Updating", severity="info", progressing=True,
                   reason="Waiting for the controller to observe the latest configuration")
    elif desired is None:
        row.update(status="Unknown", severity="unknown", reason="Controller has not reported its desired pod count")
    elif desired == 0:
        row.update(status="Inactive", severity="info", reason="No replicas requested")
    else:
        checks = conditions(item)
        failures = [clean(c.get("reason") or c["type"]) for c in checks.values()
                    if (c["type"] == "ReplicaFailure" and c.get("status") == "True")
                    or (c["type"] == "Progressing" and c.get("status") == "False")]
        if failures:
            row.update(status="Problem", severity="error", reason=" · ".join(failures))
        elif available < desired:
            progressing = checks.get("Progressing", {})
            updating = progressing.get("status") == "True" and progressing.get("reason") != "NewReplicaSetAvailable"
            row.update(status="Updating" if updating else "Partially available", severity="attention",
                       reason=f"{available} / {desired} replicas available", progressing=updating)
        else:
            row["ready"] = True
            # Only Deployment exposes a rollout progress condition. Do not infer
            # failure from StatefulSet partitions or OnDelete update strategies.
            if source == "deployments.apps" and status.get("updatedReplicas", 0) < desired and not spec.get("paused"):
                row.update(status="Updating", severity="info", progressing=True,
                           reason="Available; rollout still in progress")
        if spec.get("paused"):
            row["details"].append("Rollout paused")
    return row


def normalize_items(resource: str, items: list[dict]) -> list[dict]:
    if resource == "nodes":
        return [node_record(item) for item in items]
    if resource == "pods":
        return [pod_record(item) for item in items]
    return [workload_record(item, resource) for item in items]


def summarize(sources: dict) -> tuple[dict, list[dict]]:
    rows = []
    for source in sources.values():
        for original in source["items"]:
            row = copy.deepcopy(original)
            row["stale"] = not source["ok"]
            rows.append(row)
    nodes = [row for row in rows if row["kind"] == "Node"]
    system = [row for row in rows if row["kind"] == "Pod" and row["namespace"] == "kube-system" and row["active"]]
    apps = [row for row in rows if row["kind"] not in ("Node", "Pod") and row["namespace"] != "kube-system"]
    incomplete = not all(source["ok"] for source in sources.values())
    if sources["nodes"]["ok"] and not nodes:
        rows.append({"key": "observation/no-nodes", "source": "nodes", "kind": "Cluster", "name": "No nodes registered",
                     "namespace": "", "severity": "error", "status": "Attention", "reason": "The API reports no registered nodes.",
                     "details": [], "stale": False})
    if sources["pods"]["ok"] and not system:
        incomplete = True
        rows.append({"key": "observation/no-system", "source": "pods", "kind": "Cluster", "name": "System components not observed",
                     "namespace": "kube-system", "severity": "unknown", "status": "Incomplete", "reason": "No active pods in kube-system; system health cannot be assessed.",
                     "details": [], "stale": False})
    incomplete |= any(row["severity"] == "unknown" for row in rows)
    issues = [row for row in rows if row["severity"] in ("error", "attention", "unknown")]
    api = "reachable" if any(s["ok"] or s.get("reached") for s in sources.values()) else "unknown"
    codes = {s.get("code") for s in sources.values()}
    if api == "unknown" and codes <= {"timeout", "unavailable"}:
        api = "unreachable"
    elif api == "unknown" and codes & {"authentication", "tls"}:
        api = "access_error"
    elif api == "unknown" and codes & {"configuration", "missing_kubectl"}:
        api = "setup_required"
    summary = {
        "state": "incomplete" if incomplete else "attention" if issues else "progressing" if any(r.get("progressing") for r in rows) else "ok",
        "api": api, "nodes_ready": sum(r["ready"] for r in nodes), "nodes_total": len(nodes),
        "system_ready": sum(r["ready"] for r in system), "system_total": len(system),
        "apps_ready": sum(r["ready"] for r in apps if r["desired"] != 0),
        "apps_total": sum(r["desired"] != 0 for r in apps),
        "apps_inactive": sum(r["desired"] == 0 for r in apps), "issues": len(issues),
    }
    rows.sort(key=lambda row: (SEVERITY[row["severity"]], row["namespace"] != "kube-system", row["kind"], row["namespace"], row["name"]))
    return summary, rows


class Monitor:
    def __init__(self, runner: Kubectl):
        self.runner = runner
        self.selection = None
        self.sources = {}

    def snapshot(self, options: dict) -> dict:
        selection = {key: options[key] for key in ("enabled", "kubeconfig", "context")}
        if selection != self.selection:
            self.selection = selection
            self.sources = {}
        if not options["enabled"] or not options["context"]:
            return {"selection": selection, "setup": "Enable monitoring and select a context in Settings → Kubernetes.",
                    "sources": {}, "records": [], "summary": {"state": "incomplete", "api": "setup_required"}}

        def collect(resource):
            old = self.sources.get(resource, {"items": [], "last_success": None})
            try:
                items = normalize_items(resource, self.runner.fetch(options, resource))
                return {"ok": True, "items": items, "last_success": time.time(), "error": "", "code": "", "reached": True}
            except CollectionError as error:
                return {**old, "ok": False, "error": str(error), "code": error.code, "reached": error.reached}
            except (TypeError, ValueError, KeyError, AttributeError):
                return {**old, "ok": False, "error": "Could not interpret this resource list.", "code": "invalid_response", "reached": True}

        with ThreadPoolExecutor(max_workers=len(RESOURCES)) as pool:
            self.sources = dict(zip(RESOURCES, pool.map(collect, RESOURCES)))
        summary, rows = summarize(self.sources)
        # Publish normalized records once, never raw resource specs or credentials.
        sources = {name: {k: v for k, v in source.items() if k != "items"} for name, source in self.sources.items()}
        return {"selection": selection, "summary": summary, "sources": sources, "records": rows, "timestamp": time.time()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--config", type=Path, default=vm_config.config_path())
    parser.add_argument("--contexts", action="store_true", help="list local context names without accessing the cluster")
    parser.add_argument("--kubeconfig", default="", help="kubeconfig override for --contexts only")
    args = parser.parse_args()
    runner = Kubectl()
    # Signal handlers only set a flag: taking the runner's lock here could deadlock.
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threading.Thread(target=lambda: (stop.wait(), runner.close()), daemon=True).start()
    try:
        if args.contexts:
            print(json.dumps({"contexts": runner.contexts(args.kubeconfig)}), flush=True)
            return 0
        monitor = Monitor(runner)
        while not stop.is_set():
            started = time.monotonic()
            try:
                options = vm_config.load(args.config)["kubernetes"]
                result = monitor.snapshot(options)
                interval = options["interval"]
            except (ValueError, OSError) as error:
                result = {"fatal": "Could not read monitoring settings: " + str(error)}
                interval = 10
            if stop.is_set():
                break
            print(json.dumps(result, separators=(",", ":")), flush=True)
            if not args.watch:
                break
            stop.wait(max(0, interval - (time.monotonic() - started)))
    except CollectionError as error:
        print(json.dumps({"error": str(error), "code": error.code}), flush=True)
        return 1
    except BrokenPipeError:
        pass
    finally:
        stop.set()
        runner.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
