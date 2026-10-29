"""Tomorrow's supervised lifted-wheel sequence, offline, with EXACTLY the reviewed live config (candidate +
reviewed_by_owner + 0.05 m/s / 0.20 rad/s, as review-config wrote it: 875feb35) through the real drive core, the
patched LIVE mux and the real Xbox RemoteStop. Simulation only: no physical result is claimed from these tests."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests')); sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools/deploy/stage29_flysky_drive'))
import test_flysky_commissioning_offline as C   # noqa: E402  (Rover harness)
import atlas_flysky_drive_core as dc            # noqa: E402
import deploy_stage29 as D                      # noqa: E402

REVIEWED = dict(copy.deepcopy(C.CFG), reviewed_by_owner=True, **D.COMMISSION_CAPS)
UP, MID, DOWN = C.UP, C.MID, C.DOWN
TH, ST, ARM, STOP, SPD = C.TH, C.ST, C.ARM, C.STOP, C.SPD


def rover():
    r = C.Rover()
    r.teleop = dc.DriveLogic(copy.deepcopy(REVIEWED), True)
    return r


class ReviewedConfig(unittest.TestCase):
    def test_reviewed_config_is_the_one_on_the_rover(self):
        text = json.dumps(REVIEWED, indent=2) + '\n'                      # review-config's exact serialisation
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest()[:8], '875feb35')
        ok, errs = dc.usable(REVIEWED); self.assertTrue(ok, errs)
        self.assertEqual((REVIEWED['throttle']['channel'], REVIEWED['steering']['channel'], REVIEWED['arm']['channel'],
                          REVIEWED['stop']['channel'], REVIEWED['speed_mode']['channel']), (2, 1, 5, 6, 7))


class MorningSequence(unittest.TestCase):
    def armed(self, speed=MID):
        r = rover(); r.rx[SPD] = speed; r.commission_to_armed()
        return r

    def test_select_reset_arm_then_direction_checks(self):
        r = rover(); r.rx[SPD] = MID
        r.tick(10)
        self.assertEqual(r.last(), (0.0, 0.0))                             # latched, Xbox selected: nothing
        ok, why = r.mux.select_controller('FLYSKY'); self.assertTrue(ok, why)
        r.drive(DOWN, MID, 20); self.assertEqual(r.last(), (0.0, 0.0))     # still latched
        r.rx[TH] = MID; r.tick(4)
        r.xbox_lb_reset(); self.assertFalse(r.mux.remote_stop.latched)
        r.drive(DOWN, MID, 20); self.assertEqual(r.last(), (0.0, 0.0))     # released but SwA still up: not armed
        r.rx[TH] = MID; r.tick(4); r.rx[ARM] = DOWN; r.tick(4)
        self.assertTrue(r.teleop.armed)
        r.drive(int(MID + 0.5 * (DOWN - MID)), MID, 60)                     # right stick half up
        lin, ang = r.last()
        self.assertGreater(lin, 0.0); self.assertLessEqual(lin, 0.05 * 0.66 + 1e-9)
        r.drive(int(MID - 0.5 * (MID - UP)), MID, 60)                       # half down: reverse
        self.assertLess(r.last()[0], 0.0)
        r.drive(int(MID + 0.5 * (DOWN - MID)), DOWN, 60)                    # up + right: steering is reversed in config
        self.assertNotEqual(r.last()[1], 0.0); self.assertLessEqual(abs(r.last()[1]), 0.20 + 1e-9)
        r.rx[TH], r.rx[ST] = MID, MID; r.tick(20); self.assertEqual(r.last(), (0.0, 0.0))   # release: neutral

    def test_speed_switch_scales_and_never_exceeds_the_caps(self):
        seen = {}
        for name, pos in (('up', UP), ('middle', MID), ('down', DOWN)):
            r = self.armed(pos); r.drive(DOWN, DOWN, 80)
            seen[name] = r.last()
            self.assertLessEqual(abs(seen[name][0]), 0.05 + 1e-9, name); self.assertLessEqual(abs(seen[name][1]), 0.20 + 1e-9, name)
        self.assertAlmostEqual(seen['down'][0], 0.05, places=3)
        self.assertAlmostEqual(seen['middle'][0], 0.033, places=3)
        self.assertLessEqual(seen['up'][0], 0.0165 + 1e-6)
        self.assertLessEqual(seen['up'][0], 0.02)      # inside the base's |vx| <= 0.02 zero band: no wheel motion expected

    def test_swb_middle_also_stops_and_latches(self):
        r = self.armed(); r.drive(DOWN, MID, 40)
        dt = r.time_to_zero(lambda: r.rx.__setitem__(STOP, MID))
        self.assertLessEqual(dt, 0.15); self.assertTrue(r.mux.remote_stop.latched)

    def test_after_any_latch_reset_needs_swa_off_then_on(self):
        for stop in ('swb', 'xbox_b', 'dashboard'):
            r = self.armed(); r.drive(DOWN, MID, 40)
            if stop == 'swb':
                r.rx[STOP] = DOWN; r.tick(10); r.rx[STOP] = UP
            elif stop == 'xbox_b':
                r.xbox_b(); r.tick(10)
            else:
                r.mux.on_voice_stop(None); r.tick(10)
            self.assertTrue(r.mux.remote_stop.latched, stop)
            r.rx[TH] = MID; r.tick(4); r.xbox_lb_reset(); self.assertFalse(r.mux.remote_stop.latched, stop)
            r.drive(DOWN, MID, 40)
            self.assertEqual(r.last(), (0.0, 0.0), f'{stop}: drove after reset with SwA still down')
            r.rx[TH] = MID; r.rx[ARM] = UP; r.tick(4); r.rx[ARM] = DOWN; r.tick(4)
            r.drive(DOWN, MID, 40); self.assertGreater(r.last()[0], 0.0, stop)

    def test_lb_reset_is_refused_while_any_xbox_control_is_held(self):
        r = rover(); r.tick(10)
        ok, _ = r.mux.select_controller('FLYSKY'); self.assertTrue(ok)
        lb_a = [0] * 11; lb_a[0] = lb_a[4] = 1                              # A held with LB (the input-check rule)
        r.joy_buttons = lb_a; r.tick(45); r.joy_buttons = [0] * 11; r.tick(5)
        self.assertTrue(r.mux.remote_stop.latched)

    def test_restore_to_xbox_only_while_latched(self):
        r = self.armed(); r.drive(DOWN, MID, 40)
        ok, _ = r.mux.select_controller('XBOX'); self.assertFalse(ok)       # refused while released
        r.xbox_b(); r.tick(10)
        ok, why = r.mux.select_controller('XBOX'); self.assertTrue(ok, why)
        r.rx[ARM] = DOWN; r.drive(DOWN, MID, 40)
        self.assertEqual(r.last(), (0.0, 0.0))                              # FlySky no longer drives


if __name__ == '__main__':
    unittest.main()
