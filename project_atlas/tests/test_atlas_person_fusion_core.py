#!/usr/bin/env python3
import math
import unittest

from atlas_person_fusion_core import associate_radar, camera_person, parse_radar_targets


class PersonFusionCoreTests(unittest.TestCase):
    def test_parse_targets(self):
        targets = parse_radar_targets("T1:x=300mm,y=1200mm,spd=-40cm/s | T2:x=-200mm,y=900mm,spd=0cm/s")
        self.assertEqual(len(targets), 2)
        self.assertAlmostEqual(targets[0]["speed_mps"], -0.4)

    def test_camera_person(self):
        person = camera_person({"width": 640, "height": 360, "detections": [
            {"label": "person", "confidence": 0.9, "x1": 280, "x2": 360, "y1": 20, "y2": 340}
        ]}, 1300)
        self.assertAlmostEqual(person["bearing_rad"], 0.0, places=2)

    def test_associate_radar(self):
        targets = parse_radar_targets("T1:x=100mm,y=1500mm,spd=25cm/s | T2:x=1500mm,y=500mm,spd=0cm/s")
        match = associate_radar(0.0, targets, lidar_distance=1.5)
        self.assertEqual(match["id"], "T1")

    def test_reject_distance_mismatch(self):
        targets = parse_radar_targets("T1:x=0mm,y=3500mm,spd=10cm/s")
        self.assertIsNone(associate_radar(0.0, targets, lidar_distance=1.0))


if __name__ == "__main__":
    unittest.main()
