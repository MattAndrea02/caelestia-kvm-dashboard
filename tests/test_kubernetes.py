"""Health semantics, partial reads, bounded subprocesses and snapshot freshness."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from support import config, kube, REPO
from fake_kubectl import cluster, node, pod, workload


OPTIONS = {"enabled": True, "kubeconfig": "", "context": "lab", "interval": 10}


class HealthTests(unittest.TestCase):
    def test_node_readiness_pressure_and_cordon(self):
        item = node()
        item["spec"]["unschedulable"] = True
        self.assertEqual(kube.node_record(item)["severity"], "ok")
        for status in ("False", "Unknown"):
            with self.subTest(status=status):
                self.assertFalse(kube.node_record(node(ready=status))["ready"])
                self.assertEqual(kube.node_record(node(ready=status))["severity"], "error")
        for condition in ("MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable"):
            with self.subTest(condition=condition):
                unhealthy = node()
                unhealthy["status"]["conditions"].append({"type": condition, "status": "True"})
                self.assertIn(condition, kube.node_record(unhealthy)["reason"])
                unhealthy["status"]["conditions"][-1]["status"] = "Unknown"
                self.assertEqual(kube.node_record(unhealthy)["severity"], "unknown")

    def test_pod_phase_is_not_a_readiness_or_crash_loop_check(self):
        item = pod(ready=False)
        self.assertEqual(kube.pod_record(item)["severity"], "attention")
        item["status"]["containerStatuses"][0].update(restartCount=10, state={"waiting": {"reason": "CrashLoopBackOff"}})
        self.assertEqual(kube.pod_record(item)["severity"], "error")
        self.assertIn("CrashLoopBackOff", kube.pod_record(item)["reason"])
        item = pod()
        item["status"]["containerStatuses"][0]["restartCount"] = 200
        self.assertEqual(kube.pod_record(item)["severity"], "ok")
        self.assertEqual(kube.pod_record(pod(ready=False, phase="Succeeded"))["status"], "Completed")
        item["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
        self.assertEqual(kube.pod_record(item)["severity"], "info")
        for phase in ("Pending", "Unknown", "Failed"):
            self.assertIn(kube.pod_record(pod(ready=False, phase=phase))["severity"], ("attention", "error"))

    def test_init_container_image_errors_are_reported(self):
        item = pod(ready=False, phase="Pending")
        item["status"]["initContainerStatuses"] = [{"name": "init", "state": {"waiting": {"reason": "ImagePullBackOff"}}}]
        self.assertIn("ImagePullBackOff", kube.pod_record(item)["reason"])

    def test_workloads_availability_generation_and_inactive(self):
        for source in kube.RESOURCES[2:]:
            daemon = source == "daemonsets.apps"
            item = workload(kind="DaemonSet" if daemon else "Deployment")
            with self.subTest(source=source):
                self.assertTrue(kube.workload_record(item, source)["ready"])
                item["metadata"]["generation"] = 2
                self.assertEqual(kube.workload_record(item, source)["status"], "Updating")
                self.assertFalse(kube.workload_record(item, source)["ready"])
                item["status"]["observedGeneration"] = 2
                item["status"]["numberAvailable" if daemon else "availableReplicas"] = 1
                self.assertEqual(kube.workload_record(item, source)["severity"], "attention")
                (item["status"] if daemon else item["spec"])["desiredNumberScheduled" if daemon else "replicas"] = 0
                self.assertEqual(kube.workload_record(item, source)["status"], "Inactive")

    def test_rollout_failure_is_distinct_from_available_rollout(self):
        item = workload()
        item["status"]["updatedReplicas"] = 1
        row = kube.workload_record(item, "deployments.apps")
        self.assertTrue(row["ready"])
        self.assertTrue(row["progressing"])
        item["status"]["conditions"] = [{"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}]
        row = kube.workload_record(item, "deployments.apps")
        self.assertEqual(row["severity"], "error")
        self.assertIn("ProgressDeadlineExceeded", row["reason"])
        item["metadata"]["generation"] = 2
        self.assertNotEqual(kube.workload_record(item, "deployments.apps")["severity"], "error")

    def test_partitioned_statefulset_and_ondelete_are_not_false_failures(self):
        item = workload(kind="StatefulSet")
        item["spec"]["updateStrategy"] = {"type": "OnDelete"}
        item["status"].update(updatedReplicas=0, currentRevision="old", updateRevision="new")
        self.assertEqual(kube.workload_record(item, "statefulsets.apps")["severity"], "ok")
        item["status"].pop("availableReplicas")
        self.assertTrue(kube.workload_record(item, "statefulsets.apps")["ready"])
        item["spec"]["minReadySeconds"] = 60
        self.assertFalse(kube.workload_record(item, "statefulsets.apps")["ready"])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = cluster()
        self.runner = Mock()
        self.runner.fetch.side_effect = lambda options, resource: copy.deepcopy(self.data[resource])
        self.monitor = kube.Monitor(self.runner)

    def test_healthy_snapshot_and_problem_sorting(self):
        result = self.monitor.snapshot(OPTIONS)
        self.assertEqual(result["summary"]["state"], "ok")
        self.assertEqual(result["summary"]["nodes_ready"], 2)
        self.assertEqual(result["summary"]["apps_total"], 2)
        self.data["nodes"][1] = node("worker", "False")
        self.assertEqual(self.monitor.snapshot(OPTIONS)["records"][0]["severity"], "error")
        self.data["deployments.apps"][0]["spec"]["replicas"] = 0
        self.assertEqual(self.monitor.snapshot(OPTIONS)["summary"]["apps_inactive"], 1)

    def test_partial_failure_preserves_stale_rows_and_recovers(self):
        self.monitor.snapshot(OPTIONS)
        original = self.runner.fetch.side_effect
        def fail_pods(options, resource):
            if resource == "pods":
                raise kube.CollectionError("forbidden", "Access denied", True)
            return original(options, resource)
        self.runner.fetch.side_effect = fail_pods
        result = self.monitor.snapshot(OPTIONS)
        self.assertEqual(result["summary"]["state"], "incomplete")
        self.assertEqual(result["summary"]["api"], "reachable")
        self.assertTrue(result["sources"]["nodes"]["ok"])
        self.assertTrue(all(r["stale"] for r in result["records"] if r["kind"] == "Pod"))
        self.runner.fetch.side_effect = original
        self.assertEqual(self.monitor.snapshot(OPTIONS)["summary"]["state"], "ok")

    def test_context_and_kubeconfig_change_clear_cached_data(self):
        for changed in ({"context": "other"}, {"kubeconfig": "/different/config"}):
            with self.subTest(changed=changed):
                self.setUp()
                self.monitor.snapshot(OPTIONS)
                self.runner.fetch.side_effect = kube.CollectionError("unavailable", "Connection refused")
                old = self.monitor.snapshot(OPTIONS)
                self.assertTrue(old["records"])
                self.assertEqual(old["summary"]["api"], "unreachable")
                self.assertEqual(self.monitor.snapshot({**OPTIONS, **changed})["records"], [])

    def test_no_nodes_no_system_and_malformed_data_cannot_be_healthy(self):
        self.data["nodes"] = []
        self.assertEqual(self.monitor.snapshot(OPTIONS)["summary"]["state"], "attention")
        self.data["pods"] = []
        self.assertEqual(self.monitor.snapshot(OPTIONS)["summary"]["state"], "incomplete")
        self.data["nodes"] = [{"metadata": {"name": "bad"}, "status": None}]
        result = self.monitor.snapshot(OPTIONS)
        self.assertFalse(result["sources"]["nodes"]["ok"])

    def test_disabled_or_unselected_context_makes_no_requests(self):
        for change in ({"enabled": False}, {"context": ""}):
            self.monitor.snapshot({**OPTIONS, **change})
        self.runner.fetch.assert_not_called()


class KubectlTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.executable = self.directory / "kubectl"
        shutil.copyfile(REPO / "tests/fake_kubectl.py", self.executable)
        self.executable.chmod(0o755)
        self.calls = self.directory / "calls"
        self.environment = patch.dict(os.environ, {"PATH": str(self.directory) + os.pathsep + os.environ["PATH"],
                                                   "KUBE_TEST_CALLS": str(self.calls), "KUBE_TEST_MODE": "healthy"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.runner = kube.Kubectl()
        self.addCleanup(self.runner.close)

    def test_real_subprocess_arguments_contexts_and_readonly_snapshot(self):
        self.assertEqual(self.runner.contexts("/tmp/config with spaces"), ["lab", "other"])
        options = {**OPTIONS, "kubeconfig": "/tmp/config with spaces", "context": "lab;echo secret"}
        result = kube.Monitor(self.runner).snapshot(options)
        self.assertEqual(result["summary"]["state"], "ok")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len(calls), 6)
        for args in calls[1:]:
            self.assertIn("--context=lab;echo secret", args)
            self.assertIn("--kubeconfig=/tmp/config with spaces", args)
            self.assertIn("--request-timeout=5s", args)
            self.assertIn("get", args)
            if "nodes" not in args:
                self.assertIn("--all-namespaces", args)

    def test_stderr_is_classified_without_leaking_raw_plugin_output(self):
        with patch.dict(os.environ, {"KUBE_TEST_MODE": "partial"}):
            result = kube.Monitor(self.runner).snapshot(OPTIONS)
        self.assertEqual(result["sources"]["pods"]["code"], "forbidden")
        self.assertNotIn("sensitive-plugin-text", json.dumps(result))
        self.assertEqual(kube.command_error("Unauthorized").code, "authentication")
        self.assertEqual(kube.command_error("x509 certificate expired").code, "tls")
        with patch.dict(os.environ, {"KUBE_TEST_MODE": "malformed"}):
            with self.assertRaises(kube.CollectionError) as caught:
                self.runner.fetch(OPTIONS, "nodes")
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_missing_executable_is_a_setup_error(self):
        with patch.object(kube.subprocess, "Popen", side_effect=FileNotFoundError):
            with self.assertRaises(kube.CollectionError) as caught:
                self.runner.fetch(OPTIONS, "nodes")
        self.assertEqual(caught.exception.code, "missing_kubectl")

    def test_timeout_kills_request_and_reaps_child(self):
        with patch.dict(os.environ, {"KUBE_TEST_MODE": "timeout"}):
            started = time.monotonic()
            with self.assertRaises(kube.CollectionError) as caught:
                self.runner.fetch(OPTIONS, "nodes")
            self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertFalse(self.runner.children)

    def test_watch_termination_cancels_inflight_subprocesses(self):
        path = self.directory / "config.json"
        config.save({"kubernetes": OPTIONS}, path)
        with patch.dict(os.environ, {"KUBE_TEST_MODE": "timeout"}):
            process = subprocess.Popen([sys.executable, "-B", str(REPO / "backend/kube_monitor.py"), "--watch", "--config", str(path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while not self.calls.exists() and time.monotonic() < deadline:
                time.sleep(0.03)
            self.assertTrue(self.calls.exists())
            process.terminate()
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, "")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    unittest.main()
