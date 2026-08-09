import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from atlas_scan_geometry import (  # noqa: E402
    ray_in_base_sector,
    sensor_ray_in_base_degrees,
    wrap_degrees,
)


class AtlasScanGeometryTests(unittest.TestCase):
    def test_wrap_degrees(self):
        self.assertEqual(wrap_degrees(180.0), -180.0)
        self.assertEqual(wrap_degrees(360.0), 0.0)
        self.assertEqual(wrap_degrees(-270.0), 90.0)

    def test_rear_facing_sensor_zero_ray_is_rover_rear(self):
        self.assertEqual(sensor_ray_in_base_degrees(0.0, 180.0), -180.0)
        self.assertTrue(ray_in_base_sector(0.0, 180.0, 25.0, 180.0))
        self.assertFalse(ray_in_base_sector(0.0, 0.0, 25.0, 180.0))

    def test_rear_facing_sensor_pi_ray_is_rover_front(self):
        self.assertEqual(sensor_ray_in_base_degrees(180.0, 180.0), 0.0)
        self.assertTrue(ray_in_base_sector(180.0, 0.0, 25.0, 180.0))


if __name__ == "__main__":
    unittest.main()
