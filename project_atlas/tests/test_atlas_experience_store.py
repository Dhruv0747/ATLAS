#!/usr/bin/env python3
"""ROS-independent tests for stable experience failure classification."""

import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).parents[1] / "scripts" / "atlas_experience_store.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NODES = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"classify_failure", "recovery_strategy", "mission_outcome"}
]
SCOPE = {}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), "exec"), SCOPE)


class ExperienceReasonerTests(unittest.TestCase):
    def test_failure_classes_are_stable(self):
        classify = SCOPE["classify_failure"]
        self.assertEqual(classify("AMCL pose jump"), "localization")
        self.assertEqual(classify("TF extrapolation into the past"), "tf_timing")
        self.assertEqual(classify("BLOCKED: dead end"), "blocked")
        self.assertEqual(classify("unexplained abort"), "unknown")

    def test_strategy_is_bounded(self):
        strategy = SCOPE["recovery_strategy"]
        self.assertEqual(strategy("tight_recovery"), "sensor_guarded_bounded_recovery")
        self.assertEqual(strategy("recovery"), "bounded_peripheral_recovery")

    def test_terminal_mission_outcomes(self):
        outcome = SCOPE["mission_outcome"]
        self.assertEqual(outcome("NAMED GOAL FINISHED name=hall status=4"), "success")
        self.assertEqual(outcome("RETURN HOME VERIFIED error=0.08m"), "success")
        self.assertEqual(outcome("RETURN HOME FINISHED status=6"), "failure")
        self.assertEqual(outcome("NAMED GOAL REJECTED name=hall"), "failure")
        self.assertIsNone(outcome("RETURN HOME ACCEPTED"))


if __name__ == "__main__":
    unittest.main()
