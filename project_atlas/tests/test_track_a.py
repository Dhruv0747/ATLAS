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
# Recorded on ATLAS 2026-11-06 from the real driver (serial 17122120830, 160x120 depth): /astra/depth/camera_info
DRIVER_K = [142.586, 0.0, 79.5, 0.0, 142.586, 59.5, 0.0, 0.0, 1.0]
DRIVER_IR_640_K = [math.inf, 0.0, 319.5, 0.0, math.inf, 239.5, 0.0, 0.0, 1.0]     # IR stream: fx = inf
FRAME = 'astra_depth_optical_frame'


def good_cfg(**mount):
    cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
    cfg['mount'].update({'x_m': 0.20, 'y_m': 0.0, 'z_m': 0.30, 'pitch_deg': 0.0})
    cfg['mount'].update(mount)
    cfg['obstacle_scan']['max_height_m'] = 0.50
    return cfg


def render(scanner, surface, noise_seed=None):
    """Synthetic 16UC1 depth (mm) by ray-casting each pixel against surface(origin, dirs) -> distance along ray.
    noise_seed: add structured-light depth noise sigma = 1.5e-3 * z^2 m (conservative Kinect/Astra-class model)."""
    rays = np.c_[scanner.rays, np.ones(len(scanner.rays))]          # optical-frame direction with z=1
    dirs_base = rays @ scanner.r.T                                   # direction per unit optical z, in base_link
    t = surface(scanner.t, dirs_base)                                # optical z (m) per pixel, nan = miss
    t = np.where(np.isfinite(t) & (t > 0), t, 0.0)
    if noise_seed is not None:
        t = t + np.random.default_rng(noise_seed).normal(0.0, 1.0, t.shape) * 1.5e-3 * t ** 2 * (t > 0)
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
    def test_shipped_config_values_and_provenance(self):
        cfg = core.validate_config(yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text()))
        m, sc = cfg['mount'], cfg['obstacle_scan']
        self.assertEqual((m['x_m'], m['y_m'], m['z_m'], m['pitch_deg'], m['yaw_deg']), (0.13, 0.0, 0.30, 0.0, 0.0))
        self.assertEqual((sc['range_min_m'], sc['range_max_m'], sc['max_height_m']), (0.35, 3.0, 1.0))
        text = (ROOT / 'config/astra_obstacles.yaml').read_text()
        for marker in ('CANDIDATE (derived, not directly measured)', 'OWNER RE-LEVELLED', 'PRIOR', 'ENGINEERING BOUND, NOT a rover height'):
            self.assertIn(marker, text)

    def test_null_mount_or_height_refused(self):
        for path in (('mount', 'x_m'), ('mount', 'y_m'), ('mount', 'z_m'), ('mount', 'pitch_deg'),
                     ('obstacle_scan', 'max_height_m')):
            cfg = good_cfg(); cfg[path[0]][path[1]] = None
            with self.subTest(path=path), self.assertRaises(core.ConfigError):
                core.validate_config(cfg)

    def test_no_phantom_floor_with_pitch_error_and_noise(self):
        # Configured mount = shipped (pitch 0.8 down). Truth may differ: phone vs depth hint disagree by 2.6 deg.
        s = core.ObstacleScanner(good_cfg(x_m=0.13, pitch_deg=0.8), CAL)
        for true_pitch in (0.8, -1.8, 1.8, 2.3):     # exact; depth hint (1.8 up); 1.0 and 1.5 deg further down
            true = core.ObstacleScanner(good_cfg(x_m=0.13, pitch_deg=true_pitch), CAL)
            for seed in range(5):
                _, st = s.scan(render(true, plane_z(0.0), noise_seed=seed))
                with self.subTest(true_pitch=true_pitch, seed=seed):
                    self.assertEqual(st['obstacle_bins'], 0, 'floor must never become a phantom obstacle')

    def test_pitch_disagreement_detection_limits(self):
        s = core.ObstacleScanner(good_cfg(x_m=0.13, pitch_deg=0.8), CAL)
        mid = s.nbins // 2
        # If the phone pitch is right (measured sweep, 10 noise seeds): 10 cm objects are seen out to 2.4 m,
        # 15 cm objects across the whole 0.35-3.0 m range (the range-growing floor cut is 9.2 cm at 3 m).
        for x, h in ((0.6, 0.10), (1.0, 0.10), (2.0, 0.10), (2.4, 0.10), (2.8, 0.15), (2.95, 0.15)):
            for seed in range(3):
                r, _ = s.scan(render(s, union(plane_z(0.0), box(x, x + 0.3, -0.2, 0.2, h)), noise_seed=seed))
                with self.subTest(box_at=x, height=h, seed=seed):
                    self.assertAlmostEqual(float(r[mid]), x, delta=0.03 + 0.01 * x)
        # Worst recorded case (camera really 1.8 deg UP): points are computed too low. Documented limit:
        # 15 cm objects still seen at 1.0 m; 10 cm objects missed at >= 1.0 m until the floor-plane check (G4).
        true = core.ObstacleScanner(good_cfg(x_m=0.13, pitch_deg=-1.8), CAL)
        near, _ = s.scan(render(true, union(plane_z(0.0), box(1.0, 1.3, -0.2, 0.2, 0.15))))
        far, _ = s.scan(render(true, union(plane_z(0.0), box(2.0, 2.3, -0.2, 0.2, 0.10))))
        self.assertTrue(np.isfinite(near[mid]), '15 cm box at 1.0 m detected even in the worst pitch case')
        self.assertFalse(np.isfinite(far[mid]), 'documented G4 risk: 10 cm box at 2.0 m missed if pitch is 1.8 up')

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


class RuntimeCalibration(unittest.TestCase):
    """Intrinsics come only from the driver's runtime CameraInfo (FACTORY / driver-supplied calibration)."""
    def ok(self, **kw):
        a = dict(width=160, height=120, frame_id=FRAME, k=DRIVER_K, d=[0.0] * 5, distortion_model='plumb_bob')
        a.update(kw)
        return core.validate_camera_info(**a)

    def test_recorded_driver_camera_info_accepted(self):
        cal = self.ok()
        self.assertEqual(cal['source'], 'FACTORY_DRIVER_CAMERAINFO')
        self.assertTrue(cal['nominal'], 'centre principal point + zero distortion is flagged as the nominal model')
        self.assertFalse(self.ok(k=[143.2, 0, 80.3, 0, 143.0, 60.1, 0, 0, 1], d=[0.01, -0.02, 0, 0, 0])['nominal'])

    def test_invalid_camera_info_rejected(self):
        nan = float('nan')
        for change in ({'k': DRIVER_IR_640_K},                              # what the IR stream publishes (fx inf)
                       {'k': [nan] * 9}, {'d': [nan] * 5},                  # device stored params read all-NaN
                       {'k': [0.0] * 9}, {'k': DRIVER_K[:8]}, {'k': 'abc'},
                       {'width': 640, 'height': 480}, {'frame_id': 'astra_ir_optical_frame'},
                       {'k': [300.0, 0, 79.5, 0, 300.0, 59.5, 0, 0, 1]},      # fx implies ~30 deg HFOV
                       {'k': [142.6, 0, 79.5, 0, 120.0, 59.5, 0, 0, 1]},      # fx/fy mismatch
                       {'k': [142.6, 0, 20.0, 0, 142.6, 59.5, 0, 0, 1]},      # principal point far off-centre
                       {'k': [142.6, 3.0, 79.5, 0, 142.6, 59.5, 0, 0, 1]},    # skew
                       {'d': [5.0, 0, 0, 0, 0]}, {'distortion_model': 'equidistant'}, {'d': [0.0] * 4}):
            with self.subTest(change=change), self.assertRaises(core.CalibrationError):
                self.ok(**change)

    def test_scanner_refuses_without_calibration(self):
        s = core.ObstacleScanner(good_cfg())
        with self.assertRaises(ValueError):
            s.scan(np.zeros((120, 160), np.uint16))
        s.set_calibration(self.ok())
        s.scan(np.zeros((120, 160), np.uint16))
        s.clear_calibration()
        with self.assertRaises(ValueError):
            s.scan(np.zeros((120, 160), np.uint16))

    def test_driver_intrinsics_vs_synthetic_geometry(self):
        s = core.ObstacleScanner(good_cfg(), self.ok())
        r, _ = s.scan(render(s, union(plane_x(1.5), plane_z(0.0))))
        self.assertAlmostEqual(float(r[s.nbins // 2]), 1.5, delta=0.02)


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
        bad = copy.deepcopy(self.snip)        # a currency check would let an Astra outage stall LiDAR navigation
        bad['local_costmap']['local_costmap']['ros__parameters']['astra_layer']['astra']['expected_update_rate'] = 0.5
        self.assertFalse(all(g for _, g in self.cm.checks(self.params, self.cm.merge(self.params, bad))))


class BridgeInterlock(unittest.TestCase):
    """The domain-0 bridge may only start while the rover is verifiably parked (join spike ~100 % CPU)."""
    def setUp(self):
        import atlas_astra_bridge_parked_check as pc
        self.pc = pc
        self.st = {'ros': {'cmd_vel': {'value': {'lin': 0.0, 'ang': 0.0}, 'age': 0.1},
                           'motor_speed': {'value': 0.0, 'age': 0.2}, 'odom': {'value': {'vx': 1e-110, 'wz': -1e-236}, 'age': 0.1},
                           'motion_state': {'value': 'quiet', 'age': 335.0}}}   # camera scene motion: ignored

    def test_parked_allows_start(self):
        self.assertEqual(self.pc.parked(self.st), [])

    def test_moving_unknown_or_stale_blocks_start(self):
        for path, val in ((('cmd_vel', 'value'), {'lin': 0.1, 'ang': 0.0}), (('cmd_vel', 'value'), {'lin': 0.0, 'ang': -0.2}),
                          (('motor_speed', 'value'), 0.05), (('odom', 'value'), {'vx': 0.05, 'wz': 0.0}),
                          (('odom', 'value'), {'vx': 0.0, 'wz': 0.1}), (('odom', 'value'), {}),
                          (('cmd_vel', 'age'), 5.0), (('odom', 'age'), None), (('motor_speed', 'age'), 3.0),
                          (('cmd_vel', 'value'), {})):
            st = copy.deepcopy(self.st); st['ros'][path[0]][path[1]] = val
            with self.subTest(path=path, val=val):
                self.assertTrue(self.pc.parked(st))
        st = copy.deepcopy(self.st); del st['ros']['odom']
        self.assertTrue(self.pc.parked(st))


@unittest.skipUnless(os.environ.get('AMENT_PREFIX_PATH'), 'ROS 2 not sourced')
class RosEndToEnd(unittest.TestCase):
    """Real node + synthetic depth publisher in an isolated, localhost-only ROS domain (never domain 0 or 77)."""
    DOMAIN = '91'

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        for sub in ('scripts', 'config'):
            (cls.root / sub).mkdir(parents=True, exist_ok=True)
        for f in ('atlas_astra_obstacle_core.py', 'atlas_astra_obstacle_scan.py'):
            shutil.copy(ROOT / 'scripts' / f, cls.root / 'scripts' / f)
        (cls.root / 'config/astra_obstacles.yaml').write_text(yaml.safe_dump(good_cfg()))   # no calibration file
        cls.bad = Path(tempfile.mkdtemp())
        shutil.copytree(cls.root / 'scripts', cls.bad / 'scripts'); (cls.bad / 'config').mkdir()
        bad = good_cfg(); bad['mount']['x_m'] = None
        (cls.bad / 'config/astra_obstacles.yaml').write_text(yaml.safe_dump(bad))
        cls.env = dict(os.environ, ROS_DOMAIN_ID=cls.DOMAIN, ROS_LOCALHOST_ONLY='1')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root); shutil.rmtree(cls.bad)

    def test_preflight_shipped_config_passes_without_calibration_file(self):
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/atlas_astra_obstacle_scan.py'), '--preflight'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_preflight_refuses_incomplete_mount(self):
        p = subprocess.run([sys.executable, str(self.bad / 'scripts/atlas_astra_obstacle_scan.py'), '--preflight'],
                           capture_output=True, text=True, timeout=30, env=self.env)
        self.assertEqual(p.returncode, 78, p.stderr)

    def test_preflight_passes_good_config(self):
        p = subprocess.run([sys.executable, str(self.root / 'scripts/atlas_astra_obstacle_scan.py'), '--preflight'],
                           capture_output=True, text=True, timeout=30, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_end_to_end_calibration_fresh_blinded_stale_and_camera_loss(self):
        node = subprocess.Popen([sys.executable, str(self.root / 'scripts/atlas_astra_obstacle_scan.py')],
                                env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            os.environ.update(ROS_DOMAIN_ID=self.DOMAIN, ROS_LOCALHOST_ONLY='1')
            import rclpy
            from rclpy.node import Node
            from sensor_msgs.msg import CameraInfo, Image, LaserScan
            from std_msgs.msg import String
            rclpy.init()
            n = Node('track_a_test_harness')
            pub = n.create_publisher(Image, '/astra/depth/image_raw', 5)
            ipub = n.create_publisher(CameraInfo, '/astra/depth/camera_info', 5)
            info = {'k': DRIVER_K, 'd': [0.0] * 5}
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
                    if info is not None:
                        ci = CameraInfo(); ci.header = msg.header; ci.width, ci.height = 160, 120
                        ci.k, ci.d, ci.distortion_model = info['k'], info['d'], 'plumb_bob'
                        ipub.publish(ci)
                    rclpy.spin_once(n, timeout_sec=0.06)

            def idle(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    rclpy.spin_once(n, timeout_sec=0.1)

            idle(3.0)                                   # discovery
            saved, info = info, None                    # depth frames but no CameraInfo yet
            send(wall, seconds=2.0); idle(1.2)
            self.assertEqual(len(scans), 0, 'no scans before a validated CameraInfo')
            self.assertEqual(status[-1]['calibration'], 'NO_CALIBRATION')
            info = saved
            send(wall, seconds=3.0); idle(0.5)
            self.assertGreater(len(scans), 5, 'fresh valid frames must produce scans')
            sc = scans[-1]
            self.assertEqual(sc.header.frame_id, 'base_link')
            self.assertAlmostEqual(sc.ranges[len(sc.ranges) // 2], 1.5, delta=0.03)
            self.assertLessEqual(len(scans), 3.5 * 10 + 2, 'rate cap (10 Hz) respected')
            ok = [s for s in status if s.get('calibration') == 'OK'][-1]
            self.assertEqual((ok['calibration_source'], ok['fx'], ok['cx']), ('FACTORY_DRIVER_CAMERAINFO', 142.586, 79.5))
            before = len(scans)                         # CameraInfo turns invalid mid-run (NaN, as the device params)
            info = {'k': [float('nan')] * 9, 'd': [0.0] * 5}
            send(wall, seconds=2.0); idle(1.2)
            self.assertLessEqual(len(scans), before + 1, 'invalid CameraInfo stops publishing')
            self.assertEqual(status[-1]['calibration'], 'BAD_CALIBRATION')
            info = {'k': DRIVER_K, 'd': [0.0] * 5}       # recovers once a valid CameraInfo returns
            before = len(scans)
            send(wall, seconds=2.0); idle(0.5)
            self.assertGreater(len(scans), before + 5, 'recovers after a valid CameraInfo')
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
            self.assertTrue(all(math.isfinite(r) or r == math.inf for sc in scans for r in sc.ranges),
                            'ranges are finite or +inf only (never NaN / -inf)')
            n.destroy_node(); rclpy.shutdown()
        finally:
            node.terminate(); node.wait(timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
