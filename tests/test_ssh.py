import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from support import ssh


class SshTests(unittest.TestCase):
    def test_separate_ssh_arguments_support_ipv6(self):
        self.assertEqual(ssh.ssh_command("master", "2001:db8::1"),
                         ["ssh", "-o", "ConnectTimeout=10", "-p", "22", "-l", "master", "--", "2001:db8::1"])

    def test_reject_option_and_command_injection(self):
        for host in ("-oProxyCommand=bad", "host;id", "$(id)", "host\nother", "user@host"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                ssh.ssh_command("master", host)
        with self.assertRaises(ValueError):
            ssh.ssh_command("master;id", "vm")

    def test_detected_address_only_prompts_for_username(self):
        with patch("builtins.input", return_value="master") as user_input, patch.object(ssh.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ssh.connect("test", "192.168.122.4"), 0)
        user_input.assert_called_once_with("Username: ")
        run.assert_called_once_with(ssh.ssh_command("master", "192.168.122.4"), check=False)

    def test_missing_ip_and_invalid_user_are_prompted_in_terminal(self):
        with patch("builtins.input", side_effect=["vm.local", "bad name", "master"]), patch.object(ssh.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ssh.connect("test", ""), 0)
        run.assert_called_once_with(ssh.ssh_command("master", "vm.local"), check=False)

    def test_failed_ssh_stays_visible(self):
        with patch("builtins.input", side_effect=["master", ""]) as user_input, patch.object(ssh.subprocess, "run", return_value=SimpleNamespace(returncode=255)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ssh.connect("test", "vm"), 255)
        self.assertIn("Press Enter", user_input.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
