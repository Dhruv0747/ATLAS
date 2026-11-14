#!/usr/bin/env python3
"""2026-11-14 PROPOSAL: final-map consistency evidence and its (off-by-default) use in map acceptance."""
import copy
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import atlas_final_map_consistency as F  # noqa: E402
import atlas_map_acceptance_core as A  # noqa: E402
from test_atlas_map_acceptance_core import passing_evidence  # noqa: E402

LASER = (-0.05, 0.0, math.pi)


def room_points(w=4.0, h=3.0, step=0.05):
    """Walls of a w x h room plus an L-shaped partition (breaks symmetry)."""
    xs, ys = np.arange(0, w + 1e-9, step), np.arange(0, h + 1e-9, step)
    walls = [np.c_[xs, np.zeros_like(xs)], np.c_[xs, np.full_like(xs, h)],
             np.c_[np.zeros_like(ys), ys], np.c_[np.full_like(ys, w), ys]]
    px = np.arange(1.0, 2.0, step)
    walls.append(np.c_[px, np.full_like(px, 1.0)])
    py = np.arange(1.0, 1.8, step)
    walls.append(np.c_[np.full_like(py, 2.0), py])
    return np.vstack(walls)


def raycast(occ, pose, n=360):
    """Ideal LiDAR in the laser frame (mount LASER) at robot pose; returns ranges."""
    x, y, th = pose
    lx = x + math.cos(th) * LASER[0] - math.sin(th) * LASER[1]
    ly = y + math.sin(th) * LASER[0] + math.cos(th) * LASER[1]
    lth = th + LASER[2]
    rel = occ - [lx, ly]
    dist = np.hypot(rel[:, 0], rel[:, 1])
    bearing = np.arctan2(rel[:, 1], rel[:, 0]) - lth
    inc = 2 * math.pi / n
    idx = np.round(((bearing + math.pi) % (2 * math.pi)) / inc).astype(int) % n
    ranges = np.full(n, np.inf)
    np.minimum.at(ranges, idx, dist)
    return ranges, -math.pi, inc


def samples(occ, poses, live_offset=(0.0, 0.0, 0.0)):
    out = []
    for k, p in enumerate(poses):
        r, a0, inc = raycast(occ, p)
        live = (p[0] + live_offset[0], p[1] + live_offset[1], p[2] + live_offset[2])
        out.append(F.ScanSample(float(k), live, r, a0, inc))
    return out


POSES = [(0.6 + 2.8 * (k % 20) / 20, 0.5 + 2.0 * (k // 20) / 6, 0.3 * k) for k in range(120)]


class CoreTests(unittest.TestCase):
    def test_consistent_map_passes(self):
        occ = room_points()
        ev = F.evaluate(samples(occ, POSES, (0.05, -0.04, math.radians(2))), occ, LASER, session_id="s")
        self.assertTrue(ev["passed"], ev["failures"])
        self.assertEqual(ev["matched"], 120)
        self.assertGreaterEqual(ev["fraction_good"], 0.95)
        self.assertLess(ev["pose_offset_max_m"], 0.15)

    def test_map_that_does_not_explain_scans_fails(self):
        occ = room_points()
        scans = samples(occ, POSES)
        bad_map = room_points(w=4.6)          # a wall in the "final map" moved 0.6 m: scans no longer fit
        ev = F.evaluate(scans, bad_map, LASER)
        self.assertFalse(ev["passed"])

    def test_live_pose_far_from_best_fit_fails(self):
        occ = room_points()
        ev = F.evaluate(samples(occ, POSES, (0.0, 0.0, math.radians(14))), occ, LASER)
        self.assertFalse(ev["passed"])

    def test_too_few_scans_fails(self):
        occ = room_points()
        ev = F.evaluate(samples(occ, POSES[:20]), occ, LASER)
        self.assertFalse(ev["passed"])
        self.assertIn("too few scan samples", ev["failures"][0])

    def test_buffer_rate_limit_and_cap(self):
        buf = F.ScanSampleBuffer(F.FinalMapConsistencyPolicy(sample_period_s=0.5, max_samples=10))
        self.assertFalse(buf.add(0.0, (0, 0, 0), [1.0], 0.0, 0.1))      # no session yet
        buf.begin("s")
        added = sum(buf.add(t * 0.1, (0, 0, 0), [1.0], 0.0, 0.1) for t in range(200))
        self.assertEqual(added, 40)                                     # one per 0.5 s
        self.assertLessEqual(len(buf.samples), 10)
        self.assertLess(buf.samples[0].stamp, 2.0)                      # still covers the start of the drive


def good_consistency():
    return {"schema": 1, "session_id": "session-1", "scans": 3603, "matched": 3603, "passed": True,
            "failures": [], "policy": {"min_scan_fit": 0.85, "tolerance_m": 0.15},
            "fraction_good": 1.0, "pose_offset_max_m": 0.24, "pose_offset_max_deg": 3.0}


def run(evidence, enabled):
    return A.evaluate_acceptance_evidence(
        evidence, expected_session_id="session-1", expected_candidate_map_id="map-1",
        session_started_unix=100.0, evaluated_unix=200.0,
        policy=A.MapAcceptancePolicy(final_map_replaces_tf_jump=enabled))


def jumpy():
    ev = passing_evidence()
    ev["tf_jump"]["max_translation_m"] = 1.5
    ev["tf_jump"]["max_yaw_deg"] = 12.0
    ev["final_map_consistency"] = good_consistency()
    return ev


class AcceptanceTests(unittest.TestCase):
    def test_default_is_off_and_jump_still_rejects(self):
        self.assertFalse(A.MapAcceptancePolicy().final_map_replaces_tf_jump)
        self.assertTrue(any("translation jump" in f for f in A.evaluate_acceptance_evidence(
            jumpy(), expected_session_id="session-1", expected_candidate_map_id="map-1",
            session_started_unix=100.0, evaluated_unix=200.0)))

    def test_enabled_with_passing_consistency_accepts(self):
        self.assertEqual(run(jumpy(), True), [])

    def test_enabled_never_relaxes_closure_or_plans(self):
        for section, field, value in (("round_trip_closure", "translation_error_m", 0.23),
                                      ("bidirectional_plans", "reverse", {"passed": False, "poses": 0}),
                                      ("exact_candidate_connectivity", "connected", False)):
            ev = jumpy()
            ev[section][field] = value
            with self.subTest(section=section):
                self.assertTrue(run(ev, True))

    def test_enabled_but_consistency_bad_or_missing_rejects(self):
        mutations = [("passed", False), ("session_id", "other"), ("scans", 50), ("matched", 3000),
                     ("fraction_good", 0.90), ("pose_offset_max_m", 0.31), ("pose_offset_max_deg", 11.0),
                     ("policy", {"min_scan_fit": 0.5, "tolerance_m": 0.15}),
                     ("policy", {"min_scan_fit": 0.85, "tolerance_m": 0.30})]
        for field, value in mutations:
            ev = jumpy()
            ev["final_map_consistency"][field] = value
            with self.subTest(field=field):
                out = run(ev, True)
                self.assertTrue(any("translation jump" in f for f in out), out)
        ev = jumpy()
        del ev["final_map_consistency"]
        self.assertIn("final-map consistency evidence is missing", run(ev, True))

    def test_tf_integrity_checks_still_apply_when_enabled(self):
        ev = jumpy()
        ev["tf_jump"]["time_order_valid"] = False
        self.assertTrue(run(ev, True))


if __name__ == "__main__":
    unittest.main()
