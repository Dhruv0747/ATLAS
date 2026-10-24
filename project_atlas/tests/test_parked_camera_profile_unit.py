"""Unit tests for atlas_parked_camera_profile.py that need no ROS (offline)."""
import importlib.util, json, os, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ppc', ROOT / 'tools/vision3d/atlas_parked_camera_profile.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class FakeDash:
    def __init__(self):
        self.c = {}; outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                c = outer.c
                pol = {'stop_latched': c.get('stop_latched', True), 'manual_only': c.get('manual_only', True), 'commission_armed': c.get('commission_armed', False), 'source': c.get('source', 'STOPPED')}
                ros = {'control_policy': {'value': json.dumps(pol), 'age': c.get('policy_age', 0.2)}, 'cmd_vel': {'value': {'lin': c.get('lin', 0.0), 'ang': 0.0}, 'age': 0.2},
                       'mission_status': {'value': c.get('mission', 'READY'), 'age': 0.4}, 'motor_speed': {'value': c.get('speed', 0.0), 'age': 0.3},
                       'amcl_quality': {'value': {}, 'age': c.get('amcl_age', 1.0)}}
                body = json.dumps({'ros': ros} if self.path.startswith('/api/status') else {'latched': c.get('estop', True)}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d' % self.srv.server_address[1]


class ParkedChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = FakeDash(); M.DASH = cls.d.url

    def setUp(self):
        self.d.c = {}

    def test_parked_robot_passes(self):
        with mock.patch.object(M, 'astra_running', return_value=False):
            self.assertTrue(M.parked_checks()['estop_latched'])

    def test_each_unsafe_condition_refuses(self):
        cases = {'stop_latched': False, 'manual_only': False, 'commission_armed': True, 'source': 'WEB', 'policy_age': 9.0, 'lin': 0.05,
                 'mission': 'NAVIGATING', 'speed': 0.2, 'amcl_age': 30.0, 'estop': False}
        for k, v in cases.items():
            self.d.c = {k: v}
            with mock.patch.object(M, 'astra_running', return_value=False), self.assertRaises(M.Refuse, msg=k):
                M.parked_checks()
        self.d.c = {}
        with mock.patch.object(M, 'astra_running', return_value=True), self.assertRaises(M.Refuse):
            M.parked_checks()


class Approval(unittest.TestCase):
    def test_mutating_commands_require_owner_approval(self):
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': ''}):
            for f in (lambda: M.cmd_pause(600), lambda: M.cmd_resume(), lambda: M.cmd_session(600, 300)):
                with self.assertRaises(M.Refuse): f()


class Watchdog(unittest.TestCase):
    def test_systemd_timer_command_is_bounded_and_resumes_only(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd); return mock.Mock(returncode=0, stderr='')
        with mock.patch.dict(os.environ, {'ATLAS_PARKED_TEST_WATCHDOG': ''}), mock.patch.object(M.subprocess, 'run', side_effect=fake_run):
            info = M.arm_watchdog(600)
        run = calls[-1]
        self.assertEqual(run[:2], ['systemd-run', '--user']); self.assertIn('--on-active=600s', run)
        self.assertIn('--unit=' + M.WATCHDOG_UNIT, run); self.assertIn('--setenv=FASTDDS_BUILTIN_TRANSPORTS=UDPv4', run)
        self.assertTrue(run[-1].endswith('resume --reason watchdog')); self.assertNotIn('restart', ' '.join(run))
        self.assertEqual(info['kind'], 'systemd-timer')

    def test_arm_failure_refuses_before_any_pause(self):
        with mock.patch.dict(os.environ, {'ATLAS_PARKED_TEST_WATCHDOG': ''}), \
             mock.patch.object(M.subprocess, 'run', return_value=mock.Mock(returncode=1, stderr='no user bus')):
            with self.assertRaises(M.Refuse): M.arm_watchdog(600)

    def test_pause_arms_watchdog_before_sending_pause(self):
        order = []
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}), mock.patch.object(M, 'MARKER', Path('/tmp/ppc_marker_test.json')), \
             mock.patch.object(M, 'parked_checks', return_value={}), \
             mock.patch.object(M, 'arm_watchdog', side_effect=lambda s: order.append('arm') or {'kind': 'x'}), \
             mock.patch.object(M, 'ros', side_effect=lambda a, t=30.0: order.append(a) or {'nav_active': a != 'pause', 'loc_active': True, 'manage_success': True,
                               'nav_states': {n: ('inactive' if a == 'pause' else 'active') for n in M.NAV_NODES}, 'loc_states': {'map_server': 'active', 'amcl': 'active'}}), \
             mock.patch.object(M.time, 'sleep'):
            try:
                M.cmd_pause(600)
            finally:
                Path('/tmp/ppc_marker_test.json').unlink(missing_ok=True)
        self.assertEqual(order[:3], ['status', 'arm', 'pause'])


class NoServiceRestarts(unittest.TestCase):
    def test_tool_never_restarts_stops_or_starts_services(self):
        src = (ROOT / 'tools/vision3d/atlas_parked_camera_profile.py').read_text()
        for bad in ("'restart'", '"restart"', "'start', 'atlas", 'systemctl --user restart', "'stop', 'atlas"):
            self.assertNotIn(bad, src)
        self.assertNotIn("command = 4", src); self.assertNotIn('SHUTDOWN', src.split('# ----')[1] if '# ----' in src else '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
