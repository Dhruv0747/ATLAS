import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from atlas_lidar_odom_gate_core import (  # noqa: E402
    LidarOdomGate,
    StationaryPoseStabilizer,
    signed_lidar_speed,
)


class LidarOdomGateTests(unittest.TestCase):
    def test_accepts_normal_motion(self):
        gate = LidarOdomGate()
        self.assertTrue(gate.evaluate(1.0, 0.0, 0.0, 0.0).accepted)
        decision = gate.evaluate(1.1, 0.03, 0.0, 0.02)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "OK")

    def test_rejects_translation_jump_without_advancing_baseline(self):
        gate = LidarOdomGate()
        gate.evaluate(1.0, 0.0, 0.0, 0.0)
        self.assertEqual(gate.evaluate(1.1, 2.0, 0.0, 0.0).reason, "TRANSLATION_JUMP")
        self.assertTrue(gate.evaluate(1.2, 0.04, 0.0, 0.0).accepted)

    def test_rejects_yaw_jump(self):
        gate = LidarOdomGate()
        gate.evaluate(1.0, 0.0, 0.0, 0.0)
        self.assertEqual(gate.evaluate(1.1, 0.0, 0.0, math.pi).reason, "YAW_JUMP")

    def test_reinitializes_after_data_gap(self):
        gate = LidarOdomGate(max_gap_s=0.5)
        gate.evaluate(1.0, 0.0, 0.0, 0.0)
        decision = gate.evaluate(2.0, 4.0, 3.0, 1.0)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, "REINITIALIZED_AFTER_GAP")

    def test_rejects_nonfinite_and_non_monotonic(self):
        gate = LidarOdomGate()
        self.assertFalse(gate.evaluate(1.0, math.nan, 0.0, 0.0).accepted)
        gate.evaluate(1.0, 0.0, 0.0, 0.0)
        self.assertEqual(gate.evaluate(1.0, 0.0, 0.0, 0.0).reason, "NON_MONOTONIC_TIME")


class StationaryPoseStabilizerTests(unittest.TestCase):
    def test_stationary_drift_is_removed(self):
        stabilizer = StationaryPoseStabilizer()
        stabilizer.update(1.0, 2.0, 0.2, True)
        self.assertEqual(stabilizer.update(1.1, 1.9, 0.3, True), (0.0, 0.0, 0.0))

    def test_real_body_motion_is_integrated_after_rebase(self):
        stabilizer = StationaryPoseStabilizer()
        stabilizer.update(0.0, 0.0, 0.0, True)
        stabilizer.update(0.1, 0.0, 0.1, True)
        x_m, y_m, yaw = stabilizer.update(0.2, 0.01, 0.1, False)
        self.assertAlmostEqual(math.hypot(x_m, y_m), math.hypot(0.1, 0.01), places=6)
        self.assertAlmostEqual(yaw, 0.0, places=6)


class SignedLidarSpeedTests(unittest.TestCase):
    def test_uses_command_direction_without_rf2o_yaw(self):
        self.assertAlmostEqual(signed_lidar_speed(0.02, 0.2, 0.08, 0.0), 0.1)
        self.assertAlmostEqual(signed_lidar_speed(0.02, 0.2, -0.08, 0.0), -0.1)

    def test_falls_back_to_wheel_direction(self):
        self.assertAlmostEqual(signed_lidar_speed(0.03, 0.3, 0.0, -0.05), -0.1)

    def test_has_no_direction_when_stopped_or_invalid(self):
        self.assertEqual(signed_lidar_speed(0.02, 0.2, 0.0, 0.0), 0.0)
        self.assertEqual(signed_lidar_speed(0.02, 0.0, 0.1, 0.1), 0.0)


if __name__ == "__main__":
    unittest.main()
