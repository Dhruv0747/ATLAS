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
        self.assertIn('Autonomous', v.on_policy(ON, 10))
        self.assertIn('Manual', v.on_policy(OFF, 30))

    def test_front_block_and_repeat_suppressed(self):
        v = AutonomyVoice(); v.on_policy(ON, 0); v.on_mission('NAMED GOAL ACCEPTED name=hall', 1); v.last_any = -1e9
        self.assertIn('Front', v.on_safety('AUTONOMY BLOCKED: FRONT 0.16 m (stop 0.30 m)', 10))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 12))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 10 + REPEAT_S - 1))
        self.assertIsNotNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.15 m (stop 0.30 m)', 10 + REPEAT_S + 1))

    def test_gap_between_different_sentences(self):
        v = AutonomyVoice(); v.on_policy(ON, 0); v.on_mission('NAMED GOAL ACCEPTED name=hall', 1); v.last_any = -1e9
        self.assertIsNotNone(v.on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (3 bins)', 10))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: REAR 0.20 m (stop 0.30 m)', 10 + GAP_S / 2))
        self.assertIn('Back', v.on_safety('AUTONOMY BLOCKED: REAR 0.20 m (stop 0.30 m)', 10 + GAP_S + 0.1))

    def test_ultrasonic_data_problem_not_reported_as_obstacle(self):
        v = AutonomyVoice(); v.on_policy(ON, 0); v.on_mission('NAMED GOAL ACCEPTED name=hall', 1); v.last_any = -1e9
        self.assertIn('data', v.on_safety('AUTONOMY BLOCKED: FRONT ULTRASONIC SERIAL_BACKLOG', 10))

    def test_degraded_encoder_is_quiet(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIsNone(v.on_safety('AUTONOMY DEGRADED: ENCODER M3; SPEED 50%', 10))

    def test_goal_lifecycle(self):
        v = AutonomyVoice(); v.on_policy(OFF, 0)
        self.assertIn('hall', v.on_mission('NAMED GOAL ACCEPTED name=hall', 10))
        self.assertTrue(v.goal_active)
        self.assertIn('Front', v.on_safety('AUTONOMY BLOCKED: FRONT 0.2 m (stop 0.30 m)', 20))
        self.assertIn('नया path', v.on_recoveries(1, 30))
        self.assertIsNone(v.on_recoveries(1, 50))
        self.assertIn('पहुँच', v.on_mission('NAMED GOAL FINISHED name=hall status=4', 60))
        self.assertFalse(v.goal_active)
        self.assertIsNone(v.on_recoveries(2, 70))

    def test_map_point_and_failures(self):
        v = AutonomyVoice()
        self.assertEqual(v.on_mission('NAMED GOAL ACCEPTED name=map point 1.00,2.00', 0), 'Ok, वहाँ जा रहा हूँ।')
        self.assertIn('path नहीं', v.on_mission('NAMED GOAL FINISHED name=map point 1.00,2.00 status=6', 10))
        self.assertIn('wall', v.on_mission("ERROR navigate to map point: map point refused: too close to a wall/obstacle", 30))
        self.assertIn('Camera', v.on_mission('NAVIGATION STOPPED: camera obstacles lost (2.3s stale); cancel acknowledged', 50))

    def test_quiet_after_goal_ends_even_if_autonomy_on(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        v.on_mission('NAMED GOAL ACCEPTED name=hall', 1)
        v.on_mission('NAMED GOAL FINISHED name=hall status=6', 10)
        self.assertIsNone(v.on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (1 bins)', 30))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: LOCALIZATION XY UNCERTAINTY 0.30m', 90))

    def test_abort_spoken_once_then_quiet(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        v.on_mission('NAMED GOAL ACCEPTED name=hall', 1)
        self.assertIn('Mission cancel', v.on_mission('NAVIGATION CANCELED; ROVER STOPPED', 20))
        self.assertFalse(v.goal_active)
        self.assertIsNone(v.on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (2 bins)', 40))

    def test_estop_spoken_only_when_relevant(self):
        v = AutonomyVoice(); v.on_policy(dict(ON, stop_latched=False), 0)
        self.assertIn('Emergency', v.on_policy({'autonomy': {'armed': True}, 'stop_latched': True}, 10))
        m = AutonomyVoice(); m.on_policy(OFF, 0)
        self.assertIsNone(m.on_policy(dict(OFF, stop_latched=True), 10))


def driving():
    v = AutonomyVoice(); v.on_policy(ON, 0); v.on_mission('NAMED GOAL ACCEPTED name=hall', 1); v.last_any = -1e9
    return v


class HinglishTests(unittest.TestCase):
    """2026-11-28 owner: "use Hinglish, not pure Hindi": Hindi grammar, everyday English words."""

    def test_common_words_are_english(self):
        s = driving().on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (2 bins)', 10)
        for w in ('LiDAR', 'path', 'cover'):
            self.assertIn(w, s)
        for hindi in ('लाइडार', 'रास्ते', 'ढकिए'):
            self.assertNotIn(hindi, s)
        s = AutonomyVoice().on_mission('ERROR navigate to map point 0.5,-1.1: map point refused: too close to a wall', 0)
        self.assertNotIn('दीवार', s)


class ExactReasonTests(unittest.TestCase):
    """2026-11-28 owner: "I need the exact reason spoken, not one or two recordings, easy to understand"."""

    def test_distance_and_side_are_spoken(self):
        s = driving().on_safety('AUTONOMY BLOCKED: FRONT 0.16 m (stop 0.30 m)', 10)
        self.assertIn('sixteen centimeter', s)
        self.assertIn('Front', s)
        self.assertIn('Path clear', s)                       # what happens next / what to do
        s = driving().on_safety('AUTONOMY BLOCKED: LEFT 0.22 m', 10)
        self.assertIn('left', s.lower()); self.assertIn('twenty two centimeter', s)

    def test_same_reason_with_new_distance_is_not_repeated(self):
        v = driving()
        self.assertIsNotNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.16 m', 10))
        self.assertIsNone(v.on_safety('AUTONOMY BLOCKED: FRONT 0.12 m', 10 + GAP_S + 1))   # same reason, new number

    def test_lidar_reason_says_what_to_do(self):
        s = driving().on_safety('LIDAR AVAILABILITY STOP: unobserved motion sector (2 bins)', 10)
        self.assertIn('LiDAR', s)
        self.assertIn('black', s)                                # dark / shiny / open things near the path

    def test_localisation_kinds_differ(self):
        a = driving().on_safety('AUTONOMY BLOCKED: LOCALIZATION JUMP 0.6 m', 10)
        b = driving().on_safety('AUTONOMY BLOCKED: LOCALIZATION STALE 1.4s', 10)
        self.assertNotEqual(a, b)
        self.assertIn('अचानक', a)
        self.assertIn('Find my location', b)

    def test_encoder_and_radar(self):
        self.assertIn('Wheel', driving().on_safety('AUTONOMY STOP: ENCODER CRITICAL m3', 10))
        self.assertIn('slow', driving().on_safety('RADAR LIMIT: person 1.2 m', 10))

    def test_mission_refusals_are_specific(self):
        v = AutonomyVoice()
        s = v.on_mission('ERROR navigate to map point -0.48,0.45: saved-map navigation blocked: current pose is not '
                         'in known clear space on the accepted map (candidate start is not clear for the inflated rover)', 0)
        self.assertIn('मैं खुद', s); self.assertIn('open जगह', s)
        s = AutonomyVoice().on_mission('ERROR navigate to map point 0.55,-1.10: map point refused: too close to a '
                                       'wall/obstacle (unknown within 0.35 m)', 0)
        self.assertIn('wall', s); self.assertIn('open जगह', s)
        s = AutonomyVoice().on_mission('BUSY: ignored navigate to map point 1.00,2.00', 0)
        self.assertIn('दूसरा काम', s)
        s = AutonomyVoice().on_mission('ERROR navigate to hall: something unexpected', 0)
        self.assertIn('dashboard', s)                            # never a bare "could not be done"
        s = AutonomyVoice().on_mission('NAMED GOAL FINISHED name=hall status=6', 0)
        self.assertIn('hall', s); self.assertIn('path नहीं', s)

    def test_estop_says_how_to_release(self):
        v = AutonomyVoice(); v.on_policy(ON, 0)
        self.assertIn('remote', v.on_policy({'autonomy': {'armed': True}, 'stop_latched': True}, 10))

    def test_owner_words_english_numbers_and_left_right(self):
        """2026-11-28 owner: understands one, two, three (not ek, do, teen) and left / right (not daayein / baayein)."""
        from atlas_autonomy_voice_core import number_words
        self.assertEqual(number_words(0), "zero")
        self.assertEqual(number_words(7), "seven")
        self.assertEqual(number_words(18), "eighteen")
        self.assertEqual(number_words(40), "forty")
        self.assertEqual(number_words(135), "one hundred thirty five")
        s = driving().on_safety("AUTONOMY BLOCKED: RIGHT 0.40 m", 10)
        self.assertIn("right", s.lower()); self.assertIn("forty centimeter", s)
        self.assertNotIn("दाईं", s); self.assertNotIn("बाईं", s)
        for t in ("AUTONOMY BLOCKED: FRONT 0.18 m", "AUTONOMY BLOCKED: LEFT 0.3 m", "AUTONOMY BLOCKED: REAR 1.05 m"):
            self.assertFalse(any(c.isdigit() for c in driving().on_safety(t, 10)), t)   # no digits left for Hindi TTS

    def test_every_sentence_is_short(self):
        texts = ['AUTONOMY BLOCKED: FRONT 0.16 m', 'LIDAR AVAILABILITY STOP: x (1 bins)', 'AUTONOMY STOP: ENCODER X',
                 'AUTONOMY BLOCKED: LOCALIZATION XY UNCERTAINTY 0.3m', 'AUTONOMY BLOCKED: REAR ULTRASONIC lost']
        for t in texts:
            s = driving().on_safety(t, 10)
            self.assertIsNotNone(s, t)
            self.assertLessEqual(len(s), 160, t)


if __name__ == '__main__':
    unittest.main()
