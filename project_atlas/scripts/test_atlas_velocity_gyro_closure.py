import math
import unittest

from atlas_velocity_gyro_closure import integrate_velocity_gyro, pose_closure


class VelocityGyroClosureTest(unittest.TestCase):
    def test_straight_motion(self):
        wheel = [(i / 10, 1.0) for i in range(11)]
        gyro = [(i / 10, 0.0) for i in range(11)]
        result = integrate_velocity_gyro(wheel, gyro)
        self.assertAlmostEqual(result["closure_m"], 1.0)
        self.assertEqual(result["intervals_used"], 10)

    def test_turning_gyro_changes_heading(self):
        wheel = [(i / 10, 0.0) for i in range(11)]
        gyro = [(i / 10, math.pi / 2) for i in range(11)]
        result = integrate_velocity_gyro(wheel, gyro)
        self.assertAlmostEqual(result["yaw_change_deg"], 90.0)
        self.assertEqual(result["closure_m"], 0.0)

    def test_pose_closure(self):
        result = pose_closure([(0, 0, 0, 0), (1, 3, 4, math.pi / 2)])
        self.assertEqual(result["closure_m"], 5.0)
        self.assertEqual(result["yaw_change_deg"], 90.0)


if __name__ == "__main__":
    unittest.main()
