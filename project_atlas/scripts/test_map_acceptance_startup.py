#!/usr/bin/env python3
"""Tests for the 2026-11-12 manual-teaching start reference + startup stillness gate.

Optional: ATLAS_ATTEMPT1_EVIDENCE=<acceptance.json> ATLAS_ATTEMPT1_SESSION=<mapping_session.json> replays the
rejected remap attempt 1 (dae618d3) evidence through the new reference.
"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_map_acceptance_core import (  # noqa: E402
    MapAcceptancePolicy, evaluate_acceptance_evidence, startup_stillness_failures)

P = MapAcceptancePolicy()
STILL = {"start_odom_age_s": 0.05, "ready_odom_age_s": 0.08, "wheel_displacement_m": 0.0,
         "wheel_yaw_change_deg": 0.0}


class StartupStillness(unittest.TestCase):
    def test_still_passes(self):
        self.assertEqual(startup_stillness_failures(STILL, P), [])

    def test_missing_fails_closed(self):
        self.assertTrue(startup_stillness_failures(None, P))
        for k in STILL:
            s = dict(STILL); s[k] = None
            self.assertTrue(startup_stillness_failures(s, P), k)

    def test_moved_fails(self):
        s = dict(STILL, wheel_displacement_m=0.05)
        self.assertTrue(any("moved" in f for f in startup_stillness_failures(s, P)))

    def test_turned_fails(self):
        s = dict(STILL, wheel_yaw_change_deg=-3.0)
        self.assertTrue(any("turned" in f for f in startup_stillness_failures(s, P)))

    def test_stale_odom_fails(self):
        s = dict(STILL, ready_odom_age_s=5.0)
        self.assertTrue(any("stale" in f for f in startup_stillness_failures(s, P)))


@unittest.skipUnless(os.environ.get("ATLAS_ATTEMPT1_EVIDENCE"), "attempt-1 evidence not provided")
class Attempt1Replay(unittest.TestCase):
    def setUp(self):
        self.ev = json.load(open(os.environ["ATLAS_ATTEMPT1_EVIDENCE"]))
        self.ses = json.load(open(os.environ["ATLAS_ATTEMPT1_SESSION"]))

    def run_eval(self, ev, ref):
        return evaluate_acceptance_evidence(
            ev, expected_session_id=ev["session_id"], expected_candidate_map_id=ev["candidate_map_id"],
            session_started_unix=ref, evaluated_unix=ev["evaluated_unix"], policy=P)

    def test_old_reference_reproduces_coverage_failure(self):
        f = self.run_eval(copy.deepcopy(self.ev), self.ses["started_unix"])
        self.assertTrue(any("did not cover mapping-session start" in x for x in f), f)

    def test_ready_reference_keeps_only_real_failures(self):
        ev = copy.deepcopy(self.ev); ev["session_mode"] = "manual_teaching"; ev["startup_stillness"] = STILL
        f = self.run_eval(ev, self.ses["ready_unix"])
        print("\nattempt 1 under new reference:", f)
        self.assertFalse(any("did not cover" in x for x in f), f)
        self.assertTrue(any("jump" in x or "exceeds" in x for x in f), f)   # the real 0.92 m jump still rejects

    def test_ready_reference_without_stillness_fails_closed(self):
        ev = copy.deepcopy(self.ev); ev["session_mode"] = "manual_teaching"
        f = self.run_eval(ev, self.ses["ready_unix"])
        self.assertIn("startup stillness evidence is missing", f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
