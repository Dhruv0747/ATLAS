"""Guided mapping phase 1b: the live engine behind atlas_guided_mapping.py (pure; no ROS). 2026-11-26."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
import atlas_guided_mapping_engine as ge  # noqa: E402
from test_map_quality_core import LASER, LOOP, room, simulate  # noqa: E402

INC = 2 * math.pi / 360


def devanagari(text):
    return any('ऀ' <= ch <= 'ॿ' for ch in text)


def all_text(p):
    out = [p.get('verdict_text', '')] + list(p.get('prompts', [])) + list(p.get('notes', []))
    out += [w[2] for w in p.get('weak', [])] + [o['name'] for o in p.get('objects', [])]
    return out


class EngineTests(unittest.TestCase):
    def active(self, sid='s1'):
        e = ge.GuidedMappingEngine()
        self.assertTrue(e.set_session({'id': sid, 'state': 'active'}))
        return e

    def drive(self, e, grid, poses=LOOP, t0=0.0):
        for i, p in enumerate(poses):
            e.on_scan(t0 + i, p, -math.pi, INC, simulate(grid, p), 0.15, 12.0)
        return e

    def test_inactive_does_nothing(self):
        e = ge.GuidedMappingEngine()
        self.assertFalse(e.set_session(None))
        g = room()
        e.on_map(g)
        e.on_scan(0.0, (1.0, 1.0, 0.0), -math.pi, INC, simulate(g, (1.0, 1.0, 0.0)), 0.15, 12.0)
        p = e.payload(10.0, (1.0, 1.0, 0.0))
        self.assertEqual(p['state'], 'inactive')
        self.assertEqual(p['samples'], 0)
        self.assertEqual(p['schema'], 1)

    def test_starting_session_is_not_active(self):
        e = ge.GuidedMappingEngine()
        self.assertFalse(e.set_session({'id': 's1', 'state': 'starting'}))
        self.assertEqual(e.payload(1.0, None)['state'], 'inactive')

    def test_waiting_for_map(self):
        e = self.active()
        p = e.payload(1.0, (0, 0, 0))
        self.assertEqual(p['state'], 'waiting_for_map')
        self.assertIn('Waiting for the live map', p['verdict_text'])

    def test_full_loop_ready_and_rows_decode(self):
        e = self.active()
        g = room()
        e.on_map(g)
        self.drive(e, g)
        p = e.payload(100.0, LOOP[-1])
        self.assertEqual(p['state'], 'active')
        self.assertTrue(p['ready'], p['verdict_text'])
        self.assertIn('Map ready for review: stop the session when parked', p['prompts'])
        tiles = ge.decode_rows(p['rows'])
        self.assertEqual(sum(1 for v in tiles.values() if v == 'A'), p['counts']['ACCEPTED'])
        self.assertEqual(sum(1 for v in tiles.values() if v == 'W'), p['counts']['WEAK'])

    def test_payload_stays_small_on_a_big_map(self):
        e = self.active()
        g = room(w_m=12.0, h_m=10.0)
        e.on_map(g)
        poses = [(0.6 + 1.0 * i, 0.6 + 1.5 * j, 0.0 if j % 2 == 0 else math.pi) for j in range(7) for i in range(11)]
        self.drive(e, g, poses)
        p = e.payload(1000.0, poses[-1])
        size = len(json.dumps(p, separators=(',', ':')))
        self.assertLessEqual(size, ge.MAX_PAYLOAD_BYTES, size)
        self.assertGreater(len(ge.decode_rows(p['rows'])), 300)

    def test_new_session_resets(self):
        e = self.active('s1')
        g = room()
        e.on_map(g)
        self.drive(e, g, LOOP[:3])
        self.assertEqual(e.payload(50.0, LOOP[2])['samples'], 3)
        self.assertTrue(e.set_session({'id': 's2', 'state': 'active'}))
        p = e.payload(51.0, LOOP[2])
        self.assertEqual(p['samples'], 0)
        self.assertEqual(p['session_id'], 's2')
        self.assertEqual(p['state'], 'waiting_for_map')       # the map belongs to the old session

    def test_cpu_pause_with_hysteresis(self):
        e = self.active()
        g = room()
        e.on_map(g)
        e.on_cpu_idle(0.20)
        self.drive(e, g, LOOP[:3])
        p = e.payload(10.0, LOOP[2])
        self.assertEqual(p['state'], 'paused_cpu')
        self.assertEqual(p['samples'], 0)
        self.assertIn('paused: the rover CPU is busy', p['verdict_text'])
        e.on_cpu_idle(0.30)
        self.assertEqual(e.payload(11.0, None)['state'], 'paused_cpu')
        e.on_cpu_idle(0.40)
        self.drive(e, g, LOOP[:3], t0=20.0)
        self.assertEqual(e.payload(30.0, LOOP[2])['samples'], 3)
        e.on_cpu_idle(None)                                    # unknown CPU never pauses
        self.assertEqual(e.payload(31.0, LOOP[2])['state'], 'active')

    def test_pose_jump_prompt(self):
        e = self.active()
        g = room()
        e.on_map(g)
        self.drive(e, g)
        e.on_map_odom(200.0, 0.0, 0.0, 0.0, (2.2, 2.4))
        e.on_map_odom(201.0, 1.3, 0.1, math.radians(12), (2.2, 2.4))
        p = e.payload(202.0, (2.0, 2.3, 0.0))
        self.assertIn('Position jumped here: stop, wait for GO, then continue slowly', p['prompts'])
        self.assertFalse(p['ready'])
        self.assertTrue(any('position jumped' in w[2] for w in p['weak']))

    def test_ultrasonic_only_new_valid_fresh_samples(self):
        e = self.active()
        g = room()
        e.on_map(g)
        pose = (1.0, 1.5, 0.0)
        e.on_scan(0.0, pose, -math.pi, INC, [float('inf')] * 360, 0.15, 12.0)   # LiDAR silent everywhere

        def msg(seq, mm=600, state='VALID', age=0.05):
            return json.dumps({'sensors': {'front': {'state': state, 'range_mm': mm, 'sample_sequence': seq,
                                                     'sample_age_s': age},
                                           'rear': {'state': 'NO_ECHO', 'range_mm': None, 'sample_sequence': 9,
                                                    'sample_age_s': 0.1}}})
        self.assertEqual(e.on_ultrasonic(0.1, pose, msg(1)), 1)
        self.assertEqual(e.on_ultrasonic(0.2, pose, msg(1)), 0)                 # repeated sample
        self.assertEqual(e.on_ultrasonic(0.3, pose, msg(2, age=0.9)), 0)        # stale
        self.assertEqual(e.on_ultrasonic(0.4, pose, msg(3, state='NO_ECHO')), 0)
        self.assertEqual(e.on_ultrasonic(0.5, pose, 'not json'), 0)
        self.assertEqual(e.on_ultrasonic(0.6, pose, msg(4)), 1)

    def test_depth_object_listed_with_sources(self):
        e = self.active()
        g = room()
        e.on_map(g)
        amin, inc = -0.52, 0.0087
        for i, (x, yaw) in enumerate([(1.0, 0.0), (1.15, 0.05), (1.3, -0.05), (1.0, 0.5)]):
            pose = (x, 1.5, yaw)
            e.on_scan(float(i), pose, -math.pi, INC, [float('inf')] * 360, 0.15, 12.0)
            ranges = [2.0 - x if -10 <= math.degrees(amin + k * inc) <= 10 else float('inf') for k in range(120)]
            e.on_depth(float(i) + 0.05, pose, amin, inc, ranges)
        p = e.payload(10.0, (1.3, 1.5, 0.0))
        self.assertEqual(len(p['objects']), 1, p['objects'])
        o = p['objects'][0]
        self.assertEqual(o['sources'], ['depth'])
        self.assertTrue(o['name'].startswith('Candidate'))
        self.assertTrue(any(t.startswith('Object the LiDAR cannot see') for t in p['prompts']), p['prompts'])

    def test_depth_missing_is_reported_honestly(self):
        e = self.active()
        g = room()
        e.on_map(g)
        self.drive(e, g, LOOP[:2])
        p = e.payload(5.0, LOOP[1])
        self.assertIn('Depth camera: no data (the light mapping profile pauses it); ultrasonic and LiDAR only',
                      p['notes'])

    def test_all_text_english(self):
        e = self.active()
        g = room(door=(1.0, 1.8))
        e.on_map(g)
        self.drive(e, g)
        e.on_map_odom(200.0, 0.0, 0.0, 0.0, (1.5, 0.6))
        e.on_map_odom(201.0, 0.9, 0.0, 0.2, (1.5, 0.6))
        for p in (e.payload(300.0, (1.4, 0.7, 0.0)), ge.GuidedMappingEngine().payload(1.0, None)):
            for text in all_text(p):
                self.assertFalse(devanagari(text), text)

    def test_bad_inputs_are_ignored(self):
        e = self.active()
        g = room()
        e.on_map(g)
        e.on_scan(0.0, (float('nan'), 0, 0), -math.pi, INC, [1.0] * 360, 0.15, 12.0)
        e.on_depth(0.0, (0, 0, float('inf')), -0.5, 0.01, [1.0] * 10)
        e.on_map_odom(1.0, float('nan'), 0, 0, (0, 0))
        self.assertEqual(e.payload(2.0, None)['samples'], 0)


class SessionFileTests(unittest.TestCase):
    def test_read_session(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'mapping_session.json'
            self.assertIsNone(ge.read_session(p))
            p.write_text(json.dumps({'id': 'abc', 'state': 'active', 'mode': 'manual_teaching'}))
            self.assertEqual(ge.read_session(p)['id'], 'abc')
            p.write_text('{broken')
            self.assertIsNone(ge.read_session(p))
            p.write_text(json.dumps({'state': 'active'}))           # no id: not usable
            self.assertIsNone(ge.read_session(p))


class RowsTests(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        tiles = {(0, 0): 'A', (1, 0): 'W', (3, 0): 'A', (-2, 5): 'W', (-1, 5): 'W'}
        rows = ge.encode_rows(tiles)
        self.assertEqual(ge.decode_rows(rows), tiles)
        self.assertEqual(rows[0], [0, 0, 'AW.A'])


if __name__ == '__main__':
    unittest.main()
