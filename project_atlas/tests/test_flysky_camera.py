"""FlySky camera knobs (VrA pan, VrB tilt): offline. The knob never jumps the camera, never chases failsafe values,
needs a deliberate turn to take control, is slew-limited, and releases control so the D-pad/dashboard work."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_flysky_camera as K          # noqa: E402
from atlas_flysky_drive_core import RcFrame   # noqa: E402

MID = 1024
DT = 0.04


class Sim:
    def __init__(self, pan_fb=1931, tilt_fb=1500):
        self.cam, self.t = K.KnobCamera(), 100.0
        self.cam.on_feedback('pan', pan_fb); self.cam.on_feedback('tilt', tilt_fb)
        self.ch = {9: MID, 10: MID}
        self.failsafe, self.on = False, True
        self.out = []

    def run(self, s):
        for _ in range(int(round(s / DT))):
            self.t += DT
            raw = [MID] * 16
            for c, v in self.ch.items():
                raw[c - 1] = v
            if self.failsafe:
                raw = [MID] * 16
            f = RcFrame(tuple(raw), False, self.failsafe, self.t) if self.on else None
            cmd = self.cam.step(f, self.t)
            self.out.append((self.t, cmd))
            for name, us in cmd.items():                      # the servo follows the command
                self.cam.on_feedback(name, us)

    def cmds(self, since=0):
        return [c for _, c in self.out[since:] if c]


class Knobs(unittest.TestCase):
    def test_power_on_or_resting_knob_never_moves_the_camera(self):
        for rest in (240, MID, 1807, 1400):
            s = Sim(); s.ch[9] = s.ch[10] = rest; s.run(10)
            self.assertEqual(s.cmds(), [], rest)

    def test_small_drift_does_not_take_control(self):
        s = Sim(); s.run(2); s.ch[9] = MID + 40; s.run(3)
        self.assertEqual(s.cmds(), [])

    def test_turning_vra_pans_slew_limited_from_the_current_position(self):
        s = Sim(pan_fb=1931); s.run(2)
        mark = len(s.out); s.ch[9] = 1807; s.run(0.5)
        pans = [c['pan'] for c in s.cmds(mark) if 'pan' in c]
        self.assertTrue(pans)
        self.assertLessEqual(abs(pans[0] - 1931), 400 * 0.04 + 1)            # starts at the servo, no jump
        steps = [abs(b - a) for a, b in zip(pans, pans[1:])]
        self.assertTrue(all(d <= 400 * 0.04 + 1 for d in steps))              # D-pad speed
        s.run(2.0)
        self.assertEqual(max(c.get('pan', 0) for c in s.cmds(mark)), 2300)    # reaches the knob's end
        self.assertNotIn('tilt', {k for c in s.cmds(mark) for k in c})       # VrB untouched: tilt not commanded

    def test_vrb_tilts_and_both_stay_within_servo_limits(self):
        s = Sim(); s.run(2); s.ch[10] = 240; s.run(4)
        tilts = [c['tilt'] for c in s.cmds() if 'tilt' in c]
        self.assertEqual(min(tilts), 700)
        self.assertTrue(all(700 <= v <= 2300 for c in s.cmds() for v in c.values()))

    def test_failsafe_and_signal_loss_freeze_and_drop_control(self):
        for kind in ('failsafe', 'off'):
            with self.subTest(kind):
                s = Sim(); s.run(2); s.ch[9] = 1807; s.run(1.0)
                last = [c['pan'] for c in s.cmds() if 'pan' in c][-1]
                mark = len(s.out)
                if kind == 'failsafe':
                    s.failsafe = True
                else:
                    s.on = False
                s.run(3)
                self.assertEqual(s.cmds(mark), [])                            # frozen at `last`, never chases 1024
                s.failsafe, s.on = False, True
                mark = len(s.out); s.run(5)
                self.assertEqual(s.cmds(mark), [])                            # back: needs a NEW deliberate turn
                self.assertGreater(last, 1931)

    def test_releases_control_after_the_knob_stops(self):
        s = Sim(); s.run(2); s.ch[9] = 1500; s.run(4.0)
        mark = len(s.out); s.run(3)
        self.assertEqual(s.cmds(mark), [])                                    # released: D-pad/dashboard free again
        self.assertFalse(s.cam.axes['pan'].engaged)
        s.ch[9] = 1540; s.run(1)
        self.assertEqual(s.cmds(len(s.out) - 25), [])                         # a nudge under the threshold: nothing
        s.ch[9] = 1700; s.run(1)
        self.assertTrue(s.cmds(len(s.out) - 25))                              # turned again: control back

    def test_no_servo_feedback_no_commands(self):
        s = Sim(); s.cam.axes['pan'].feedback = None; s.run(2); s.ch[9] = 1807; s.run(2)
        self.assertNotIn('pan', {k for c in s.cmds() for k in c})

    def test_reversal(self):
        self.assertEqual(K.knob_to_us(240, False), 700); self.assertEqual(K.knob_to_us(1807, False), 2300)
        self.assertEqual(K.knob_to_us(240, True), 2300); self.assertAlmostEqual(K.knob_to_us(1024, False), 1500, delta=1)

    def test_never_touches_driving_or_the_estop(self):
        code = (ROOT / 'scripts/atlas_flysky_camera.py').read_text()
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        for bad in ('cmd_vel', 'Twist', 'remote_stop', 'estop', 'reset_request', 'flysky/stop', 'serial'):
            self.assertNotIn(bad, code, bad)
        self.assertEqual(sorted(set(re.findall(r"'(/[a-z_/]+)'", code))),
                         ['/atlas/camera_tracking/enabled', '/atlas/rc/frames', '/camera/bottom_servo_cmd_us',
                          '/camera/bottom_servo_us', '/camera/second_servo_cmd_us', '/camera/second_servo_us'])


if __name__ == '__main__':
    unittest.main()
