"""Stage 29 FlySky SwD E-STOP reset: offline fault injection, end to end (real drive core + real gesture -> the LIVE
mux with the Stage 29 patch AND the reset patch -> real Xbox RemoteStop), on one simulated 50 ms clock.
Every assertion is about the latch and about what reaches /cmd_vel. Simulation only: no physical result is claimed."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests')); sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools/deploy/stage29_flysky_drive'))
import test_flysky_mux_patch as M               # noqa: E402
import test_flysky_commissioning_offline as C   # noqa: E402
import atlas_flysky_drive_core as dc            # noqa: E402
import atlas_flysky_reset as R                  # noqa: E402
import insert_flysky_reset_mux as RP            # noqa: E402
import deploy_stage29 as D                      # noqa: E402

REVIEWED = dict(copy.deepcopy(C.CFG), reviewed_by_owner=True, **D.COMMISSION_CAPS)
UP, MID, DOWN = C.UP, C.MID, C.DOWN
TH, ST, ARM, STOP, SPD, SWD = C.TH, C.ST, C.ARM, C.STOP, C.SPD, R.RESET_CHANNEL
M.METHODS |= {'on_encoder_health', 'flysky_reset_observe', 'on_flysky_reset_request', 'on_voice_stop'}


def build_mux(clock):
    text = RP.apply(M.patch.apply(M.BASELINE.read_text()))
    cls, Channel, _ = M.build(text, clock)
    return cls, Channel, text


class Rover(C.Rover):
    """The commissioning rover, with the reset-patched mux, the gesture in the teleop, and simulated encoders."""

    def __init__(self, reset_gate=True, drive_gate=True):
        super().__init__(reviewed=True, gate=drive_gate)
        old = self.mux
        cls, Channel, self.text = build_mux(lambda: self.t)
        m = cls()                                       # the builder keeps only the methods under test (no __init__)
        m.__dict__.update(old.__dict__)                 # same harness state as the commissioning rover
        m.flysky_reset_gate = R.MuxResetGate(reset_gate)
        m.output.publish.side_effect = lambda tw: self.outs.append((self.t, tw.linear.x, tw.angular.z))
        self.mux = m
        self.teleop = dc.DriveLogic(copy.deepcopy(REVIEWED), drive_gate)
        self.gesture = R.ResetGesture(reset_gate, seq=1_000)
        self.rx.update({SPD: MID, SWD: UP})
        self.requests, self.hand_turn, self.encoders_on = [], False, True

    def tick(self, n=1):
        for _ in range(n):
            super().tick(1)
            req = self.gesture.step(self.teleop, self.t) if self.teleop_alive else None
            if req is not None:
                self.requests.append(req)
                self.mux.on_flysky_reset_request(M.String(json.dumps(req)))
            if self.encoders_on and self.n % 2 == 0:     # /atlas/encoder_health at 10 Hz
                lin = self.outs[-1][1] if self.outs else 0.0
                moving = abs(lin) > 1e-6 or self.hand_turn
                d = [0.004 if moving else 0.0] * 4
                self.mux.on_encoder_health(M.String(json.dumps({'state': 'READY', 'packet_fresh': True,
                                                                'encoder_interval_delta_m': d})))

    def ready(self):
        """FlySky selected, latched, every precondition true and settled."""
        self.tick(10)
        ok, why = self.mux.select_controller('FLYSKY'); assert ok, why
        self.tick(90)                                   # > 3 s healthy link + 1 s SwD up, > 2 s latched
        assert self.mux.remote_stop.latched

    def swd_gesture(self, up_s=1.2, hold_s=2.5):
        self.rx[SWD] = UP; self.tick(int(up_s / C.DT))
        self.rx[SWD] = DOWN; self.tick(int(hold_s / C.DT))
        self.rx[SWD] = UP; self.tick(4)

    def released(self):
        return not self.mux.remote_stop.latched

    def zero_since(self, mark):
        return all(lx == 0.0 and az == 0.0 for _, lx, az in self.outs[mark:])

    def policy_reset(self):
        return json.loads(self.policy())['flysky_reset']


class Gesture(unittest.TestCase):
    def test_reset_releases_but_nothing_moves_until_a_fresh_arm(self):
        r = Rover(); r.ready(); mark = len(r.outs)
        r.swd_gesture()
        self.assertTrue(r.released(), r.policy_reset())
        self.assertEqual(r.mux.remote_stop.reason, 'REMOTE STOP: released by FlySky SwD reset')
        self.assertEqual(len(r.requests), 1)
        r.drive(DOWN, MID, 40)                            # stick up without arming: still zero
        self.assertTrue(r.zero_since(mark)); self.assertFalse(r.teleop.armed)
        r.rx[TH] = MID; r.tick(4); r.rx[ARM] = DOWN; r.tick(4)
        self.assertTrue(r.teleop.armed)
        r.drive(DOWN, MID, 60)
        self.assertGreater(r.last()[0], 0.0); self.assertLessEqual(r.last()[0], 0.05 * 0.66 + 1e-9)

    def test_single_quick_flip_never_releases(self):
        for hold in (0.1, 0.5, 1.0, 1.9):
            r = Rover(); r.ready(); r.swd_gesture(hold_s=hold)
            self.assertFalse(r.released(), hold); self.assertEqual(r.requests, [], hold)

    def test_stuck_switch_never_releases(self):
        r = Rover(); r.ready(); r.swd_gesture(hold_s=6.0)
        self.assertFalse(r.released()); self.assertEqual(r.requests, [])
        r.rx[SWD] = DOWN; r.tick(200)                      # left down for 10 s more
        self.assertFalse(r.released())

    def test_power_on_or_selection_with_swd_down_never_releases(self):
        r = Rover(); r.rx[SWD] = DOWN; r.ready()           # SwD already down when everything became ready
        r.tick(60); r.rx[SWD] = UP; r.tick(10)
        self.assertFalse(r.released())
        self.assertEqual(r.gesture.state, 'WAIT_SWD_UP')

    def test_early_down_before_one_second_up_does_not_count(self):
        r = Rover(); r.rx[SWD] = DOWN; r.ready()          # not qualified: SwD was never UP for 1 s
        r.swd_gesture(up_s=0.5, hold_s=2.5)
        self.assertFalse(r.released())
        r.swd_gesture(up_s=1.2, hold_s=2.5)               # the proper gesture then works
        self.assertTrue(r.released())

    def test_every_broken_precondition_blocks(self):
        breaks = {
            'SwA on (armed position)':   lambda r: r.rx.__setitem__(ARM, DOWN),
            'SwA between (centre)':      lambda r: r.rx.__setitem__(ARM, MID),
            'SwB at STOP':               lambda r: r.rx.__setitem__(STOP, DOWN),
            'SwB middle':                lambda r: r.rx.__setitem__(STOP, MID),
            'throttle off centre':       lambda r: r.rx.__setitem__(TH, 1300),
            'steering off centre':       lambda r: r.rx.__setitem__(ST, 1300),
            'SwD centre value':          lambda r: r.rx.__setitem__(SWD, MID),
        }
        for name, brk in breaks.items():
            with self.subTest(name):
                r = Rover(); r.ready(); brk(r); r.tick(4)
                self.assertEqual(r.gesture.state, 'BLOCKED' if name != 'SwD centre value' else 'BLOCKED')
                self.assertTrue(r.gesture.blocked)
                r.rx[SWD] = UP if name != 'SwD centre value' else MID; r.tick(30)
                r.rx[SWD] = DOWN if name != 'SwD centre value' else MID; r.tick(50)
                r.rx[SWD] = UP if name != 'SwD centre value' else MID; r.tick(4)
                self.assertFalse(r.released(), name); self.assertEqual(r.requests, [], name)

    def test_break_in_the_middle_of_the_hold_aborts(self):
        for name, key, val in (('arm', ARM, DOWN), ('stop', STOP, DOWN), ('stick', TH, 1400)):
            with self.subTest(name):
                r = Rover(); r.ready()
                r.rx[SWD] = UP; r.tick(25); r.rx[SWD] = DOWN; r.tick(20)
                good = r.rx.get(key, MID); r.rx[key] = val; r.tick(2); r.rx[key] = good
                r.tick(30); r.rx[SWD] = UP; r.tick(4)
                self.assertFalse(r.released(), name)

    def test_transmitter_off_and_signal_restoration(self):
        r = Rover(); r.ready()
        r.rx[SWD] = UP; r.tick(25); r.rx[SWD] = DOWN; r.tick(20)
        r.tx_on = False; r.tick(10)                         # link lost mid-hold (failsafe frames)
        r.tx_on = True; r.tick(30); r.rx[SWD] = UP; r.tick(4)
        self.assertFalse(r.released())
        # restored link: the full gesture right after restoration is refused until 3 s of healthy link
        r = Rover(); r.ready(); r.tx_on = False; r.failsafe_frames = True; r.tick(20)
        r.tx_on = True; r.rx[SWD] = UP; r.tick(10)          # 0.5 s after restoration
        self.assertIn('receiver link healthy', ' '.join(r.gesture.blocked))
        r.rx[SWD] = DOWN; r.tick(50); r.rx[SWD] = UP; r.tick(4)
        self.assertFalse(r.released())

    def test_receiver_silent_blocks(self):
        r = Rover(); r.ready(); r.tx_on = False; r.failsafe_frames = False; r.tick(20)
        self.assertEqual(r.gesture.state, 'BLOCKED')
        self.assertIn('receiver not LIVE', r.gesture.blocked[0])


class MuxChecks(unittest.TestCase):
    def test_xbox_off_blocks_and_xbox_absence_still_latches(self):
        r = Rover(); r.ready(); r.xbox_on = False
        r.swd_gesture()
        self.assertFalse(r.released())
        self.assertEqual(r.mux.remote_stop.reason, 'REMOTE STOP: joystick unavailable')

    def test_xbox_button_held_blocks(self):
        for button in (0, 1, 4, 7):
            with self.subTest(button=button):
                r = Rover(); r.ready()
                b = [0] * 11; b[button] = 1; r.joy_buttons = b
                r.swd_gesture()
                self.assertFalse(r.released(), button)

    def test_rover_moving_or_wheel_turned_by_hand_blocks(self):
        r = Rover(); r.ready(); r.hand_turn = True
        r.swd_gesture()
        self.assertFalse(r.released())
        self.assertIn('stationary', r.policy_reset()['last_reason'])

    def test_encoders_stale_block(self):
        r = Rover(); r.ready(); r.encoders_on = False; r.tick(20)
        r.swd_gesture()
        self.assertFalse(r.released()); self.assertIn('stationary', r.policy_reset()['last_reason'])

    def test_not_selected_or_gates_off_block(self):
        r = Rover(); r.tick(70); r.swd_gesture()           # Xbox still the selected controller
        self.assertFalse(r.released()); self.assertEqual(r.requests, [])
        self.assertEqual(r.gesture.state, 'UNAVAILABLE')
        r = Rover(reset_gate=False); r.ready(); r.swd_gesture()
        self.assertFalse(r.released()); self.assertEqual(r.gesture.state, 'OFF')
        # teleop gesture on but the MUX gate off (mismatched rollout): the mux refuses
        r = Rover(); r.mux.flysky_reset_gate.enabled = False; r.ready(); r.swd_gesture()
        self.assertFalse(r.released()); self.assertIn('reset is off', r.policy_reset()['last_reason'])

    def test_stale_replayed_and_rapid_requests_are_refused(self):
        r = Rover(); r.ready()
        g = r.mux.flysky_reset_gate
        req = lambda seq, t, hold=2.5: M.String(json.dumps({'gesture': R.GESTURE, 'seq': seq, 't_mono': t,
                                                            'hold_s': hold, 'channel': R.RESET_CHANNEL}))
        r.mux.on_flysky_reset_request(req(5_000, r.t - 1.0)); self.assertFalse(r.released())
        self.assertIn('stale', g.last_reason)
        r.mux.on_flysky_reset_request(req(5_000, r.t)); self.assertFalse(r.released())
        self.assertIn('repeated', g.last_reason)
        r.mux.on_flysky_reset_request(req(5_001, r.t, hold=0.5)); self.assertIn('hold time', g.last_reason)
        r.mux.on_flysky_reset_request(M.String('garbage')); self.assertFalse(r.released())
        r.mux.on_flysky_reset_request(req(5_002, r.t)); self.assertTrue(r.released())      # a good one works
        r.xbox_b(); r.tick(50)
        r.mux.on_flysky_reset_request(req(5_003, r.t)); self.assertFalse(r.released())
        self.assertIn('less than 3 s ago', g.last_reason)
        r.mux.on_flysky_reset_request(req(5_002, r.t)); self.assertIn('repeated', g.last_reason)

    def test_must_be_latched_for_two_seconds(self):
        r = Rover(); r.ready(); r.swd_gesture(); self.assertTrue(r.released())
        r.tick(70); r.mux.on_voice_stop(None); r.tick(4)    # dashboard stop, then an immediate request
        req = {'gesture': R.GESTURE, 'seq': 9_999_999, 't_mono': r.t, 'hold_s': 2.5, 'channel': R.RESET_CHANNEL}
        r.mux.on_flysky_reset_request(M.String(json.dumps(req)))
        self.assertFalse(r.released()); self.assertIn('latched less than', r.mux.flysky_reset_gate.last_reason)

    def test_handover_during_gesture_aborts(self):
        r = Rover(); r.ready()
        r.rx[SWD] = UP; r.tick(25); r.rx[SWD] = DOWN; r.tick(20)
        ok, _ = r.mux.select_controller('XBOX'); self.assertTrue(ok); r.tick(5)
        ok, _ = r.mux.select_controller('FLYSKY'); self.assertTrue(ok)
        r.tick(25); r.rx[SWD] = UP; r.tick(4)
        self.assertFalse(r.released())


class EachCheckAlone(unittest.TestCase):
    """Every check is proven on its own (several are also backed by a second check end to end)."""
    ENC = {'state': 'READY', 'packet_fresh': True, 'encoder_interval_delta_m': [0.0] * 4}

    def gate(self, now=100.0):
        g = R.MuxResetGate(True)
        g.observe(now - 5.0, True, False, self.ENC, now - 5.0)       # latched and still since 95 s
        return g

    def decide(self, g, now=100.0, seq=1, **over):
        kw = dict(drive_enabled=True, controller='FLYSKY', latched=True, commanding=False, xbox_rx=now - 0.05,
                  xbox_neutral_since=now - 3.0, enc=self.ENC, enc_rx=now - 0.05)
        kw.update(over)
        req = json.dumps({'gesture': R.GESTURE, 'seq': seq, 't_mono': now, 'hold_s': 2.5, 'channel': R.RESET_CHANNEL})
        return g.decide(now, req, **kw)

    def test_all_good_releases(self):
        self.assertTrue(self.decide(self.gate())[0])

    def test_each_mux_condition_alone_refuses(self):
        for name, over in {'xbox stale': dict(xbox_rx=99.0), 'xbox never seen': dict(xbox_rx=None),
                           'xbox touched recently': dict(xbox_neutral_since=99.6),
                           'commanding': dict(commanding=True), 'not latched': dict(latched=False),
                           'xbox selected': dict(controller='XBOX'), 'drive gate off': dict(drive_enabled=False),
                           'encoders stale': dict(enc_rx=99.0),
                           'encoder fault': dict(enc=dict(self.ENC, state='DEGRADED')),
                           'encoder packet old': dict(enc=dict(self.ENC, packet_fresh=False)),
                           'wheel moving': dict(enc=dict(self.ENC, encoder_interval_delta_m=[0, 0, 0.002, 0]))}.items():
            with self.subTest(name):
                self.assertFalse(self.decide(self.gate(), **over)[0], name)

    def test_stationary_must_last_one_second(self):
        g = R.MuxResetGate(True)
        g.observe(90.0, True, False, self.ENC, 90.0)
        g.observe(99.5, True, False, dict(self.ENC, encoder_interval_delta_m=[0.01] * 4), 99.5)   # moved at 99.5
        g.observe(99.6, True, False, self.ENC, 99.6)
        ok, why = self.decide(g); self.assertFalse(ok); self.assertIn('stationary', why)

    def test_gesture_states_alone(self):
        r = Rover(); r.ready()
        r.rx[SWD] = DOWN; r.tick(110)                      # held 5.5 s
        self.assertEqual(r.gesture.state, 'WAIT_SWD_UP'); self.assertIn('stuck', r.gesture.blocked[0])
        r = Rover(); r.rx[SWD] = DOWN; r.ready()
        self.assertEqual(r.gesture.state, 'WAIT_SWD_UP'); self.assertIsNone(r.gesture.down_since)
        r = Rover(); r.ready(); r.rx[SWD] = DOWN; r.tick(20)
        self.assertEqual(r.gesture.state, 'HOLDING'); r.tick(25)
        self.assertEqual(r.gesture.state, 'RELEASE_NOW')


class StopsStillWork(unittest.TestCase):
    def armed_after_flysky_reset(self):
        r = Rover(); r.ready(); r.swd_gesture(); assert r.released()
        r.rx[ARM] = DOWN; r.tick(4); r.drive(DOWN, MID, 40); assert r.last()[0] > 0
        return r

    def test_every_stop_still_latches_and_zeroes(self):
        stops = {'xbox_b': lambda r: r.xbox_b(), 'swb_down': lambda r: r.rx.__setitem__(STOP, DOWN),
                 'swb_middle': lambda r: r.rx.__setitem__(STOP, MID), 'dashboard': lambda r: r.mux.on_voice_stop(None),
                 'xbox_off': lambda r: setattr(r, 'xbox_on', False), 'tx_off': lambda r: setattr(r, 'tx_on', False)}
        for name, ev in stops.items():
            with self.subTest(name):
                r = self.armed_after_flysky_reset()
                dt = r.time_to_zero(lambda: ev(r))
                self.assertLessEqual(dt, 1.3, name); self.assertTrue(r.mux.remote_stop.latched, name)

    def test_swa_off_still_stops(self):
        r = self.armed_after_flysky_reset()
        dt = r.time_to_zero(lambda: r.rx.__setitem__(ARM, UP)); self.assertLessEqual(dt, 0.15)

    def test_xbox_lb_reset_still_works(self):
        r = Rover(); r.ready(); r.rx[SWD] = UP
        r.xbox_lb_reset(); self.assertTrue(r.released())
        self.assertEqual(r.mux.remote_stop.reason, 'REMOTE STOP: released by neutral LB hold')

    def test_reset_again_after_a_stop_needs_the_full_gesture_and_a_fresh_arm(self):
        r = self.armed_after_flysky_reset()
        r.rx[STOP] = DOWN; r.tick(10); r.rx[STOP] = UP; r.tick(4)
        self.assertTrue(r.mux.remote_stop.latched)
        r.rx[ARM] = UP; r.rx[TH] = MID; r.tick(70)
        r.swd_gesture(); self.assertTrue(r.released())
        mark = len(r.outs); r.drive(DOWN, MID, 30); self.assertTrue(r.zero_since(mark))   # SwA still OFF
        r.rx[TH] = MID; r.tick(2); r.rx[ARM] = DOWN; r.tick(4); r.drive(DOWN, MID, 30)
        self.assertGreater(r.last()[0], 0.0)

    def test_reboot_starts_latched_and_needs_everything_again(self):
        r = Rover(); r.rx[SWD] = DOWN                       # transmitter left with SwD down overnight
        self.assertTrue(r.mux.remote_stop.latched)
        r.ready(); self.assertFalse(r.released())
        r.rx[SWD] = UP; r.tick(4); self.assertFalse(r.released())


class Source(unittest.TestCase):
    def test_reset_patch_is_additive_and_needs_the_stage29_mux(self):
        base = M.patch.apply(M.BASELINE.read_text())
        out = RP.apply(base)
        compile(out, 'mux', 'exec')
        removed = [l for l in base.splitlines() if l not in out.splitlines()]
        self.assertEqual(removed, [])
        with self.assertRaises(SystemExit):
            RP.apply(M.BASELINE.read_text())             # not the Stage 29 mux
        with self.assertRaises(SystemExit):
            RP.apply(out)                                # twice

    def test_reset_never_commands_motion(self):
        src = (ROOT / 'scripts/atlas_flysky_reset.py').read_text()
        for bad in ('Twist', 'cmd_vel', 'publish', 'serial', 'latched = False', '.latched=False'):
            self.assertNotIn(bad, src.split('"""', 2)[2], bad)
        patch_src = (ROOT / 'tools/deploy/stage29_flysky_drive/insert_flysky_reset_mux.py').read_text()
        self.assertEqual(patch_src.count('rs.latched, rs.reason = False, why'), 1)    # one release, after all checks

    def test_ch8_is_free_in_the_reviewed_config(self):
        self.assertIsNone(R.channel_conflict(REVIEWED))
        bad = copy.deepcopy(REVIEWED); bad['speed_mode']['channel'] = 8
        self.assertIn('CH8', R.channel_conflict(bad))


if __name__ == '__main__':
    unittest.main()
