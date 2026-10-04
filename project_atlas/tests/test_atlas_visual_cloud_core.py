#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).parents[1] / "scripts" / "atlas_visual_cloud_core.py"
CONFIG = Path(__file__).parents[1] / "config" / "atlas_visual_cloud.json"
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

    def test_retained_map_not_false_stopped_or_live(self):
        value = MODULE.topic_stat([10.0], now=4000., expected_hz=.05, retained=True)
        self.assertEqual(value['health'], 'CACHED')
        self.assertEqual(value['age_s'], 3990.)
        self.assertEqual(value['hz'], 0.)
        self.assertEqual(MODULE.topic_stat([], retained=True)['health'], 'STOPPED')
        self.assertEqual(MODULE.topic_stat([10.], now=4000., expected_hz=10)['health'], 'STOPPED')

    def test_activity_detects_motion_and_active_missions(self):
        self.assertTrue(MODULE.is_robot_activity(
            "/cmd_vel", {"linear_x": 0.02, "angular_z": 0.0}))
        self.assertTrue(MODULE.is_robot_activity(
            "/cmd_vel_nav", {"linear_x": 0.0, "angular_z": -0.1}))
        self.assertTrue(MODULE.is_robot_activity(
            "/atlas/mission_status", "NAVIGATING to Hall"))
        self.assertTrue(MODULE.is_robot_activity(
            "/atlas/mission_status", "EXPLORATION ACTIVE session=1234"))
        self.assertTrue(MODULE.is_robot_activity(
            "/atlas/mission_status", "RETURN HOME GOAL DISPATCHED attempt=1"))
        self.assertTrue(MODULE.is_robot_activity(
            "/atlas/recovery_status", "RECOVERING: bounded backup"))

    def test_idle_or_zero_signals_do_not_trigger_activity(self):
        self.assertFalse(MODULE.is_robot_activity(
            "/cmd_vel", {"linear_x": 0.0, "angular_z": 0.0}))
        self.assertFalse(MODULE.is_robot_activity(
            "/atlas/mission_status", "IDLE"))
        self.assertFalse(MODULE.is_robot_activity(
            "/atlas/recovery_status", "RECOVERY STOPPED"))
        self.assertFalse(MODULE.is_robot_activity(
            "/atlas/mission_status", "RETURN HOME VERIFIED error=0.02m"))
        self.assertFalse(MODULE.is_robot_activity(
            "/atlas/mission_status", "MAPPING NOT ACTIVE; ACCEPTED MAP PRESERVED"))
        self.assertFalse(MODULE.is_robot_activity("/scan", {"ranges": [1.0]}))

    def test_adaptive_interval_preserves_active_cadence(self):
        self.assertTrue(MODULE.interval_due(10.0, 11.0, True, 1.0, 5.0))
        self.assertFalse(MODULE.interval_due(10.0, 11.0, False, 1.0, 5.0))
        self.assertTrue(MODULE.interval_due(10.0, 15.0, False, 1.0, 5.0))
        self.assertTrue(MODULE.interval_due(0.0, 0.1, False, 1.0, 5.0))

    def test_idle_config_is_bounded_and_status_lease_covers_slow_heartbeat(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertGreaterEqual(
            config["idle_publish_interval_s"], config["publish_interval_s"])
        self.assertGreaterEqual(
            config["idle_graph_interval_s"], config["graph_interval_s"])
        mission_period = 1.0 / config["topics"]["/atlas/mission_status"]
        self.assertGreaterEqual(config["active_hold_s"], 2.0 * mission_period)


if __name__ == "__main__": unittest.main()
