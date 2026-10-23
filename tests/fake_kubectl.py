#!/usr/bin/env python3
"""Deterministic kubectl substitute for tests; never connects to a cluster."""

import json
import os
from pathlib import Path
import sys
import time


def node(name="control-plane", ready="True"):
    return {"metadata": {"name": name, "uid": name}, "spec": {}, "status": {
        "conditions": [{"type": "Ready", "status": ready}],
        "nodeInfo": {"kubeletVersion": "v1.35.0"}}}


def pod(name="coredns", namespace="kube-system", ready=True, phase="Running"):
    return {"metadata": {"name": name, "namespace": namespace, "uid": name}, "spec": {"nodeName": "worker"},
            "status": {"phase": phase, "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                       "containerStatuses": [{"name": "main", "ready": ready, "restartCount": 0, "state": {"running": {}}}]}}


def workload(name="web", namespace="default", kind="Deployment"):
    result = {"metadata": {"name": name, "namespace": namespace, "uid": name, "generation": 1},
              "spec": {"replicas": 2}, "status": {"observedGeneration": 1, "readyReplicas": 2,
                                                 "availableReplicas": 2, "updatedReplicas": 2}}
    if kind == "DaemonSet":
        result["spec"] = {}
        result["status"] = {"observedGeneration": 1, "desiredNumberScheduled": 2, "numberAvailable": 2, "numberReady": 2}
    return result


def cluster():
    return {"nodes": [node(), node("worker")],
            "pods": [pod(), pod("kube-apiserver"), pod("web-1", "default"), pod("web-2", "default")],
            "deployments.apps": [workload(), workload("coredns", "kube-system")],
            "statefulsets.apps": [workload("database", kind="StatefulSet")],
            "daemonsets.apps": [workload("network", "kube-system", "DaemonSet")]}


def main():
    args = sys.argv[1:]
    if os.environ.get("KUBE_TEST_CALLS"):
        with open(os.environ["KUBE_TEST_CALLS"], "a") as stream:
            stream.write(json.dumps(args) + "\n")
    if "get-contexts" in args:
        print("lab\nother")
        return 0
    mode = os.environ.get("KUBE_TEST_MODE", "healthy")
    if os.environ.get("KUBE_TEST_MODE_FILE"):
        mode = Path(os.environ["KUBE_TEST_MODE_FILE"]).read_text().strip()
    resource = args[args.index("get") + 1]
    if mode == "timeout":
        if os.environ.get("KUBE_TEST_PID"):
            Path(os.environ["KUBE_TEST_PID"]).write_text(str(os.getpid()))
        time.sleep(30)
    if mode == "offline":
        print("Unable to connect to the server: connection refused", file=sys.stderr)
        return 1
    if mode == "partial" and resource == "pods":
        print("Error from server (Forbidden): sensitive-plugin-text", file=sys.stderr)
        return 1
    if mode == "malformed":
        print("not JSON")
        return 0
    data = cluster()
    if mode == "degraded":
        data["nodes"][1]["status"]["conditions"][0]["status"] = "False"
        failing = data["pods"][2]
        failing["status"]["conditions"][0]["status"] = "False"
        failing["status"]["containerStatuses"][0].update(ready=False, restartCount=7, state={"waiting": {"reason": "CrashLoopBackOff", "message": "Application exits during startup"}})
        data["deployments.apps"][0]["status"].update(availableReplicas=1, readyReplicas=1)
    print(json.dumps({"apiVersion": "v1", "kind": "List", "items": [] if mode == "empty" else data[resource]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
