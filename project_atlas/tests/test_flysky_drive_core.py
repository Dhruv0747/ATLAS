"""FlySky driving decision core: every fail-closed rule, offline (no ROS)."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_flysky_core as core           # noqa: E402
import atlas_flysky_drive_core as d        # noqa: E402

CFG = json.loads((ROOT / 'config/atlas_flysky_drive.json').read_text())
UP, MID, DOWN = 240, 1024, 1807


def reviewed(**over):
    c = copy.deepcopy(CFG); c['reviewed_by_owner'] = True
    c.update(over); return c


def msg(ch=None, seq=0, failsafe=False, frame_lost=False):
    vals = [MID] * 16
    # defaults: arm OFF (SwA up), stop RUN (SwB up), speed low (SwC up)
    vals[4], vals[5], vals[6] = UP, UP, UP
    for k, v in (ch or {}).items():
        vals[k - 1] = v
    return {'proto': 'sbus', 'hex': core.encode_sbus(vals, failsafe=failsafe, frame_lost=frame_lost).hex(), 'seq': seq}


class Rig:
    def __init__(self, cfg=None, gate=True):
        self.t = 100.0; self.seq = 0
        self.L = d.DriveLogic(cfg if cfg is not None else reviewed(), gate)
        self.policy()

    def policy(self, latched=False, ctrl='FLYSKY'):
        self.L.on_policy(d.Policy(self.t, latched, ctrl))

    def frame(self, ch=None, **kw):
        self.seq += 1
        self.L.on_frame(d.parse_message(msg(ch, self.seq, **kw), self.t))

    def tick(self, dt=0.05, ch=None, policy=True, frame=True, **kw):
        self.t += dt
        if policy:
            self.policy(*([] if policy is True else policy))
        if frame:
            self.frame(ch, **kw)
        return self.L.step(self.t)

    def arm(self):
        self.tick(ch={5: UP}); out = self.tick(ch={5: DOWN})
        assert out.state == 'ARMED', out
        return out


class Config(unittest.TestCase):
    def test_shipped_config_is_valid_but_unreviewed(self):
        self.assertEqual(d.validate(CFG), [])
        ok, errs = d.usable(CFG)
        self.assertFalse(ok); self.assertTrue(any('reviewed' in e for e in errs))

    def test_shipped_throttle_is_not_the_non_centring_left_stick(self):
        self.assertNotEqual(CFG['throttle']['channel'], 3)

    def test_rejections(self):
        bad = [
            dict(max_linear_mps=0.26), dict(max_angular_radps=0.81), dict(max_accel_mps2=1.5),
            dict(frame_timeout_s=0.6), dict(policy_timeout_s=2.0),
        ]
        for over in bad:
            self.assertNotEqual(d.validate(reviewed(**over)), [], over)
        c = reviewed(); c['throttle']['self_centring'] = False
        self.assertTrue(any('self_centring' in e for e in d.validate(c)))
        c = reviewed(); c['steering']['channel'] = 2
        self.assertTrue(any('share channel' in e for e in d.validate(c)))
        c = reviewed(); c['arm']['on_above'] = 1000          # a centre failsafe would read ON
        self.assertTrue(any('arm' in e for e in d.validate(c)))
        c = reviewed(); c['arm']['off_below'] = 1000         # a 992 centre would read OFF
        self.assertTrue(any('arm' in e for e in d.validate(c)))
        c = reviewed(); c['stop']['run_below'] = 1100        # a centre failsafe would read RUN
        self.assertTrue(any('stop' in e for e in d.validate(c)))
        c = reviewed(); c['throttle']['deadband'] = 0.0
        self.assertTrue(any('deadband' in e for e in d.validate(c)))
        c = reviewed(); c['throttle']['max'] = 1100
        self.assertTrue(d.validate(c))
        self.assertTrue(d.validate('nope'))


class Gating(unittest.TestCase):
    def test_gate_off_publishes_nothing_even_if_reviewed(self):
        r = Rig(gate=False); r.tick(ch={5: UP}); out = r.tick(ch={5: DOWN, 2: DOWN})
        self.assertEqual((out.state, out.command, out.stop_request), ('DISABLED', None, False))

    def test_unreviewed_config_publishes_nothing(self):
        r = Rig(cfg=copy.deepcopy(CFG)); r.tick(ch={5: UP}); out = r.tick(ch={5: DOWN})
        self.assertEqual((out.state, out.command), ('DISABLED', None))

    def test_not_selected_publishes_nothing(self):
        r = Rig(); out = r.tick(policy=(False, 'XBOX'), ch={5: DOWN})
        self.assertEqual((out.state, out.command, out.stop_request), ('NOT_SELECTED', None, False))

    def test_stale_policy_zeroes(self):
        r = Rig(); r.arm(); out = r.tick(dt=0.6, policy=False, ch={5: DOWN, 2: DOWN})
        self.assertEqual((out.state, out.command), ('POLICY_STALE', (0.0, 0.0)))
        self.assertTrue(out.stop_request)

    def test_latched_estop_zeroes_and_needs_rearm(self):
        r = Rig(); r.arm()
        out = r.tick(policy=(True, 'FLYSKY'), ch={5: DOWN, 2: DOWN})
        self.assertEqual((out.state, out.command), ('STOP_LATCHED', (0.0, 0.0)))
        out = r.tick(ch={5: DOWN, 2: MID})                    # released, arm still ON: must cycle
        self.assertEqual(out.state, 'WAIT_ARM_OFF')


class Arming(unittest.TestCase):
    def test_no_arm_through_at_start(self):
        r = Rig(); out = r.tick(ch={5: DOWN})
        self.assertEqual((out.state, out.command), ('WAIT_ARM_OFF', (0.0, 0.0)))

    def test_arm_needs_centred_throttle(self):
        r = Rig(); r.tick(ch={5: UP}); out = r.tick(ch={5: DOWN, 2: DOWN})
        self.assertEqual(out.state, 'WAIT_NEUTRAL')
        self.assertEqual(out.command, (0.0, 0.0))
        out = r.tick(ch={5: DOWN, 2: MID}); self.assertEqual(out.state, 'ARMED')

    def test_arm_off_disarms_without_latch(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: UP, 2: DOWN})
        self.assertEqual((out.state, out.command, out.stop_request), ('WAIT_ARM_ON', (0.0, 0.0), False))

    def test_centre_value_failsafe_without_flags_cannot_drive(self):
        # A receiver whose failsafe output is "every channel centre" and which does NOT set the flag.
        r = Rig(); r.arm()
        out = r.tick(ch={5: MID, 6: MID, 2: MID})
        self.assertEqual(out.command, (0.0, 0.0)); self.assertNotEqual(out.state, 'ARMED')
        out = r.tick(ch={5: MID, 6: UP, 2: DOWN})
        self.assertEqual(out.command, (0.0, 0.0)); self.assertEqual(out.state, 'INVALID_INPUT')


class Driving(unittest.TestCase):
    def test_full_forward_is_capped_and_slew_limited(self):
        r = Rig(); r.arm(); outs = [r.tick(ch={5: DOWN, 2: DOWN, 7: DOWN}) for _ in range(40)]
        lins = [o.command[0] for o in outs]
        self.assertTrue(all(b >= a for a, b in zip(lins, lins[1:])))
        self.assertLessEqual(lins[0], CFG['max_accel_mps2'] * 0.05 + 1e-9)
        self.assertAlmostEqual(lins[-1], CFG['max_linear_mps'])
        self.assertLessEqual(max(lins), d.HARD_MAX_LINEAR_MPS)

    def test_release_is_immediate(self):
        r = Rig(); r.arm()
        for _ in range(40):
            r.tick(ch={5: DOWN, 2: DOWN, 7: DOWN})
        out = r.tick(ch={5: DOWN, 2: MID, 7: DOWN})
        self.assertEqual(out.command, (0.0, 0.0))

    def test_reverse_goes_through_zero(self):
        r = Rig(); r.arm()
        for _ in range(20):
            r.tick(ch={5: DOWN, 2: DOWN, 7: DOWN})
        out = r.tick(ch={5: DOWN, 2: UP, 7: DOWN})
        self.assertEqual(out.command[0], 0.0)
        out = r.tick(ch={5: DOWN, 2: UP, 7: DOWN}); self.assertLess(out.command[0], 0.0)

    def test_steering_direction_and_speed_mode(self):
        r = Rig(); r.arm()
        right = r.tick(ch={5: DOWN, 4: DOWN, 7: DOWN}).command[1]
        self.assertLess(right, 0.0)                           # stick right -> negative yaw (clockwise, ROS REP-103)
        self.assertAlmostEqual(abs(right), CFG['max_angular_radps'])
        low = r.tick(ch={5: DOWN, 4: DOWN, 7: UP}).command[1]
        self.assertAlmostEqual(abs(low), CFG['max_angular_radps'] * 0.33)

    def test_deadband(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: DOWN, 2: MID + 50, 4: MID - 50})
        self.assertEqual(out.command, (0.0, 0.0))

    def test_impossible_reading_zeroes(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: DOWN, 2: 2000})
        self.assertEqual((out.state, out.command), ('INVALID_INPUT', (0.0, 0.0)))


class Inputs(unittest.TestCase):
    def test_inputs_report_what_the_logic_sees(self):
        r = Rig(); self.assertIsNone(r.L.inputs())
        r.tick(ch={5: MID, 6: DOWN, 2: DOWN, 7: DOWN})
        i = r.L.inputs()
        self.assertEqual((i['arm'], i['stop'], i['speed_scale']), ('INVALID', 'STOP', 1.0))
        self.assertAlmostEqual(i['throttle'], 1.0)


class SignalLoss(unittest.TestCase):
    def test_stale_frames_zero_and_request_latch_until_confirmed(self):
        r = Rig(); r.arm(); r.tick(ch={5: DOWN, 2: DOWN})
        out = r.tick(dt=0.35, frame=False)
        self.assertEqual((out.state, out.command, out.stop_request), ('NO_SIGNAL', (0.0, 0.0), True))
        again = [r.tick(dt=0.1, frame=False).stop_request for _ in range(12)]
        self.assertGreaterEqual(sum(again), 2)                # re-requested while the mux has not latched
        out = r.tick(policy=(True, 'FLYSKY'), frame=False)
        self.assertEqual(out.state, 'STOP_LATCHED')
        out = r.tick(frame=True, ch={5: DOWN}); self.assertFalse(out.stop_request); self.assertEqual(out.state, 'WAIT_ARM_OFF')

    def test_repeated_frame_is_not_fresh(self):
        r = Rig(); r.arm()
        m = msg({5: DOWN}, seq=999)
        r.L.on_frame(d.parse_message(m, r.t))
        r.t += 0.35; r.policy(); r.L.on_frame(d.parse_message(m, r.t))   # same seq again
        self.assertEqual(r.L.step(r.t).state, 'NO_SIGNAL')

    def test_failsafe_flag_zeroes_and_latches(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: DOWN, 2: DOWN}, failsafe=True)
        self.assertEqual((out.state, out.command, out.stop_request), ('FAILSAFE', (0.0, 0.0), True))

    def test_frame_lost_flag_zeroes_and_disarms(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: DOWN, 2: DOWN}, frame_lost=True)
        self.assertEqual((out.state, out.command), ('FRAME_LOST', (0.0, 0.0)))
        self.assertEqual(r.tick(ch={5: DOWN}).state, 'WAIT_ARM_OFF')

    def test_stop_switch_requests_latch(self):
        r = Rig(); r.arm(); out = r.tick(ch={5: DOWN, 6: DOWN, 2: DOWN})
        self.assertEqual((out.state, out.command, out.stop_request), ('STOP_SWITCH', (0.0, 0.0), True))

    def test_malformed_messages_are_ignored(self):
        for m in (None, {}, {'proto': 'ibus', 'hex': '00'}, {'proto': 'sbus', 'hex': 'zz'}, {'proto': 'sbus', 'hex': '0f00'}):
            self.assertIsNone(d.parse_message(m, 0.0))
        self.assertIsNone(d.parse_policy('not json', 0.0)); self.assertIsNone(d.parse_policy('{"stop_latched": 1}', 0.0))
        p = d.parse_policy('{"stop_latched": false}', 0.0); self.assertEqual(p.manual_controller, 'XBOX')


if __name__ == '__main__':
    unittest.main()
