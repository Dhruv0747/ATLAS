"""2026-11-16 Astra depth coverage (core.last_coverage) feeding the LiDAR-availability guard. Needs numpy (rover)."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import numpy as np  # noqa: E402
import atlas_astra_obstacle_core as core  # noqa: E402
import atlas_lidar_availability as ala  # noqa: E402
from test_track_a import CAL, good_cfg, render, plane_z, box, union  # noqa: E402


def cover_msg(s, cover, ranges):
    return NS(header=NS(frame_id='base_link'), angle_min=s.amin, angle_increment=s.inc,
              ranges=[float(c) if np.isfinite(c) else float('inf') for c in cover],
              intensities=[1.0 if np.isfinite(r) else 0.0 for r in ranges])


class AstraCoverageTests(unittest.TestCase):
    def setUp(self):
        self.s = core.ObstacleScanner(good_cfg(x_m=0.13, pitch_deg=0.8), CAL)
        self.mid = self.s.nbins // 2

    def test_clear_floor_gives_floor_coverage_and_no_obstacle(self):
        r, _ = self.s.scan(render(self.s, plane_z(0.0)))
        cov = self.s.last_coverage
        self.assertFalse(np.isfinite(r[self.mid]))
        self.assertTrue(np.isfinite(cov[self.mid]) and cov[self.mid] > 0.8, cov[self.mid])

    def test_obstacle_bin_coverage_is_obstacle_range(self):
        r, _ = self.s.scan(render(self.s, union(plane_z(0.0), box(1.0, 1.3, -0.2, 0.2, 0.15))))
        self.assertTrue(np.isfinite(r[self.mid]))
        self.assertAlmostEqual(float(self.s.last_coverage[self.mid]), float(r[self.mid]), places=5)

    def test_no_valid_depth_no_evidence(self):
        r, _ = self.s.scan(np.zeros((120, 160), dtype=np.uint16))     # e.g. glass / black: no valid pixels
        self.assertFalse(np.isfinite(self.s.last_coverage).any())

    def test_guard_accepts_covered_front_bin(self):
        r, _ = self.s.scan(render(self.s, plane_z(0.0)))
        g = ala.LidarAvailability()
        g.update_coverage(cover_msg(self.s, self.s.last_coverage, r), 10.0)
        self.assertIn(0, g.covered(10.1))                  # dead-ahead LiDAR bin covered by clear floor
        self.assertEqual(g.covered(10.0 + ala.COVER_TIMEOUT_S + 0.1), set())   # stale coverage ignored


if __name__ == '__main__':
    unittest.main()
