"""2026-11-19 wheel-curvature sign (staged): servo-LOW is physical front-left. No ROS, no hardware.

The real functions are extracted from scripts/yahboom_base.py with ast (same approach as test_speed_loop_base), so the
checks exercise the code that would be deployed.
"""
import ast
import math
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from atlas_encoder_selection import four_wheel_path_scales  # noqa: E402

SOURCE = SCRIPTS / 'yahboom_base.py'
CONSTS = {'FRONT_STEER_CENTER', 'REAR_STEER_CENTER', 'FRONT_STEER_RIGHT', 'FRONT_STEER_LEFT', 'REAR_STEER_RIGHT',
          'REAR_STEER_LEFT', 'AUTONOMOUS_STEER_SIGN'}
FUNCS = {'applied_curvature_per_m', '_clamp_servo', 'opposite_steering_targets'}


def load():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) in CONSTS for t in node.targets):
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCS:
            keep.append(node)
    ns = {'math': math}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


NS = load()
L, T = 0.367, 0.260
POS = ('rear_left', 'rear_right', 'front_left', 'front_right')


def autonomous_angles(vx, wz):
    """The kinematic branch of _drive_pwm: signed vx, AUTONOMOUS_STEER_SIGN mirror, +-35 deg clamp."""
    steer = math.degrees(math.atan((L * wz) / (2.0 * vx)))
    steer = NS['AUTONOMOUS_STEER_SIGN'] * max(-35.0, min(35.0, steer))
    return NS['opposite_steering_targets'](steer / 35.0)


class AppliedCurvatureTests(unittest.TestCase):
    def test_recorded_left_turn_angles_are_positive_curvature(self):
        # stage3_roundtrip8 / penalty_test: Nav2 wz > 0 (left) applied front 50-70, rear 110-134 deg, and the IM10A
        # gyro confirmed a physical LEFT turn in 186/186 forward samples.
        for front, rear in ((50, 134), (62, 118), (70, 110)):
            self.assertGreater(NS['applied_curvature_per_m'](front, rear, L), 0.0, (front, rear))
        self.assertLess(NS['applied_curvature_per_m'](117, 64, L), 0.0)
        self.assertEqual(NS['applied_curvature_per_m'](90, 90, L), 0.0)

    def test_left_turn_makes_left_wheels_inner(self):
        k = NS['applied_curvature_per_m'](62, 118, L)
        rl, rr, fl, fr = four_wheel_path_scales(k, L, T, POS)
        self.assertLess(rl, rr)
        self.assertLess(fl, fr)

    def test_recorded_increments_agree_after_normalization(self):
        # penalty_test_20261116 CRITICAL sample (front 62 / rear 118, v 0.15 m/s): raw per-wheel increments
        # reconstructed from the logged values -> rear-left 0.30 mm, rear-right 11.9 mm, front-right 3.9 mm.
        # The old sign spread them further apart; the fixed sign must bring rear-right and front-right (both outer)
        # to the same body-centre value.
        k = NS['applied_curvature_per_m'](62, 118, L)
        s = four_wheel_path_scales(k, L, T, POS)
        old = four_wheel_path_scales(-k, L, T, POS)
        self.assertAlmostEqual(s[1], s[3], places=9)          # both outer wheels share one scale
        self.assertGreater(s[1], 1.0)
        self.assertLess(old[1], 1.0)                           # the old sign called the outer wheels inner

    def test_wheel_yaw_rate_follows_the_command_forward_and_reverse(self):
        # vz = vx * curvature must have the sign of the commanded wz, forward and backward (yahboom_base odometry).
        for vx, wz in ((0.15, 0.4), (0.15, -0.4), (0.11, 1.0), (-0.11, 1.0), (-0.11, -1.0), (0.2, 0.05)):
            front, rear = autonomous_angles(vx, wz)
            vz = vx * NS['applied_curvature_per_m'](front, rear, L)
            self.assertGreater(vz * wz, 0.0, (vx, wz, front, rear))


if __name__ == '__main__':
    unittest.main()
