import math
import unittest
from types import SimpleNamespace as NS

import numpy as np
from scipy.spatial import cKDTree

from atlas_amcl_diversity_multidrive import held_out_points, outcome_groups, score_window


def scan(t_ranges=1.0, n=120):
    return NS(angle_min=-math.pi, angle_increment=2 * math.pi / n,
              ranges=[t_ranges] * n, range_min=0.15, range_max=12.0)


def result(mode, seed, final, jumps=0, step=0.0):
    traj = [{'time_s': 0.0, 'pose': [0.0, 0.0, 0.0]}, {'time_s': 40.0, 'pose': list(final)}]
    return {'mode': mode, 'seed': seed, 'initial': {'pose': [0.0, 0.0, 0.0]}, 'updates': 2,
            'resamples': 0 if mode == 'parked_gate' else 2, 'jumps_over_0_5m': jumps,
            'max_step_m': step, 'trajectory': traj, 'final': traj[-1]}


class MultiDriveTests(unittest.TestCase):
    def test_outcome_groups_split_distinct_poses(self):
        poses = [(0, 0, 0), (0.1, 0, 0), (3, 0, 0), (0, 0, math.pi)]
        self.assertEqual(outcome_groups(poses), [2, 1, 1])

    def test_held_out_respects_window_and_spacing(self):
        scans = [(t, scan()) for t in (5.0, 9.5, 10.0, 10.5, 11.2, 30.0)]
        chosen = held_out_points(scans, 9.0, 12.0)
        self.assertEqual(len(chosen), 2)  # 9.5 and 10.5 (>=0.9 s apart); 11.2 too close

    def test_held_out_skips_sparse_scans(self):
        self.assertEqual(held_out_points([(1.0, scan(0.1))], 0.0, 2.0), [])

    def test_score_window_pairs_seeds_and_flags_degradation(self):
        # Circular wall of radius 1 m around the origin; scans see it at 1 m.
        angles = np.linspace(0, 2 * math.pi, 720, endpoint=False)
        tree = cKDTree(np.column_stack((np.cos(angles), np.sin(angles))))
        scans = [(t, scan()) for t in (91.0, 92.0, 93.0)]
        doc = {'window_offset_s': [0.0, 95.0], 'results': [
            result('baseline', 1, (0, 0, 0)), result('baseline', 2, (0, 0, 0)),
            result('parked_gate', 1, (0, 0, 0)), result('parked_gate', 2, (0, 0, 0)),
            result('jitter_medium', 1, (0.5, 0, 0)), result('jitter_medium', 2, (0, 0, 0))]}
        out = score_window(doc, tree, np.zeros(3), scans)
        self.assertAlmostEqual(out['policies']['baseline']['fit_median'], 1.0)
        cmp = out['policies']['jitter_medium']['vs_baseline']
        self.assertEqual(cmp['paired_seeds'], 2)
        self.assertEqual(cmp['seeds_worse_by_margin'], 1)
        self.assertEqual(cmp['seeds_better_by_margin'], 0)

    def test_score_window_requires_held_out_scans(self):
        doc = {'window_offset_s': [0.0, 95.0], 'results': [result('baseline', 1, (0, 0, 0))]}
        with self.assertRaises(ValueError):
            score_window(doc, cKDTree(np.zeros((1, 2))), np.zeros(3), [(10.0, scan())])


if __name__ == '__main__':
    unittest.main()
