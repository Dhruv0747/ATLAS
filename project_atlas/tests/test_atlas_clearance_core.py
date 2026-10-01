import math
import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from atlas_clearance_core import clearance_channel


class ClearanceTests(unittest.TestCase):
    def test_reports_both_channels_and_source(self):
        result = clearance_channel(1.85, 0.51)
        self.assertEqual(result, {
            "lidar_m": 1.85,
            "ultrasonic_m": 0.51,
            "fused_m": 0.51,
            "fused_source": "ULTRASONIC",
        })

    def test_missing_ultrasonic_keeps_lidar_primary(self):
        result = clearance_channel(1.39, math.inf)
        self.assertEqual(result["fused_m"], 1.39)
        self.assertEqual(result["fused_source"], "LIDAR")
        self.assertIsNone(result["ultrasonic_m"])


if __name__ == "__main__":
    unittest.main()
