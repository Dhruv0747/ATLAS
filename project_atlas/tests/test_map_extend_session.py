"""Extend-map sessions (owner 2026-11-26): pure helpers + mission-control behaviour with stubs.
The mission-control part needs ROS 2 to import (runs on the Jetson copy); the helper part runs anywhere."""
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_map_extend_session as es  # noqa: E402
try:
    import atlas_mission_control as M
except Exception:  # pragma: no cover - ROS not available
    M = None


def q(yaw):
    return {'qx': 0.0, 'qy': 0.0, 'qz': math.sin(yaw / 2), 'qw': math.cos(yaw / 2)}


class HelperTests(unittest.TestCase):
    def test_start_needs_fresh_verified_lidar_check(self):
        now = 1000.0
        ok = {'state': 'VERIFIED', 'written_unix': now - 1, 'checked_unix': now - 10}
        self.assertIsNone(es.extend_start_refusal(ok, now))
        self.assertIn('LiDAR-verified', es.extend_start_refusal(dict(ok, state='DEGRADED'), now))
        self.assertIn('not running', es.extend_start_refusal(dict(ok, written_unix=now - 40), now))
        self.assertIn('older than', es.extend_start_refusal(dict(ok, checked_unix=now - 120), now))
        self.assertIn('no LiDAR localization check', es.extend_start_refusal(None, now))

    def test_init_maps_slam_frame_into_saved_frame(self):
        """T = P_map * inverse(P_odom): SLAM starts with map == odom, so T(odom pose) must give the saved-map pose."""
        pm = dict({'frame_id': 'map', 'x': 1.0, 'y': 2.0}, **q(math.radians(90)))
        po = dict({'frame_id': 'odom', 'x': 0.5, 'y': -0.2}, **q(math.radians(30)))
        tx, ty, th = es.compose_init(pm, po)
        c, s = math.cos(th), math.sin(th)
        self.assertAlmostEqual(tx + c * 0.5 - s * -0.2, 1.0, places=6)
        self.assertAlmostEqual(ty + s * 0.5 + c * -0.2, 2.0, places=6)
        self.assertAlmostEqual(math.degrees(th), 60.0, places=6)
        with self.assertRaises(ValueError):
            es.compose_init(dict(pm, frame_id='odom'), po)

    def test_request_file(self):
        with tempfile.TemporaryDirectory() as d:
            session = {'id': 'abc123', 'mode': es.EXTEND_MODE,
                       'extend': {'base_map_id': 'm1', 'init': [1, 2, 0.5]}}
            p = es.write_request(Path(d), session, Path('/x/.atlas_candidate_abc123.yaml'), {'x': 3, 'y': 4})
            r = json.loads(p.read_text())
            self.assertEqual(r['session_id'], 'abc123')
            self.assertEqual(r['init'], [1, 2, 0.5])
            self.assertEqual(r['base_map_id'], 'm1')
            self.assertEqual(r['candidate_yaml'], '/x/.atlas_candidate_abc123.yaml')
            self.assertEqual(r['state'], 'pending')
            self.assertTrue(es.is_extend(session))
            self.assertFalse(es.is_extend({'mode': 'manual_teaching'}))
            self.assertFalse(es.is_extend(None))


@unittest.skipIf(M is None, 'atlas_mission_control needs ROS 2')
class MissionControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def node(self, check_state='VERIFIED'):
        n = object.__new__(M.AtlasMissionControl)
        n.mapping_session_file = self.d / 'mapping_session.json'
        n.map_prefix = self.d / 'atlas_latest'
        n.extend_state_dir = self.d / 'map_extend'
        n.localization_check_file = self.d / 'localization_check.json'
        n.localization_check_file.write_text(json.dumps(
            {'state': check_state, 'written_unix': 1000.0, 'checked_unix': 995.0}))
        n.mapping_light = True
        n.calls = []
        rec = lambda name: (lambda *a, **k: n.calls.append(name))
        for name in ('start_mapping_recording', 'pause_mapping_background', 'stop_mapping_recording',
                     'restore_mapping_background', 'begin_map_acceptance_observation', 'set_home',
                     'ensure_nav2_for_acceptance', 'save_localization_seed'):
            setattr(n, name, rec(name))
        n.ensure_mapping_stack = lambda with_nav2=True: n.calls.append('ensure_mapping_stack')
        n.wheel_odom_snapshot = lambda: {'x': 0.0}
        n.startup_stillness = lambda a, b: {'ok': True}
        n.statuses = []
        n.status = lambda t: n.statuses.append(t)
        n.get_logger = lambda: types.SimpleNamespace(info=lambda *_: None, warning=lambda *_: None,
                                                      error=lambda *_: None)
        n.current_pose = lambda: dict({'frame_id': 'map', 'x': 1.0, 'y': 2.0}, **q(0.5))
        n.odom_pose = lambda: dict({'frame_id': 'odom', 'x': 0.2, 'y': 0.1}, **q(0.1))
        n.current_map_id = lambda: 'accepted-map-id'
        n.zero_pub = types.SimpleNamespace(publish=lambda *_: None)
        n.mapping_guard = types.SimpleNamespace(disarm=lambda: None)
        n.cancel_all_nav_goals = lambda: True
        n.accept_saved_map = lambda prefix, session: n.calls.append('accept_saved_map') or 'new-id'
        n.explore_unit = 'atlas-explore.service'
        n.mapping_finishing = False
        n.stable_current_pose = lambda: {'frame_id': 'map', 'x': 5.0, 'y': 6.0}
        return n

    def run_start(self, n, extend):
        with mock.patch.object(M.time, 'time', return_value=1000.0):
            n.start_manual_mapping(extend=extend) if extend else n.start_manual_mapping()

    def run_stop(self, n):
        def fake_run(cmd, **kw):
            n.calls.append(' '.join(cmd[:3]))
            return types.SimpleNamespace(returncode=3 if 'is-active' in cmd else 0, stderr='', stdout='')
        with mock.patch.object(M.subprocess, 'run', side_effect=fake_run):
            n.stop_exploration()

    def test_extend_start_refused_without_verified_lidar(self):
        n = self.node(check_state='DEGRADED')
        with self.assertRaises(RuntimeError) as cm:
            self.run_start(n, extend=True)
        self.assertIn('LiDAR-verified', str(cm.exception))
        self.assertFalse(n.mapping_session_file.exists())
        self.assertNotIn('ensure_mapping_stack', n.calls)

    def test_extend_start_records_init_and_keeps_home(self):
        n = self.node()
        self.run_start(n, extend=True)
        s = json.loads(n.mapping_session_file.read_text())
        self.assertEqual(s['mode'], 'extend_teaching')
        self.assertEqual(s['state'], 'active')
        self.assertEqual(s['extend']['base_map_id'], 'accepted-map-id')
        self.assertEqual(len(s['extend']['init']), 3)
        self.assertNotIn('set_home', n.calls)                # the saved home pose is not overwritten
        self.assertTrue(any('EXTEND MAPPING ACTIVE' in t for t in n.statuses), n.statuses)

    def test_normal_start_unchanged(self):
        n = self.node()
        self.run_start(n, extend=False)
        s = json.loads(n.mapping_session_file.read_text())
        self.assertEqual(s['mode'], 'manual_teaching')
        self.assertNotIn('extend', s)
        self.assertIn('set_home', n.calls)

    def test_extend_stop_never_promotes(self):
        n = self.node()
        self.run_start(n, extend=True)
        n.active_mapping_session = lambda: json.loads(n.mapping_session_file.read_text())
        self.run_stop(n)
        self.assertNotIn('accept_saved_map', n.calls)
        self.assertNotIn('save_localization_seed', n.calls)      # the saved map's seed is not overwritten
        self.assertNotIn('ensure_nav2_for_acceptance', n.calls)
        self.assertIn('ros2 run nav2_map_server', n.calls)      # the piece itself is saved
        reqs = list((self.d / 'map_extend').glob('*.request.json'))
        self.assertEqual(len(reqs), 1)
        r = json.loads(reqs[0].read_text())
        self.assertEqual(r['end_pose_slam'], {'frame_id': 'map', 'x': 5.0, 'y': 6.0})
        self.assertFalse(n.mapping_session_file.exists())
        self.assertTrue(any('EXTEND PIECE SAVED' in t and 'SAVED MAP UNCHANGED' in t for t in n.statuses),
                        n.statuses)

    def test_normal_stop_still_promotes(self):
        n = self.node()
        self.run_start(n, extend=False)
        n.active_mapping_session = lambda: json.loads(n.mapping_session_file.read_text())
        self.run_stop(n)
        self.assertIn('accept_saved_map', n.calls)
        self.assertIn('save_localization_seed', n.calls)


if __name__ == '__main__':
    unittest.main()
