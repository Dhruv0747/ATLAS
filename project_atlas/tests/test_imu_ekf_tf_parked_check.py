"""Pure parts of tools/localization/imu_ekf_tf_parked_check.py (Stage 4 part A, parked). No ROS. 2026-11-23."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'localization'))
import imu_ekf_tf_parked_check as g  # noqa: E402


def data(seconds=60.0, hz=10.0, gz=0.0, ekf_yaw_end=0.0, wheel=0.0, cov=0.0001, gap_at=None):
    n = int(seconds * hz)
    ts = [k / hz for k in range(n)]
    if gap_at is not None:
        ts = [t + (0.5 if t >= gap_at else 0.0) for t in ts]
    imu = [(t, gz, cov) for t in ts]
    ekf = [(t, 1.0, 2.0, 30.0 + ekf_yaw_end * k / (n - 1)) for k, t in enumerate(ts)]
    return imu, ekf, [wheel] * 600, {'odom->base_link': int(10 * seconds), 'map->odom': int(7 * seconds)}


class ParkedCheckTests(unittest.TestCase):
    def ev(self, **kw):
        imu, ekf, wheel, tf = data(**kw)
        return g.evaluate(imu, ekf, wheel, tf, 60.0)

    def test_bounds(self):
        self.assertEqual(g.bounded_duration(60.0), 60.0)
        for bad in (5.0, 300.0):
            with self.assertRaises(ValueError):
                g.bounded_duration(bad)

    def test_like_the_live_rover_passes(self):          # 2026-11-23 probe: 10.1 Hz, gz 0, EKF 10 Hz, TF 10 / 7.4 Hz
        r = self.ev()
        self.assertEqual(r['verdict'], 'PASS', r['failed'])

    def test_bias_and_drift_fail(self):
        r = self.ev(gz=0.003)                           # 0.003 rad/s -> 10 deg/min
        self.assertIn('imu_bias', r['failed']); self.assertIn('imu_drift', r['failed'])

    def test_missing_covariance_fails(self):
        self.assertIn('imu_covariance', self.ev(cov=0.0)['failed'])

    def test_gap_and_ekf_drift_fail(self):
        self.assertIn('imu_rate', self.ev(gap_at=20.0)['failed'])
        self.assertIn('ekf_drift', self.ev(ekf_yaw_end=2.0)['failed'])

    def test_moving_is_reported_as_moved_not_fail(self):
        self.assertEqual(self.ev(wheel=0.05)['verdict'], 'MOVED')

    def test_no_data_fails_cleanly(self):
        r = g.evaluate([], [], [], {}, 60.0)
        self.assertEqual(r['verdict'], 'FAIL')
        self.assertIn('parked', r['failed'])

    def test_tool_is_read_only(self):
        src = (ROOT / 'tools' / 'localization' / 'imu_ekf_tf_parked_check.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertNotIn('create_publisher', calls)
        self.assertNotIn('create_client', calls)
        self.assertNotIn('cmd_vel', src)
        self.assertIn('atlas_master_plan.record_stage4a(res, out.name)', src)


if __name__ == '__main__':
    unittest.main()
