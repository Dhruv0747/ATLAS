"""CHECK MY LOCATION when AMCL has no pose (2026-10-11 Dhruv Room restart).

The live failure: after a reboot the startup verifier left AMCL un-seeded, so /amcl_pose never
published, and the check refused to start with the merged message "SCAN UNAVAILABLE or AMCL
reference unavailable", although the LiDAR, scan-time TF and accepted map were all fine.

These tests pin the corrected contract:
  * every blocking condition has its own code and a stage table;
  * AMCL is an optional comparison: NOT_INITIALIZED / STALE / TF_UNAVAILABLE never block the
    independent LiDAR search, and without AMCL the best answer is LIDAR_ONLY_MATCH, never VERIFIED;
  * ambiguity and thin coverage are reported as such, not as a match;
  * mid-check changes (motion, AMCL appearing) void the result;
  * an old success is kept apart from the current state.
No ROS, network or motion.
"""
import math
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import numpy as np  # noqa: E402,F401  (geometry below needs numpy, as on the Jetson)
import atlas_localization_verify_core as core  # noqa: E402
from atlas_location_check_job import LocationCheckJob, evidence_error  # noqa: E402
import atlas_location_check_ros as adapter  # noqa: E402
from atlas_location_check_ros import Blocked, ManualLocationCheck, compare  # noqa: E402
from test_atlas_localization_verify import ROOM_A, ROOM_B, SYMMETRIC_B, ray_scan, write_map  # noqa: E402

FAKE_TIME = sys.modules.setdefault('rclpy.time', N(Time=N(from_msg=lambda msg: None)))


def zero():
    return N(x=0., y=0., z=0.)


def identity_tf():
    return N(transform=N(translation=zero(), rotation=N(x=0., y=0., z=0., w=1.)))


class FakeNode:
    """The fields ManualLocationCheck reads from the localization monitor node."""

    def __init__(self, now=100., scan_at=99.9, amcl=None, amcl_at=None, ranges=None, frame='laser_frame',
                 missing_tf=()):
        self.clock = now
        self.data_lock = threading.Lock()
        header = N(stamp=N(sec=int(scan_at), nanosec=int(round((scan_at % 1) * 1e9))), frame_id=frame)
        scan = N(header=header, ranges=ranges or [2.] * 360, angle_min=-math.pi, angle_increment=math.pi / 180,
                 range_min=.15, range_max=12.)
        self.scans = [(scan_at, scan)]
        self.amcl = amcl
        self.amcl_at = amcl_at
        self.amcl_stamp = amcl_at
        self.amcl_covariance = [0.] * 36
        self.logic = N(policy=core.VerifyPolicy())
        self.missing_tf = set(missing_tf)
        self.tf = N(lookup_transform=self.lookup)

    def lookup(self, target, source, when):
        if (target, source) in self.missing_tf:
            raise LookupError('%s<-%s not available' % (target, source))
        return identity_tf()

    def get_clock(self):
        return N(now=lambda: N(nanoseconds=int(self.clock * 1e9)))


def make_check(node, latched=True, moving_since=None, cmd=None, missing=(), map_ok=True):
    header = node.scans[-1][1].header
    a = ManualLocationCheck.__new__(ManualLocationCheck)
    a.node = node
    a.lock = threading.RLock()
    a.map_id = 'accepted'
    a.loaded_id = 'accepted' if map_ok else None
    a.motion_epoch = 0
    a.map_epoch = 1
    a.last_motion = moving_since if moving_since is not None else node.clock - 10.
    a.path = Path('/nonexistent')
    a.jobs = LocationCheckJob(clock=lambda: node.clock)
    a.last_block = None
    command = cmd or N(linear=zero(), angular=zero())
    values = {'odom': (node.clock - .05, N(header=header, twist=N(twist=N(linear=zero(), angular=zero())))),
              'imu': (node.clock - .05, N(header=header)),
              'policy': (node.clock - .05, N(data='{"stop_latched": %s}' % ('true' if latched else 'false'))),
              'cmd': (node.clock - .05, command)}
    a.values = {k: v for k, v in values.items() if k not in missing}
    return a


def evidence(check):
    with patch('atlas_location_check_ros.time.monotonic', side_effect=lambda: check.node.clock):
        return check.evidence()[0]


class EvidenceStages(unittest.TestCase):
    def blocked(self, check):
        with self.assertRaises(Blocked) as ctx:
            evidence(check)
        return ctx.exception

    def test_amcl_not_initialized_does_not_block_lidar_search(self):
        e = evidence(make_check(FakeNode(amcl=None)))
        self.assertEqual(e['amcl_status'], 'NOT_INITIALIZED')
        self.assertIsNone(e['amcl_pose'])
        self.assertEqual(e['stages']['amcl']['status'], 'not_available')
        self.assertEqual(e['stages']['scan']['status'], 'ready')
        self.assertEqual(e['stages']['scan_tf']['status'], 'ready')
        self.assertIsNone(evidence_error(e))                      # the job manager accepts it
        LocationCheckJob().start(e)

    def test_amcl_stale_is_reported_not_blocking(self):
        e = evidence(make_check(FakeNode(amcl=(1., 2., 0.), amcl_at=90.)))
        self.assertEqual(e['amcl_status'], 'STALE')
        self.assertIn('exceeds 2.5', e['amcl_reason'])
        self.assertIsNone(e['amcl_pose'])
        self.assertIsNone(evidence_error(e))

    def test_amcl_ok_keeps_full_tf_chain_requirement(self):
        e = evidence(make_check(FakeNode(amcl=(0., 0., 0.), amcl_at=99.9)))
        self.assertEqual(e['amcl_status'], 'OK')
        self.assertTrue(e['tf_chain_consistent'])
        self.assertEqual(e['amcl_pose'], [0., 0., 0.])

    def test_amcl_pose_without_map_odom_tf_degrades_to_lidar_only(self):
        e = evidence(make_check(FakeNode(amcl=(0., 0., 0.), amcl_at=99.9, missing_tf={('map', 'odom')})))
        self.assertEqual(e['amcl_status'], 'TF_UNAVAILABLE')
        self.assertIsNone(e['amcl_pose'])
        self.assertIsNone(evidence_error(e))

    def test_no_scan(self):
        node = FakeNode()
        check = make_check(node)
        node.scans = []
        self.assertEqual(self.blocked(check).code, 'LIDAR_SCAN_UNAVAILABLE')

    def test_stale_scan(self):
        err = self.blocked(make_check(FakeNode(scan_at=97.)))
        self.assertEqual(err.code, 'LIDAR_SCAN_STALE')
        self.assertEqual(err.stages['scan']['status'], 'stale')

    def test_scan_time_tf_missing(self):
        err = self.blocked(make_check(FakeNode(missing_tf={('base_link', 'laser_frame')})))
        self.assertEqual(err.code, 'SCAN_TIME_TF_UNAVAILABLE')
        self.assertEqual(err.stages['scan_tf']['status'], 'missing')

    def test_map_not_ready(self):
        err = self.blocked(make_check(FakeNode(), map_ok=False))
        self.assertEqual(err.code, 'ACCEPTED_MAP_NOT_READY')

    def test_stop_not_latched(self):
        self.assertEqual(self.blocked(make_check(FakeNode(), latched=False)).code, 'STOP_NOT_LATCHED')

    def test_moving(self):
        self.assertEqual(self.blocked(make_check(FakeNode(), moving_since=99.5)).code, 'ROVER_MOVING')

    def test_nonzero_command(self):
        cmd = N(linear=N(x=.2, y=0., z=0.), angular=zero())
        self.assertEqual(self.blocked(make_check(FakeNode(), cmd=cmd)).code, 'MOTOR_COMMAND_ACTIVE')

    def test_missing_scan_sectors(self):
        ranges = [2.] * 180 + [math.inf] * 180
        err = self.blocked(make_check(FakeNode(ranges=ranges)))
        self.assertEqual(err.code, 'INSUFFICIENT_LIDAR_COVERAGE')
        self.assertEqual(err.stages['coverage']['status'], 'invalid')

    def test_missing_odometry(self):
        self.assertEqual(self.blocked(make_check(FakeNode(), missing=('odom',))).code, 'ODOMETRY_UNAVAILABLE')

    def test_future_sensor_stamp_has_its_own_code(self):
        node = FakeNode()
        check = make_check(node)
        at, imu = check.values['imu']
        check.values['imu'] = (at, N(header=N(stamp=N(sec=101, nanosec=0), frame_id='imu')))   # 1 s in the future
        err = self.blocked(check)
        self.assertEqual(err.code, 'SENSOR_TIMESTAMP_INVALID')
        self.assertEqual(err.stages['imu']['status'], 'invalid')

    def test_old_merged_message_is_gone(self):
        src = (ROOT / 'scripts' / 'atlas_location_check_ros.py').read_text()
        self.assertNotIn('SCAN UNAVAILABLE or AMCL reference unavailable', src)


class IndependentMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.map = core.load_map(write_map(cls.tmp.name, ROOM_A + ROOM_B))
        cls.policy = core.VerifyPolicy()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_compare(self, truth, amcl, walls=ROOM_A + ROOM_B, m=None, keep=None):
        amin, inc, ranges = ray_scan(walls, truth)
        if keep is not None:
            ranges = [r if keep(i) else math.inf for i, r in enumerate(ranges)]
        scan = N(ranges=ranges, angle_min=amin, angle_increment=inc, range_min=.15, range_max=12.)
        return compare(m or self.map, scan, (0., 0., 0.), amcl, self.policy, lambda: None)

    def test_lidar_only_match_without_amcl(self):
        truth = (8.0, 1.6, math.radians(-100))
        r = self.run_compare(truth, None)
        self.assertEqual(r['state'], 'LIDAR_ONLY_MATCH', r['reason'])
        self.assertIn('NOT verified', r['reason'])
        self.assertIsNone(r['amcl_pose'])
        self.assertIsNone(r['xy_disagreement_m'])
        self.assertLess(math.hypot(r['lidar_pose']['x'] - truth[0], r['lidar_pose']['y'] - truth[1]), .15)

    def test_never_verified_without_amcl(self):
        for truth in ((8.0, 1.6, math.radians(-100)), (0.8, 1.2, math.radians(77))):
            self.assertNotEqual(self.run_compare(truth, None)['state'], 'VERIFIED')

    def test_ambiguous_room_is_not_a_match(self):
        sym = core.load_map(write_map(self.tmp.name, ROOM_A + SYMMETRIC_B))
        r = self.run_compare((7.5, 1.0, .3), None, walls=ROOM_A + SYMMETRIC_B, m=sym)
        self.assertIn(r['state'], ('AMBIGUOUS', 'UNCERTAIN'))
        self.assertNotEqual(r['state'], 'LIDAR_ONLY_MATCH')

    def test_thin_scan_is_insufficient(self):
        r = self.run_compare((8.0, 1.6, math.radians(-100)), None, keep=lambda i: i % 6 == 0)
        self.assertEqual(r['state'], 'INSUFFICIENT_LIDAR_COVERAGE')

    def test_with_amcl_correct_and_wrong(self):
        truth = (8.0, 1.6, math.radians(-100))
        self.assertEqual(self.run_compare(truth, truth)['state'], 'VERIFIED')
        wrong = self.run_compare(truth, (0.8, 1.2, math.radians(77)))
        self.assertEqual(wrong['state'], 'MISMATCH')
        self.assertGreater(wrong['xy_disagreement_m'], 5)


def good(**over):
    e = dict(scan_age_s=.2, scan_receipt_age_s=.1, odom_age_s=.1, imu_age_s=.1, amcl_status='NOT_INITIALIZED',
             amcl_age_s=None, amcl_pose=None, map_id='m', loaded_map_id='m', stationary_epoch=1, localization_epoch=1,
             scan_stamp=123., stationary=True, stop_latched=True, commands_zero=True, tf_at_scan=True,
             tf_chain_consistent=False, coverage_qualified=True)
    e.update(over)
    return e


class JobLifecycle(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.wall = 1000.
        self.job = LocationCheckJob(clock=lambda: self.now, wall=lambda: self.wall)

    def test_amcl_appearing_mid_check_voids_result(self):
        token = self.job.start(good())
        with self.assertRaises(Exception):
            self.job.checkpoint(token, good(amcl_status='OK', amcl_age_s=.1, amcl_pose=[1., 2., 0.], tf_chain_consistent=True))
        self.assertEqual(self.job.snapshot()['state'], 'STALE')
        self.assertIn('AMCL status changed', self.job.snapshot()['reason'])

    def test_motion_mid_check_voids_result(self):
        token = self.job.start(good())
        with self.assertRaises(Exception):
            self.job.checkpoint(token, good(stationary_epoch=2))
        self.assertEqual(self.job.snapshot()['state'], 'STALE')

    def test_amcl_ok_still_requires_its_evidence(self):
        self.assertIn('amcl_age_s', evidence_error(good(amcl_status='OK')))
        self.assertIn('tf_chain_consistent', evidence_error(good(amcl_status='OK', amcl_age_s=.1)))

    def test_last_success_is_kept_apart_from_current_state(self):
        token = self.job.start(good())
        self.assertTrue(self.job.finish(token, dict(state='LIDAR_ONLY_MATCH', lidar_pose=dict(x=0.2, y=-1.4, yaw_deg=72.),
                                                    best_fit=.99, margin=.12), good()))
        self.wall += 60
        token = self.job.start(good())
        self.job.abort(token, 'STALE', 'ROVER_MOVING: moved')
        self.assertFalse(self.job.finish(token, error='moved'))
        snap = self.job.snapshot()
        self.assertEqual(snap['state'], 'STALE')
        self.assertTrue(snap['last_success']['historical'])
        self.assertEqual(snap['last_success']['state'], 'LIDAR_ONLY_MATCH')
        self.assertAlmostEqual(snap['last_success']['age_s'], 60., places=3)
        self.job.start(good())                                      # slot released after abort

    def test_late_finish_from_old_worker_is_ignored(self):
        old = self.job.start(good())
        self.job.cancel(old)
        self.assertFalse(self.job.finish(old, dict(state='LIDAR_ONLY_MATCH'), good()))
        new = self.job.start(good())
        self.assertFalse(self.job.finish(old, dict(state='VERIFIED'), good()))
        self.assertEqual(self.job.snapshot()['request_id'], new)

    def test_timeout(self):
        token = self.job.start(good())
        self.now += 31
        self.assertFalse(self.job.finish(token, dict(state='LIDAR_ONLY_MATCH'), good()))
        self.assertEqual(self.job.snapshot()['state'], 'TIMED_OUT')


class AdapterLifecycle(unittest.TestCase):
    def test_rejection_is_recorded_for_both_pages(self):
        node = FakeNode(amcl=None)
        node.search_lock = threading.Lock()
        check = make_check(node)
        node.scans = []
        check.last_request = 0.
        written = {}
        check.write_status = lambda: written.update(check.jobs.snapshot(), last_block=check.last_block)
        resp = N(success=None, message=None)
        with patch('atlas_location_check_ros.time.monotonic', side_effect=lambda: node.clock):
            check.start(None, resp)
        self.assertFalse(resp.success)
        self.assertIn('LIDAR_SCAN_UNAVAILABLE', resp.message)
        self.assertEqual(written['last_block']['code'], 'LIDAR_SCAN_UNAVAILABLE')
        self.assertFalse(node.search_lock.locked())                   # never leaks the search mutex

    def test_status_file_carries_last_block(self):
        check = make_check(FakeNode())
        check.last_block = dict(code='STOP_NOT_LATCHED', reason='x', stages={}, at_unix=1.)
        with tempfile.TemporaryDirectory() as d, patch.object(adapter, 'STATE_FILE', Path(d) / 's.json'):
            check.write_status()
            import json
            data = json.loads((Path(d) / 's.json').read_text())
        self.assertEqual(data['last_block']['code'], 'STOP_NOT_LATCHED')
        self.assertFalse(data['navigation_authorized'])

    def test_motion_during_run_is_stale_not_uncertain(self):
        node = FakeNode(amcl=None)
        node.search_lock = threading.Lock()
        node.map = None
        check = make_check(node)
        check.write_status = lambda: None
        e = evidence(check)
        token = check.jobs.start(e)
        node.search_lock.acquire()
        def moved(*a, **k):
            raise Blocked('ROVER_MOVING', 'Motion seen in the last 2 s')
        with patch.object(adapter, 'compare', side_effect=moved):
            check.run(token, e, node.scans[-1][1])
        snap = check.jobs.snapshot()
        self.assertEqual(snap['state'], 'STALE')
        self.assertIn('ROVER_MOVING', snap['reason'])
        self.assertFalse(node.search_lock.locked())


if __name__ == '__main__':
    unittest.main()
