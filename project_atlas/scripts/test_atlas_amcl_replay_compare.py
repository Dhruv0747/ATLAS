"""Tests for the replay/original AMCL jump comparison."""

import unittest

from atlas_amcl_replay_compare import summarize


class ReplayComparisonTest(unittest.TestCase):
    def test_post_stop_jump_classification(self):
        poses = [(9.0, 0.0, 0.0, 0.1),
                 (9.5, 0.6, 0.0, 0.2),
                 (10.5, 0.6, 0.0, 0.2),
                 (11.5, 1.3, 0.0, 0.4)]
        result = summarize(poses, stop_s=10.0)
        self.assertEqual(result["poses"], 4)
        self.assertEqual(result["post_stop_poses"], 2)
        self.assertEqual(len(result["large_jumps"]), 2)
        self.assertEqual(result["post_stop_large_jumps"], 1)
        self.assertEqual(result["max_jump_m"], 0.7)

    def test_long_gap_not_a_step(self):
        result = summarize([(0.0, 0.0, 0.0, 0.1),
                            (3.0, 2.0, 0.0, 0.1)], stop_s=1.0)
        self.assertEqual(result["large_jumps"], [])


if __name__ == "__main__":
    unittest.main()
