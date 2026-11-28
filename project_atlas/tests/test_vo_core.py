"""Step 7 shadow visual odometry core (scripts/atlas_vo_core.py): tracker, states, evaluator. 2026-11-23."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

try:                                            # the ICP cores need scipy (cKDTree); GitHub CI installs numpy only
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:                             # CI without scipy: these tests are reported SKIPPED, never passed
    HAVE_SCIPY = False
NEEDS_SCIPY = unittest.skipUnless(HAVE_SCIPY, 'scipy not installed (ICP / shadow VO cores); run on the Jetson')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
if HAVE_SCIPY:
    import atlas_vo_core as vo  # noqa: E402

CFG = vo.VoConfig() if HAVE_SCIPY else None
# a box seen from its side face and a slanted cabinet: constrains every planar direction
ROOM = [((2.0, -2.0), (2.0, 2.0)), ((2.0, 2.0), (-1.0, 2.0)), ((1.0, 0.3), (1.0, 0.7)), ((1.0, 0.3), (1.4, 0.3)),
        ((1.5, -0.6), (2.0, -1.0))]
# only walls facing ATLAS (normals all along x): sideways motion is unobservable
CORRIDOR = [((2.0, -2.0), (2.0, 2.0)), ((1.2, -0.3), (1.2, 0.1))]


def room_scan(pose, rng=None, corridor=False):
    """Synthetic Astra obstacle scan (+-30 deg, 0.5 deg bins) of a room corner + a box, seen from pose."""
    x0, y0, th = pose
    walls = CORRIDOR if corridor else ROOM
    amin, inc, n = -0.52, 0.0087, 120
    ranges = []
    for i in range(n):
        a = th + amin + i * inc
        dx, dy = math.cos(a), math.sin(a)
        best = math.inf
        for (ax, ay), (bx, by) in walls:
            ex, ey = bx - ax, by - ay
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            t = ((ax - x0) * ey - (ay - y0) * ex) / den
            u = ((ax - x0) * dy - (ay - y0) * dx) / den
            if t > 0 and 0 <= u <= 1:
                best = min(best, t)
        if rng is not None and math.isfinite(best):
            best += rng.normal(0, 0.005)
        ranges.append(best if best <= 3.0 else math.inf)
    return ranges, amin, inc


def feed(tr, poses, rate_hz=10.0, t0=100.0, noise=None):
    t = t0
    for p in poses:
        r, amin, inc = room_scan(p, noise)
        tr.update(vo.scan_points(r, amin, inc, CFG), t - 0.05, t)
        t += 1.0 / rate_hz
    return t


@NEEDS_SCIPY
class TrackerTests(unittest.TestCase):
    def test_parked_holds_still_and_is_good(self):
        tr = vo.VoTracker()
        t = feed(tr, [(0, 0, 0)] * 60, noise=np.random.default_rng(1))
        s = tr.status(t - 0.1)
        self.assertEqual(s['state'], 'GOOD', s)
        self.assertLess(math.hypot(s['pose'][0], s['pose'][1]), 0.02)
        self.assertLess(abs(s['pose'][2]), 1.0)
        self.assertGreaterEqual(s['rate_hz'], 8.0)

    def test_tracks_a_gentle_left_arc(self):
        tr = vo.VoTracker()
        poses, x, y, th = [], 0.0, 0.0, 0.0
        poses += [(0.0, 0.0, 0.0)] * vo.WARMUP_SCANS      # parked at start: warm-up before the first keyframe
        for _ in range(40):                   # 0.10 m/s, 0.15 rad/s at 10 Hz for 4 s -> ~34 deg, 0.4 m
            poses.append((x, y, th))
            x += 0.01 * math.cos(th); y += 0.01 * math.sin(th); th += 0.015
        t = feed(tr, poses, noise=np.random.default_rng(2))
        s = tr.status(t - 0.1)
        last = poses[-1]
        self.assertAlmostEqual(s['pose'][2], math.degrees(last[2]), delta=2.0)
        self.assertAlmostEqual(math.hypot(s['pose'][0], s['pose'][1]), math.hypot(last[0], last[1]), delta=0.05)
        self.assertLess(math.hypot(s['pose'][0] - last[0], s['pose'][1] - last[1]), 0.06)

    def test_corridor_end_is_degraded_not_good(self):
        tr = vo.VoTracker()
        t = 100.0
        for _ in range(30):
            r, amin, inc = room_scan((0, 0, 0), corridor=True)
            tr.update(vo.scan_points(r, amin, inc, CFG), t - 0.05, t)
            t += 0.1
        s = tr.status(t - 0.1)
        self.assertEqual(s['state'], 'DEGRADED', s)
        self.assertLess(s['geometry'], 0.2)

    def test_bad_scans_while_parked_do_not_move_the_pose(self):
        """2026-11-23 16:02 live FAIL: parked, VO jumped 14 cm / 4.8 deg exactly when scans were rejected (the
        rejected scan became the new keyframe). A person in view, a garbage scan, or a burst must not move it."""
        rng = np.random.default_rng(3)
        tr, t = vo.VoTracker(), 100.0

        def step(r):
            nonlocal t
            tr.update(vo.scan_points(r, -0.52, 0.0087, CFG), t - 0.05, t)
            t += 0.2
        good = lambda: room_scan((0, 0, 0), rng)[0]
        for _ in range(20):
            step(good())
        for k in range(40):
            r = good()
            if k in (5, 17, 18):                       # garbage scans (also two in a row)
                r = list(rng.uniform(0.4, 3.0, len(r)))
            if 25 <= k < 30:                           # a person standing 0.7 m ahead, covering a third of the view
                r = [0.7 + rng.normal(0, 0.01) if 40 <= i < 80 else v for i, v in enumerate(r)]
            step(r)
        for _ in range(15):
            step(good())
        s = tr.status(t - 0.1)
        self.assertLess(math.hypot(s['pose'][0], s['pose'][1]), 0.02, s)
        self.assertLess(abs(s['pose'][2]), 1.0, s)

    def test_partial_scan_never_becomes_the_keyframe(self):
        """2026-11-23 live capture: a partial first scan (52 of ~93 points) as keyframe biased every parked match by
        2.5-5 cm / 1-2 deg. Here: start on a partial scan, and partial scans keep arriving now and then."""
        rng = np.random.default_rng(5)
        tr, t = vo.VoTracker(), 100.0
        for k in range(150):
            r = room_scan((0, 0, 0), rng)[0]
            if k < 4:                                  # start-up ramp: the view fills in over 4 scans
                r = [math.inf if i < 60 - 15 * k else v for i, v in enumerate(r)]
            elif k % 37 == 0:                          # left half of the view missing
                r = [math.inf if i < 60 else v for i, v in enumerate(r)]
            tr.update(vo.scan_points(r, -0.52, 0.0087, CFG), t - 0.05, t)
            t += 0.15
        s = tr.status(t - 0.1)
        self.assertLess(math.hypot(s['pose'][0], s['pose'][1]), 0.02, s)
        self.assertLess(abs(s['pose'][2]), 1.0, s)
        self.assertGreaterEqual(len(tr.odo.key_points), 100)

    def test_keyframe_reset_reads_degraded_for_a_while(self):
        tr, t = vo.VoTracker(), 100.0
        r0 = room_scan((0, 0, 0))[0]
        for _ in range(20):
            tr.update(vo.scan_points(r0, -0.52, 0.0087, CFG), t - 0.05, t); t += 0.1
        rng = np.random.default_rng(4)
        for _ in range(vo.RESET_AFTER_REJECTS):       # tracking broken: continuity lost, keyframe reset
            tr.update(vo.scan_points(list(rng.uniform(0.4, 3.0, 120)), -0.52, 0.0087, CFG), t - 0.05, t); t += 0.1
        for _ in range(5):
            tr.update(vo.scan_points(r0, -0.52, 0.0087, CFG), t - 0.05, t); t += 0.1
        s = tr.status(t - 0.1)
        self.assertEqual(s['state'], 'DEGRADED', s)
        self.assertGreaterEqual(s['resets'], 1)          # garbage keyframe, then back to a good one
        for _ in range(30):
            tr.update(vo.scan_points(r0, -0.52, 0.0087, CFG), t - 0.05, t); t += 0.1
        self.assertEqual(tr.status(t - 0.1)['state'], 'GOOD')

    def test_lost_when_no_scans(self):
        tr = vo.VoTracker()
        t = feed(tr, [(0, 0, 0)] * 20)
        self.assertEqual(tr.status(t + 3.0)['state'], 'LOST')
        self.assertEqual(vo.VoTracker().status(0.0)['state'], 'LOST')

    def test_one_flat_wall_is_degraded(self):
        pts = np.c_[np.full(80, 2.0), np.linspace(-1, 1, 80)]
        tr = vo.VoTracker()
        for i in range(30):
            tr.update(pts, 100 + i * 0.1 - 0.05, 100 + i * 0.1)
        self.assertEqual(tr.status(102.95)['state'], 'DEGRADED')
        self.assertLess(tr.status(102.95)['geometry'], 0.05)


@NEEDS_SCIPY
class ClassifyTests(unittest.TestCase):
    def test_states(self):
        self.assertEqual(vo.classify(10, 0.1, 0.9, CFG), 'GOOD')
        self.assertEqual(vo.classify(10, 0.8, 0.9, CFG), 'DEGRADED')
        self.assertEqual(vo.classify(2, 0.1, 0.9, CFG), 'DEGRADED')
        self.assertEqual(vo.classify(10, 0.1, 0.2, CFG), 'DEGRADED')
        self.assertEqual(vo.classify(10, 2.0, 0.9, CFG), 'LOST')
        self.assertEqual(vo.classify(0.5, 0.1, 0.9, CFG), 'LOST')
        self.assertEqual(vo.classify(10, None, 0.9, CFG), 'LOST')


def samples(n=40, **kw):
    base = {'state': 'GOOD', 'rate_hz': 9.5, 'age_s': 0.12, 'pose': [0.001, 0.0, 0.1], 'cpu_pct': 6.0,
            'shadow': True, 'domain': 77}
    base.update(kw)
    return [dict(base) for _ in range(n)]


ARC_L = {'vo_yaw_deg': 24.0, 'icp_yaw_deg': 26.0, 'vo_dist_m': 0.27, 'icp_dist_m': 0.29, 'state': 'GOOD'}
ARC_R = {'vo_yaw_deg': -23.0, 'icp_yaw_deg': -25.5, 'vo_dist_m': 0.28, 'icp_dist_m': 0.30, 'state': 'GOOD'}


@NEEDS_SCIPY
class Step7Tests(unittest.TestCase):
    def test_pass(self):
        r = vo.evaluate_step7(samples(), [0.0] * 20, True, [ARC_L, ARC_R], 'turn_check_x.json', 0.1)
        self.assertEqual(r['verdict'], 'PASS', r)

    def test_needs_motion_without_turn_check(self):
        r = vo.evaluate_step7(samples(), [0.0] * 20, True, [], None, None)
        self.assertEqual(r['verdict'], 'NEEDS MOTION')

    def test_old_turn_check_needs_motion(self):
        r = vo.evaluate_step7(samples(), [0.0] * 20, True, [ARC_L, ARC_R], 'old.json', 30.0)
        self.assertEqual(r['verdict'], 'NEEDS MOTION')
        self.assertTrue(r['notes'])

    def test_disagreement_is_not_usable(self):
        bad = dict(ARC_L, vo_yaw_deg=10.0)
        r = vo.evaluate_step7(samples(), [0.0] * 20, True, [bad, ARC_R], 'x.json', 0.1)
        self.assertEqual(r['verdict'], 'NOT USABLE')
        self.assertIn('motion_heading_agrees', r['failed'])

    def test_lost_in_motion_is_not_usable(self):
        r = vo.evaluate_step7(samples(), [0.0] * 20, True, [ARC_L, dict(ARC_R, state='LOST')], 'x.json', 0.1)
        self.assertEqual(r['verdict'], 'NOT USABLE')

    def test_fail_cases(self):
        cases = {
            'vo_running': (samples(5), [0.0], True),
            'shadow_only': (samples(), [0.0], False),
            'atlas_parked': (samples(), [0.0, 0.08], True),
            'rate_ok': (samples(rate_hz=2.0), [0.0], True),
            'age_ok': (samples(age_s=0.9), [0.0], True),
            'mostly_good_parked': (samples(state='DEGRADED'), [0.0], True),
            'cpu_within_budget': (samples(cpu_pct=60.0), [0.0], True),
        }
        for key, (s, w, iso) in cases.items():
            r = vo.evaluate_step7(s, w, iso, [ARC_L, ARC_R], 'x.json', 0.1)
            self.assertEqual(r['verdict'], 'FAIL', key)
            self.assertIn(key, r['failed'], key)
        drift = samples(20) + samples(20, pose=[0.06, 0.0, 0.1])
        r = vo.evaluate_step7(drift, [0.0], True, [], None, None)
        self.assertIn('parked_drift_ok', r['failed'])
        wrong_domain = samples(domain=0)
        self.assertIn('shadow_only', vo.evaluate_step7(wrong_domain, [0.0], True, [], None, None)['failed'])

    def test_isolation_texts(self):
        ekf = (ROOT / 'config' / 'atlas_ekf.yaml').read_text(encoding='utf-8')
        nav2 = (ROOT / 'config' / 'nav2_params.yaml').read_text(encoding='utf-8')
        bridge = (ROOT / 'config' / 'astra_obstacles_bridge.yaml').read_text(encoding='utf-8')
        self.assertTrue(vo.isolation_texts_ok([ekf], nav2, bridge))       # the repo today: VO feeds nothing
        self.assertFalse(vo.isolation_texts_ok([ekf + '\n    odom2: /astra/vo/odom\n'], nav2, bridge))
        self.assertFalse(vo.isolation_texts_ok([ekf], nav2, bridge + '\n  /astra/vo/odom:\n'))

    def test_arc_compare(self):
        a = vo.arc_compare([0, 0, 170.0], [0.2, 0.1, -170.0], (1, 1, 10.0), (1.3, 1.0, 30.0))
        self.assertEqual(a['vo_yaw_deg'], 20.0)
        self.assertEqual(a['icp_yaw_deg'], 20.0)
        self.assertAlmostEqual(a['vo_dist_m'], 0.224, places=3)
        self.assertEqual(a['icp_dist_m'], 0.3)
        self.assertIsNone(vo.arc_compare(None, [0, 0, 0], (0, 0, 0), (0, 0, 0)))


@NEEDS_SCIPY
class TurnCheckVoHookTests(unittest.TestCase):
    """turn_ground_check.py only READS the VO status file and records VO vs ICP per arc (never a verdict input)."""

    def setUp(self):
        import json, tempfile, time
        sys.path.insert(0, str(ROOT / 'tools' / 'drive'))
        sys.path.insert(0, str(ROOT / 'tools' / 'perception'))
        import turn_ground_check as tgc
        import vo_shadow_check as vsc
        self.tgc, self.vsc, self.json, self.time = tgc, vsc, json, time
        self.dir = Path(tempfile.mkdtemp())
        self.f = self.dir / 'vo_shadow_status.json'

    def status(self, pose, state='GOOD', age=0.0):
        self.f.write_text(self.json.dumps({'pose': pose, 'state': state, 'wall_time': self.time.time() - age}))

    def test_arc_record(self):
        self.status([0.0, 0.0, 5.0])
        v0 = self.tgc.vo_shadow_pose(self.f)
        self.status([0.25, 0.10, 29.0])
        r = self.tgc.vo_arc(v0, ((1.0, 1.0), 90.0), ((0.9, 1.27), 115.0), path=self.f)
        self.assertEqual(r['vo_yaw_deg'], 24.0)
        self.assertEqual(r['icp_yaw_deg'], 25.0)
        self.assertAlmostEqual(r['icp_dist_m'], 0.288, places=3)
        self.assertEqual((r['state'], r['state_start']), ('GOOD', 'GOOD'))

    def test_stale_or_missing_vo_records_nothing(self):
        self.assertIsNone(self.tgc.vo_shadow_pose(self.dir / 'missing.json'))
        self.status([0, 0, 0], age=5.0)
        self.assertIsNone(self.tgc.vo_shadow_pose(self.f))
        self.status([0, 0, 0])
        v0 = self.tgc.vo_shadow_pose(self.f)
        self.assertIsNone(self.tgc.vo_arc(v0, (None, None), ((0, 0), 0.0), path=self.f))

    def test_step7_reads_newest_turn_check_with_vo(self):
        old = self.dir / 'turn_check_20261120_100000.json'
        old.write_text(self.json.dumps({'arcs': [{'vo': ARC_L}, {'vo': ARC_R}]}))
        new = self.dir / 'imu_workload_check_20261123_100000.json'
        new.write_text(self.json.dumps({'arcs': [{'vo': None}, {}]}))           # newer, but recorded no VO
        arcs, name, age = self.vsc.newest_vo_arcs(self.time.time(), state=self.dir)
        self.assertEqual(name, old.name)
        self.assertEqual(len(arcs), 2)
        self.assertLess(age, 1.0)
        self.assertEqual(self.vsc.newest_vo_arcs(self.time.time(), state=self.dir / 'none')[0], [])


if __name__ == '__main__':
    unittest.main()
