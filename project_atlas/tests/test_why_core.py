"""Home "Why isn't ATLAS moving?" explainer (2026-11-28, owner: dashboard easier to understand). Pure, no ROS."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_why_core as why  # noqa: E402

MANUAL = {'autonomy': {'armed': False, 'arm_blockers': ['latch the E-STOP first (arm while stopped)']},
          'stop_latched': False, 'stop_reason': 'REMOTE STOP: released by neutral LB hold', 'source': 'STOPPED'}
ARMED = {'autonomy': {'armed': True, 'arm_blockers': []}, 'stop_latched': False, 'source': 'NAV2'}
GOAL = 'NAMED GOAL ACCEPTED name=map point 0.93,-5.01'


def ex(policy=ARMED, safety=None, safety_age=0.2, mission='READY', mission_age=0.5, policy_age=0.1):
    return why.explain(policy, policy_age, safety, safety_age, mission, mission_age)


class WhyTests(unittest.TestCase):
    def test_no_live_data(self):
        r = ex(policy=None)
        self.assertEqual(r['level'], 'unknown')
        self.assertIn('No live safety data', r['title'])
        self.assertEqual(ex(policy_age=5.0)['level'], 'unknown')

    def test_estop_wins_over_everything(self):
        r = ex(policy=dict(ARMED, stop_latched=True, stop_reason='REMOTE STOP: B pressed'),
               safety='LIDAR AVAILABILITY STOP: unobserved motion sector (2 bins)', mission=GOAL)
        self.assertEqual(r['level'], 'stop')
        self.assertIn('E-STOP', r['title'])
        self.assertIn('remote', r['fix'])
        self.assertIn('B pressed', r['detail'])

    def test_lidar_blind_spot_while_driving(self):
        """The 11:31 part-B run: 156x this text, the page said only TIMEOUT."""
        r = ex(safety='LIDAR AVAILABILITY STOP: unobserved motion sector (1 bins)', mission=GOAL)
        self.assertEqual(r['level'], 'stop')
        self.assertIn('LiDAR cannot see', r['title'])
        self.assertIn('dark, shiny or open', r['fix'])
        self.assertEqual(r['source'], 'safety mux')

    def test_guard_texts(self):
        self.assertIn('too close', ex(safety='AUTONOMY BLOCKED: FRONT 0.18 m', mission=GOAL)['title'])
        self.assertIn('ultrasonic', ex(safety='AUTONOMY BLOCKED: FRONT ULTRASONIC data lost', mission=GOAL)['title'])
        self.assertIn('not sure where', ex(safety='AUTONOMY BLOCKED: LOCALIZATION STALE 1.4s', mission=GOAL)['title'])
        self.assertIn('wheel', ex(safety='AUTONOMY STOP: ENCODER CRITICAL m3', mission=GOAL)['title'])

    def test_stale_safety_text_is_ignored(self):
        r = ex(safety='LIDAR AVAILABILITY STOP: x', safety_age=8.0, mission=GOAL)
        self.assertEqual(r['level'], 'ok')
        self.assertIn('Driving', r['title'])

    def test_healthy_safety_texts_are_not_blocks(self):
        for t in ('AUTONOMY IDLE', 'ULTRASONIC DIRECTIONAL VETO: no veto; NOT a path-clear guarantee; LIDAR PRIMARY',
                  'ULTRASONIC DISABLED; LIDAR PRIMARY'):
            self.assertEqual(ex(safety=t, mission=GOAL)['level'], 'ok', t)

    def test_slowed_is_ok_with_note(self):
        r = ex(safety='AUTONOMY DEGRADED: ENCODER ; SPEED 50%', mission=GOAL)
        self.assertEqual(r['level'], 'ok')
        self.assertIn('slower', r['detail'])

    def test_mission_refusals(self):
        r = ex(mission='ERROR navigate to map point -0.48,0.45: saved-map navigation blocked: current pose is not in '
                       'known clear space on the accepted map (candidate start is not clear for the inflated rover)')
        self.assertEqual(r['level'], 'wait')
        self.assertIn('too close to', r['title'])
        self.assertIn('open floor', r['fix'])
        self.assertEqual(r['source'], 'mission control')
        r = ex(mission='ERROR navigate to map point 0.55,-1.10: map point refused: too close to a wall/obstacle')
        self.assertIn('target', r['title'])
        r = ex(mission='NAMED GOAL FINISHED name=hall status=6')
        self.assertIn('could not find a way', r['title'])
        r = ex(mission='NAMED GOAL FINISHED name=hall status=4')
        self.assertEqual(r['level'], 'ok'); self.assertIn('Arrived', r['title'])
        r = ex(mission='ERROR navigate to hall: localization uncertain')
        self.assertIn('not sure where', r['title'])

    def test_goal_but_manual_mode(self):
        r = ex(policy=MANUAL, mission=GOAL)
        self.assertEqual(r['level'], 'stop')
        self.assertIn('Manual mode', r['title'])

    def test_idle_states(self):
        r = ex(policy=MANUAL)
        self.assertEqual(r['level'], 'ok')
        self.assertIn('Manual mode', r['title'])
        self.assertIn('latch the E-STOP first', r['fix'])           # arm blockers are shown as the next action
        r = ex()
        self.assertEqual(r['level'], 'ok')
        self.assertIn('Ready', r['title'])

    def test_driving(self):
        r = ex(mission=GOAL)
        self.assertEqual((r['level'], r['title']), ('ok', 'Driving to map point 0.93,-5.01'))

    def test_texts_are_english_and_short(self):
        r = ex(safety='LIDAR AVAILABILITY STOP: unobserved motion sector (1 bins)', mission=GOAL)
        for k in ('title', 'fix'):
            self.assertTrue(r[k].isascii(), k)
            self.assertLessEqual(len(r[k]), 200, k)


if __name__ == '__main__':
    unittest.main()
