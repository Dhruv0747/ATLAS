"""Dashboard restart (2026-11-20): the old password-piping reboot stays gone; the new one needs
dashboard confirmation + same origin + a NOPASSWD sudoers rule, and latches the drive stop first."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_status_web_estop_safety import SCRIPTS, Recorder, post, web  # noqa: E402  (stubs ROS)


class SafeReboot(unittest.TestCase):
    def setUp(self):
        self.saved, web.ROS = web.ROS, Recorder()
        web.SHUTDOWN_PENDING.clear()

    def tearDown(self):
        web.ROS = self.saved
        web.SHUTDOWN_PENDING.clear()

    def test_source_never_pipes_a_password(self):
        src = (SCRIPTS / 'atlas_status_web.py').read_text(encoding='utf-8')
        self.assertNotIn('sudo -S', src)
        self.assertNotIn("'-S'", src)

    def test_reboot_without_confirmation_is_rejected(self):
        with mock.patch.object(web.atlas_wifi_web, 'same_origin', return_value=True):
            status, payload = post({'action': 'reboot'})
        self.assertEqual(status, 403)
        self.assertFalse(payload['ok'])
        self.assertFalse(web.SHUTDOWN_PENDING.is_set())

    def test_reboot_cross_origin_is_rejected(self):
        with mock.patch.object(web.atlas_wifi_web, 'same_origin', return_value=False):
            status, payload = post({'action': 'reboot', 'confirm': 'RESTART_ATLAS'})
        self.assertEqual(status, 403)
        self.assertFalse(web.SHUTDOWN_PENDING.is_set())

    def test_reboot_without_sudo_rule_is_unavailable(self):
        with mock.patch.object(web.atlas_wifi_web, 'same_origin', return_value=True), \
             mock.patch.object(web, 'reboot_sudo_rule_present', return_value=False):
            status, payload = post({'action': 'reboot', 'confirm': 'RESTART_ATLAS'})
        self.assertEqual(status, 503)
        self.assertFalse(web.SHUTDOWN_PENDING.is_set())
        self.assertNotIn('LATCH', web.ROS.events)

    def test_confirmed_reboot_latches_stop_then_restarts(self):
        calls = []
        with mock.patch.object(web.atlas_wifi_web, 'same_origin', return_value=True), \
             mock.patch.object(web, 'reboot_sudo_rule_present', return_value=True), \
             mock.patch.object(web, 'stop_rover', lambda *a, **k: calls.append('stop')), \
             mock.patch.object(web, 'run_quiet', lambda cmd, **k: calls.append(tuple(cmd)) or (True, '')), \
             mock.patch.object(web.time, 'sleep', lambda s: None), \
             mock.patch.object(web.threading, 'Thread') as thread:
            status, payload = post({'action': 'reboot', 'confirm': 'RESTART_ATLAS'})
            self.assertEqual(status, 202)
            self.assertTrue(payload['ok'])
            self.assertTrue(web.SHUTDOWN_PENDING.is_set())
            self.assertIn('LATCH', web.ROS.events)
            self.assertIn('stop', calls)
            self.assertIn('reboot_latch', [line['event'] for line in web.ROS.log_lines])
            target = thread.call_args.kwargs.get('target') or thread.call_args.args[0]
            target()
        self.assertIn(('sudo', '-n', '/sbin/shutdown', '-r', 'now'), calls)


class SudoRuleParsing(unittest.TestCase):
    def test_nopasswd_reboot_rule_detected(self):
        listing = ('User jetson may run the following commands on atlas:\n'
                   '    (ALL : ALL) ALL\n'
                   '    (root) NOPASSWD: /sbin/shutdown -h now, /sbin/shutdown -r now\n')
        self.assertTrue(web.reboot_sudo_rule_present(listing))

    def test_only_poweroff_rule_is_not_enough(self):
        listing = '    (ALL : ALL) ALL\n    (root) NOPASSWD: /sbin/shutdown -h now\n'
        self.assertFalse(web.reboot_sudo_rule_present(listing))

    def test_password_rule_is_not_enough(self):
        self.assertFalse(web.reboot_sudo_rule_present('    (root) /sbin/shutdown -r now\n'))

    def test_wider_rule_is_not_matched(self):
        self.assertFalse(web.reboot_sudo_rule_present('    (root) NOPASSWD: /sbin/shutdown\n'))


if __name__ == '__main__':
    unittest.main()
