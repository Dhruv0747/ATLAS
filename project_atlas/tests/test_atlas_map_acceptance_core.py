#!/usr/bin/env python3
"""Offline tests for fail-closed candidate-map promotion evidence."""

import ast
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


CORE = Path(__file__).parents[1] / "scripts" / "atlas_map_acceptance_core.py"
SPEC = importlib.util.spec_from_file_location("atlas_map_acceptance_core", CORE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def passing_evidence():
    return {
        "schema_version": MODULE.EVIDENCE_SCHEMA_VERSION,
        "session_id": "session-1",
        "candidate_map_id": "map-1",
        "motion_dispatched": False,
        "tf_jump": {
            "session_id": "session-1",
            "sample_count": 100,
            "observation_started_unix": 100.5,
            "observation_ended_unix": 199.0,
            "max_translation_m": 0.149,
            "max_yaw_deg": 4.99,
            "max_sample_gap_s": 0.1,
            "time_order_valid": True,
            "source_stamp_started_unix": 100.5,
            "source_stamp_ended_unix": 199.0,
            "max_source_age_s": 0.1,
            "source_time_order_valid": True,
        },
        "round_trip_closure": {
            "session_id": "session-1",
            "translation_error_m": 0.149,
            "yaw_error_deg": 9.99,
        },
        "exact_candidate_connectivity": {
            "session_id": "session-1",
            "candidate_map_id": "map-1",
            "connected": True,
            "unknown_is_blocked": True,
            "inflation_radius_m": 0.18,
        },
        "full_footprint_connectivity": {
            "connected": True,
            "observed_unix": 199.0,
            "length_m": 0.50,
            "width_m": 0.36,
        },
        "bidirectional_plans": {
            "forward": {"passed": True, "poses": 12},
            "reverse": {"passed": True, "poses": 11},
        },
    }


def evaluate(evidence):
    return MODULE.evaluate_acceptance_evidence(
        evidence,
        expected_session_id="session-1",
        expected_candidate_map_id="map-1",
        session_started_unix=100.0,
        evaluated_unix=200.0,
    )


class MapAcceptanceCoreTests(unittest.TestCase):
    def test_complete_evidence_passes(self):
        self.assertEqual(evaluate(passing_evidence()), [])

    def test_every_required_section_is_fail_closed(self):
        for section in (
            "tf_jump",
            "round_trip_closure",
            "exact_candidate_connectivity",
            "full_footprint_connectivity",
            "bidirectional_plans",
        ):
            evidence = passing_evidence()
            del evidence[section]
            with self.subTest(section=section):
                self.assertTrue(evaluate(evidence))

    def test_jump_closure_footprint_and_each_direction_are_enforced(self):
        mutations = (
            ("tf_jump", "max_translation_m", 0.151),
            ("tf_jump", "max_yaw_deg", 5.01),
            ("round_trip_closure", "translation_error_m", 0.151),
            ("round_trip_closure", "yaw_error_deg", 10.01),
            ("exact_candidate_connectivity", "connected", False),
            ("exact_candidate_connectivity", "inflation_radius_m", 0.17),
            ("full_footprint_connectivity", "connected", False),
            ("full_footprint_connectivity", "width_m", 0.34),
            ("bidirectional_plans", "forward", {"passed": False, "poses": 0}),
            ("bidirectional_plans", "reverse", {"passed": False, "poses": 0}),
        )
        for section, field, value in mutations:
            evidence = passing_evidence()
            evidence[section][field] = value
            with self.subTest(section=section, field=field):
                self.assertTrue(evaluate(evidence))

    def test_stale_wrong_session_and_wrong_candidate_are_rejected(self):
        evidence = passing_evidence()
        evidence["session_id"] = "old-session"
        evidence["candidate_map_id"] = "old-map"
        evidence["tf_jump"]["observation_ended_unix"] = 190.0
        evidence["full_footprint_connectivity"]["observed_unix"] = 190.0
        failures = evaluate(evidence)
        self.assertGreaterEqual(len(failures), 4)

    def test_tracker_detects_wrapped_yaw_and_translation_jump(self):
        tracker = MODULE.TransformJumpTracker()
        tracker.begin("session-1", 100.0, 100.1)
        tracker.observe(0.0, 0.0, math.radians(179.0), 101.0, 100.9)
        tracker.observe(0.10, 0.0, math.radians(-179.0), 102.0, 101.9)
        result = tracker.snapshot()
        self.assertEqual(result["sample_count"], 2)
        self.assertAlmostEqual(result["max_translation_m"], 0.10)
        self.assertAlmostEqual(result["max_yaw_deg"], 2.0)
        self.assertEqual(result["observation_started_unix"], 101.0)
        self.assertAlmostEqual(result["max_sample_gap_s"], 1.0)

    def test_sparse_or_non_monotonic_tf_evidence_is_rejected(self):
        evidence = passing_evidence()
        evidence["tf_jump"]["max_sample_gap_s"] = 5.01
        self.assertTrue(any("uncovered gap" in item for item in evaluate(evidence)))

        evidence = passing_evidence()
        evidence["tf_jump"]["time_order_valid"] = False
        self.assertTrue(any("not monotonic" in item for item in evaluate(evidence)))

        evidence = passing_evidence()
        evidence["tf_jump"]["observation_started_unix"] = 198.0
        self.assertTrue(any("did not cover" in item for item in evaluate(evidence)))

        evidence = passing_evidence()
        evidence["tf_jump"]["source_stamp_ended_unix"] = 190.0
        self.assertTrue(any("source timestamp is stale" in item for item in evaluate(evidence)))

        evidence = passing_evidence()
        evidence["tf_jump"]["source_time_order_valid"] = False
        self.assertTrue(any("source timestamps are invalid" in item
                            for item in evaluate(evidence)))

    def test_no_motion_attestation_is_required(self):
        evidence = passing_evidence()
        del evidence["motion_dispatched"]
        self.assertTrue(any("no-motion" in item for item in evaluate(evidence)))

    def test_pair_promotion_restores_both_old_members_on_second_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_yaml = root / "candidate.yaml"
            candidate_image = root / "candidate.pgm"
            accepted_yaml = root / "accepted.yaml"
            accepted_image = root / "accepted.pgm"
            candidate_yaml.write_bytes(b"image: accepted.pgm\nresolution: 0.05\n")
            candidate_image.write_bytes(b"P5\n1 1\n255\n\xfe")
            accepted_yaml.write_bytes(b"image: accepted.pgm\nresolution: 0.1\n")
            accepted_image.write_bytes(b"P5\n1 1\n255\n\x00")
            old_yaml = accepted_yaml.read_bytes()
            old_image = accepted_image.read_bytes()
            expected_id = MODULE.map_pair_id(candidate_yaml, candidate_image)
            real_replace = MODULE.os.replace
            calls = 0

            def fail_second_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated YAML commit failure")
                return real_replace(source, destination)

            with mock.patch.object(MODULE.os, "replace", side_effect=fail_second_replace):
                with self.assertRaisesRegex(RuntimeError, "previous accepted map restored"):
                    MODULE.transactionally_promote_map_pair(
                        candidate_yaml=candidate_yaml,
                        candidate_image=candidate_image,
                        accepted_yaml=accepted_yaml,
                        accepted_image=accepted_image,
                        backup_dir=root / "backups",
                        expected_map_id=expected_id,
                        backup_tag="test",
                    )
            self.assertEqual(accepted_yaml.read_bytes(), old_yaml)
            self.assertEqual(accepted_image.read_bytes(), old_image)

    def test_bundle_promotion_restores_map_and_metadata_if_yaml_commit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_yaml = root / "candidate.yaml"
            candidate_image = root / "candidate.pgm"
            accepted_yaml = root / "accepted.yaml"
            accepted_image = root / "accepted.pgm"
            home = root / "home.json"
            candidate_yaml.write_bytes(b"image: accepted.pgm\nresolution: 0.05\n")
            candidate_image.write_bytes(b"P5\n1 1\n255\n\xfe")
            accepted_yaml.write_bytes(b"image: accepted.pgm\nresolution: 0.1\n")
            accepted_image.write_bytes(b"P5\n1 1\n255\n\x00")
            home.write_bytes(b'{"map_id":"old"}')
            old_values = {
                accepted_yaml: accepted_yaml.read_bytes(),
                accepted_image: accepted_image.read_bytes(),
                home: home.read_bytes(),
            }
            expected_id = MODULE.map_pair_id(candidate_yaml, candidate_image)
            real_replace = MODULE.os.replace
            calls = 0

            def fail_yaml_commit(source, destination):
                nonlocal calls
                calls += 1
                # metadata, image, then the authoritative YAML
                if calls == 3:
                    raise OSError("simulated authoritative YAML failure")
                return real_replace(source, destination)

            with mock.patch.object(MODULE.os, "replace", side_effect=fail_yaml_commit):
                with self.assertRaisesRegex(RuntimeError, "previous accepted map restored"):
                    MODULE.transactionally_promote_map_pair(
                        candidate_yaml=candidate_yaml,
                        candidate_image=candidate_image,
                        accepted_yaml=accepted_yaml,
                        accepted_image=accepted_image,
                        backup_dir=root / "backups",
                        expected_map_id=expected_id,
                        backup_tag="bundle-test",
                        metadata_updates={home: b'{"map_id":"new"}'},
                    )
            for path, expected in old_values.items():
                self.assertEqual(path.read_bytes(), expected)

    def test_pair_promotion_commits_the_exact_validated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_yaml = root / "candidate.yaml"
            candidate_image = root / "candidate.pgm"
            accepted_yaml = root / "accepted.yaml"
            accepted_image = root / "accepted.pgm"
            candidate_yaml.write_bytes(b"image: accepted.pgm\nresolution: 0.05\n")
            candidate_image.write_bytes(b"P5\n1 1\n255\n\xfe")
            expected_id = MODULE.map_pair_id(candidate_yaml, candidate_image)
            promoted_id = MODULE.transactionally_promote_map_pair(
                candidate_yaml=candidate_yaml,
                candidate_image=candidate_image,
                accepted_yaml=accepted_yaml,
                accepted_image=accepted_image,
                backup_dir=root / "backups",
                expected_map_id=expected_id,
                backup_tag="test",
            )
            self.assertEqual(promoted_id, expected_id)
            self.assertEqual(MODULE.map_pair_id(accepted_yaml, accepted_image), expected_id)

    def test_metadata_preparation_binds_current_and_legacy_poses_safely(self):
        home, seed, places = MODULE.prepare_map_bound_metadata_values(
            home={"mapping_session_id": "session-1", "x": 1.0},
            seed={"mapping_session_id": "session-1", "x": 1.1},
            places={
                "dhruv room": {"mapping_session_id": "session-1", "x": 1.0},
                "legacy": {"x": 9.0},
                "already versioned": {"map_id": "other-map", "x": 5.0},
                "map_id": "old-map",
            },
            session_id="session-1",
            new_map_id="new-map",
            old_map_id="old-map",
        )
        self.assertEqual(home["map_id"], "new-map")
        self.assertEqual(seed["map_id"], "new-map")
        self.assertNotIn("mapping_session_id", home)
        self.assertEqual(places["dhruv room"]["map_id"], "new-map")
        self.assertEqual(places["legacy"]["map_id"], "old-map")
        self.assertEqual(places["already versioned"]["map_id"], "other-map")
        self.assertEqual(places["map_id"], "old-map")

    def test_first_map_marks_unversioned_legacy_pose_as_unusable(self):
        _home, _seed, places = MODULE.prepare_map_bound_metadata_values(
            home={"mapping_session_id": "session-1", "x": 1.0},
            seed={"mapping_session_id": "session-1", "x": 1.1},
            places={"legacy": {"x": 9.0}},
            session_id="session-1",
            new_map_id="new-map",
            old_map_id=None,
        )
        self.assertEqual(
            places["legacy"]["map_id"], MODULE.UNBOUND_LEGACY_MAP_ID
        )

    def test_exact_candidate_connectivity_uses_saved_bytes_and_blocks_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yaml_path = root / "candidate.yaml"
            image_path = root / "candidate.pgm"
            yaml_path.write_text(
                "image: candidate.pgm\n"
                "mode: trinary\n"
                "resolution: 0.2\n"
                "origin: [0.0, 0.0, 0.0]\n"
                "negate: 0\n"
                "occupied_thresh: 0.65\n"
                "free_thresh: 0.25\n",
                encoding="utf-8",
            )
            width, height = 9, 7
            pixels = bytearray([254] * (width * height))
            image_path.write_bytes(
                f"P5\n{width} {height}\n255\n".encode("ascii") + pixels
            )
            start = {"x": 0.5, "y": 0.7}
            goal = {"x": 1.3, "y": 0.7}
            result = MODULE.exact_candidate_connectivity(
                yaml_path, image_path, start, goal, inflation_radius_m=0.18
            )
            self.assertTrue(result["connected"])
            self.assertTrue(result["unknown_is_blocked"])

            for row in range(height):
                pixels[row * width + 4] = 205
            image_path.write_bytes(
                f"P5\n{width} {height}\n255\n".encode("ascii") + pixels
            )
            result = MODULE.exact_candidate_connectivity(
                yaml_path, image_path, start, goal, inflation_radius_m=0.18
            )
            self.assertFalse(result["connected"])

    def test_closure_and_rotated_footprint_geometry(self):
        start = {
            "frame_id": "map", "x": 0.0, "y": 0.0,
            "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0,
        }
        end = dict(start, x=0.1, qz=math.sin(math.radians(5.0)),
                   qw=math.cos(math.radians(5.0)))
        closure = MODULE.closure_evidence(start, end)
        self.assertAlmostEqual(closure["translation_error_m"], 0.1)
        self.assertAlmostEqual(closure["yaw_error_deg"], 10.0)
        dimensions = MODULE.polygon_dimensions(
            [(0.25, 0.18), (0.25, -0.18), (-0.25, -0.18), (-0.25, 0.18)]
        )
        self.assertEqual(dimensions["length_m"], 0.5)
        self.assertEqual(dimensions["width_m"], 0.36)

    def test_gate_precedes_first_accepted_map_replace(self):
        source = Path(__file__).parents[1] / "scripts" / "atlas_mission_control.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "AtlasMissionControl")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "accept_saved_map")
        gate = next(node.lineno for node in ast.walk(method)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "validate_candidate_map")
        promotions = [node.lineno for node in ast.walk(method)
                      if isinstance(node, ast.Call)
                      and ((isinstance(node.func, ast.Name)
                            and node.func.id == "transactionally_promote_map_pair")
                           or (isinstance(node.func, ast.Attribute)
                               and node.func.attr == "transactionally_promote_map_pair"))]
        self.assertEqual(len(promotions), 1)
        self.assertLess(gate, promotions[0])

    def test_plan_evidence_uses_only_compute_path_action(self):
        source = Path(__file__).parents[1] / "scripts" / "atlas_mission_control.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "AtlasMissionControl")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "plan_only_evidence")
        send_calls = [node for node in ast.walk(method)
                      if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "send_goal_async"]
        self.assertEqual(len(send_calls), 1)
        owner = send_calls[0].func.value
        self.assertIsInstance(owner, ast.Attribute)
        self.assertEqual(owner.attr, "path_planner")
        forbidden = {"nav", "nav_through", "zero_pub"}
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr in forbidden
                             for node in ast.walk(method)))


if __name__ == "__main__":
    unittest.main()
