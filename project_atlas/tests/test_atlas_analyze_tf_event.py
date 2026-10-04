import math
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from atlas_analyze_tf_event import (  # noqa: E402
    HeaderAudit,
    PoseSample,
    PoseSpool,
    ScanPairer,
    compose_map_base_event,
    compose_se2,
    ordered_pose_summary,
    pose_step,
)


class TransformMathTests(unittest.TestCase):
    def test_compose_se2_rotates_child_translation(self):
        x_m, y_m, yaw = compose_se2(1.0, 2.0, math.pi / 2, 2.0, 0.0, math.pi / 2)
        self.assertAlmostEqual(x_m, 1.0)
        self.assertAlmostEqual(y_m, 4.0)
        self.assertAlmostEqual(abs(yaw), math.pi)

    def test_pose_step_wraps_yaw_at_pi(self):
        first = PoseSample(1, 10, 10, 0.0, 0.0, math.radians(179.0))
        second = PoseSample(2, 20, 20, 0.0, 0.0, math.radians(-179.0))
        self.assertAlmostEqual(math.degrees(pose_step(first, second).yaw_rad), 2.0)


class HeaderAuditTests(unittest.TestCase):
    def test_detects_duplicate_regression_and_zero(self):
        audit = HeaderAudit()
        for sequence, header in enumerate((100, 100, 90, 0, 110), start=1):
            audit.add(header, sequence * 1000, sequence)
        result = audit.summary()
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["regressions"], 1)
        self.assertEqual(result["zero_stamps"], 1)
        self.assertAlmostEqual(result["max_regression_ms"], 0.00001)


class PoseSpoolTests(unittest.TestCase):
    def test_header_order_can_have_different_maximum_than_record_order(self):
        # Record order: x 0 -> 10 -> 11, max step 10.
        # Header order: x 0 -> 11 -> 10, max step 11.
        samples = (
            PoseSample(1, 10, 100, 0.0, 0.0, 0.0),
            PoseSample(2, 20, 300, 10.0, 0.0, 0.0),
            PoseSample(3, 30, 200, 11.0, 0.0, 0.0),
        )
        with tempfile.TemporaryDirectory() as directory:
            spool = PoseSpool(Path(directory) / "spool.sqlite3")
            try:
                for sample in samples:
                    spool.add("tf:map->odom", sample)
                spool.finish()
                result = ordered_pose_summary(
                    spool.iter_series("tf:map->odom", "header"), 10
                )
                self.assertEqual(
                    result["max_translation_step"]["current"]["sequence"], 3
                )
                self.assertAlmostEqual(
                    result["max_translation_step"]["translation_step_m"], 11.0
                )
            finally:
                spool.close()

    def test_composes_map_base_with_nearest_odom_base_header(self):
        map_before = PoseSample(1, 100, 1000, 1.0, 0.0, 0.0)
        map_after = PoseSample(2, 200, 2000, 2.0, 0.0, 0.0)
        event = pose_step(map_before, map_after)
        with tempfile.TemporaryDirectory() as directory:
            spool = PoseSpool(Path(directory) / "spool.sqlite3")
            try:
                spool.add("tf:map->odom", map_before)
                spool.add("tf:map->odom", map_after)
                spool.add(
                    "tf:odom->base_footprint",
                    PoseSample(3, 110, 1010, 0.5, 0.0, 0.0),
                )
                spool.add(
                    "tf:odom->base_footprint",
                    PoseSample(4, 210, 2010, 0.6, 0.0, 0.0),
                )
                spool.finish()
                result = compose_map_base_event(
                    spool, event, "tf:odom->base_footprint", 100
                )
                self.assertAlmostEqual(result["poses"][0]["map_base"]["x_m"], 1.5)
                self.assertAlmostEqual(result["poses"][1]["map_base"]["x_m"], 2.6)
                self.assertAlmostEqual(result["map_base_translation_step_m"], 1.1)
            finally:
                spool.close()


class ScanPairerTests(unittest.TestCase):
    def test_pairs_out_of_record_order_by_exact_header(self):
        pairer = ScanPairer(pending_limit=4)
        pairer.add("filtered", 100, 1_500_000)
        pairer.add("raw", 100, 1_000_000)
        result = pairer.summary(raw_count=1, filtered_count=1)
        self.assertEqual(result["paired_scans"], 1)
        self.assertEqual(result["pairs_with_identical_header"], 1)
        self.assertAlmostEqual(
            result["filtered_receipt_minus_raw_receipt_ms"]["mean"], 0.5
        )

    def test_pending_state_is_bounded(self):
        pairer = ScanPairer(pending_limit=2)
        pairer.add("raw", 1, 1)
        pairer.add("raw", 2, 2)
        pairer.add("raw", 3, 3)
        result = pairer.summary(raw_count=3, filtered_count=0)
        self.assertEqual(result["unmatched_at_end"]["raw"], 2)
        self.assertEqual(result["evicted_from_bounded_pair_buffer"]["raw"], 1)

    def test_pairs_rewritten_headers_by_near_receipt_time(self):
        pairer = ScanPairer(pending_limit=4, tolerance_ms=50.0)
        pairer.add("raw", 1_000_000_000, 2_000_000_000)
        pairer.add("filtered", 1_130_000_000, 2_004_000_000)
        result = pairer.summary(raw_count=1, filtered_count=1)
        self.assertEqual(result["paired_scans"], 1)
        self.assertEqual(result["pairs_with_identical_header"], 0)
        self.assertAlmostEqual(
            result["filtered_header_minus_raw_header_ms"]["mean"], 130.0
        )


if __name__ == "__main__":
    unittest.main()
