"""Unit tests for the isolated AMCL no-motion replay schedule."""

import unittest

from atlas_amcl_nomotion_replay_client import next_phase_ns


class NoMotionPhaseTest(unittest.TestCase):
    def test_next_boundary(self):
        self.assertEqual(next_phase_ns(1_000_000_000, 578_000_000),
                         1_578_000_000)

    def test_exact_boundary_advances(self):
        self.assertEqual(next_phase_ns(1_578_000_000, 578_000_000),
                         2_578_000_000)

    def test_past_boundary_advances(self):
        self.assertEqual(next_phase_ns(1_600_000_000, 578_000_000),
                         2_578_000_000)


if __name__ == "__main__":
    unittest.main()
