import copy
import math
import unittest

import numpy as np
from scipy.spatial import cKDTree

from atlas_amcl_diversity_summary import (check_invariants, endpoint_fit, last_span,
                                          odd_beam_points, recovered)


def row(mode, seed, poses, resamples=None):
    traj = [{'time_s': float(i), 'pose': list(p)} for i, p in enumerate(poses)]
    return {'mode': mode, 'seed': seed, 'initial': {'pose': [0.0, 0.0, 0.0]},
            'updates': len(traj), 'resamples': len(traj) if resamples is None else resamples,
            'trajectory': traj, 'final': traj[-1]}


class DiversitySummaryTests(unittest.TestCase):
    def test_recovery_needs_both_position_and_heading(self):
        ref = (0.0, 0.0, 0.0)
        self.assertTrue(recovered((0.4, 0.2, math.radians(19)), ref))
        self.assertFalse(recovered((0.4, 0.4, 0.0), ref))
        self.assertFalse(recovered((0.0, 0.0, math.radians(21)), ref))
        self.assertTrue(recovered((0.0, 0.0, math.radians(359)), ref))

    def test_last_span_uses_final_window_only(self):
        traj = [{'time_s': 0.0, 'pose': [9, 9, 0]}, {'time_s': 40.0, 'pose': [0, 0, 0]},
                {'time_s': 50.0, 'pose': [0.3, 0.4, 0]}]
        self.assertAlmostEqual(last_span(traj, 30.0), 0.5)

    def test_last_span_rejects_empty(self):
        with self.assertRaises(ValueError):
            last_span([])

    def test_odd_beams_split_before_filtering(self):
        ranges = [1.0, 1.0, float('inf'), 1.0, 0.1, 1.0]
        pts = odd_beam_points(0.0, math.pi / 2, ranges, 0.15, 12.0)
        self.assertEqual(len(pts), 3)  # indices 1, 3, 5
        self.assertTrue(np.allclose(pts[0], [0.0, 1.0], atol=1e-9))

    def test_endpoint_fit_counts_close_endpoints(self):
        tree = cKDTree(np.array([[2.0, 0.0], [2.0, 1.0]]))
        pts = np.array([[1.0, 0.0], [1.0, 1.0], [5.0, 0.0]])
        within, median = endpoint_fit(pts, np.array([1.0, 0.0, 0.0]), np.zeros(3), tree)
        self.assertAlmostEqual(within, 2 / 3)
        self.assertAlmostEqual(median, 0.0)

    def test_invariants_accept_consistent_runs(self):
        doc = {'results': [row('parked_gate', 1, [[0, 0, 0]] * 3, resamples=0),
                           row('parked_gate', 2, [[0, 0, 0]] * 3, resamples=0),
                           row('jitter_medium', 1, [[0, 0, 0], [0.1, 0, 0], [0.2, 0, 0]])]}
        self.assertEqual(check_invariants(doc), 3)

    def test_invariants_reject_moving_gate(self):
        doc = {'results': [row('parked_gate', 1, [[0, 0, 0], [0.1, 0, 0]], resamples=0)]}
        with self.assertRaises(AssertionError):
            check_invariants(doc)

    def test_invariants_reject_unequal_initial_state(self):
        a = row('baseline', 1, [[0, 0, 0]])
        b = copy.deepcopy(a)
        b['initial'] = {'pose': [1.0, 0.0, 0.0]}
        with self.assertRaises(AssertionError):
            check_invariants({'results': [a, b]})

    def test_invariants_reject_nonfinite_pose(self):
        doc = {'results': [row('baseline', 1, [[float('nan'), 0, 0]])]}
        with self.assertRaises(AssertionError):
            check_invariants(doc)


if __name__ == '__main__':
    unittest.main()
