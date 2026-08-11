import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from atlas_vision_lidar_core import associate_detection, pixel_to_bearing


class VisionLidarCoreTests(unittest.TestCase):
    def test_image_center_is_forward(self):
        self.assertAlmostEqual(pixel_to_bearing(328, 656, math.radians(66)), 0.0)

    def test_image_left_is_positive_bearing(self):
        self.assertGreater(pixel_to_bearing(100, 656, math.radians(66)), 0.0)

    def test_associates_forward_base_point_with_rear_facing_lidar(self):
        ranges = [float("inf")] * 360
        # Raw -180 degrees becomes base-frame forward because the sensor is
        # physically mounted with a pi-yaw transform.
        ranges[0] = 1.0
        result = associate_detection(
            ranges, -math.pi, math.radians(1), 0.02, 12.0,
            math.radians(3), math.radians(-3),
        )
        self.assertIsNotNone(result)
        x, y, distance = result
        self.assertAlmostEqual(x, 0.95, places=2)
        self.assertAlmostEqual(y, 0.0, places=2)
        self.assertAlmostEqual(distance, 0.95, places=2)

    def test_rejects_scan_outside_camera_sector(self):
        ranges = [float("inf")] * 360
        ranges[90] = 1.0
        self.assertIsNone(associate_detection(
            ranges, -math.pi, math.radians(1), 0.02, 12.0,
            math.radians(3), math.radians(-3),
        ))


if __name__ == "__main__":
    unittest.main()
