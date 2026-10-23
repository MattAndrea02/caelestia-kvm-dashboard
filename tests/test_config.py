from pathlib import Path
import tempfile
import unittest

from support import config, ssh


class ConfigTests(unittest.TestCase):
    def test_atomic_save_roundtrip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/config.json"
            data = config.normalize({"ssh": {"port": 2222, "username": "master"}})
            config.save(data, path)
            self.assertEqual(config.load(path), data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.glob(".vm-dashboard-*")), [])

    def test_invalid_settings_do_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config.save({}, path)
            previous = path.read_text()
            for patch in ({"ssh": {"port": 0}}, {"ssh": {"port": 65536}}, {"interval": 0}, {"uris": []}, {"ssh": {"username": "x;id"}}):
                with self.subTest(patch=patch), self.assertRaises(ValueError):
                    config.save(patch, path)
                self.assertEqual(path.read_text(), previous)

    def test_per_vm_overrides_inherit_unspecified_defaults(self):
        data = config.normalize({"ssh": {"port": 2222, "username": "master"},
                                 "machines": {"vm": {"port": 0, "host": "vm.local", "username": "root"}}})
        options = config.ssh_options(data, "vm", "192.168.122.4")
        self.assertEqual(options["port"], 2222)
        self.assertEqual(options["username"], "root")
        self.assertEqual(options["host"], "vm.local")
        self.assertEqual(config.ssh_options(data, "other", "192.168.122.5")["username"], "master")

    def test_ssh_port_timeout_and_identity_are_separate_arguments(self):
        command = ssh.ssh_command("master", "vm", 2222, 30, "/tmp/key with spaces")
        self.assertEqual(command, ["ssh", "-o", "ConnectTimeout=30", "-p", "2222", "-l", "master", "-i", "/tmp/key with spaces", "--", "vm"])


if __name__ == "__main__":
    unittest.main()
