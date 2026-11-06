#!/usr/bin/env python3
"""Track A automated tests: simulated data only. No camera, motor, actuator or production ROS domain is touched.

Run: python3 -m unittest -v tests/test_track_a.py   (from project_atlas/; needs numpy, yaml; ROS tests need
     /opt/ros/humble sourced and run in an isolated localhost-only domain chosen by the test itself).
"""
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools/track_a'))
import atlas_astra_obstacle_core as core  # noqa: E402

K = [143.0, 0.0, 79.5, 0.0, 143.0, 59.5, 0.0, 0.0, 1.0]   # synthetic 160x120 intrinsics (~58 deg HFOV)
CAL = {'k': K, 'd': [0.0] * 5}
SERIAL = 'TEST-SERIAL'


def good_cfg(**mount):
    cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
    cfg['mount'].update({'x_m': 0.20, 'y_m': 0.0, 'z_m': 0.30, 'pitch_deg': 0.0})
    cfg['mount'].update(mount)
    cfg['obstacle_scan']['max_height_m'] = 0.50
    return cfg


def render(scanner, surface):
    """Synthetic 16UC1 depth (mm) by ray-casting each pixel against surface(origin, dirs) -> distance along ray."""
    rays = np.c_[scanner.rays, np.ones(len(scanner.rays))]          # optical-frame direction with z=1
    dirs_base = rays @ scanner.r.T                                   # direction per unit optical z, in base_link
    t = surface(scanner.t, dirs_base)                                # optical z (m) per pixel, nan = miss
    t = np.where(np.isfinite(t) & (t > 0), t, 0.0)
    return np.round(t * 1000).clip(0, 65535).astype(np.uint16).reshape(120, 160)


def plane_x(x0):     # vertical wall at base x = x0
    return lambda o, d: np.where(d[:, 0] > 1e-9, (x0 - o[0]) / d[:, 0], np.nan)


def plane_z(z0):     # horizontal plane (floor/ceiling) at base z = z0
    return lambda o, d: np.where(np.abs(d[:, 2]) > 1e-9, (z0 - o[2]) / d[:, 2], np.nan)


def box(x0, x1, y0, y1, ztop):   # front face of a box x0..x1, y0..y1, height 0..ztop
    def f(o, d):
        t = np.where(d[:, 0] > 1e-9, (x0 - o[0]) / d[:, 0], np.nan)
        p = o + d * t[:, None]
        hit = (p[:, 1] >= y0) & (p[:, 1] <= y1) & (p[:, 2] >= 0) & (p[:, 2] <= ztop)
        return np.where(hit, t, np.nan)
    return f


def union(*fs):
    def f(o, d):
        ts = np.stack([s(o, d) for s in fs])
        ts = np.where(np.isfinite(ts) & (ts > 0), ts, np.inf)
        m = ts.min(axis=0)
        return np.where(np.isfinite(m), m, np.nan)
    return f


class ConfigGate(unittest.TestCase):
    def test_shipped_config_refuses_unmeasured_mount(self):
        cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
        with self.assertRaises(core.ConfigError) as e:
            core.validate_config(cfg)
        for k in ('mount.x_m', 'mount.y_m', 'max_height_m'):          # still BLOCKED after G2 recovery
            self.assertIn(k, str(e.exception))
        for k in ('mount.z_m', 'mount.pitch_deg'):                       # recovered + accepted (G2 doc)
            self.assertNotIn(k + ' not measured', str(e.exception))

    def test_g2_recovered_values_are_plausible_and_keep_floor_out(self):
        cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
        self.assertEqual((cfg['mount']['z_m'], cfg['mount']['pitch_deg']), (0.30, 0.8))
        # With the recovered height/pitch (and the derived x candidate only for this simulation), a floor-only
        # scene must stay out of the obstacle band across the whole 0.35-3.0 m range.
        s = core.ObstacleScanner(good_cfg(x_m=0.13, z_m=0.30, pitch_deg=0.8), CAL)
        ranges, st = s.scan(render(s, plane_z(0.0)))
        self.assertEqual(st['obstacle_bins'], 0)
        # Sensitivity to the recorded pitch disagreement (phone 0.8 down vs depth hint 1.8 up, 2.6 deg apart).
        # If the camera really points 1.8 up but config says 0.8 down, points are computed TOO LOW: the floor never
        # leaks in (no phantom obstacles), but low objects far away can drop below the 4 cm floor cut.
        true = core.ObstacleScanner(good_cfg(x_m=0.13, z_m=0.30, pitch_deg=-1.8), CAL)
        _, leak = s.scan(render(true, plane_z(0.0)))
        self.assertEqual(leak['obstacle_bins'], 0, 'floor must not become phantom obstacles')
        near, _ = s.scan(render(true, union(plane_z(0.0), box(1.0, 1.3, -0.2, 0.2, 0.10))))
        far, _ = s.scan(render(true, union(plane_z(0.0), box(2.0, 2.3, -0.2, 0.2, 0.10))))
        self.assertTrue(np.isfinite(near[s.nbins // 2]), '10 cm box at 1.0 m still detected')
        self.assertFalse(np.isfinite(far[s.nbins // 2]), 'documented G4 risk: 10 cm box at 2.0 m missed')

    def test_good_config_passes(self):
        core.validate_config(good_cfg())

    def test_implausible_values_rejected(self):
        for bad in ({'z_m': 5.0}, {'z_m': -0.1}, {'pitch_deg': 80.0}, {'x_m': float('nan')}, {'y_m': True},
                    {'x_m': '0.2'}):
            with self.subTest(bad=bad), self.assertRaises(core.ConfigError):
                core.validate_config(good_cfg(**bad))

    def test_height_band_and_ranges_checked(self):
        for path, val in ((('obstacle_scan', 'max_height_m'), 0.06), (('obstacle_scan', 'range_max_m'), 0.3),
                          (('obstacle_scan', 'target_frame'), 'astra_link'), (('astra', 'depth_width'), 320),
                          (('obstacle_scan', 'stale_s'), 30.0), (('obstacle_scan', 'min_valid_fraction'), 1.5)):
            cfg = good_cfg(); cfg[path[0]][path[1]] = val
            with self.subTest(path=path, val=val), self.assertRaises(core.ConfigError):
                core.validate_config(cfg)


class CalibrationGate(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / 'config/astra_calibration').mkdir(parents=True)
        (self.root / 'tools').mkdir()
        os.symlink(ROOT / 'tools/vision3d', self.root / 'tools/vision3d')
        (self.root / 'config/vision3d_live.json').write_text(json.dumps({'identity': {'device_serial': SERIAL}}))
        self.doc = {'device_serial': SERIAL, 'source': 'measured_target', 'independently_validated': True,
                    'validation_evidence': 'synthetic test', 'width': 160, 'height': 120,
                    'frame_id': 'astra_depth_optical_frame', 'k': K, 'd': [0.0] * 5, 'distortion_model': 'plumb_bob'}

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, doc):
        (self.root / 'config/astra_calibration/depth_160x120.json').write_text(json.dumps(doc))

    def test_missing_file_refused(self):
        with self.assertRaises(FileNotFoundError):
            core.load_validated_calibration(self.root)

    def test_valid_doc_accepted(self):
        self.write(self.doc)
        self.assertEqual(core.load_validated_calibration(self.root)['k'], K)

    def test_invalid_docs_refused(self):
        for change in ({'independently_validated': False}, {'validation_evidence': None},
                       {'device_serial': 'OTHER'}, {'width': 640}, {'frame_id': 'astra_ir_optical_frame'},
                       {'source': 'factory_guess'}, {'k': K[:8]}):
            with self.subTest(change=change):
                self.write(dict(self.doc, **change))
                with self.assertRaises(Exception):
                    core.load_validated_calibration(self.root)


class Geometry(unittest.TestCase):
    def setUp(self):
        self.s = core.ObstacleScanner(good_cfg(), CAL)

    def centre(self, ranges):
        return float(ranges[self.s.nbins // 2])

    def test_wall_range(self):
        ranges, st = self.s.scan(render(self.s, union(plane_x(1.5), plane_z(0.0))))
        self.assertAlmostEqual(self.centre(ranges), 1.5, delta=0.02)
        self.assertEqual(self.s.decide(st, 0.1), 'OK')

    def test_floor_only_gives_no_obstacles(self):
        ranges, st = self.s.scan(render(self.s, plane_z(0.0)))
        self.assertEqual(st['obstacle_bins'], 0)

    def test_ceiling_above_rover_ignored(self):
        ranges, st = self.s.scan(render(self.s, union(plane_z(0.0), plane_z(1.0))))
        self.assertEqual(st['obstacle_bins'], 0)

    def test_low_box_detected(self):
        ranges, st = self.s.scan(render(self.s, union(plane_z(0.0), box(1.0, 1.3, -0.2, 0.2, 0.10))))
        self.assertAlmostEqual(self.centre(ranges), 1.0, delta=0.02)

    def test_too_close_and_too_far_ignored(self):
        for wall in (0.30, 3.4):
            ranges, st = self.s.scan(render(self.s, plane_x(wall)))
            with self.subTest(wall=wall):
                self.assertEqual(st['obstacle_bins'], 0)

    def test_tilted_mount_keeps_floor_out_and_wall_right(self):
        s = core.ObstacleScanner(good_cfg(pitch_deg=15.0), CAL)
        ranges, st = s.scan(render(s, plane_z(0.0)))
        self.assertEqual(st['obstacle_bins'], 0)
        ranges, st = s.scan(render(s, union(plane_z(0.0), plane_x(1.2))))
        self.assertAlmostEqual(float(ranges[s.nbins // 2]), 1.2, delta=0.02)

    def test_side_offset_and_yaw_geometry(self):
        s = core.ObstacleScanner(good_cfg(y_m=0.10, yaw_deg=10.0), CAL)
        ranges, _ = s.scan(render(s, plane_x(1.5)))
        i = int(round((0.0 - s.amin) / s.inc))
        self.assertAlmostEqual(float(ranges[i]), 1.5, delta=0.03)

    def test_optical_rotation_matches_launch_static_tf(self):
        def rpy(r, p, y):
            cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
            return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                             [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                             [-sp, cp * sr, cp * cr]])
        for pitch, yaw in ((0.0, 0.0), (15.0, 0.0), (-5.0, 8.0)):
            m = {'x_m': 0.2, 'y_m': 0.0, 'z_m': 0.3, 'pitch_deg': pitch, 'yaw_deg': yaw}
            r_core, _ = core.optical_to_base(m)
            r_tf = rpy(0, math.radians(pitch), math.radians(yaw)) @ rpy(-math.pi / 2, 0, -math.pi / 2)
            with self.subTest(pitch=pitch, yaw=yaw):
                np.testing.assert_allclose(r_core, r_tf, atol=1e-9)


class InvalidData(unittest.TestCase):
    def setUp(self):
        self.s = core.ObstacleScanner(good_cfg(), CAL)

    def test_nan_inf_zero_never_become_obstacles(self):
        d = np.full((120, 160), np.nan, dtype=np.float32)
        d[::2] = np.inf; d[1::4] = 0.0; d[3::4] = -np.inf
        ranges, st = self.s.scan(d, '32FC1')
        self.assertEqual(st['obstacle_bins'], 0)
        self.assertEqual(st['valid_fraction'], 0.0)
        self.assertEqual(self.s.decide(st, 0.1), 'BLINDED')

    def test_mixed_valid_and_invalid(self):
        d = render(self.s, union(plane_x(1.5), plane_z(0.0))).astype(np.float32) / 1000
        d[:, ::3] = np.nan
        ranges, st = self.s.scan(d, '32FC1')
        self.assertAlmostEqual(float(ranges[self.s.nbins // 2]), 1.5, delta=0.03)

    def test_blinded_camera_publishes_nothing(self):
        ranges, st = self.s.scan(np.zeros((120, 160), np.uint16))
        self.assertEqual(self.s.decide(st, 0.05), 'BLINDED')

    def test_stale_and_bad_ages(self):
        st = {'valid_fraction': 1.0}
        for age, want in ((0.1, 'OK'), (0.6, 'STALE'), (float('nan'), 'STALE'), (float('inf'), 'STALE'),
                          (-1.0, 'STALE')):
            with self.subTest(age=age):
                self.assertEqual(self.s.decide(st, age), want)

    def test_bad_frames_raise_not_publish(self):
        with self.assertRaises(ValueError):
            self.s.scan(np.zeros((240, 320), np.uint16))
        with self.assertRaises(ValueError):
            self.s.scan(np.zeros((120, 160), np.uint8), 'mono8')


class Nav2Merge(unittest.TestCase):
    NAV = os.environ.get('TRACK_A_NAV2_PARAMS')

    def setUp(self):
        if not self.NAV:
            self.skipTest('TRACK_A_NAV2_PARAMS not set')
        import check_nav2_merge as cm
        self.cm = cm
        self.params = yaml.safe_load(Path(self.NAV).read_text())
        self.snip = yaml.safe_load(cm.SNIPPET.read_text())

    def test_live_params_merge_all_checks_pass(self):
        res = self.cm.checks(self.params, self.cm.merge(self.params, self.snip))
        self.assertTrue(all(g for _, g in res), [n for n, g in res if not g])

    def test_validator_catches_unsafe_snippets(self):
        bad = copy.deepcopy(self.snip)
        bad['local_costmap']['local_costmap']['ros__parameters']['astra_layer']['astra']['inf_is_valid'] = True
        self.assertFalse(all(g for _, g in self.cm.checks(self.params, self.cm.merge(self.params, bad))))
        bad = copy.deepcopy(self.snip)
        bad['local_costmap']['local_costmap']['ros__parameters']['plugins'] = ['astra_layer', 'inflation_layer']
        self.assertFalse(all(g for _, g in self.cm.checks(self.params, self.cm.merge(self.params, bad))))


@unittest.skipUnless(os.environ.get('AMENT_PREFIX_PATH'), 'ROS 2 not sourced')
class RosEndToEnd(unittest.TestCase):
    """Real node + synthetic depth publisher in an isolated, localhost-only ROS domain (never domain 0 or 77)."""
    DOMAIN = '91'

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        for sub in ('scripts', 'tools', 'config/astra_calibration'):
            (cls.root / sub).mkdir(parents=True, exist_ok=True)
        for f in ('atlas_astra_obstacle_core.py', 'atlas_astra_obstacle_scan.py'):
            shutil.copy(ROOT / 'scripts' / f, cls.root / 'scripts' / f)
        os.symlink(ROOT / 'tools/vision3d', cls.root / 'tools/vision3d')
        (cls.root / 'config/astra_obstacles.yaml').write_text(yaml.safe_dump(good_cfg()))
        (cls.root / 'config/vision3d_live.json').write_text(json.dumps({'identity': {'device_serial': SERIAL}}))
        doc = {'device_serial': SERIAL, 'source': 'measured_target', 'independently_validated': True,
               'validation_evidence': 'synthetic test', 'width': 160, 'height': 120,
               'frame_id': 'astra_depth_optical_frame', 'k': K, 'd': [0.0] * 5, 'distortion_model': 'plumb_bob'}
        (cls.root / 'config/astra_calibration/depth_160x120.json').write_text(json.dumps(doc))
        cls.env = dict(os.environ, ROS_DOMAIN_ID=cls.DOMAIN, ROS_LOCALHOST_ONLY='1')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def test_preflight_refuses_real_config(self):
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/atlas_astra_obstacle_scan.py'), '--preflight'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 78, p.stderr)

    def test_preflight_passes_good_config(self):
        p = subprocess.run([sys.executable, str(self.root / 'scripts/atlas_astra_obstacle_scan.py'), '--preflight'],
                           capture_output=True, text=True, timeout=30, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_end_to_end_fresh_blinded_stale_and_camera_loss(self):
        node = subprocess.Popen([sys.executable, str(self.root / 'scripts/atlas_astra_obstacle_scan.py')],
                                env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            os.environ.update(ROS_DOMAIN_ID=self.DOMAIN, ROS_LOCALHOST_ONLY='1')
            import rclpy
            from rclpy.node import Node
            from sensor_msgs.msg import Image, LaserScan
            from std_msgs.msg import String
            rclpy.init()
            n = Node('track_a_test_harness')
            pub = n.create_publisher(Image, '/astra/depth/image_raw', 5)
            scans, status = [], []
            n.create_subscription(LaserScan, '/astra/obstacle_scan', scans.append, 10)
            n.create_subscription(String, '/astra/obstacle_scan_status', lambda m: status.append(json.loads(m.data)), 10)
            scanner = core.ObstacleScanner(good_cfg(), CAL)
            wall = render(scanner, union(plane_x(1.5), plane_z(0.0)))

            def send(arr, age=0.0, seconds=2.0):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    msg = Image(); t = n.get_clock().now().nanoseconds * 1e-9 - age
                    msg.header.stamp.sec = int(t); msg.header.stamp.nanosec = int((t % 1) * 1e9)
                    msg.header.frame_id = 'astra_depth_optical_frame'
                    msg.height, msg.width, msg.encoding, msg.is_bigendian, msg.step = 120, 160, '16UC1', 0, 320
                    msg.data = arr.tobytes()
                    pub.publish(msg)
                    rclpy.spin_once(n, timeout_sec=0.06)

            def idle(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    rclpy.spin_once(n, timeout_sec=0.1)

            idle(3.0)                                   # discovery
            send(wall, seconds=3.0); idle(0.5)
            self.assertGreater(len(scans), 5, 'fresh valid frames must produce scans')
            sc = scans[-1]
            self.assertEqual(sc.header.frame_id, 'base_link')
            self.assertAlmostEqual(sc.ranges[len(sc.ranges) // 2], 1.5, delta=0.03)
            self.assertLessEqual(len(scans), 3.5 * 10 + 2, 'rate cap (10 Hz) respected')
            for label, arr, age in (('BLINDED', np.zeros((120, 160), np.uint16), 0.0), ('STALE', wall, 2.0)):
                before = len(scans)
                send(arr, age=age, seconds=2.0); idle(1.2)
                with self.subTest(label):
                    self.assertEqual(len(scans), before, f'{label}: no scan may be published')
                    self.assertIn(label, [s['state'] for s in status[-3:]])
            before = len(scans)
            idle(2.5)                                   # camera disconnected: no frames at all
            self.assertEqual(len(scans), before)
            self.assertEqual(status[-1]['state'], 'STALE')
            n.destroy_node(); rclpy.shutdown()
        finally:
            node.terminate(); node.wait(timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
