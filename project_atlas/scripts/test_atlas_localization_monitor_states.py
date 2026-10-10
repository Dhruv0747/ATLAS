"""Monitor state machine edge cases (no ROS, no motion).

Covers the 2026-10-10 defects: state stuck at MOVING after a stop, stale
results applied after a move/stop during a check, stale scans/odometry/AMCL,
unsynchronised worker writes, and the 30 s + search-time recheck interval.
"""
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest

import atlas_localization_monitor as mon
from atlas_localization_monitor import MonitorLogic

OK = {'state': 'VERIFIED', 'reason': 'test', 'amcl_fit': 0.97}
LOST = {'state': 'LOST', 'reason': 'test', 'recovery_pose': {'x': 3.9, 'y': -0.6, 'yaw_deg': 157.0}}
POSE = (1.0, 2.0, 0.5)


def drive_then_stop(logic, t_stop=10.0):
    for i in range(int(t_stop * 10)):
        logic.on_motion(i / 10.0, True)
    logic.on_motion(t_stop, False)


def fresh(logic, now):
    logic.on_motion(now, False)          # odom keeps arriving at 10 Hz in reality
    logic.on_inputs(now, 0.1, 0.5)


class StateMachineTests(unittest.TestCase):
    def test_stop_shows_settling_then_verifying_then_verified_within_5s(self):
        logic = MonitorLogic()
        drive_then_stop(logic, 10.0)
        self.assertEqual(logic.state['state'], 'PARKED_SETTLING')     # no longer "MOVING"
        fresh(logic, 11.0)
        self.assertFalse(logic.check_due(11.0))
        fresh(logic, 12.25)
        self.assertTrue(logic.check_due(12.25))
        token = logic.begin_check(12.25)
        self.assertEqual(logic.state['state'], 'VERIFYING')
        self.assertFalse(logic.check_due(12.5))                        # one check at a time
        fresh(logic, 14.6)
        logic.on_result(14.6, dict(OK), 'suggest', token, POSE, POSE)
        self.assertEqual(logic.state['state'], 'VERIFIED')
        self.assertFalse(logic.state['navigation_authorized'])
        self.assertAlmostEqual(logic.state['timing']['stop_to_result_s'], 4.6)
        self.assertAlmostEqual(logic.state['timing']['search_s'], 2.35)

    def test_no_second_check_while_one_is_in_flight(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        fresh(logic, 40.0)
        self.assertFalse(logic.check_due(40.0))                        # no pile-up behind a slow search
        fresh(logic, 42.2)                                             # > 30 s: abandoned, DEGRADED
        self.assertEqual(logic.state['state'], 'DEGRADED')
        self.assertIn('did not finish', logic.state['reason'])
        logic.on_result(43.0, dict(OK), 'suggest', token, POSE, POSE)  # late result discarded
        self.assertEqual(logic.state['state'], 'DEGRADED')
        fresh(logic, 72.3)
        self.assertTrue(logic.check_due(72.3))

    def test_result_from_before_a_move_is_discarded_even_if_parked_again(self):
        # old code: parked_since was non-None again, so the stale result was applied
        logic = MonitorLogic()
        drive_then_stop(logic, 10.0)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_motion(13.0, True)
        logic.on_motion(14.0, False)
        logic.on_result(15.0, dict(OK), 'suggest', token, POSE, POSE)
        self.assertEqual(logic.state['state'], 'PARKED_SETTLING')
        self.assertIn('result_discarded', [h['event'] for h in logic.drain_history()])
        fresh(logic, 16.1)
        self.assertTrue(logic.check_due(16.1))                         # new episode checks promptly

    def test_amcl_pose_change_during_check_discards_result(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_result(14.0, dict(OK), 'suggest', token, POSE, (1.3, 2.0, 0.5))
        self.assertNotEqual(logic.state['state'], 'VERIFIED')
        self.assertTrue(logic.check_due(14.25))

    def test_small_amcl_jitter_does_not_discard(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_result(14.0, dict(OK), 'suggest', token, POSE, (1.02, 2.01, 0.51))
        self.assertEqual(logic.state['state'], 'VERIFIED')

    def test_odometry_stale_is_input_stale_and_blocks_checks(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_inputs(13.5, 0.1, 0.5)                                # no odom since 12.1
        self.assertEqual(logic.state['state'], 'INPUT_STALE')
        self.assertIn('odometry', logic.state['reason'])
        self.assertFalse(logic.check_due(13.6))
        logic.on_result(14.0, dict(OK), 'suggest', token, POSE, POSE)
        self.assertEqual(logic.state['state'], 'INPUT_STALE')         # never VERIFIED on stale odom

    def test_scan_stale_while_parked_then_recovers(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_motion(13.0, False)
        logic.on_inputs(13.0, 1.6, 0.5)                                # LiDAR stopped
        self.assertEqual(logic.state['state'], 'INPUT_STALE')
        self.assertIn('LiDAR', logic.state['reason'])
        logic.on_result(14.0, dict(OK), 'suggest', token, POSE, POSE)
        self.assertEqual(logic.state['state'], 'INPUT_STALE')
        self.assertFalse(logic.check_due(14.0))
        fresh(logic, 15.0)                                             # scans back
        self.assertEqual(logic.state['state'], 'PARKED_SETTLING')
        self.assertTrue(logic.check_due(15.0))

    def test_amcl_stale_while_parked(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        logic.on_motion(17.0, False)
        logic.on_inputs(17.0, 0.1, None)                               # no AMCL pose since the stop
        self.assertEqual(logic.state['state'], 'INPUT_STALE')
        self.assertIn('AMCL', logic.state['reason'])

    def test_periodic_recheck_keeps_verified_and_counts_from_start(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.0)
        token = logic.begin_check(12.0)
        logic.on_result(14.5, dict(OK), 'suggest', token, POSE, POSE)
        fresh(logic, 41.9)
        self.assertFalse(logic.check_due(41.9))
        fresh(logic, 42.0)
        self.assertTrue(logic.check_due(42.0))                         # 30 s from the START
        logic.begin_check(42.0)
        self.assertEqual(logic.state['state'], 'VERIFIED')             # no flicker to VERIFYING
        self.assertTrue(logic.state['rechecking'])

    def test_check_error_after_move_is_discarded(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_motion(13.0, True)
        logic.on_check_error(13.5, token, RuntimeError('tf'))
        self.assertEqual(logic.state['state'], 'MOVING_UNVERIFIED')

    def test_lost_is_never_hidden_and_never_authorizes(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        self.assertIsNone(logic.on_result(14.0, dict(LOST), 'suggest', token, POSE, POSE))
        self.assertEqual(logic.state['state'], 'LOST')
        self.assertFalse(logic.state['navigation_authorized'])

    def test_auto_reseed_confirmation_is_rate_limited(self):
        logic = MonitorLogic()
        logic.awaiting_confirmation = True
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_result(14.0, dict(LOST, recovery_pose=None), 'auto', token, POSE, POSE)
        fresh(logic, 14.5)
        self.assertFalse(logic.check_due(14.5))
        fresh(logic, 17.2)
        self.assertTrue(logic.check_due(17.2))

    def test_concurrent_callbacks_never_publish_verified_while_moving(self):
        logic = MonitorLogic()
        stop = threading.Event()
        bad = []

        def worker():
            while not stop.is_set():
                tok = logic.episode
                logic.on_result(0.0, dict(OK), 'suggest', tok, POSE, POSE)

        def reader():
            while not stop.is_set():
                s = logic.snapshot()
                if s.get('state') == 'VERIFIED' and s.get('episode') is not None and logic.parked_since is None \
                        and s['episode'] == logic.episode:
                    bad.append(s)

        threads = [threading.Thread(target=worker), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        rnd = random.Random(3)
        for i in range(4000):
            logic.on_motion(i * 0.01, rnd.random() < 0.5)
        stop.set()
        for t in threads:
            t.join()
        logic.on_motion(99.0, True)
        self.assertEqual(logic.state['state'], 'MOVING_UNVERIFIED')
        self.assertEqual(bad, [])


class InputTests(unittest.TestCase):
    def test_usable_scans_rejects_old_and_pre_stop_scans(self):
        stamped = [(t, f's{t}') for t in (7.0, 9.5, 10.2, 11.0, 12.0)]
        self.assertEqual(mon.usable_scans(stamped, 12.1, 10.0), ['s10.2', 's11.0', 's12.0'])
        self.assertEqual(mon.usable_scans(stamped, 12.1, None), [])
        self.assertEqual(mon.usable_scans(stamped, 30.0, 10.0), [])

    def test_history_is_bounded_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'h.jsonl'
            for i in range(50):
                mon.append_history([{'event': 'x', 'i': i, 'pad': 'p' * 100}], path, max_bytes=1000)
            self.assertLessEqual(path.stat().st_size, 1000 + 200)
            self.assertTrue(path.with_suffix('.jsonl.1').exists())
            self.assertEqual(json.loads(path.read_text().splitlines()[-1])['i'], 49)

    def test_history_records_every_transition(self):
        logic = MonitorLogic()
        drive_then_stop(logic)
        fresh(logic, 12.1)
        token = logic.begin_check(12.1)
        logic.on_result(14.0, dict(OK), 'suggest', token, POSE, POSE)
        events = [h['event'] for h in logic.drain_history()]
        self.assertEqual(events, ['moving', 'stopped', 'check_started', 'result'])
        self.assertEqual(logic.drain_history(), [])


if __name__ == '__main__':
    unittest.main()
