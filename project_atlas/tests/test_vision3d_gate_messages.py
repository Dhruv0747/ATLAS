"""26 Oct 2026: clear Vision Lab refusal text for the stationary gate (E-STOP released / zero speed unconfirmed).
Offline: simulated worker (fake clock, no camera/ROS/network/services) with the REAL stationary_gate policy check.
The gate decision, limits and E-STOP behaviour are unchanged; only the operator explanation is added."""
import hashlib
import json
import subprocess
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_vision3d_stage31b_guard import Sim, R   # noqa: E402

ESTOP = 'ATLAS is not parked. Press B on the remote to engage E-STOP, wait 2 seconds, then start 3D Vision Lab.'
ZERO = 'ATLAS cannot confirm zero speed. Check the drive safety status before starting 3D Vision Lab.'


def ros(latched=True, cmd_age=0.1, policy_age=0.1, source='STOPPED', reason='REMOTE STOP: B pressed'):
    return {'control_policy': {'age': policy_age, 'value': json.dumps({'stop_latched': latched, 'stop_reason': reason,
            'manual_only': True, 'commission_armed': False, 'source': source})},
            'cmd_vel': {'age': cmd_age, 'value': {'lin': 0.0, 'ang': 0.0}}}


class OperatorMessage(unittest.TestCase):
    def test_exact_texts(self):
        self.assertEqual(R.MSG_ESTOP_RELEASED, ESTOP); self.assertEqual(R.MSG_ZERO_SPEED_UNCONFIRMED, ZERO)

    def test_released_with_stale_cmd(self):           # 26 Oct field case: released, mux idle -> stale cmd_vel first
        self.assertEqual(R.operator_message('stale or missing cmd_vel', ros(latched=False, cmd_age=189.3)), ESTOP)

    def test_released_with_fresh_cmd(self):
        self.assertEqual(R.operator_message('stationary policy admission failed', ros(latched=False)), ESTOP)

    def test_latched_but_cmd_stale(self):
        self.assertEqual(R.operator_message('stale or missing cmd_vel', ros(cmd_age=5.0)), ZERO)

    def test_unknown_policy_keeps_raw(self):
        for r in ({}, ros(policy_age=3.0), {'control_policy': {'age': 0.1, 'value': 'not json'}},
                  {'control_policy': {'age': True, 'value': {'stop_latched': False}}}, None):
            self.assertIsNone(R.operator_message('stale or missing cmd_vel', r))

    def test_other_refusals_keep_raw(self):
        self.assertIsNone(R.operator_message('stationary policy admission failed', ros(source='REMOTE')))  # latched, not STOPPED
        for raw in ('nonzero/unknown motor command', 'RESOURCE BLOCKED: CPU', 'viewer lease expired', ''):
            self.assertIsNone(R.operator_message(raw, ros(latched=False)))


class WorkerRefusals(unittest.TestCase):
    def test_estop_released_refuses_before_camera_with_clear_text(self):
        s = Sim(ros=lambda i: ros(latched=False, cmd_age=189.3, reason='REMOTE STOP: released by operator')).run()
        self.assertEqual(s.state['state'], 'OFF')
        self.assertEqual(s.state['reason'], ESTOP); self.assertEqual(s.state['operator_message'], ESTOP)
        self.assertEqual(s.state['diagnostic_reason'], 'stale or missing cmd_vel')
        stop = [e for e in s.state['lifecycle'] if e['event'] == 'session_stopping']
        self.assertEqual(stop[-1]['reason'], 'stale or missing cmd_vel')     # raw reason preserved in diagnostics
        self.assertIsNone(s.launched_at); self.assertFalse(s.killed)          # camera never started, nothing retried

    def test_latched_but_zero_speed_unconfirmed(self):
        s = Sim(ros=lambda i: ros(cmd_age=4.0)).run()
        self.assertEqual(s.state['reason'], ZERO); self.assertEqual(s.state['diagnostic_reason'], 'stale or missing cmd_vel')
        self.assertIsNone(s.launched_at)

    def test_released_during_session_stops_camera(self):
        s = Sim(ros=lambda i: ros(latched=i < 10)).run()
        self.assertEqual(s.state['reason'], ESTOP); self.assertIsNotNone(s.launched_at)
        self.assertTrue(s.state['driver_stopped']); self.assertEqual(s.killed[0].args, (4242, R.signal.SIGINT))

    def test_parked_session_starts_and_completes(self):
        s = Sim(ros=lambda i: ros()).run()
        self.assertIn('session complete', s.state['reason']); self.assertIsNotNone(s.launched_at)
        self.assertNotIn('operator_message', s.state); self.assertNotIn('diagnostic_reason', s.state)

    def test_resource_block_unchanged(self):
        s = Sim(ros=lambda i: ros(), cpu=lambda i, w: 80.0 if i == 1 else 64.0).run()
        self.assertEqual(s.state['state'], 'RESOURCE BLOCKED'); self.assertNotIn('operator_message', s.state)


class SafetyUnchanged(unittest.TestCase):
    def test_gate_file_identical_to_deployed(self):
        gate = (ROOT / 'tools/vision3d/stationary_gate.py').read_bytes()
        self.assertEqual(hashlib.sha256(gate).hexdigest(), '0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9')

    def test_no_new_control_paths(self):
        src = (ROOT / 'scripts/atlas_vision3d_runtime.py').read_text()
        body = src[src.index('def operator_message'):src.index('def lifecycle_event')]
        for bad in ('publish', 'remote_stop', 'reset', 'systemctl', 'Popen', 'cmd_vel_mux', 'urlopen'):
            self.assertNotIn(bad, body)
        self.assertEqual((R.MIN_CPU_WINDOW_S, R.MAX_CPU_WINDOW_S), (1.0, 2.0))


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class DashboardText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = r"""
const S = require(process.argv[1]);
const rt = (x) => Object.assign({ state: 'OFF', mode: 'depth', worker_pid: 31, driver_stopped: true }, x);
console.log(JSON.stringify({
  estop: S.sessionView(rt({ reason: process.argv[2], operator_message: process.argv[2], diagnostic_reason: 'stale or missing cmd_vel' }), {}, S.newMemo(), 0),
  zero: S.sessionView(rt({ reason: process.argv[3], operator_message: process.argv[3] }), {}, S.newMemo(), 0),
  midway: S.sessionView(rt({ driver_pid: 9, reason: process.argv[2], operator_message: process.argv[2] }), {}, S.newMemo(), 0),
  legacy: S.sessionView(rt({ reason: 'stationary policy admission failed' }), {}, S.newMemo(), 0),
  done: S.sessionView(rt({ reason: '60-second session complete; explicit Start required' }), {}, S.newMemo(), 0) }));"""
        out = subprocess.check_output(['node', '-e', js, str(ROOT / 'web/v2/vision3d_state.js'), ESTOP, ZERO], text=True)
        cls.v = json.loads(out)

    def test_estop_text_shown_verbatim(self):
        self.assertEqual(self.v['estop']['text'], ESTOP); self.assertEqual(self.v['estop']['title'], 'Not started')
        self.assertEqual(self.v['estop']['tone'], 'warn')

    def test_zero_speed_text(self):
        self.assertEqual(self.v['zero']['text'], ZERO)

    def test_stopped_mid_session_title(self):
        self.assertEqual(self.v['midway']['title'], 'Stopped safely'); self.assertTrue(self.v['midway']['text'].startswith(ESTOP))

    def test_older_reasons_unchanged(self):
        self.assertIn('not confirmed stopped', self.v['legacy']['text'])
        self.assertIn('60-second session ended', self.v['done']['text'])


if __name__ == '__main__':
    unittest.main()
