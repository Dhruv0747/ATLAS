"""'What ATLAS sees' gate view (2026-11-22): per-direction sources and probes, using the real gate functions."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_gate_view as gv  # noqa: E402
import atlas_lidar_availability as la  # noqa: E402


def scan(ranges, stamp=100.0):
    return NS(header=NS(frame_id='laser_frame', stamp=NS(sec=int(stamp), nanosec=int((stamp % 1) * 1e9))),
              range_min=0.15, range_max=12.0, angle_min=-math.pi, angle_increment=math.radians(1.0),
              ranges=list(ranges))


def robot_bin_to_rays(b):
    """laser_frame ray indices (angle_min -180, 1 deg) whose robot bearing falls in bin b (laser yawed 180)."""
    return [i for i in range(360) if int(((i - 180 + 180) % 360) // 5) % 72 == b]


class Grid:
    """Open box map: free inside, walls at |x|,|y| = 3 m, unknown nothing."""
    def __init__(self, unknown_east=False):
        self.res, self.ox, self.oy, self.w, self.h, self.occ, self.free = 0.05, -4.0, -4.0, 160, 160, 65, 25
        self.data = []
        for gy in range(self.h):
            for gx in range(self.w):
                x, y = self.ox + (gx + .5) * self.res, self.oy + (gy + .5) * self.res
                v = 100 if max(abs(x), abs(y)) >= 3.0 else 0
                if unknown_east and x > 1.0 and abs(y) < 0.5:
                    v = -1
                self.data.append(v)

    first_wall = la.OccGrid.first_wall


class GateViewTests(unittest.TestCase):
    def guard(self, ranges, now=10.0, stamp=100.0):
        g = la.LidarAvailability()
        g.update(scan(ranges, stamp), now)
        return g

    def test_missing_scan(self):
        self.assertEqual(gv.build(None, None, 0, 0)['state'], 'MISSING')

    def test_full_scan_all_lidar_and_probes_pass(self):
        g = self.guard([2.0] * 360)
        out = gv.build(g, scan([2.0] * 360), 10.1, 100.1)
        self.assertEqual(out['counts'], {'lidar': 72})
        self.assertTrue(all(p['ok'] for p in out['probes'].values()))

    def test_no_echo_ahead_is_none_and_forward_probe_stops(self):
        r = [2.0] * 360
        for b in (0, 71):                       # dead ahead (robot 0..5 and 355..360)
            for i in robot_bin_to_rays(b):
                r[i] = float('inf')
        g = self.guard(r)
        out = gv.build(g, scan(r), 10.1, 100.1)
        srcs = {it['bin']: it['source'] for it in out['bins']}
        self.assertEqual(srcs[0], 'none'); self.assertEqual(srcs[71], 'none')
        self.assertFalse(out['probes']['forward']['ok'])
        self.assertIn('unobserved', out['probes']['forward']['reason'])
        self.assertTrue(out['probes']['reverse']['ok'])
        self.assertEqual(out['map_fallback'], 'no map')

    def test_map_explains_gap_toward_mapped_wall(self):
        r = [2.0] * 360
        for i in robot_bin_to_rays(0):
            r[i] = float('inf')
        g = self.guard(r)
        out = gv.build(g, scan(r), 10.1, 100.1, grid=Grid(), pose=(0.0, 0.0, 0.0), xy_std=0.05, yaw_std=2.0,
                       pose_age_s=0.5)
        it = out['bins'][0]
        self.assertEqual(it['source'], 'map')
        self.assertEqual(it['map']['hit'], 'wall')
        self.assertTrue(out['probes']['forward']['ok'])

    def test_unknown_map_stays_none_and_reports_point(self):
        r = [2.0] * 360
        for i in robot_bin_to_rays(0):
            r[i] = float('inf')
        g = self.guard(r)
        out = gv.build(g, scan(r), 10.1, 100.1, grid=Grid(unknown_east=True), pose=(0.0, 0.0, 0.0), xy_std=0.05,
                       yaw_std=2.0, pose_age_s=0.5)
        it = out['bins'][0]
        self.assertEqual(it['source'], 'none')
        self.assertEqual(it['map']['hit'], 'unknown')
        self.assertAlmostEqual(it['map']['point'][0], 1.0, delta=0.1)
        self.assertFalse(out['probes']['forward']['ok'])

    def test_unconfident_location_disables_map_fallback(self):
        r = [2.0] * 360
        for i in robot_bin_to_rays(0):
            r[i] = float('inf')
        g = self.guard(r)
        out = gv.build(g, scan(r), 10.1, 100.1, grid=Grid(), pose=(0.0, 0.0, 0.0), xy_std=0.30, yaw_std=2.0,
                       pose_age_s=0.5)
        self.assertEqual(out['bins'][0]['source'], 'none')
        self.assertIn('not confident', out['map_fallback'])

    def test_front_ultrasonic_covers_dead_ahead(self):
        r = [2.0] * 360
        for b in (0, 71):
            for i in robot_bin_to_rays(b):
                r[i] = float('inf')
        g = self.guard(r)
        val = {'sensors': {'front': {'state': 'VALID', 'range_mm': 1500, 'sample_age_s': 0.1},
                           'rear': {'state': 'INVALID', 'range_mm': 0, 'sample_age_s': 0.1}}}
        out = gv.build(g, scan(r), 10.1, 100.1, validity=val)
        self.assertEqual(out['ultrasonic_m'], {'front': 1.5})
        self.assertEqual(out['bins'][0]['source'], 'ultrasonic')

    def test_astra_obstacles_reported_when_fresh(self):
        g = self.guard([2.0] * 360)
        g.cover_obstacles, g.cover_received, g.cover_bins = {3: 0.9}, 10.0, set()
        out = gv.build(g, scan([2.0] * 360), 10.1, 100.1)
        self.assertEqual(out['astra_obstacles'], [{'bin': 3, 'distance_m': 0.9}])
        self.assertTrue(out['astra_fresh'])
        stale = gv.build(g, scan([2.0] * 360), 12.0, 100.1)
        self.assertEqual(stale['astra_obstacles'], [])

    def test_stale_ultrasonic_ignored(self):
        val = {'sensors': {'front': {'state': 'VALID', 'range_mm': 1500, 'sample_age_s': 2.0}}}
        self.assertEqual(gv.ultrasonic_ranges(val), {})

    def test_stale_scan_probe_reports_stale(self):
        g = self.guard([2.0] * 360, now=10.0)
        out = gv.build(g, scan([2.0] * 360), 12.0, 102.0)
        self.assertIn('stale', out['probes']['forward']['reason'])


if __name__ == '__main__':
    unittest.main()
