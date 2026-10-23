"""Verify that installation is repeatable, reversible and respects local edits."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from support import setup


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "source"
        self.target = Path(self.directory.name) / "target"
        self.source.mkdir()
        (self.source / "shell.qml").write_text('import "modules"\n')
        (self.source / setup.CONTENT).parent.mkdir(parents=True)
        (self.source / setup.CONTENT).write_text(
            'import QtQuick\n'
            '                enabled: Config.dashboard.showWeather\n            }\n'
            '            Behavior on contentX {\n')
        (self.source / "untouched.txt").write_text("original")
        (self.source / setup.PAGE_REGISTRY).parent.mkdir(parents=True)
        (self.source / setup.PAGE_REGISTRY).write_text('        // About\n')
        (self.source / setup.PAGE_COMPONENTS).write_text('import QtQuick\n        // About\n')

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()):
            setup.install(self.source, self.target)

    def test_repeat_install_keeps_source_unchanged_and_links_unmodified_files(self):
        before = setup.fingerprint(self.source)
        self.install()
        first = setup.fingerprint(self.target)
        self.install()
        self.assertEqual(setup.fingerprint(self.source), before)
        self.assertEqual(setup.fingerprint(self.target), first)
        self.assertTrue((self.target / "untouched.txt").is_symlink())
        self.assertFalse((self.target / "shell.qml").is_symlink())
        self.assertIn('text: "VMs"', (self.target / setup.CONTENT).read_text())
        self.assertEqual((self.target / setup.CONTENT).read_text().count('text: "Kubernetes"'), 1)
        self.assertIn("KubeSettingsPage", (self.target / setup.PAGE_COMPONENTS).read_text())
        self.assertIn('label: "Kubernetes"', (self.target / setup.PAGE_REGISTRY).read_text())
        self.assertTrue((self.target / "modules/dashboard/vms/kube_monitor.py").is_file())
        self.assertTrue((self.target / "modules/dashboard/vms/KubeTab.qml").is_file())
        setup.verify_owned(self.target)  # The same check guards uninstall.

    def test_unmanaged_config_and_local_edits_are_preserved(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            self.install()
        self.target.rmdir()
        self.install()
        (self.target / setup.CONTENT).write_text("user edit")
        with self.assertRaisesRegex(ValueError, "local changes"):
            self.install()
        self.assertEqual((self.target / setup.CONTENT).read_text(), "user edit")

    def test_upstream_breakage_fails_before_replacing_working_install(self):
        self.install()
        before = setup.fingerprint(self.target)
        (self.source / setup.CONTENT).write_text("a future incompatible dashboard")
        with self.assertRaisesRegex(ValueError, "integration point"):
            self.install()
        self.assertEqual(setup.fingerprint(self.target), before)


if __name__ == "__main__":
    unittest.main()
