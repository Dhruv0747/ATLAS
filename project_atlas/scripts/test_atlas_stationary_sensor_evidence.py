import math
import unittest
from atlas_stationary_sensor_evidence import coverage, latest, pose_span


class SensorEvidenceTests(unittest.TestCase):
    def test_empty_is_unknown_not_stationary(self):
        self.assertIsNone(pose_span([]))
        self.assertIsNone(coverage([], 0, 8)['max_gap_s'])

    def test_duplicate_and_regression_are_exposed(self):
        result = coverage([1, 2, 2, 1.5, 7], 0, 8)
        self.assertEqual(result['duplicates'], 1)
        self.assertEqual(result['regressions'], 1)
        self.assertEqual(result['max_gap_s'], 5)

    def test_boundary_gap_is_not_hidden(self):
        self.assertEqual(coverage([6, 7, 8], 0, 8)['max_gap_s'], 6)

    def test_no_future_pose_selection(self):
        self.assertIsNone(latest([(2, 'future')], 1))
        self.assertEqual(latest([(0, 'past'), (2, 'future')], 1)[1], 'past')

    def test_wrap_is_not_full_rotation(self):
        result = pose_span([(0, 0, math.radians(179)), (0, 0, math.radians(-179))])
        self.assertAlmostEqual(result['yaw_span_deg'], 2)

    def test_translation_and_heading_are_separate(self):
        result = pose_span([(0, 0, 0), (.3, .4, math.pi/2)])
        self.assertAlmostEqual(result['xy_bbox_diagonal_m'], .5)
        self.assertAlmostEqual(result['yaw_span_deg'], 90)


if __name__ == '__main__':
    unittest.main()
