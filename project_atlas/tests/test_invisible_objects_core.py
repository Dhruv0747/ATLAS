"""Guided mapping assistant: invisible-object candidates from depth + ultrasonic where the LiDAR has no echo. 2026-11-16."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_invisible_objects_core as io  # noqa: E402
import atlas_map_quality_core as mq  # noqa: E402


def lidar(blind_deg=(), dist=4.0):
    """LiDAR that sees a wall at `dist` everywhere except the base-frame bearings in blind_deg (no echo)."""
    s = io.LidarSectors(-math.pi, 2 * math.pi / 360, [dist] * 360, 0.1, 12.0)
    s.best = [dist] * 360
    for b in blind_deg:
        s.best[b % 360] = float('inf')
    return s


def depth_scan(obj_bearing_deg=(), r=1.0, n=121):
    """Astra-like scan: angle_min -0.52, step 0.0087; returns `r` for bins whose bearing is within obj_bearing_deg."""
    amin, inc = -0.52, 0.0087
    ranges = []
    for i in range(n):
        a = math.degrees(amin + i * inc)
        ranges.append(r if any(lo <= a <= hi for lo, hi in obj_bearing_deg) else float('inf'))
    return amin, inc, ranges


def empty_map():
    return mq.Grid(100, 100, 0.05, -2.5, -2.5, [0] * 10000)


class InvisibleTests(unittest.TestCase):
    def sofa_drive(self, lidar_sees=False, grid=None):
        """Robot at x 0..0.3 looking +x at an object 1.0-1.2 m ahead, bearing about -10..+10 deg."""
        inv = io.InvisibleObjects()
        for i, (x, yaw) in enumerate([(0.0, 0.0), (0.15, 0.05), (0.3, -0.05), (0.0, 0.6)]):
            r = 1.0 - x
            amin, inc, ranges = depth_scan([(-10, 10)], r=r)
            li = lidar(dist=r if lidar_sees else 4.0, blind_deg=() if lidar_sees else range(-15, 16))
            inv.add_depth(float(i), (x, 0.0, yaw), amin, inc, ranges, li, grid)
        return inv

    def test_depth_only_object_becomes_candidate(self):
        inv = self.sofa_drive()
        c = inv.candidates({'hall': (1.68, -5.35), 'near': (2.0, 0.0)})
        self.assertEqual(len(c), 1, c)
        poly = c[0]['polygon']
        xs = [q[0] for q in poly]
        self.assertLess(min(xs), 1.0)
        self.assertGreater(max(xs), 1.0)
        self.assertTrue(c[0]['candidate'])
        self.assertEqual(c[0]['name'], 'Candidate 1')
        self.assertEqual(c[0]['evidence']['sources'], ['depth'])
        self.assertEqual(c[0]['evidence']['nearest_place'], 'near')

    def test_lidar_visible_object_is_ignored(self):
        self.assertEqual(self.sofa_drive(lidar_sees=True).candidates(), [])

    def test_mapped_wall_is_ignored(self):
        g = empty_map()
        for gy in range(100):
            for gx in range(100):
                x = -2.5 + (gx + 0.5) * 0.05
                if 0.95 <= x <= 1.05:
                    g.data[gy * 100 + gx] = 100
        self.assertEqual(self.sofa_drive(grid=g).candidates(), [])

    def test_single_viewpoint_is_not_enough(self):
        inv = io.InvisibleObjects()
        for i in range(5):
            amin, inc, ranges = depth_scan([(-10, 10)])
            inv.add_depth(float(i), (0.0, 0.0, 0.0), amin, inc, ranges, lidar(blind_deg=range(-15, 16)))
        self.assertEqual(inv.candidates(), [])

    def test_passer_by_fades_out(self):
        inv = self.sofa_drive()
        # the object leaves: later depth frames see through to 2.5 m along the same bearings, 6 times
        for i in range(6):
            amin, inc, ranges = depth_scan([(-12, 12)], r=2.5)
            inv.add_depth(10.0 + i, (0.05 * (i % 2), 0.0, 0.0), amin, inc, ranges, lidar(blind_deg=range(-15, 16)))
        self.assertEqual([c for c in inv.candidates() if c['polygon'][0][0] < 1.5], [])

    def test_ultrasonic_needs_lidar_gap_and_repeats(self):
        inv = io.InvisibleObjects()
        for i in range(8):
            inv.add_ultrasonic(float(i), (0.1 * (i % 3), 0.0, 0.0), 'front', 0.6, lidar(blind_deg=range(-12, 13)))
        c = inv.candidates()
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]['evidence']['sources'], ['ultrasonic'])
        xs = [q[0] for q in c[0]['polygon']]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0.95, delta=0.15)
        inv2 = io.InvisibleObjects()
        for i in range(8):
            self.assertEqual(inv2.add_ultrasonic(float(i), (0.1 * (i % 3), 0.0, 0.0), 'front', 0.6,
                                                 lidar(dist=0.85)), 0)          # LiDAR sees it: no evidence
        self.assertEqual(inv2.add_ultrasonic(0.0, (0, 0, 0), 'front', 5.0, lidar(blind_deg=range(360))), 0)
        self.assertEqual(inv2.add_ultrasonic(0.0, (0, 0, 0), 'left', 0.5, lidar(blind_deg=range(360))), 0)

    def test_rear_sensor_points_backwards(self):
        inv = io.InvisibleObjects()
        for i in range(8):
            inv.add_ultrasonic(float(i), (0.1 * (i % 3), 0.0, 0.0), 'rear', 0.5,
                               lidar(blind_deg=range(165, 196)))
        c = inv.candidates()
        self.assertEqual(len(c), 1)
        self.assertLess(max(q[0] for q in c[0]['polygon']), -0.4)

    def test_lidar_sectors_use_laser_mount(self):
        ranges = [float('inf')] * 360
        ranges[180] = 1.0                       # laser angle 0 = base bearing 180 (laser yaw 180, x -0.05)
        s = io.LidarSectors(-math.pi, 2 * math.pi / 360, ranges, 0.1, 12.0)
        self.assertAlmostEqual(s.min_range(math.pi, 1.0), 1.05, delta=0.02)
        self.assertEqual(s.min_range(0.0, 5.0), float('inf'))

    def test_unmapped_lidar_object_is_a_map_change(self):
        """A box the map does not have (map free there) but the LiDAR sees: reported by the map-change layer."""
        g = empty_map()
        changes = io.InvisibleObjects(io.MAP_CHANGE_POLICY)
        for i, (x, y) in enumerate([(-1.0, 0.0), (-0.8, 0.3), (-1.0, -0.4)]):
            ranges = [float('inf')] * 360
            # laser yaw 180 + angle_min -180: beam k points at base bearing k deg
            for k in range(360):
                a = math.radians(k)
                # box: x in [0.5, 0.7], y in [-0.2, 0.2]; laser at (x - 0.05, y)
                lx = x - 0.05
                for r100 in range(20, 300):
                    r = r100 / 100.0
                    px, py = lx + r * math.cos(a), y + r * math.sin(a)
                    if 0.5 <= px <= 0.7 and -0.2 <= py <= 0.2:
                        ranges[k] = r
                        break
            changes.add_unmapped_lidar(float(i), (x, y, 0.0), -math.pi, 2 * math.pi / 360, ranges, 0.15, 12.0, g)
        c = changes.candidates()
        self.assertEqual(len(c), 1, c)
        self.assertEqual(c[0]['evidence']['sources'], ['lidar-unmapped'])
        xs = [q[0] for q in c[0]['polygon']]
        self.assertLess(min(xs), 0.55)
        # the same box drawn into the map: no map change
        for gy in range(100):
            for gx in range(100):
                px, py = -2.5 + (gx + 0.5) * 0.05, -2.5 + (gy + 0.5) * 0.05
                if 0.5 <= px <= 0.7 and -0.2 <= py <= 0.2:
                    g.data[gy * 100 + gx] = 100
        again = io.InvisibleObjects(io.MAP_CHANGE_POLICY)
        for i, (x, y) in enumerate([(-1.0, 0.0), (-0.8, 0.3)]):
            ranges = [float('inf')] * 360
            ranges[0] = 0.5 - x + 0.05
            again.add_unmapped_lidar(float(i), (x, y, 0.0), -math.pi, 2 * math.pi / 360, ranges, 0.15, 12.0, g)
        self.assertEqual(again.candidates(), [])

    def test_overlaps(self):
        a = [[0, 0], [1, 0], [1, 1], [0, 1]]
        self.assertTrue(io.overlaps(a, [[0.5, 0.5], [2, 0.5], [2, 2], [0.5, 2]]))
        self.assertFalse(io.overlaps(a, [[1.5, 0], [2, 0], [2, 1], [1.5, 1]]))

    def test_bad_input(self):
        inv = io.InvisibleObjects()
        amin, inc, ranges = depth_scan([(-10, 10)])
        self.assertEqual(inv.add_depth(0.0, (float('nan'), 0, 0), amin, inc, ranges, lidar()), 0)
        self.assertEqual(inv.add_depth(0.0, (0, 0, 0), amin, inc, ranges, None), 0)
        self.assertEqual(inv.candidates(), [])


if __name__ == '__main__':
    unittest.main()
