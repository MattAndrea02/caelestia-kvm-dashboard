"""Exercise measurement semantics and failures without changing any real VMs."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from support import monitor


class MeasurementTests(unittest.TestCase):
    def test_guest_memory_requires_fresh_available_stats(self):
        stats = {"available": 2048, "usable": 768, "last_update": 100}
        self.assertEqual(monitor.guest_memory_used(stats, 110), 1280)
        self.assertIsNone(monitor.guest_memory_used(stats, 161))
        self.assertIsNone(monitor.guest_memory_used({"rss": 512}, 110))
        self.assertIsNone(monitor.guest_memory_used({**stats, "usable": 3000}, 110))

    def test_cpu_sampling_and_restart_do_not_report_false_spikes(self):
        domain = Mock()
        domain.UUIDString.return_value = "uuid"
        domain.ID.return_value = 1
        domain.isActive.return_value = True
        domain.name.return_value = "test"
        domain.memoryStats.return_value = {}
        domain.interfaceAddresses.return_value = {}
        sampler = monitor.Monitor([])
        domain.info.return_value = [1, 2048, 2048, 2, 1_000_000_000]
        with patch.object(monitor.time, "monotonic", return_value=10):
            self.assertIsNone(sampler.domain_snapshot(domain, "test")['cpu_percent'])
        domain.info.return_value[-1] = 3_000_000_000
        with patch.object(monitor.time, "monotonic", return_value=12):
            self.assertEqual(sampler.domain_snapshot(domain, "test")['cpu_percent'], 50)
        domain.ID.return_value = 2
        with patch.object(monitor.time, "monotonic", return_value=14):
            self.assertIsNone(sampler.domain_snapshot(domain, "test")['cpu_percent'])
        domain.isActive.return_value = False
        domain.info.return_value[0] = 5
        snapshot = sampler.domain_snapshot(domain, "test")
        self.assertFalse(snapshot["can_ssh"])
        self.assertEqual(snapshot["state"], "Down")
        self.assertIsNone(snapshot["guest_used_kib"])

    def test_address_fallback_filters_loopback_and_link_local(self):
        domain = Mock()
        domain.interfaceAddresses.side_effect = [monitor.libvirt.libvirtError("unsupported"), {
            "vnet0": {"addrs": [{"addr": ip} for ip in ["::1", "fe80::1", "192.168.122.4", "127.0.0.1", "bad", "2001:db8::1"]]}
        }]
        self.assertEqual(monitor.addresses(domain), ["192.168.122.4", "2001:db8::1"])

    def test_startup_and_shutdown_states(self):
        domain = Mock()
        domain.UUIDString.return_value = "uuid"
        domain.ID.return_value = -1
        domain.isActive.return_value = False
        domain.name.return_value = "test"
        domain.memoryStats.return_value = {}
        domain.interfaceAddresses.return_value = {}
        domain.info.return_value = [5, 2048, 2048, 2, 0]
        sampler = monitor.Monitor([])
        self.assertEqual(sampler.domain_snapshot(domain, "test")["state"], "Down")
        domain.isActive.return_value = True
        domain.ID.return_value = 1
        domain.info.return_value[0] = 1
        with patch.object(monitor.time, "monotonic", return_value=10):
            self.assertEqual(sampler.domain_snapshot(domain, "test")["state"], "Starting up")
        with patch.object(monitor.time, "monotonic", return_value=21):
            self.assertEqual(sampler.domain_snapshot(domain, "test")["state"], "Up")
        domain.info.return_value[0] = 4
        self.assertEqual(sampler.domain_snapshot(domain, "test")["state"], "Shutting down")

    def test_partial_connection_failure_retains_other_vms(self):
        connection = Mock()
        domain = Mock()
        connection.listAllDomains.return_value = [domain]
        sampler = monitor.Monitor(["good", "bad"])
        data = {"key": "one", "name": "vm", "active": True, "up": False, "vcpus": 2, "memory_kib": 4096}
        with patch.object(monitor.libvirt, "openReadOnly", side_effect=[connection, monitor.libvirt.libvirtError("denied")]), patch.object(sampler, "domain_snapshot", return_value=data):
            result = sampler.snapshot()
        self.assertEqual(result["machines"], [data])
        self.assertEqual(result["summary"]["other_active"], 1)
        self.assertEqual(result["summary"]["vcpus"], 2)
        self.assertIn("denied", result["errors"][0])
        sampler.close()

    def test_default_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.assertEqual(monitor.settings(path)["uris"], monitor.DEFAULT_URIS)
            path.write_text('{"interval": 0}')
            with self.assertRaises(ValueError):
                monitor.settings(path)

    @unittest.skipIf(monitor.libvirt is None, "libvirt not installed")
    def test_readonly_libvirt_test_driver(self):
        sampler = monitor.Monitor(["test:///default"])
        try:
            first = sampler.snapshot()
            second = sampler.snapshot()
            self.assertEqual(first["errors"], [])
            self.assertEqual(first["machines"][0]["state"], "Up")
            self.assertIsNotNone(second["machines"][0]["cpu_percent"])
        finally:
            sampler.close()


if __name__ == "__main__":
    unittest.main()
