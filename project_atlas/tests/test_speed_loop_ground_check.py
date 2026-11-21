"""Pure parts of tools/drive/speed_loop_ground_check.py (bounds and verdict). No ROS. 2026-11-15."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'drive'))
import speed_loop_ground_check as g  # noqa: E402


def ramp(target, seconds=6.0, steady=None):
    steady = target if steady is None else steady
    out, d = [], 0.0
    for k in range(int(seconds * 10)):
        t = k / 10
        v = 0.0 if t < 0.5 else steady
        d += v * 0.1
        out.append({'t': t, 'v': v, 'd': d})
    return out


class GroundCheckTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(g.bounded_args(0.10, 0.6, 12.0), (0.10, 0.6, 12.0))
        for bad in ((0.3, 0.6, 12), (0.01, 0.6, 12), (0.1, 2.0, 12), (0.1, 0.6, 30), (0.1, 0.6, 1)):
            with self.assertRaises(ValueError):
                g.bounded_args(*bad)

    def test_pass(self):
        r = g.evaluate(ramp(0.10), 0.10, 'DISTANCE', icp_distance=0.52)
        self.assertEqual(r['verdict'], 'PASS', r['checks'])

    def test_open_loop_overspeed_fails(self):
        r = g.evaluate(ramp(0.10, steady=0.45), 0.10, 'DISTANCE')
        self.assertEqual(r['verdict'], 'FAIL')
        self.assertFalse(r['checks']['peak_below_limit'])

    def test_guard_stop_or_no_start_fails(self):
        self.assertEqual(g.evaluate(ramp(0.10), 0.10, 'STOP_LIDAR_0.55M')['verdict'], 'FAIL')
        self.assertEqual(g.evaluate(ramp(0.10, steady=0.0), 0.10, 'TIMEOUT')['verdict'], 'FAIL')

    def test_icp_disagreement_fails(self):
        self.assertEqual(g.evaluate(ramp(0.10), 0.10, 'DISTANCE', icp_distance=0.2)['verdict'], 'FAIL')



class EffectiveTargetTests(unittest.TestCase):
    def test_uses_base_reported_target(self):
        smp = [{'t': 0.1 * i, 'v': 0.0, 'd': 0.0, 'base_target': 0.075} for i in range(10)]
        self.assertEqual(g.effective_target(smp, 0.15), 0.075)
        self.assertEqual(g.effective_target([{'t': 0, 'v': 0, 'd': 0}], 0.15), 0.15)

    def test_breakaway_surge_before_steady_window_ignored(self):
        smp = [{'t': 0.1 * i, 'd': 0.006 * i, 'v': (0.27 if 5 <= i <= 7 else 0.075 if i > 7 else 0.0)}
               for i in range(80)]
        r = g.evaluate(smp, 0.075, 'DISTANCE')
        self.assertTrue(r['checks']['peak_below_limit'], r)
        late = [dict(s, v=0.3) if s['t'] >= 3 and s['t'] < 3.3 else s for s in smp]
        self.assertFalse(g.evaluate(late, 0.075, 'DISTANCE')['checks']['peak_below_limit'])

if __name__ == '__main__':
    unittest.main()
