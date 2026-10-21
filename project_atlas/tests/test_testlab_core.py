import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import atlas_testlab_core as T  # noqa: E402
from atlas_drive_pid_lifted import (  # noqa: E402
    CommissioningRejected, LiftedDriveCommission, LiftedState, SafetySnapshot)

C = T.CIRCUMFERENCE_M


def make_frame(t, dist, raw=None, seq=None, fresh=True, age=0.05, rejected=()):
    raw = raw or [int(d / C * 2200) * s for d, s in zip(dist, (1, -1, 1, -1))]
    return T.Frame(t, 1.8e9 + t, seq if seq is not None else int(t * 20), tuple(raw), tuple(dist),
                   (2238.4, 2215.0, 2199.1, 2230.5), (1, -1, 1, -1), fresh, age, (1, 2, 3, 4), tuple(rejected))


class FakeOwner:
    """The REAL LiftedDriveCommission wrapped the way yahboom_base wraps it, on a fake clock."""

    def __init__(self):
        self.now = 100.0
        self.core = LiftedDriveCommission()
        self.stop_latched = True
        self.remote_b = False
        self.entry_stable = 6.0
        self.entry_problem = ''
        self.raw_enabled = True
        self.cut_ready = True
        self.sequence_ack = -1
        self.observation = None
        self.rejects = []
        self.counts = [0, 0, 0, 0]
        self.requests = []
        self.last_pwm = (0, 0, 0, 0)

    def snap(self):
        return SafetySnapshot(
            stop_latched=self.stop_latched, policy_age_s=0.0, drive_mode='STOPPED', cmd_vel=(0.0, 0.0, 0.0),
            applied_pwm=self.last_pwm, controller_link_ok=True, encoder_valid=(True,) * 4, encoder_ages_s=(0.0,) * 4,
            measured_speeds_mps=(0.0,) * 4, jetson_temp_c=50.0, bms_ok=True, bms_age_s=0.0,
            bms_cell_voltages_v=(3.35,) * 4, stationary_duration_s=2.0, physical_power_cut_ready=self.cut_ready,
            remote_b_stop=self.remote_b)

    def request(self, msg):
        self.requests.append(dict(msg))
        if not self.raw_enabled:
            self.rejects.append('raw_lifted_interface_disabled')
            return
        try:
            action = msg.get('op')
            before = [self.counts[i] for i in range(4)]
            d = self.core.command(msg, self.now, self.snap())
            self.sequence_ack = int(msg['seq'])
            if action == 'pulse':
                w = msg['wheel'] - 1
                self.counts[w] += int(math.copysign(400, msg['pwm']))   # healthy simulated wheel
                self.observation = {'wheel': msg['wheel'], 'baseline_count': before[w], 'final_count': self.counts[w],
                                    'delta_count': self.counts[w] - before[w], 'expected_sign': 1 if msg['pwm'] > 0 else -1,
                                    'observed_sign': 1 if msg['pwm'] > 0 else -1, 'result': 'MATCH'}
            self.last_pwm = d.motor_pwm
        except CommissioningRejected as exc:
            self.rejects.append(str(exc))
            self.last_pwm = (0, 0, 0, 0)
            if msg.get('op') == 'exit':
                pass

    def advance(self, dt):
        self.now += dt
        d = self.core.tick(self.now, self.snap())
        self.last_pwm = d.motor_pwm

    def status(self):
        s = dict(self.core.status())
        snap = self.snap()
        arm_ready = (self.core.state == LiftedState.LOCKED and self.core._snapshot_problem(snap, None) == ''
                     and snap.stop_latched is False)
        exit_ready = self.core.locked and self.core._release_problem(snap) == ''
        s.update({'schema': 1, 'raw_interface_enabled': self.raw_enabled, 'physical_power_cut_confirmed': self.cut_ready,
                  'arm_ready': arm_ready, 'exit_ready': exit_ready, 'entry_stable_s': self.entry_stable,
                  'entry_problem': self.entry_problem, 'stop_latched': self.stop_latched, 'remote_b_stop': self.remote_b,
                  'bms_ok': True, 'bms_age_s': 0.2, 'bms_cells_v': [3.35] * 4, 'sequence_ack': self.sequence_ack,
                  'pulse_observation': self.observation})
        if self.core.session:
            s['session_fingerprint'] = hashlib.sha256(self.core.session.encode()).hexdigest()
        return s


class Harness:
    """Runs a PulseRun against FakeOwner at 20 Hz; `operator` callbacks play the human."""

    def __init__(self, direction='forward', wheel=2, pwm=30, dur=0.3, **owner_kw):
        self.owner = FakeOwner()
        for k, v in owner_kw.items():
            setattr(self.owner, k, v)
        self.run = T.PulseRun(T.validate_pulse(wheel, direction, pwm, dur), self.owner.request, clock=lambda: self.owner.now)
        self.max_abs_pwm = 0.0
        self.pulses = 0

    def step(self, dt=0.05, deliver=True):
        self.owner.advance(dt)
        if deliver:
            self.run.on_status(self.owner.status())
        self.run.tick()
        self.owner.advance(0.0)
        self.max_abs_pwm = max(self.max_abs_pwm, max(abs(x) for x in self.owner.last_pwm))
        self.pulses = sum(1 for r in self.owner.requests if r['op'] == 'pulse')

    def run_until(self, pred, limit=1500, **kw):
        for _ in range(limit):
            if pred() or self.run.done:
                return
            self.step(**kw)
        raise AssertionError('timeout in phase ' + self.run.phase)


class ValidatePulse(unittest.TestCase):
    def test_limits_come_from_the_approved_commissioning_module(self):
        from atlas_drive_pid_lifted import MAX_RAW_PWM, MAX_RAW_DURATION_S, MIN_RAW_DURATION_S
        self.assertEqual((MAX_RAW_PWM, MIN_RAW_DURATION_S, MAX_RAW_DURATION_S), (50, 0.2, 0.5))
        self.assertEqual(T.validate_pulse(3, 'reverse', 50, 0.5), {'wheel': 3, 'pwm': -50, 'duration_s': 0.5})
        self.assertEqual(T.validate_pulse(1, 'forward', 1, 0.2)['pwm'], 1)

    def test_rejects_everything_out_of_bounds(self):
        bad = [(0, 'forward', 10, .3), (5, 'forward', 10, .3), (True, 'forward', 10, .3), ('1', 'forward', 10, .3),
               (1.0, 'forward', 10, .3), (1, 'sideways', 10, .3), (1, 'forward', 0, .3), (1, 'forward', 51, .3),
               (1, 'forward', 10.5, .3), (1, 'forward', True, .3), (1, 'forward', -10, .3), (1, 'forward', 10, .19),
               (1, 'forward', 10, .51), (1, 'forward', 10, float('nan')), (1, 'forward', 10, float('inf')),
               (1, 'forward', 10, None), (None, None, None, None), ([1], 'forward', 10, .3)]
        for args in bad:
            with self.assertRaises(ValueError, msg=str(args)):
                T.validate_pulse(*args)


class GateReport(unittest.TestCase):
    def test_fails_closed_when_status_missing_or_stale(self):
        self.assertFalse(T.gate_report(None, None)['entry_ok'])
        o = FakeOwner()
        self.assertTrue(T.gate_report(o.status(), 0.2)['entry_ok'])
        self.assertFalse(T.gate_report(o.status(), 5.0)['entry_ok'])

    def test_each_condition_independently_blocks(self):
        for key, val in (('raw_interface_enabled', False), ('physical_power_cut_confirmed', False), ('stop_latched', False),
                         ('remote_b_stop', True), ('bms_ok', False), ('entry_problem', 'wheels_not_stationary'),
                         ('entry_stable_s', 4.9), ('state', 'LOCKED')):
            s = FakeOwner().status()
            s[key] = val
            self.assertFalse(T.gate_report(s, 0.1)['entry_ok'], key)

    def test_unknown_values_are_not_ok(self):
        s = FakeOwner().status()
        del s['entry_problem']
        self.assertFalse(T.gate_report(s, 0.1)['entry_ok'])
        s = FakeOwner().status()
        s['bms_cells_v'] = [3.35, 3.35, 3.35, 3.9]
        self.assertFalse(T.gate_report(s, 0.1)['entry_ok'])


class PulseRunAgainstRealStateMachine(unittest.TestCase):
    def operator_release(self, h):
        h.owner.stop_latched = False

    def test_happy_path_one_bounded_pulse_then_zero_and_idle(self):
        h = Harness('reverse', wheel=3, pwm=25, dur=0.3)
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        self.assertEqual(h.pulses, 0, 'no pulse may happen before the operator releases the stop')
        self.assertTrue(h.run.public()['needs_operator'])
        self.operator_release(h)
        h.run_until(lambda: h.run.phase == 'WAIT_RELATCH')
        h.owner.stop_latched = True
        h.run_until(lambda: h.run.done)
        self.assertEqual(h.run.phase, 'DONE', h.run.error)
        self.assertEqual(h.pulses, 1)
        pulse = [r for r in h.owner.requests if r['op'] == 'pulse'][0]
        self.assertEqual(set(pulse), set(T.PULSE_REQUEST_FIELDS))
        self.assertEqual((pulse['mode'], pulse['wheel'], pulse['pwm'], pulse['duration_s']), ('raw_pulse', 3, -25, 0.3))
        self.assertLessEqual(h.max_abs_pwm, 25)
        self.assertEqual(h.owner.last_pwm, (0, 0, 0, 0))
        self.assertEqual(h.owner.core.state, LiftedState.IDLE)
        self.assertEqual(h.run.observation['result'], 'MATCH')
        self.assertEqual(h.owner.rejects, [])
        # only the single selected wheel ever received output
        self.assertEqual(sum(1 for r in h.owner.requests if r['op'] == 'enter'), 1)

    def test_only_allowed_ops_and_fields_are_ever_published(self):
        h = Harness()
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        self.operator_release(h)
        h.run_until(lambda: h.run.phase == 'WAIT_RELATCH')
        h.owner.stop_latched = True
        h.run_until(lambda: h.run.done)
        allowed = {'enter': {'op', 'session', 'seq', 'confirm', 'lifted'}, 'heartbeat': {'op', 'session', 'seq'},
                   'arm': {'op', 'session', 'seq'}, 'pulse': set(T.PULSE_REQUEST_FIELDS),
                   'abort': {'op', 'session', 'seq', 'reason'}, 'exit': {'op', 'session', 'seq'}}
        seqs = []
        for r in h.owner.requests:
            self.assertIn(r['op'], allowed)
            self.assertEqual(set(r), allowed[r['op']], r['op'])
            seqs.append(r['seq'])
        self.assertEqual(seqs, sorted(set(seqs)), 'sequence numbers must be strictly increasing')

    def test_operator_never_releases_stop_means_no_pulse(self):
        h = Harness()
        h.run.OPERATOR_TIMEOUT_S = 3.0
        h.run_until(lambda: h.run.phase in ('WAIT_RELATCH',), limit=400)
        self.assertEqual(h.pulses, 0)
        self.assertIn('operator_did_not_release_stop', h.run.error)
        self.assertEqual(h.owner.last_pwm, (0, 0, 0, 0))
        h.run_until(lambda: h.run.done)
        self.assertEqual(h.owner.core.state, LiftedState.IDLE)

    def test_cancel_before_pulse_aborts_and_never_pulses(self):
        h = Harness()
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        h.run.cancel('operator_stop_button')
        h.run_until(lambda: h.run.phase == 'WAIT_RELATCH')
        self.assertEqual(h.pulses, 0)
        self.assertEqual(h.owner.core.state, LiftedState.ABORTED)
        h.owner.stop_latched = True
        h.run_until(lambda: h.run.done)
        self.assertEqual(h.owner.core.state, LiftedState.IDLE)

    def test_cancel_during_pulse_zeroes_immediately(self):
        h = Harness(dur=0.5)
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        self.operator_release(h)
        h.run_until(lambda: h.owner.core.state == LiftedState.PULSE)
        self.assertNotEqual(h.owner.last_pwm, (0, 0, 0, 0))
        h.run.cancel('operator_stop_button')
        self.assertEqual(h.owner.core.state, LiftedState.ABORTED)
        h.owner.advance(0.0)
        self.assertEqual(h.owner.last_pwm, (0, 0, 0, 0))

    def test_entry_not_ready_never_sends_enter(self):
        h = Harness(entry_problem='wheels_not_stationary')
        h.run.ENTRY_TIMEOUT_S = 2.0
        h.run_until(lambda: h.run.done, limit=200)
        self.assertEqual(h.run.phase, 'FAILED')
        self.assertIn('entry_not_ready', h.run.error)
        self.assertEqual([r['op'] for r in h.owner.requests], [])

    def test_disabled_or_no_power_cut_never_enters(self):
        for kw in ({'raw_enabled': False}, {'cut_ready': False}):
            h = Harness(**kw)
            h.run.ENTRY_TIMEOUT_S = 1.0
            h.run_until(lambda: h.run.done, limit=100)
            self.assertEqual(h.run.phase, 'FAILED')
            self.assertEqual(h.owner.requests, [])

    def test_status_loss_after_enter_fails_safe_and_owner_lease_expires(self):
        h = Harness(dur=0.5)
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        self.operator_release(h)
        h.run_until(lambda: h.owner.core.state == LiftedState.PULSE)
        for _ in range(60):                       # status stops arriving
            h.step(deliver=False)
        self.assertEqual(h.owner.core.state, LiftedState.ABORTED)
        self.assertEqual(h.owner.last_pwm, (0, 0, 0, 0))
        self.assertLessEqual(h.pulses, 1)

    def test_independent_lease_zeroes_output_if_the_web_process_dies(self):
        o = FakeOwner()
        sid = LiftedDriveCommission.new_session_token()
        o.request({'op': 'enter', 'session': sid, 'seq': 0, 'confirm': T.CONFIRMATION_PHRASE, 'lifted': True})
        o.stop_latched = False
        o.request({'op': 'arm', 'session': sid, 'seq': 1})
        o.request({'op': 'pulse', 'session': sid, 'seq': 2, 'mode': 'raw_pulse', 'wheel': 1, 'pwm': 50, 'duration_s': 0.5})
        o.advance(0.1)
        self.assertEqual(o.last_pwm[0], 50)
        o.advance(0.6)                           # no heartbeat for > 0.5 s: web backend is gone
        self.assertEqual(o.core.state, LiftedState.ABORTED)
        self.assertEqual(o.last_pwm, (0, 0, 0, 0))

    def test_foreign_session_status_is_ignored(self):
        h = Harness()
        h.run_until(lambda: h.run.phase == 'WAIT_LOCKED')
        evil = h.owner.status()
        evil['session_fingerprint'] = 'f' * 64
        evil['state'] = 'ARMED'
        h.run.on_status(evil)
        self.assertNotEqual(h.run.status.get('state'), 'ARMED')

    def test_owner_rejection_of_pulse_ends_in_failsafe(self):
        h = Harness()
        h.run_until(lambda: h.run.phase == 'WAIT_RELEASE')
        self.operator_release(h)
        h.owner.cut_ready = False                 # power cut-off confirmation vanishes before the pulse
        h.run_until(lambda: h.run.phase in ('WAIT_RELATCH', 'FAILED'))
        self.assertEqual(h.pulses, 0)
        self.assertEqual(h.owner.last_pwm, (0, 0, 0, 0))

    def test_recover_exits_a_session_left_locked_after_restart(self):
        o = FakeOwner()
        sid = LiftedDriveCommission.new_session_token()
        o.request({'op': 'enter', 'session': sid, 'seq': 0, 'confirm': T.CONFIRMATION_PHRASE, 'lifted': True})
        o.stop_latched = False
        o.advance(0.7)                            # lease expired -> ABORTED
        self.assertEqual(o.core.state, LiftedState.ABORTED)
        run = T.PulseRun({'wheel': 1, 'pwm': 10, 'duration_s': 0.3}, o.request, clock=lambda: o.now, token=sid, first_seq=1)
        run.recover()
        run.on_status(o.status())
        run.tick()
        self.assertEqual(run.phase, 'WAIT_RELATCH')
        o.stop_latched = True
        for _ in range(10):
            o.advance(0.05)
            run.on_status(o.status())
            run.tick()
        self.assertEqual(o.core.state, LiftedState.IDLE)
        self.assertEqual(run.phase, 'DONE')


class Faults(unittest.TestCase):
    def frames(self, per_s, secs=4.0, hz=20, start=0.0):
        """per_s: forward turns/s of each wheel."""
        out, d = [], [0.0] * 4
        n = int(secs * hz)
        for k in range(n + 1):
            out.append(make_frame(start + k / hz, list(d)))
            d = [d[i] + per_s[i] * C / hz for i in range(4)]
        return out

    def codes(self, fr, **kw):
        return {(f['code'], f['channel']) for f in T.detect_faults(fr, {}, fr[-1].rx + 0.05, **kw)}

    def test_healthy_rolling_has_no_faults(self):
        self.assertEqual(self.codes(self.frames([1, 1, 1, 1])), set())

    def test_rest_has_no_faults(self):
        self.assertEqual(self.codes(self.frames([0, 0, 0, 0])), set())

    def test_frozen_channel(self):
        self.assertIn(('FROZEN_COUNTS', 3), self.codes(self.frames([1, 1, 0, 1])))

    def test_missing_pulses_stage25_m3_signature(self):
        self.assertIn(('MISSING_PULSES', 3), self.codes(self.frames([1, 1, 0.1, 1])))

    def test_unexpected_sign_in_free_drive_is_a_warning(self):
        fr = self.frames([1, -0.6, 1, 1])
        got = [f for f in T.detect_faults(fr, {}, fr[-1].rx + 0.05) if f['code'] == 'UNEXPECTED_SIGN']
        self.assertEqual([(f['channel'], f['severity']) for f in got], [(2, 'warn')])

    def test_unexpected_sign_when_direction_is_expected_is_a_fault(self):
        fr = self.frames([0, -0.5, 0, 0])
        got = [f for f in T.detect_faults(fr, {}, fr[-1].rx + 0.05, expect={'channel': 2, 'sign': 1})]
        self.assertEqual([(f['code'], f['severity']) for f in got], [('UNEXPECTED_SIGN', 'fault')])

    def test_stale_data(self):
        fr = self.frames([1, 1, 1, 1], secs=2)
        self.assertIn(('STALE_DATA', 0), {(f['code'], f['channel']) for f in T.detect_faults(fr, {}, fr[-1].rx + 2.0)})
        stale = [make_frame(1.0, [0] * 4, fresh=False)]
        self.assertIn(('STALE_DATA', 0), {(f['code'], f['channel']) for f in T.detect_faults(stale, {}, 1.05)})
        self.assertIn(('STALE_DATA', 0), {(f['code'], f['channel']) for f in T.detect_faults([make_frame(1.0, [0] * 4, age=0.9)], {}, 1.05)})

    def test_no_data(self):
        self.assertEqual(T.detect_faults([], {}, 0.0)[0]['code'], 'NO_DATA')

    def test_count_jump(self):
        a = make_frame(0.0, [0, 0, 0, 0], raw=[0, 0, 0, 0])
        b = make_frame(0.05, [0, 0, 0, 0], raw=[5000, 0, 0, 0], seq=2)
        self.assertIn(('COUNT_JUMP', 1), {(f['code'], f['channel']) for f in T.detect_faults([a, b], {}, 0.06)})

    def test_consensus_rejection_is_reported(self):
        fr = [make_frame(0.0, [0] * 4, rejected=(2,)), make_frame(0.05, [0] * 4, rejected=(2,))]
        self.assertIn(('CONSENSUS_REJECTED', 2), {(f['code'], f['channel']) for f in T.detect_faults(fr, {}, 0.06)})

    def test_direction_comparison_flags_forward_loss(self):
        fwd = self.frames([1, 1, 0.1, 1], secs=4)
        rev = self.frames([-1, -1, -0.96, -1], secs=4, start=fwd[-1].rx + 0.05)
        # carry distances on so the series is continuous
        off = list(fwd[-1].dist)
        rev = [make_frame(f.rx, [off[i] + f.dist[i] for i in range(4)]) for f in rev]
        rows = {r['channel']: r for r in T.direction_comparison(fwd + rev)['rows']}
        self.assertEqual(rows[3]['verdict'], 'ASYMMETRIC')
        self.assertLess(rows[3]['fwd_ratio'], 0.2)
        self.assertGreater(rows[3]['rev_ratio'], 0.9)
        self.assertEqual(rows[1]['verdict'], 'BALANCED')

    def test_direction_comparison_needs_motion(self):
        rows = T.direction_comparison(self.frames([0, 0, 0, 0]))['rows']
        self.assertTrue(all(r['verdict'] == 'NEED_MORE_MOTION' for r in rows))


class ChannelView(unittest.TestCase):
    def test_columns(self):
        fr = [make_frame(k * 0.05, [k * 0.002 * s for s in (1, 1, 1, 1)]) for k in range(60)]
        v = T.channel_view(fr, {'state': 'READY', 'consensus_state': 'AVAILABLE', 'last_change_age_s': [.1, .2, .3, .4]}, fr[-1].rx + 0.02)
        self.assertEqual([c['channel'] for c in v['channels']], [1, 2, 3, 4])
        c0 = v['channels'][0]
        self.assertEqual(c0['direction'], 'forward')
        self.assertIsNotNone(c0['rpm_estimate'])
        self.assertAlmostEqual(c0['rpm_estimate'], 0.04 / C * 60, delta=2.0)
        self.assertEqual(v['health_state'], 'READY')
        self.assertLess(v['frame_age_s'], 0.1)
        self.assertEqual(T.channel_view([], {}, 0.0)['channels'], [])


class HandTestLogic(unittest.TestCase):
    def test_matches_the_standalone_read_only_tool(self):
        p = Path(__file__).resolve().parents[1] / 'tools' / 'diagnostics' / 'encoder_hand_test.py'
        spec = importlib.util.spec_from_file_location('eht', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual((m.PASS_LO, m.PASS_HI, m.CROSSTALK_WARN, m.ASYMMETRY_WARN, m.CIRCUMFERENCE_M),
                         (T.PASS_LO, T.PASS_HI, T.CROSSTALK_WARN, T.ASYMMETRY_WARN, T.CIRCUMFERENCE_M))
        for w in (1, 2, 3, 4):
            for dr in ('forward', 'reverse'):
                for frac in (-1.0, -0.4, 0.0, 0.05, 0.3, 0.8, 1.0, 1.4):
                    for cross in (0.0, 0.5):
                        d = [cross * C if i != w - 1 else frac * C * (1 if dr == 'forward' else -1) for i in range(4)]
                        self.assertEqual(m.evaluate_step(w, dr, d), T.evaluate_step(w, dr, d))

    def test_flow_never_energizes_and_reports_stage25_pattern(self):
        h = T.HandTest()
        f0 = make_frame(0, [0, 0, 0, 0])
        h.begin(3, 'forward', f0)
        r = h.finish(make_frame(5, [0, 0, 0.05 * C, 0]))
        self.assertEqual(r['status'], 'NO_COUNT')
        h.begin(3, 'reverse', make_frame(6, [0, 0, 0.05 * C, 0]))
        r = h.finish(make_frame(9, [0, 0, 0.05 * C - 0.96 * C, 0]))
        self.assertEqual(r['status'], 'PASS')
        s = h.summary()
        self.assertEqual(s[3]['verdict'], 'FAIL')
        self.assertEqual(s[1]['verdict'], 'NOT_TESTED')
        with self.assertRaises(ValueError):
            h.finish(f0)
        with self.assertRaises(ValueError):
            h.begin(5, 'forward', f0)


class CsvSession(unittest.TestCase):
    def test_format_channels_and_timestamps(self):
        s = T.LabSession('abc123', 'hand', 1.8e9, 50.0)
        s.event('session_start', 1.8e9, 50.0, note='hand rotation')
        for k in range(3):
            s.add_frame(make_frame(50.1 + k * 0.05, [k * .01] * 4), 'READY', 'FROZEN_COUNTS:3' if k == 2 else '')
        s.event('step', 1.8e9 + 1, 51.0, channel=3, note='M3 forward')
        rows = list(csv.DictReader(io.StringIO(s.to_csv())))
        self.assertEqual(list(rows[0].keys()), list(T.CSV_COLUMNS))
        samples = [r for r in rows if r['event'] == 'sample']
        self.assertEqual(len(samples), 12)
        self.assertEqual(sorted({r['channel'] for r in samples}), ['1', '2', '3', '4'])
        self.assertEqual(samples[2]['motor'], 'M3 front-left')
        self.assertEqual(samples[2]['position'], 'front_left')
        self.assertTrue(samples[0]['iso_time_utc'].endswith('Z'))
        self.assertEqual(samples[-1]['faults'], 'FROZEN_COUNTS:3')
        self.assertTrue(all(r['session_id'] == 'abc123' for r in rows))
        self.assertEqual(rows[-1]['channel'], '3')

    def test_duplicate_frames_not_logged_twice_and_bounded(self):
        s = T.LabSession('x', 'observe', 1.8e9, 0.0)
        f = make_frame(0.1, [0] * 4)
        s.add_frame(f, None)
        s.add_frame(f, None)
        self.assertEqual(len(s.rows), 4)
        s.add_frame(make_frame(T.MAX_SESSION_S + 5, [0] * 4, seq=999), None)
        self.assertTrue(s.truncated and s.closed)


class ParseUpdate(unittest.TestCase):
    def test_real_message_shape_and_garbage(self):
        msg = json.dumps({'sequence': 7, 'raw_counts': [1, 2, 3, 4], 'wheel_distances_m': [0.1, 0.2, 0.3, 0.4],
                          'counts_per_revolution': [2238.4, 2215.0, 2199.1, 2230.5], 'encoder_signs': [1, -1, 1, -1],
                          'packet_fresh': True, 'packet_age_s': 0.03, 'accepted_channels': [1, 2, 3, 4], 'rejected_channels': []})
        f = T.parse_update(msg, 1.0, 2.0)
        self.assertEqual((f.seq, f.raw, f.packet_age_s), (7, (1, 2, 3, 4), 0.03))
        for bad in ('', '{', '[]', '{"raw_counts":[1,2,3],"wheel_distances_m":[1,2,3,4]}',
                    '{"raw_counts":[1,2,3,NaN],"wheel_distances_m":[1,2,3,4]}', None, 5):
            self.assertIsNone(T.parse_update(bad, 1.0, 2.0))


class CoreCannotActuate(unittest.TestCase):
    def test_no_hardware_or_generic_actuator_surface(self):
        src = (SCRIPTS / 'atlas_testlab_core.py').read_text()
        for banned in ('import serial', 'rclpy', 'cmd_vel', 'Twist', 'create_publisher', 'subprocess', 'os.system',
                       'open(', '/dev/tty', 'Rosmaster', 'set_motor'):
            self.assertNotIn(banned, src.replace('# no ROS', ''), banned)


if __name__ == '__main__':
    unittest.main()
