#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).parents[1] / "scripts" / "atlas_visual_cloud_core.py"
SPEC = importlib.util.spec_from_file_location("atlas_visual_cloud_core", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class VisualCloudCoreTests(unittest.TestCase):
    def test_health_transitions(self):
        self.assertEqual(MODULE.link_health(None, 10, 0), "STOPPED")
        self.assertEqual(MODULE.link_health(0.02, 10, 9.5), "HEALTHY")
        self.assertEqual(MODULE.link_health(1.2, 10, 9.5), "DELAYED")
        self.assertEqual(MODULE.link_health(6.0, 10, 0), "STOPPED")

    def test_requested_failure_taxonomy(self):
        self.assertEqual(MODULE.classify_failure("Starting point in lethal space"), "COSTMAP")
        self.assertEqual(MODULE.classify_failure("AMCL pose jump"), "LOCALIZATION")
        self.assertEqual(MODULE.classify_failure("controller progress checker failed"), "CONTROLLER")
        self.assertEqual(MODULE.classify_failure("unexplained"), "UNKNOWN")

    def test_topic_statistics(self):
        value = MODULE.topic_stat([9.0, 9.5, 10.0], now=10.1, expected_hz=2.0)
        self.assertEqual(value["hz"], 2.0)
        self.assertEqual(value["health"], "HEALTHY")


if __name__ == "__main__": unittest.main()
