"""Live saved-map check (owner 2026-11-26: "where can I see that the map needs updating"): LiDAR objects the saved map
does not have, counted only while the scan fits the map. Pure; no ROS."""
import json
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
import atlas_guided_mapping_engine as ge  # noqa: E402
import atlas_map_quality_core as mq  # noqa: E402

INC = 2 * math.pi / 360
BOX = (2.4, 2.7, 1.2, 1.6)                      # furniture added after the map was made (inside the 4 x 3 m room)


def room():
    """Free 4 x 3 m room with walls, unknown outside (same as test_map_quality_core.room)."""
    from test_map_quality_core import room as r
    return r()


def ranges(grid, pose, box=None):
    """Simulated LiDAR (laser x -0.05, yaw 180: beam k points at base bearing k deg)."""
    x, y, yaw = pose
    lx, ly = x - 0.05 * math.cos(yaw), y - 0.05 * math.sin(yaw)
    out = []
    for k in range(360):
        a = yaw + math.radians(k)
        r, hit = 0.05, float('inf')
        while r < 6.0:
            px, py = lx + r * math.cos(a), ly + r * math.sin(a)
            if box and box[0] <= px <= box[1] and box[2] <= py <= box[3]:
                hit = r
                break
            c = grid.cell(px, py)
            if c is None or grid.value(*c) == -1:
                break
            if grid.value(*c) >= 65:
                hit = r
                break
            r += 0.02
        out.append(hit)
    return out


POSES = [(0.8, 0.8, 0.0), (1.0, 1.4, 0.2), (0.9, 2.1, -0.3), (1.3, 0.6, 0.4), (1.2, 2.3, -0.5), (0.7, 1.5, 0.0)]


class MonitorTests(unittest.TestCase):
    def feed(self, m, g, poses=POSES, box=BOX, truth_offset=(0.0, 0.0, 0.0), t0=0.0):
        for i, p in enumerate(poses):
            truth = (p[0] + truth_offset[0], p[1] + truth_offset[1], p[2] + truth_offset[2])
            m.on_scan(t0 + 2.0 * i, p, -math.pi, INC, ranges(g, truth, box), 0.15, 12.0)

    def test_added_furniture_is_reported(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        self.feed(m, g)
        p = m.payload(100.0)
        self.assertEqual(p['state'], 'map_check')
        self.assertEqual(len(p['map_changes']), 1, p)
        poly = p['map_changes'][0]['polygon']
        xs, ys = [q[0] for q in poly], [q[1] for q in poly]
        self.assertTrue(min(xs) < 2.5 and max(xs) > 2.4 and min(ys) < 1.5 and max(ys) > 1.3, poly)
        self.assertEqual(p['map_changes'][0]['name'], 'Map change 1')
        self.assertIn('1 place looks different from the saved map', p['verdict_text'])
        self.assertTrue(any('Map out of date here' in t for t in p['prompts']), p['prompts'])

    def test_matching_room_is_clean(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        self.feed(m, g, box=None)
        p = m.payload(100.0)
        self.assertEqual(p['map_changes'], [])
        self.assertIn('Saved map matches what the LiDAR sees', p['verdict_text'])
        self.assertGreaterEqual(p['counts']['frames_used'], 5)

    def test_poor_fit_frames_are_not_used(self):
        """A wrong position must not look like a changed room."""
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        self.feed(m, g, box=None, truth_offset=(0.45, -0.3, 0.25))
        p = m.payload(100.0)
        self.assertEqual(p['map_changes'], [])
        self.assertEqual(p['counts']['frames_used'], 0)
        self.assertGreaterEqual(p['counts']['frames_skipped_fit'], 5)
        self.assertIn('position does not match the map', p['verdict_text'])

    def test_rate_limit_one_frame_per_second(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        for k in range(10):
            m.on_scan(k * 0.1, POSES[k % 2], -math.pi, INC, ranges(g, POSES[k % 2]), 0.15, 12.0)
        self.assertEqual(m.payload(5.0)['counts']['frames_used'], 1)

    def test_new_map_resets_evidence(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        self.feed(m, g)
        self.assertEqual(len(m.payload(100.0)['map_changes']), 1)
        m.on_map(room())                                    # same map again: kept
        self.assertEqual(len(m.payload(101.0)['map_changes']), 1)
        g2 = room()
        g2.data[10] = 100                                   # a different map (e.g. a promoted remap): reset
        m.on_map(g2)
        p = m.payload(102.0)
        self.assertEqual(p['map_changes'], [])
        self.assertEqual(p['counts']['frames_used'], 0)

    def test_paused_while_autonomy_armed(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        m.set_autonomy_armed(True)
        self.feed(m, g)
        p = m.payload(100.0)
        self.assertEqual(p['state'], 'map_check_paused')
        self.assertEqual(p['counts']['frames_used'], 0)
        self.assertIn('paused while autonomy is on', p['verdict_text'])
        m.set_autonomy_armed(False)
        self.feed(m, g, t0=200.0)
        self.assertEqual(len(m.payload(300.0)['map_changes']), 1)

    def test_cpu_pause(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        m.on_cpu_idle(0.1)
        self.feed(m, g)
        self.assertEqual(m.payload(100.0)['state'], 'paused_cpu')

    def test_waiting_for_map_and_size(self):
        m = ge.MapChangeMonitor()
        self.assertEqual(m.payload(1.0)['state'], 'waiting_for_map')
        g = room()
        m.on_map(g)
        self.feed(m, g)
        self.assertLessEqual(len(json.dumps(m.payload(100.0), separators=(',', ':'))), ge.MAX_PAYLOAD_BYTES)

    def test_evidence_is_bounded(self):
        m = ge.MapChangeMonitor(max_cells=50)
        g = room()
        m.on_map(g)
        for k in range(200):                                # 200 scattered single hits
            m.changes._hit(0.5 + 0.06 * (k % 50), 0.5 + 0.06 * (k // 50), 1.0, (k, 0, 0), 'lidar-unmapped')
        m.on_scan(500.0, POSES[0], -math.pi, INC, ranges(g, POSES[0]), 0.15, 12.0)
        self.assertLessEqual(len(m.changes.cells), 50)

    def test_text_english(self):
        g = room()
        for armed, idle in ((False, None), (True, None), (False, 0.1)):
            m = ge.MapChangeMonitor()
            m.on_map(g)
            m.set_autonomy_armed(armed)
            m.on_cpu_idle(idle)
            self.feed(m, g)
            p = m.payload(100.0)
            for text in [p['verdict_text']] + p['prompts'] + p['notes'] + [c['name'] for c in p['map_changes']]:
                self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in text), text)


class PositionsWordingTests(unittest.TestCase):
    """Owner 2026-11-26: while parked the card said "checked from 9 positions" for 9 scans from ONE position."""
    def test_parked_counts_one_position(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        for k in range(6):
            m.on_scan(2.0 * k, POSES[0], -math.pi, INC, ranges(g, POSES[0]), 0.15, 12.0)
        p = m.payload(100.0)
        self.assertEqual(p['counts']['frames_used'], 6)
        self.assertEqual(p['counts']['positions'], 1)
        self.assertIn('checked from 1 position only: drive around to check more', p['verdict_text'])
        self.assertNotIn('6 positions', p['verdict_text'])

    def test_moving_counts_distinct_positions(self):
        g = room()
        m = ge.MapChangeMonitor()
        m.on_map(g)
        for k, p in enumerate(POSES):
            m.on_scan(2.0 * k, p, -math.pi, INC, ranges(g, p), 0.15, 12.0)
        p = m.payload(100.0)
        self.assertEqual(p['counts']['positions'], len(POSES))
        self.assertIn(f'Saved map matches what the LiDAR sees (checked from {len(POSES)} positions)', p['verdict_text'])


if __name__ == '__main__':
    unittest.main()
