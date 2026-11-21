"""2026-11-19 optional left/right (front-corner) HC-SR04 support, staged. No ROS, no hardware."""
import ast
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas_lidar_availability as ala  # noqa: E402

REPO_CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'ultrasonic_mounts.json'
GOOD = (0.10, -0.18, -10.0, 10.0)


def bridge_function():
    tree = ast.parse((SCRIPTS / 'ultrasonic_arduino_bridge.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'side_ultrasonic_commands')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'bridge', 'exec'), ns)
    return ns['side_ultrasonic_commands']


def scan(blank_deg=()):
    ranges = []
    for k in range(360):
        robot_deg = (k + 0.5) % 360
        ranges.append(float('inf') if int(robot_deg) in blank_deg else 3.0)
    return NS(header=NS(frame_id='laser_frame', stamp=NS(sec=100, nanosec=0)), range_min=.15, range_max=12.,
              angle_min=-math.pi, angle_increment=math.pi / 180, ranges=ranges)


class MountConfigTests(unittest.TestCase):
    def test_repo_config_is_disabled_until_measured(self):
        self.assertEqual(ala.load_side_mounts(REPO_CONFIG), {})

    def test_enabled_and_implausible_entries(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'm.json'
            p.write_text(json.dumps({'right': {'enabled': True, 'x_m': 0.1, 'y_m': -0.18, 'axis_deg': -10,
                                               'half_cone_deg': 10}}))
            self.assertEqual(ala.load_side_mounts(p), {'right': GOOD})
            p.write_text(json.dumps({'left': {'enabled': True, 'x_m': 2.0, 'y_m': 0.18, 'axis_deg': 10,
                                              'half_cone_deg': 10}}))
            with self.assertRaises(ValueError):
                ala.load_side_mounts(p)


class CoverageTests(unittest.TestCase):
    def test_no_mount_no_coverage(self):
        ext = ala.sweep_extent(0.12, 0.0)
        self.assertEqual(ala.side_ultrasonic_covered_bins({'right': 1.5}, ext, {}), set())

    def test_short_reading_covers_nothing(self):
        ext = ala.sweep_extent(0.12, 0.0)
        self.assertEqual(ala.side_ultrasonic_covered_bins({'right': 0.2}, ext, {'right': GOOD}), set())

    def test_geometry_sanity_sensor_on_the_laser_axis(self):
        # Synthetic: a sensor at the laser origin looking along -27.5 deg sees the whole -30..-25 bin.
        ext = ala.sweep_extent(0.12, 0.0)
        cov = ala.side_ultrasonic_covered_bins({'right': 1.5}, ext, {'right': (ala.LASER_X, 0.0, -27.5, 10.0)})
        self.assertIn(66, cov)
        self.assertTrue(all(b >= 60 for b in cov), cov)          # right-front only, never the left or rear

    def test_corner_mount_cannot_vouch_for_its_own_blind_side(self):
        # A sensor on the bumper corner cannot see the points right beside itself, so it must not cover the
        # door-frame bins (-35..-20 deg) on its own: the guard keeps vetoing until the LiDAR sees the frame.
        ext = ala.sweep_extent(0.12, 0.0)
        cov = ala.side_ultrasonic_covered_bins({'right': 1.5}, ext, {'right': (0.25, -0.18, -30.0, 10.0)})
        self.assertFalse(cov & {65, 66, 67})

    def test_reason_ignores_side_ranges_without_mounts(self):
        old = dict(ala.SIDE_US_MOUNTS)
        try:
            ala.SIDE_US_MOUNTS = {}
            g = ala.LidarAvailability(); g.update(scan(blank_deg=set(range(345, 350))), 10.0)
            r = g.reason(0.1, 0.0, 100.1, 10.1, ultrasonic={'right': 1.5})
            self.assertIn('unobserved', r)
        finally:
            ala.SIDE_US_MOUNTS = old


def bridge_swap():
    tree = ast.parse((SCRIPTS / 'ultrasonic_arduino_bridge.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'swap_left_right_payload')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'bridge', 'exec'), ns)
    return ns['swap_left_right_payload']


class SwapTests(unittest.TestCase):
    def test_left_right_exchanged_and_marked(self):
        f = bridge_swap()
        p = {'reason': 'SAMPLE_REPORT', 'sensors': {'front': {'range_mm': 1}, 'left': {'range_mm': 226},
                                                     'right': {'range_mm': 238}, 'rear': {'range_mm': 4}}}
        q = f(p)
        self.assertEqual(q['sensors']['left']['range_mm'], 238)
        self.assertEqual(q['sensors']['right']['range_mm'], 226)
        self.assertEqual(q['sensors']['front'], p['sensors']['front'])
        self.assertTrue(q['left_right_swapped'])
        self.assertEqual(p['sensors']['left']['range_mm'], 226)           # input not modified

    def test_invalid_snapshot_passes_through(self):
        f = bridge_swap()
        p = {'reason': 'SERIAL_BACKLOG', 'sensors': {}}
        self.assertIs(f(p), p)


class BridgeTests(unittest.TestCase):
    def test_channels_touched_only_when_explicit(self):
        f = bridge_function()
        self.assertEqual(f({}), [])
        self.assertEqual(f({'ATLAS_LEFT_ULTRASONIC_ENABLED': '1'}), ['USENABLE,L,1'])
        self.assertEqual(f({'ATLAS_LEFT_ULTRASONIC_ENABLED': '0', 'ATLAS_RIGHT_ULTRASONIC_ENABLED': '1'}),
                         ['USENABLE,L,0', 'USENABLE,R,1'])
        self.assertEqual(f({'ATLAS_RIGHT_ULTRASONIC_ENABLED': 'yes'}), [])


if __name__ == '__main__':
    unittest.main()
