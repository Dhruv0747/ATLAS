"""Step 6 wheel PID evaluation (tools/drive/wheel_pid_evaluation.py): pure decision. 2026-11-23."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'drive'))
import wheel_pid_evaluation as w  # noqa: E402

LIVE_EH = {'state': 'DEGRADED', 'faults': [], 'excluded_encoders': [3], 'selected_encoders': [1, 2, 4],
           'link_state': 'LIVE'}                       # 2026-11-23 live /api/status
PID_OFF = (ROOT / 'config' / 'drive_pid.yaml').read_text(encoding='utf-8')


class PidEvalTests(unittest.TestCase):
    def test_today_is_not_advised_and_says_why(self):
        r = w.evaluate(LIVE_EH, 'COMMANDED, NOT MEASURED', True, True, PID_OFF)
        self.assertEqual(r['verdict'], 'NOT ADVISED')
        self.assertIn('M3 excluded', r['detail'])
        self.assertIn('no angle sensor', r['detail'])
        self.assertTrue(r['checks']['speed_loop_validated'])
        self.assertTrue(r['checks']['per_wheel_pid_safe_off'])

    def test_four_healthy_encoders_advise_pid(self):
        eh = dict(LIVE_EH, state='HEALTHY', excluded_encoders=[], selected_encoders=[1, 2, 3, 4])
        self.assertEqual(w.evaluate(eh, 'COMMANDED, NOT MEASURED', True, True, PID_OFF)['verdict'], 'ADVISED')

    def test_unsafe_or_missing_data_fails(self):
        on = PID_OFF.replace('enabled: false', 'enabled: true', 1)
        r = w.evaluate(LIVE_EH, 'COMMANDED, NOT MEASURED', True, True, on)
        self.assertEqual(r['verdict'], 'FAIL'); self.assertIn('per_wheel_pid_safe_off', r['failed'])
        self.assertEqual(w.evaluate({}, None, True, True, PID_OFF)['verdict'], 'FAIL')
        self.assertEqual(w.evaluate(dict(LIVE_EH, link_state='STALE'), None, True, True, PID_OFF)['verdict'], 'FAIL')

    def test_repo_drive_pid_ships_disabled(self):
        self.assertFalse(w.evaluate(LIVE_EH, None, True, True, PID_OFF)['measured']['per_wheel_pid_enabled'])


if __name__ == '__main__':
    unittest.main()
