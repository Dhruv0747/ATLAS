#!/usr/bin/env python3
"""Offline tests for fail-closed ATLAS mapping-session readiness."""

import importlib.util
from pathlib import Path
import sys
import unittest


CORE = Path(__file__).parents[1] / "scripts" / "atlas_mapping_session_core.py"
SPEC = importlib.util.spec_from_file_location("atlas_mapping_session_core", CORE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MappingSessionReadinessTests(unittest.TestCase):
    def test_manual_starting_is_not_active(self):
        self.assertFalse(MODULE.mapping_session_is_active({
            "state": "starting",
            "mode": "manual_teaching",
            "drive_ready": False,
        }))

    def test_manual_active_requires_explicit_true(self):
        self.assertFalse(MODULE.mapping_session_is_active({
            "state": "active",
            "mode": "manual_teaching",
        }))
        self.assertFalse(MODULE.mapping_session_is_active({
            "state": "active",
            "mode": "manual_teaching",
            "drive_ready": False,
        }))
        self.assertFalse(MODULE.mapping_session_is_active({
            "state": "active",
            "mode": "manual_teaching",
            "drive_ready": "true",
        }))
        self.assertTrue(MODULE.mapping_session_is_active({
            "state": "active",
            "mode": "manual_teaching",
            "drive_ready": True,
        }))

    def test_existing_exploration_active_format_remains_compatible(self):
        self.assertTrue(MODULE.mapping_session_is_active({
            "state": "active",
        }))

    def test_invalid_values_fail_closed(self):
        for value in (None, [], "active", 1, {"state": "starting"}, {}):
            with self.subTest(value=value):
                self.assertFalse(MODULE.mapping_session_is_active(value))


if __name__ == "__main__":
    unittest.main()
