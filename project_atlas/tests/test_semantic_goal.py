"""Master-plan step 9 part B (semantic goal through Nav2, owner-triggered, bounded): pure decisions. 2026-11-26."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'perception'))
import semantic_goal_check as sg  # noqa: E402

NOW = 1_800_000_000.0
ROBOT = {'x': 1.97, 'y': -5.48, 'yaw': math.radians(-167.0)}


def advisory(**kw):
    a = {'when': '2026-11-26 10:54', 'written_unix': NOW - 120, 'frame': 'map', 'advisory_only': True,
         'robot': dict(ROBOT), 'camera_home_us': [1801, 1501],
         'objects': [{'label': 'bed', 'map_x': 0.25, 'map_y': -4.92, 'seen': 0.9, 'spread_m': 0.008, 'confidence': 0.68,
                      'advisory_goal': {'x': 0.92, 'y': -5.14, 'yaw_deg': 162.0}},
                     {'label': 'chair', 'map_x': 2.5, 'map_y': -3.0, 'seen': 0.6, 'confidence': 0.9,
                      'advisory_goal': {'x': 2.3, 'y': -3.6, 'yaw_deg': 70.0}}]}
    a.update(kw)
    return a


class PickTargetTests(unittest.TestCase):
    def test_people_and_animals_are_never_goals(self):
        """2026-11-26 11:52 run picked a 'person'. Driving to people is the later human-aware step, not this one."""
        a = advisory(objects=[{'label': 'person', 'map_x': 0.9, 'map_y': -5.4, 'seen': 1.0, 'confidence': 0.9,
                               'advisory_goal': {'x': 1.5, 'y': -5.4, 'yaw_deg': 180.0}},
                              {'label': 'chair', 'map_x': 1.0, 'map_y': -5.0, 'seen': 0.7, 'confidence': 0.6,
                               'advisory_goal': {'x': 1.6, 'y': -5.1, 'yaw_deg': 170.0}}])
        t, why = sg.pick_target(a, ROBOT, NOW)
        self.assertEqual((t['label'], why), ('chair', []))
        only = advisory(objects=[dict(a['objects'][0]), dict(a['objects'][0], label='dog')])
        self.assertIn('people or animals', sg.pick_target(only, ROBOT, NOW)[1][0])

    def test_steps_back_to_first_map_clear_stop_point(self):
        """2026-11-26 12:22: the 0.70 m stop point was refused by mission control (occupied within 0.35 m); 1.1 m was
        clear. Owner: step back automatically along the line of sight, 0.7 -> 1.3 m, first map-clear point."""
        chair = {'label': 'chair', 'map_x': 0.54, 'map_y': 0.87, 'seen': 0.7, 'confidence': 0.53,
                 'advisory_goal': {'x': -0.11, 'y': 0.60, 'yaw_deg': 22.6}}
        robot = dict(ROBOT, x=-1.69, y=-0.06, yaw=math.radians(17.0))
        a = advisory(objects=[chair], robot=dict(robot))
        clear = lambda x, y: None if math.hypot(x - 0.54, y - 0.87) >= 1.05 else 'too close to a wall/obstacle'
        t, why = sg.pick_target(a, robot, NOW, clear_fn=clear)
        self.assertEqual(why, [])
        self.assertAlmostEqual(t['standoff_m'], 1.1, delta=0.001)
        self.assertAlmostEqual(math.hypot(t['goal_x'] - 0.54, t['goal_y'] - 0.87), 1.1, delta=0.01)
        self.assertAlmostEqual(t['goal_yaw_deg'], 22.6, delta=0.1)          # still facing the chair
        self.assertLess(t['goal_dist_m'], 1.8)
        # nothing clear up to 1.3 m: refused with the map reason, nothing sent
        t, why = sg.pick_target(a, robot, NOW, clear_fn=lambda x, y: 'occupied')
        self.assertIn('no map-clear stop point', why[0])
        # no map available: the 0.70 m point is kept and mission control decides
        t, why = sg.pick_target(a, robot, NOW)
        self.assertEqual((t['goal_x'], t['goal_y'], t['standoff_m']), (-0.11, 0.6, 0.7))

    def test_picks_most_seen_object(self):
        t, why = sg.pick_target(advisory(), ROBOT, NOW)
        self.assertEqual(why, [])
        self.assertEqual(t['label'], 'bed')
        self.assertEqual((t['goal_x'], t['goal_y']), (0.92, -5.14))
        self.assertAlmostEqual(t['goal_dist_m'], 1.10, delta=0.02)

    def test_refusals(self):
        self.assertIn('part A', sg.pick_target(None, ROBOT, NOW)[1][0])
        self.assertIn('older', sg.pick_target(advisory(written_unix=NOW - 4000), ROBOT, NOW)[1][0])
        old = advisory(); del old['written_unix']; del old['robot']
        self.assertIn('part A again', sg.pick_target(old, ROBOT, NOW)[1][0])        # files from before this test
        nocam = advisory(); del nocam['camera_home_us']
        self.assertIn('camera-forward fix', sg.pick_target(nocam, ROBOT, NOW)[1][0])  # turned-camera results
        moved = dict(ROBOT, x=ROBOT['x'] + 0.5)
        self.assertIn('moved', sg.pick_target(advisory(), moved, NOW)[1][0])
        turned = dict(ROBOT, yaw=ROBOT['yaw'] + math.radians(30))
        self.assertIn('moved', sg.pick_target(advisory(), turned, NOW)[1][0])
        self.assertIn('no object', sg.pick_target(advisory(objects=[]), ROBOT, NOW)[1][0])
        self.assertIn('pose', sg.pick_target(advisory(), None, NOW)[1][0])

    def test_far_and_near_goals_refused(self):
        far = advisory(objects=[{'label': 'tv', 'map_x': -3.0, 'map_y': -5.4, 'seen': 1.0,
                                 'advisory_goal': {'x': -2.3, 'y': -5.4, 'yaw_deg': 180.0}}])
        self.assertIn('too far', sg.pick_target(far, ROBOT, NOW)[1][0])
        near = advisory(objects=[{'label': 'tv', 'map_x': 1.3, 'map_y': -5.5, 'seen': 1.0,
                                  'advisory_goal': {'x': 1.95, 'y': -5.47, 'yaw_deg': 180.0}}])
        self.assertIn('already', sg.pick_target(near, ROBOT, NOW)[1][0])


class MissionTests(unittest.TestCase):
    L = 'map point 0.92,-5.14'

    def test_events(self):
        ev = lambda s: sg.mission_event(s, 0.92, -5.14)
        self.assertEqual(ev('QUEUED navigate to map point 0.92,-5.14'), 'queued')
        self.assertEqual(ev('NAMED GOAL DISPATCHED name=map point 0.92,-5.14'), 'dispatched')
        self.assertEqual(ev('NAMED GOAL ACCEPTED name=map point 0.92,-5.14'), 'accepted')
        self.assertEqual(ev('NAMED GOAL FINISHED name=map point 0.92,-5.14 status=4'), 'succeeded')
        self.assertEqual(ev('NAMED GOAL FINISHED name=map point 0.92,-5.14 status=6'), 'failed')
        self.assertEqual(ev('NAMED GOAL REJECTED name=map point 0.92,-5.14'), 'failed')
        self.assertEqual(ev('ERROR navigate to map point 0.92,-5.14: map point refused: occupied'), 'failed')
        self.assertEqual(ev('BUSY: ignored navigate to map point 0.92,-5.14'), 'failed')
        self.assertEqual(ev('NAVIGATION STOPPED: camera obstacles lost (x); goal cancelled'), 'failed')
        self.assertEqual(ev('NAVIGATION CANCELED; ROVER STOPPED'), 'failed')
        self.assertIsNone(ev('NAMED GOAL FINISHED name=hall status=4'))              # another goal
        self.assertIsNone(ev('READY'))

    def test_fast_refusal_counts_even_if_queued_was_missed(self):
        """2026-11-26 11:52: mission control refused at once; the 1 Hz status never showed QUEUED, so the refusal was
        ignored for 15 s. A refusal naming OUR goal that is new since the send counts; a stale one does not."""
        err = 'ERROR navigate to map point 0.55,-1.10: map point refused: too close to a wall/obstacle'
        acc = sg.accept_event
        self.assertTrue(acc('failed', set(), err, 'READY'))                         # new since the send
        self.assertFalse(acc('failed', set(), err, err))                            # same text as before the send
        self.assertTrue(acc('failed', {'queued'}, err, err))                        # after our goal was seen
        self.assertFalse(acc('failed', set(), 'NAVIGATION CANCELED; ROVER STOPPED', 'READY'))   # not ours by name
        self.assertFalse(acc('succeeded', set(), 'NAMED GOAL FINISHED name=map point 0.55,-1.10 status=4', 'READY'))
        self.assertTrue(acc('succeeded', {'accepted'}, 'NAMED GOAL FINISHED name=map point 0.55,-1.10 status=4', 'x'))
        self.assertTrue(acc('queued', set(), 'QUEUED navigate to map point 0.55,-1.10', 'READY'))
        self.assertFalse(acc(None, set(), 'READY', 'READY'))

    def test_off_course(self):
        s, g = (0.0, 0.0), (2.0, 0.0)
        self.assertAlmostEqual(sg.off_course(s, g, (1.0, 0.3)), 0.3)
        self.assertAlmostEqual(sg.off_course(s, g, (-0.5, 0.0)), 0.5)
        self.assertAlmostEqual(sg.off_course(s, s, (0.0, 0.4)), 0.4)


def target():
    return {'label': 'bed', 'map_x': 0.25, 'map_y': -4.92, 'goal_x': 0.92, 'goal_y': -5.14, 'goal_yaw_deg': 162.0,
            'goal_dist_m': 1.1}


def confirm(n_match, n=5):
    rounds = [[('bed', 0.7, 0.30, -4.95)] for _ in range(n_match)] + [[] for _ in range(n - n_match)]
    return rounds


class EvaluateTests(unittest.TestCase):
    def run_eval(self, **kw):
        a = dict(refused=[], seen={'queued', 'dispatched', 'accepted', 'succeeded'}, end_reason='ARRIVED',
                 final_pose={'x': 0.95, 'y': -5.12, 'yaw': math.radians(165.0)}, target=target(),
                 confirm_rounds=confirm(5), max_off_course_m=0.2, elapsed_s=14.0, limit_stop=None)
        a.update(kw)
        return sg.evaluate(**a)

    def test_pass(self):
        r = self.run_eval()
        self.assertEqual(r['verdict'], 'PASS', r)
        self.assertIn('bed', r['detail'])

    def test_refused_sends_nothing(self):
        r = self.run_eval(refused=['ATLAS moved since step 9 part A'], seen=set(), end_reason=None,
                          final_pose=None, confirm_rounds=[])
        self.assertEqual(r['verdict'], 'REFUSED')
        self.assertIn('nothing was sent', r['detail'])

    def test_failures(self):
        for kw, key in ((dict(end_reason='OWNER_STOP'), 'no_owner_stop'),
                        (dict(end_reason='TIMEOUT', elapsed_s=61.0), 'within_time'),
                        (dict(end_reason='NAV2_FAILED', seen={'queued', 'failed'}), 'nav2_succeeded'),
                        (dict(final_pose={'x': 1.3, 'y': -5.2, 'yaw': math.radians(162.0)}), 'arrived_at_stop_point'),
                        (dict(final_pose={'x': 0.92, 'y': -5.14, 'yaw': math.radians(100.0)}), 'facing_object'),
                        (dict(confirm_rounds=confirm(2)), 'object_confirmed'),
                        (dict(end_reason='OFF_COURSE', max_off_course_m=1.2), 'stayed_on_course'),
                        (dict(end_reason='LIMIT', limit_stop='CPU'), 'limits_held')):
            r = self.run_eval(**kw)
            self.assertEqual(r['verdict'], 'FAIL', key)
            self.assertIn(key, r['failed'], key)

    def test_confirm_needs_same_label_near_recorded_spot(self):
        wrong = [[('chair', 0.9, 0.30, -4.95)]] * 5
        self.assertIn('object_confirmed', self.run_eval(confirm_rounds=wrong)['failed'])
        moved = [[('bed', 0.9, 1.0, -4.0)]] * 5
        self.assertIn('object_confirmed', self.run_eval(confirm_rounds=moved)['failed'])


class BlockReasonTests(unittest.TestCase):
    """2026-11-26 owner: "show reason" when the safety chain keeps ATLAS from moving."""
    LOG = ['[ERROR] [1795672914.371533048] [atlas_cmd_vel_mux]: LIDAR AVAILABILITY STOP: unobserved motion sector (1 bins)',
           '[ERROR] [1795672915.016764455] [atlas_cmd_vel_mux]: LIDAR AVAILABILITY STOP: unobserved motion sector (2 bins)',
           '[INFO] [1795672915.1] [atlas_cmd_vel_mux]: autonomy armed',
           '[WARN] [1795672916.0] [atlas_cmd_vel_mux]: AUTONOMY BLOCKED: FRONT 0.18 m',
           '[WARN] [1795672922.630413929] [atlas_cmd_vel_mux]: Safety stop: autonomy switched OFF',
           '[WARN] [1795672922.643195070] [atlas_cmd_vel_mux]: AUTONOMY OFF (manual only)',
           '[WARN] [1795672922.7] [atlas_cmd_vel_mux]: Safety stop: NAV2 released']

    def test_summary_counts_reasons_and_skips_our_own_abort(self):
        s = sg.mux_summary(self.LOG)
        self.assertEqual(s[0], {'reason': 'LIDAR AVAILABILITY STOP: unobserved motion sector', 'count': 2})
        self.assertEqual(s[1]['reason'], 'AUTONOMY BLOCKED: FRONT')
        self.assertEqual(len(s), 2)
        self.assertEqual(sg.mux_summary([]), [])

    def test_hints_in_english(self):
        self.assertIn('LiDAR could not see', sg.block_hint('LIDAR AVAILABILITY STOP: unobserved motion sector'))
        self.assertIn('too close', sg.block_hint('AUTONOMY BLOCKED: FRONT'))
        self.assertIn('ultrasonic', sg.block_hint('AUTONOMY BLOCKED: FRONT ULTRASONIC data lost'))
        self.assertIn('where it is', sg.block_hint('ERROR navigate to map point 1.00,2.00: localization uncertain'))
        self.assertIn('wall', sg.block_hint('ERROR navigate to map point 1.00,2.00: map point refused: too close to a wall'))
        self.assertIsNone(sg.block_hint(None))

    def test_failed_result_names_the_reason(self):
        a = dict(refused=[], seen={'queued', 'accepted'}, end_reason='TIMEOUT', final_pose={'x': 2.26, 'y': -5.15, 'yaw': 0.0},
                 target=target(), confirm_rounds=[], max_off_course_m=0.02, elapsed_s=60.2, limit_stop=None,
                 blocked=sg.mux_summary(self.LOG))
        r = sg.evaluate(**a)
        self.assertEqual(r['verdict'], 'FAIL')
        self.assertEqual(r['measured']['blocked_by'], 'LIDAR AVAILABILITY STOP: unobserved motion sector')
        self.assertIn('LiDAR could not see', r['measured']['hint'])
        self.assertIn('blocked by the safety chain', r['detail'])
        r = sg.evaluate(**dict(a, blocked=[], mission_text='ERROR navigate to map point 0.92,-5.14: too close to a wall'))
        self.assertIn('wall', r['measured']['hint'])
        self.assertIn('too close to a wall', r['detail'])


if __name__ == '__main__':
    unittest.main()
