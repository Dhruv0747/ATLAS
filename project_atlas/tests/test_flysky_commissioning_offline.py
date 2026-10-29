"""Stage 29 commissioning, offline and end to end: real drive core -> patched LIVE mux -> real Xbox RemoteStop.

Until now the core and the mux were tested separately. Here the teleop's output feeds mux.on_command / on_flysky_stop,
the mux's published policy feeds the teleop, and everything ticks on one simulated 50 ms clock (teleop 20 Hz, mux
watchdog 20 Hz, receiver frames 10 Hz, Xbox /joy ~16 Hz). Every assertion is about what reaches /cmd_vel."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests')); sys.path.insert(0, str(ROOT / 'scripts'))
import test_flysky_mux_patch as M          # noqa: E402  (mux builder on the live baseline)
import atlas_flysky_core as core           # noqa: E402
import atlas_flysky_drive_core as dc       # noqa: E402
from atlas_remote_stop import RemoteStop   # noqa: E402

M.METHODS.add('on_voice_stop')            # exercise the real voice/dashboard stop-only input too

CFG = json.loads((ROOT / 'config/atlas_flysky_drive.json').read_text())
UP, MID, DOWN = 240, 1024, 1807
TH, ST, ARM, STOP, SPD = (CFG[k]['channel'] for k in ('throttle', 'steering', 'arm', 'stop', 'speed_mode'))
DT = 0.05


class Rover:
    def __init__(self, reviewed=True, gate=True):
        self.t = 100.0
        cfg = copy.deepcopy(CFG); cfg['reviewed_by_owner'] = reviewed
        self.teleop = dc.DriveLogic(cfg, gate)
        cls, Channel, _ = M.build(M.patch.apply(M.BASELINE.read_text()), lambda: self.t)
        m = cls()
        m.remote_stop = RemoteStop()
        m.manual_only, m.commission_until = True, 0.0
        m.manual_controller, m.flysky_drive_enabled = 'XBOX', gate
        m.flysky_max_linear, m.flysky_max_angular = 0.15, 0.60
        m.remote_linear_deadband, m.remote_angular_deadband, m.remote_steer_hold_s = 0.06, 0.12, 0.35
        m._remote_held_yaw = m._remote_last_steer_rx = m._remote_raw_steer = m._remote_raw_steer_rx = 0.0
        m.operating_mode, m.radar_gate_enabled = 'MANUAL', False
        m.encoder_health, m.encoder_health_rx = {}, 0.0
        m.mapping_remote_max_linear, m.mapping_remote_max_angular = 0.3, 1.2
        m.channels = {n: Channel(n, tp, p, 0.35) for n, tp, p in (
            ('REMOTE', '/cmd_vel_joy', 1), ('FLYSKY', '/cmd_vel_flysky', 1), ('COMMISSION', '/cmd_vel_commission', 2),
            ('RECOVERY', '/cmd_vel_recovery', 3), ('WEB', '/cmd_vel_web', 4), ('NAV2', '/cmd_vel_nav', 6))}
        m.active_name, m.last_sent = None, M.Twist()
        m._remote_stop_hold_latched = m._remote_stop_hold_reason = None
        m._remote_stop_last_zero = m._remote_stop_last_status = float('-inf')
        m.output, m.safety_output, m.mode_output, m.policy_output = Mock(), Mock(), Mock(), Mock()
        m.get_logger = lambda: NS(warn=lambda *a: None, error=lambda *a: None, info=lambda *a: None)
        self.mux = m
        self.rx = {ARM: UP, STOP: UP, SPD: DOWN}     # transmitter on, arm OFF, RUN, 100 % of the (low) test limit
        self.tx_on, self.failsafe_frames, self.xbox_on, self.teleop_alive = True, False, True, True
        self.joy_buttons = [0] * 11
        self.seq, self.n, self.stop_requests = 0, 0, 0
        self.outs = []                              # (t, linear, angular) every /cmd_vel publish
        m.output.publish.side_effect = lambda tw: self.outs.append((self.t, tw.linear.x, tw.angular.z))

    def policy(self):
        self.mux.publish_mode()
        return self.mux.policy_output.publish.call_args[0][0].data

    def tick(self, n=1):
        for _ in range(n):
            self.t += DT; self.n += 1
            if self.xbox_on and self.n % 1 == 0:
                self.mux.on_stop_joy(NS(axes=[0.0] * 6, buttons=list(self.joy_buttons)))
            if self.n % 2 == 0 and (self.tx_on or self.failsafe_frames):
                vals = [MID] * 16
                for ch, v in self.rx.items():
                    vals[ch - 1] = v
                if not self.tx_on:                  # FS-iA receiver after transmitter loss: centre values + flag
                    vals = [MID] * 16
                self.seq += 1
                f = core.encode_sbus(vals, failsafe=not self.tx_on)
                self.teleop.on_frame(dc.parse_message({'proto': 'sbus', 'hex': f.hex(), 'seq': self.seq}, self.t))
            self.teleop.on_policy(dc.parse_policy(self.policy(), self.t))
            if self.teleop_alive:
                out = self.teleop.step(self.t)
                if out.stop_request:
                    self.stop_requests += 1
                    self.mux.on_flysky_stop(None)
                if out.command is not None:
                    self.mux.on_command('FLYSKY', M.tw(*out.command))
            self.mux.watchdog()

    def last(self):
        return self.outs[-1][1:] if self.outs else (0.0, 0.0)

    def xbox_lb_reset(self):
        lb = [0] * 11; lb[4] = 1
        self.joy_buttons = lb; self.tick(45)          # > 2 s hold with sticks centred
        self.joy_buttons = [0] * 11; self.tick(2)

    def xbox_b(self):
        b = [0] * 11; b[1] = 1
        self.joy_buttons = b; self.tick(1); self.joy_buttons = [0] * 11; self.tick(1)

    def commission_to_armed(self):
        self.tick(10)
        ok, why = self.mux.select_controller('FLYSKY'); assert ok, why
        self.xbox_lb_reset(); assert not self.mux.remote_stop.latched
        self.tick(4); self.rx[ARM] = DOWN; self.tick(4)
        assert self.teleop.armed, self.teleop.step(self.t)

    def drive(self, throttle=DOWN, steer=MID, ticks=40):
        self.rx[TH], self.rx[ST] = throttle, steer
        self.tick(ticks)

    def time_to_zero(self, event):
        """Ticks after `event` until the last /cmd_vel publish is zero and stays zero for 0.5 s."""
        t0, mark = self.t, len(self.outs); event(); self.tick(20)
        # Order by publish index (simulated time does not advance inside a tick, so timestamps can tie).
        idx = next((i for i in range(mark, len(self.outs)) if self.outs[i][1] == 0.0 and self.outs[i][2] == 0.0), None)
        assert idx is not None, 'never stopped'
        assert all(lx == 0.0 and az == 0.0 for _, lx, az in self.outs[idx:]), 'motion resumed after the stop'
        return round(self.outs[idx][0] - t0, 3)


class Commissioning(unittest.TestCase):
    def test_full_sequence_reaches_cmd_vel_within_limits(self):
        r = Rover(); r.commission_to_armed()
        self.assertEqual(r.last(), (0.0, 0.0))                          # armed with throttle centred: still zero
        r.drive(throttle=DOWN, steer=DOWN)
        lx, az = r.last()
        self.assertAlmostEqual(lx, CFG['max_linear_mps']); self.assertAlmostEqual(az, -CFG['max_angular_radps'])
        self.assertEqual(r.mux.active_name, 'FLYSKY')

    def test_nothing_drives_before_each_gate(self):
        r = Rover(); r.tick(10)
        r.rx[ARM] = DOWN; r.drive()                                     # Xbox selected: FlySky ignored
        self.assertTrue(all(lx == 0.0 for _, lx, _ in r.outs))
        self.assertTrue(r.mux.select_controller('FLYSKY')[0]); r.drive()   # selected but latched
        self.assertTrue(all(lx == 0.0 for _, lx, _ in r.outs))
        r.rx[TH] = MID; r.xbox_lb_reset(); r.rx[TH] = DOWN; r.drive()   # released, arm was ON throughout: no arm-through
        self.assertTrue(all(lx == 0.0 for _, lx, _ in r.outs))
        self.assertEqual(r.teleop.step(r.t).state, 'WAIT_ARM_OFF')

    def test_unreviewed_or_gate_off_never_drives(self):
        for kw in ({'reviewed': False}, {'gate': False}):
            r = Rover(**kw); r.tick(10)
            ok, _ = r.mux.select_controller('FLYSKY')
            if ok:
                r.xbox_lb_reset()
            r.rx[ARM] = UP; r.tick(4); r.rx[ARM] = DOWN; r.drive()
            self.assertTrue(all(lx == 0.0 for _, lx, _ in r.outs), kw)


class StopPaths(unittest.TestCase):
    def armed_and_driving(self):
        r = Rover(); r.commission_to_armed(); r.drive(throttle=DOWN, ticks=40)
        self.assertGreater(r.last()[0], 0.0)
        return r

    def test_transmitter_off_zeroes_next_tick_and_latches(self):
        r = self.armed_and_driving(); r.failsafe_frames = True
        dt = r.time_to_zero(lambda: setattr(r, 'tx_on', False))
        self.assertLessEqual(dt, 0.15)                                   # next frame (<=0.1 s) + one tick
        self.assertTrue(r.mux.remote_stop.latched); self.assertIn('FlySky stop', r.mux.remote_stop.reason)

    def test_receiver_silent_zeroes_within_frame_timeout_and_latches(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: setattr(r, 'tx_on', False))           # no frames at all
        self.assertLessEqual(dt, CFG['frame_timeout_s'] + 2 * DT)
        self.assertTrue(r.mux.remote_stop.latched)

    def test_teleop_crash_is_caught_by_the_mux_watchdog(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: setattr(r, 'teleop_alive', False))
        self.assertLessEqual(dt, 0.35 + 2 * DT)                          # mux FLYSKY source timeout

    def test_swb_stop_latches(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: r.rx.__setitem__(STOP, DOWN))
        self.assertLessEqual(dt, 0.15); self.assertTrue(r.mux.remote_stop.latched)

    def test_swa_off_zeroes_without_latch_and_needs_rearm(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: r.rx.__setitem__(ARM, UP))
        self.assertLessEqual(dt, 0.15); self.assertFalse(r.mux.remote_stop.latched)
        r.rx[ARM] = DOWN; r.tick(10)                                     # throttle still forward: must not re-arm
        self.assertEqual(r.last(), (0.0, 0.0))
        r.rx[TH] = MID; r.tick(4); r.rx[TH] = DOWN; r.tick(40)
        self.assertGreater(r.last()[0], 0.0)

    def test_stick_release_stops(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: r.rx.__setitem__(TH, MID))
        self.assertLessEqual(dt, 0.15)

    def test_xbox_b_latches_while_flysky_drives(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(r.xbox_b)
        self.assertLessEqual(dt, 0.1); self.assertIn('B pressed', r.mux.remote_stop.reason)

    def test_xbox_switched_off_latches(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: setattr(r, 'xbox_on', False))
        self.assertLessEqual(dt, 0.5 + 2 * DT); self.assertIn('joystick unavailable', r.mux.remote_stop.reason)

    def test_dashboard_or_voice_stop_latches(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: r.mux.on_voice_stop(None))         # /atlas/voice/stop (dashboard stop path too)
        self.assertLessEqual(dt, 0.05); self.assertIn('voice stop', r.mux.remote_stop.reason)

    def test_centre_value_failsafe_without_flag_cannot_drive(self):
        r = self.armed_and_driving()
        dt = r.time_to_zero(lambda: r.rx.update({ARM: MID, STOP: MID, TH: MID, ST: MID}))
        self.assertLessEqual(dt, 0.15)


class Handover(unittest.TestCase):
    def test_handover_rules_end_to_end(self):
        r = Rover(); r.commission_to_armed(); r.drive(ticks=20)
        self.assertFalse(r.mux.select_controller('XBOX')[0])            # released: refused
        r.xbox_b(); self.assertTrue(r.mux.select_controller('XBOX')[0])
        r.xbox_lb_reset(); mark = len(r.outs); r.drive(ticks=20)        # FlySky input now ignored
        self.assertTrue(all(lx == 0.0 for t, lx, _ in r.outs[mark:]))
        self.assertIsNone(r.mux.active_name); self.assertEqual(r.mux.last_sent.linear.x, 0.0)
        self.assertFalse(r.mux.channels['FLYSKY'].engaged)
        self.assertEqual(r.teleop.step(r.t).state, 'NOT_SELECTED')


if __name__ == '__main__':
    unittest.main()
