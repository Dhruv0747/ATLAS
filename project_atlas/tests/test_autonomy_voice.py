from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_autonomy_voice_core import AutonomyVoice, GAP_S, REPEAT_S

ON = {'autonomy': {'armed': True}, 'stop_latched': False}
OFF = {'autonomy': {'armed': False}, 'stop_latched': False}


class AutonomyVoiceTests(unittest.TestCase):
    def test_quiet_in_manual(self):
        v = AutonomyVoice(); v.on_policy(OFF, 0)
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.16 m (stop 0.30 m)', 10))

    def test_mode_changes_spoken(self):
        v = AutonomyVoice(); v.on_policy(OFF, 0)
        self.assertIn('ऑटोनॉमस', v.on_policy(ON, 10))
        self.assertIn('मैनुअल', v.on_policy(OFF, 30))

    def test_front_block_and_repeat_suppressed(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIn('आगे', v.on_safety('AUTONOMY BLOCKED: FRONT 0.16 m (stop 0.30 m)', 10))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 12))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 10 + REPEAT_S - 1))
        self.assertIsNotNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 10 + REPEAT_S + 1))

    def test_gap_between_different_sentences(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIsNotNone(v.on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (3 bins)', 10))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: REAR 0.20 m (stop 0.30 m)', 10 + GAP_S / 2))
        self.assertIn('पीछे', v.on_safety('AUTONOMY BLOCKED: REAR 0.20 m (stop 0.30 m)', 10 + GAP_S + 0.1))

    def test_ultrasonic_data_problem_not_reported_as_obstacle(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIn('डेटा', v.on_safety('AUTONOMY BLOCKED: FRONT ULTRASONIC SERIAL_BACKLOG', 10))

    def test_degraded_encoder_is_quiet(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIsNone(v.on_safety('AUTONOMY DEGRADED: ENCODER M3; SPEED 50%', 10))

    def test_goal_lifecycle(self):
        v = AutonomyVoice(); v.on_policy(OFF, 0)
        self.assertIn('hall', v.on_mission('NAMED GOAL ACCEPTED name=hall', 10))
        self.assertTrue(v.goal_active)
        self.assertIn('आगे', v.on_safety('AUTONOMY BLOCKED: FRONT 0.2 m (stop 0.30 m)', 20))
        self.assertIn('नया रास्ता', v.on_recoveries(1, 30))
        self.assertIsNone(v.on_recoveries(1, 50))
        self.assertIn('पहुँच', v.on_mission('NAMED GOAL FINISHED name=hall status=4', 60))
        self.assertFalse(v.goal_active)
        self.assertIsNone(v.on_recoveries(2, 70))

    def test_map_point_and_failures(self):
        v = AutonomyVoice()
        self.assertEqual(v.on_mission('NAMED GOAL ACCEPTED name=map point 1.00,2.00', 0), 'ठीक है, वहाँ जा रहा हूँ।')
        self.assertIn('रास्ता नहीं', v.on_mission('NAMED GOAL FINISHED name=map point 1.00,2.00 status=6', 10))
        self.assertIn('दीवार', v.on_mission("ERROR navigate to map point: map point refused: too close to a wall/obstacle", 30))
        self.assertIn('कैमरा', v.on_mission('NAVIGATION STOPPED: camera obstacles lost (2.3s stale); cancel acknowledged', 50))

    def test_estop_spoken_only_when_relevant(self):
        v = AutonomyVoice(); v.on_policy(dict(ON, stop_latched=False), 0)
        self.assertIn('इमरजेंसी', v.on_policy({'autonomy': {'armed': True}, 'stop_latched': True}, 10))
        m = AutonomyVoice(); m.on_policy(OFF, 0)
        self.assertIsNone(m.on_policy(dict(OFF, stop_latched=True), 10))


if __name__ == '__main__':
    unittest.main()
