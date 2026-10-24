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


class WatchdogSelfResume(unittest.TestCase):
    def test_watchdog_resume_never_disarms_itself_and_clears_marker(self):
        mk = Path('/tmp/ppc_marker_self.json'); mk.write_text(json.dumps({'watchdog': {'kind': 'test-sleeper', 'pid': 999999}}))
        killed = []
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes', 'ATLAS_PARKED_FROM_WATCHDOG': '1'}), mock.patch.object(M, 'MARKER', mk), \
             mock.patch.object(M.os, 'killpg', side_effect=lambda *a: killed.append(a)), \
             mock.patch.object(M, 'ros', return_value={'nav_active': True, 'loc_active': True, 'nav_states': {n: 'active' for n in M.NAV_NODES}}):
            self.assertTrue(M.cmd_resume('watchdog'))
        self.assertEqual(killed, []); self.assertFalse(mk.exists())


FAKE_SYSTEMCTL = """#!/bin/bash
# fake systemctl --user <is-active|stop|start> <unit>; state dir $FAKE_UNITS; failing starts listed in $FAKE_UNITS/fail
echo "$(date +%s.%N) $2 $3" >> "$FAKE_UNITS/calls"
f="$FAKE_UNITS/$3"
case "$2" in
  is-active) cat "$f" 2>/dev/null || echo inactive ;;
  stop) echo inactive > "$f" ;;
  start) if grep -qx "$3" "$FAKE_UNITS/fail" 2>/dev/null; then echo failed > "$f"; exit 1; fi; echo active > "$f" ;;
esac
"""


class AIServicePause(unittest.TestCase):
    ESSENTIAL = ('atlas-voice-companion', 'atlas-local-llm', 'atlas-agent-supervisor', 'atlas-camera', 'rover-base-telemetry',
                 'atlas-cmd-vel-mux', 'atlas-ekf', 'atlas-localization', 'atlas-lidar', 'atlas-safety-status', 'atlas-sensor-recovery',
                 'atlas-mission-control', 'atlas-localization-monitor', 'rover-status-web', 'atlas-im10a', 'atlas-uno-r4-sensor-hub',
                 'atlas-scan-filter', 'atlas-lidar-odom', 'atlas-lidar-odom-gate', 'rover-radar', 'atlas-remote', 'atlas-tight-recovery')

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        (d / 'systemctl').write_text(FAKE_SYSTEMCTL); (d / 'systemctl').chmod(0o755)
        self.units = d / 'units'; self.units.mkdir()
        for u in M.AI_SERVICES:
            (self.units / (u + '.service')).write_text('active')
        (self.units / 'atlas-visual-cloud-server.service').write_text('inactive')   # one already off
        self.env = mock.patch.dict(os.environ, {'FAKE_UNITS': str(self.units), 'OWNER_APPROVED': 'yes'}); self.env.start()
        self.p = [mock.patch.object(M, 'SYSTEMCTL', str(d / 'systemctl')), mock.patch.object(M, 'MARKER', d / 'marker.json'),
                  mock.patch.object(M, 'parked_checks', return_value={}), mock.patch.object(M, 'arm_watchdog', return_value={'kind': 'x'}),
                  mock.patch.object(M, 'disarm_watchdog'), mock.patch.object(M.time, 'sleep')]
        for x in self.p: x.start()
        self.nav = {'state': 'active'}; self.order = []
        def ros(action, t=30.0):
            self.order.append('ros:' + action)
            if action == 'pause': self.nav['state'] = 'inactive'
            if action == 'resume': self.nav['state'] = 'active'
            a = self.nav['state'] == 'active'
            return {'nav_active': a, 'loc_active': True, 'manage_success': True, 'nav_states': {n: self.nav['state'] for n in M.NAV_NODES},
                    'loc_states': {'map_server': 'active', 'amcl': 'active'}}
        self.p.append(mock.patch.object(M, 'ros', side_effect=ros)); self.p[-1].start()

    def tearDown(self):
        for x in self.p: x.stop()
        self.env.stop(); self.tmp.cleanup()

    def calls(self):
        return [l.split()[1:] for l in (self.units / 'calls').read_text().splitlines()] if (self.units / 'calls').exists() else []

    def test_list_is_fixed_and_excludes_every_essential_service(self):
        self.assertFalse(set(M.AI_SERVICES) & set(self.ESSENTIAL))
        src = (ROOT / 'tools/vision3d/atlas_parked_camera_profile.py').read_text()
        self.assertNotIn("'restart'", src); self.assertNotIn('"restart"', src)
        self.assertNotIn('--with-ai-pause\', nargs', src)                         # flag is boolean, not a unit list

    def test_pause_stops_only_running_ai_services_after_nav_pause_and_records_them(self):
        M.cmd_pause(600, with_ai=True)
        stops = [c[1] for c in self.calls() if c[0] == 'stop']
        self.assertEqual(stops, [u + '.service' for u in M.AI_SERVICES if u != 'atlas-visual-cloud-server'])
        self.assertEqual(json.loads(M.MARKER.read_text())['ai_services_stopped'], [u for u in M.AI_SERVICES if u != 'atlas-visual-cloud-server'])
        self.assertEqual(self.order[:2], ['ros:status', 'ros:pause'])

    def test_resume_restarts_ai_services_before_navigation_and_never_starts_one_that_was_off(self):
        M.cmd_pause(600, with_ai=True); self.order.clear(); open(self.units / 'calls', 'w').close()
        self.assertTrue(M.cmd_resume('test'))
        starts = [c[1] for c in self.calls() if c[0] == 'start']
        self.assertEqual(starts, [u + '.service' for u in M.AI_SERVICES if u != 'atlas-visual-cloud-server'])
        self.assertEqual((self.units / 'atlas-visual-cloud-server.service').read_text().strip(), 'inactive')
        self.assertIn('ros:resume', self.order); self.assertFalse(M.MARKER.exists())
        for u in M.AI_SERVICES[:-1]: self.assertEqual((self.units / (u + '.service')).read_text().strip(), 'active')

    def test_failed_ai_restart_is_reported_once_and_navigation_still_resumes(self):
        (self.units / 'fail').write_text('atlas-agent-team.service\n')
        M.cmd_pause(600, with_ai=True); open(self.units / 'calls', 'w').close()
        out = []
        with mock.patch.object(M, 'log', side_effect=lambda e, **k: out.append(e)):
            self.assertTrue(M.cmd_resume('test'))
        self.assertIn('AI_RESUME_INCOMPLETE', out); self.assertIn('ros:resume', self.order)
        self.assertEqual(sum(1 for c in self.calls() if c == ['start', 'atlas-agent-team.service']), 1)   # no retry loop

    def test_without_flag_no_service_is_touched(self):
        M.cmd_pause(600, with_ai=False); M.cmd_resume('test')
        self.assertFalse([c for c in self.calls() if c[0] in ('stop', 'start')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
