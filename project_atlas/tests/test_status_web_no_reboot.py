"""The unauthenticated, password-piping reboot action must stay removed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_status_web_estop_safety import SCRIPTS, Recorder, post, web  # noqa: E402  (stubs ROS)


class NoReboot(unittest.TestCase):
    def test_source_has_no_password_pipe_or_reboot_branch(self):
        src = (SCRIPTS / 'atlas_status_web.py').read_text(encoding='utf-8')
        self.assertNotIn('sudo -S', src)
        self.assertNotIn('action == "reboot"', src)

    def test_reboot_request_is_rejected(self):
        saved, web.ROS = web.ROS, Recorder()
        try:
            status, payload = post({'action': 'reboot'})
        finally:
            web.ROS = saved
        self.assertEqual(status, 400)
        self.assertFalse(payload['ok'])


if __name__ == '__main__':
    unittest.main()
