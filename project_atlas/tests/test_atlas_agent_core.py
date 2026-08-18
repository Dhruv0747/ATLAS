#!/usr/bin/env python3
"""Unit tests for the safety-critical, ROS-independent agent planner rules."""

import importlib.util
from pathlib import Path
import sys
import unittest


CORE = Path(__file__).parents[1] / "scripts" / "atlas_agent_core.py"
SPEC = importlib.util.spec_from_file_location("atlas_agent_core", CORE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AtlasAgentCoreTests(unittest.TestCase):
    def test_named_place_offline_plans_preserve_target(self):
        save = MODULE.fallback_plan("Save this as kitchen")
        self.assertEqual(save["steps"][0]["action"], "save_named_place")
        self.assertEqual(save["steps"][0]["target"], "kitchen")
        go = MODULE.fallback_plan("Go to kitchen")
        self.assertEqual(go["steps"][0]["action"], "navigate_named_place")
        self.assertEqual(go["steps"][0]["target"], "kitchen")
        back = MODULE.fallback_plan("Come back to my room")
        self.assertEqual(back["steps"][0]["action"], "navigate_named_place")
        self.assertEqual(back["steps"][0]["target"], "my room")

    def test_named_place_requires_valid_target(self):
        with self.assertRaises(ValueError):
            MODULE.validate_plan({"steps": [{"action": "navigate_named_place"}]})

    def test_named_place_waits_for_terminal_nav2_result(self):
        self.assertIsNone(
            MODULE.evaluate_action_status(
                "navigate_named_place", "NAMED GOAL ACCEPTED name=kitchen"
            )
        )
        self.assertTrue(
            MODULE.evaluate_action_status(
                "navigate_named_place", "NAMED GOAL FINISHED name=kitchen status=4"
            )
        )
        self.assertFalse(
            MODULE.evaluate_action_status(
                "navigate_named_place", "NAMED GOAL FINISHED name=kitchen status=6"
            )
        )

    def test_mapping_stores_home_before_starting(self):
        plan = MODULE.fallback_plan("Map this room")
        self.assertEqual(
            [step["action"] for step in plan["steps"]],
            ["set_home", "start_mapping"],
        )
        self.assertTrue(MODULE.plan_requires_motion(plan))

    def test_stop_has_priority(self):
        plan = MODULE.fallback_plan("Emergency stop moving")
        self.assertEqual(plan["steps"][0]["action"], "cancel_navigation")
        self.assertTrue(MODULE.plan_is_stop_only(plan))

    def test_unknown_request_observes_only(self):
        plan = MODULE.fallback_plan("Please consider the situation")
        self.assertEqual(plan["steps"][0]["action"], "inspect_status")
        self.assertFalse(MODULE.plan_requires_motion(plan))

    def test_untrusted_tool_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            MODULE.validate_plan(
                {"steps": [{"action": "raw_motor_pwm", "reason": "unsafe"}]}
            )

    def test_plan_length_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            MODULE.validate_plan(
                {
                    "steps": [
                        {"action": "inspect_status", "reason": "observe"}
                        for _ in range(MODULE.MAX_PLAN_STEPS + 1)
                    ]
                }
            )

    def test_mapping_injects_home_and_removes_unsolicited_recovery(self):
        cloud_plan = {
            "steps": [
                {"action": "start_mapping", "reason": "map"},
                {"action": "request_tight_recovery", "reason": "maybe tight"},
            ]
        }
        plan = MODULE.enforce_request_policy(
            cloud_plan, "map this room", "TIGHT_CLEARANCE"
        )
        self.assertEqual(
            [step["action"] for step in plan["steps"]],
            ["set_home", "start_mapping"],
        )

    def test_recovery_requires_request_or_real_blocked_phase(self):
        cloud_plan = {
            "steps": [{"action": "request_tight_recovery", "reason": "escape"}]
        }
        rejected = MODULE.enforce_request_policy(
            cloud_plan, "inspect the rover", "TIGHT_CLEARANCE"
        )
        self.assertEqual(rejected["steps"][0]["action"], "inspect_status")
        allowed = MODULE.enforce_request_policy(
            cloud_plan, "recover because you are stuck", "BLOCKED"
        )
        self.assertEqual(allowed["steps"][0]["action"], "request_tight_recovery")

    def test_return_home_requires_successful_final_action_status(self):
        self.assertIsNone(
            MODULE.evaluate_action_status("return_home", "RETURN HOME ACCEPTED")
        )
        self.assertTrue(
            MODULE.evaluate_action_status(
                "return_home", "RETURN HOME FINISHED status=4"
            )
        )
        self.assertFalse(
            MODULE.evaluate_action_status(
                "return_home", "RETURN HOME FINISHED status=6"
            )
        )

    def test_blocked_recovery_is_failure(self):
        self.assertFalse(
            MODULE.evaluate_action_status(
                "request_tight_recovery", "BLOCKED: no safe corridor"
            )
        )


if __name__ == "__main__":
    unittest.main()
