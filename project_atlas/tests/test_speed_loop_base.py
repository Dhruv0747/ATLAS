"""yahboom_base integration of the closed-loop autonomous speed (2026-11-15). No ROS, no hardware.

The real _drive_pwm / _slew_motor_pwm / _speed_loop_* methods are extracted from scripts/yahboom_base.py with ast and
run against a stub node, so the checks below exercise the code that would be deployed.
"""
import ast
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_speed_loop as sl  # noqa: E402
from test_speed_loop import Rover  # noqa: E402

SOURCE = SCRIPTS / 'yahboom_base.py'
CONSTS = {'MAX_VX', 'MAX_WZ', 'MAX_PWM', 'MIN_RUN_PWM', 'REMOTE_MAX_PWM', 'REMOTE_BOOST_THRESHOLD',
          'REMOTE_BOOST_MIN_PWM', 'REMOTE_BOOST_MAX_PWM', 'AUTONOMOUS_MIN_RUN_PWM', 'LOW_SPEED_HOLD_PWM',
          'PWM_RAMP_STEP', 'TURN_PWM_BIAS', 'SPEED_LOOP_STATUS_IDLE_PERIOD_S', 'AUTONOMOUS_STEER_SIGN', 'REMOTE_STEER_SIGN',
          'FRONT_STEER_CENTER', 'REAR_STEER_CENTER', 'FRONT_STEER_RIGHT', 'FRONT_STEER_LEFT',
          'REAR_STEER_RIGHT', 'REAR_STEER_LEFT'}
FUNCS = {'motor_outputs', '_clamp_servo', 'opposite_steering_targets'}
METHODS = {'_drive_pwm', '_slew_motor_pwm', '_step_toward', '_init_speed_loop', '_speed_loop_idle',
           '_speed_loop_pwm', '_heading_corrected_wz'}


class Clock:
    def __init__(self):
        self.t = 100.0

    def monotonic(self):
        return self.t

    def time(self):
        return self.t


def load(clock):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    body, methods = [], []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTS for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCS:
            body.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'YahboomBase':
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
    assert {m.name for m in methods} == METHODS, {m.name for m in methods}
    ns = {'math': math, 'json': json, 'time': clock, 'String': lambda data: SimpleNamespace(data=data),
          'Float32': lambda data: SimpleNamespace(data=data), 'SpeedFeedback': sl.SpeedFeedback,
          'load_speed_loop_config': sl.load_speed_loop_config, 'turn_split': sl.turn_split,
          '_SPEED_LOOP_IMPORT_ERROR': ''}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), 'exec'), ns)
    cls = type('Base', (), {m.name: None for m in methods})
    mod = ast.Module(body=[ast.ClassDef(name='Base', bases=[], keywords=[], body=methods, decorator_list=[])],
                     type_ignores=[])
    exec(compile(ast.fix_missing_locations(mod), str(SOURCE), 'exec'), ns)
    return ns


class Pub:
    def __init__(self):
        self.msgs = []

    def publish(self, msg):
        self.msgs.append(msg.data)


def make_base(config_text, clock, source='NAV'):
    ns = load(clock)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'speed_loop.yaml'
        if config_text is not None:
            path.write_text(config_text)
        ns['SPEED_LOOP_CONFIG'] = path
        b = ns['Base']()
        b.get_logger = lambda: SimpleNamespace(warning=lambda *_: None)
        b._init_speed_loop()
    b._drive_source = source
    b._applied_pwm = 0
    b._wheelbase_m = 0.3
    b._front_target_angle = b._front_applied_angle = ns['FRONT_STEER_CENTER']
    b._rear_target_angle = b._rear_applied_angle = ns['REAR_STEER_CENTER']
    b._closed_loop_update = lambda *a: None
    b.outputs = []
    b._write_motor_outputs = b.outputs.append
    b._pub_front_steer = b._pub_rear_steer = b._pub_steer_mode = Pub()
    b._pub_speed_loop = Pub()
    return b, ns


ENABLED = 'speed_loop:\n  enabled: true\n  params: {}\n'


def drive(b, clock, rover, vx, seconds, wz=0.0, feed_ok=True, odom=True):
    """10 Hz: odometry sample then drive tick, like the two base timers. Returns per-tick (v, max|pwm|)."""
    trace = []
    for _ in range(int(round(seconds / 0.1))):
        clock.t += 0.1
        applied = b.outputs[-1] if b.outputs else (0, 0, 0, 0)
        # motor_outputs() = (L, -R, L, -R): body-forward PWM is the polarity-corrected mean
        mean_pwm = int(round((applied[0] - applied[1] + applied[2] - applied[3]) / 4.0))
        delta = rover.step(mean_pwm) if rover else 0.0
        if odom and b._speed_feedback is not None:
            b._speed_feedback.feed(delta, feed_ok, clock.t)
        b._drive_pwm(vx, wz)
        # servo slew as in _motor_keepalive (2 deg per tick)
        b._front_applied_angle = b._step_toward(b._front_applied_angle, b._front_target_angle, 2)
        b._rear_applied_angle = b._step_toward(b._rear_applied_angle, b._rear_target_angle, 2)
        trace.append((rover.v if rover else 0.0, max(abs(v) for v in b.outputs[-1])))
    return trace


class BaseIntegrationTests(unittest.TestCase):
    def test_disabled_or_missing_config_keeps_legacy_open_loop(self):
        for text in (None, 'speed_loop:\n  enabled: false\n'):
            clock = Clock()
            b, _ = make_base(text, clock)
            self.assertFalse(b._speed_loop_enabled)
            drive(b, clock, None, 0.07, 1.0)
            self.assertEqual(max(abs(v) for v in b.outputs[-1]), 62)   # legacy map 60 + 40 x 0.07
            self.assertEqual(b._pub_speed_loop.msgs, [])

    def test_enabled_tracks_slow_nav_command_on_motor_model(self):
        for breakaway in (45, 55, 60):
            for target in (0.10, 0.15):
                clock = Clock()
                b, _ = make_base(ENABLED, clock)
                tr = drive(b, clock, Rover(breakaway, breakaway - 10, 1), target, 10.0)
                late = [v for v, _ in tr[50:]]
                with self.subTest(breakaway=breakaway, target=target):
                    self.assertLess(abs(sum(late) / len(late) - target), 0.04)
                    self.assertLess(max(v for v, _ in tr), max(1.5 * target, target + 0.08) + 0.12)
                    self.assertLessEqual(max(p for _, p in tr), 75)

    def test_remote_path_unchanged_when_enabled(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock, source='REMOTE')
        drive(b, clock, None, 0.3, 1.5)
        legacy, nsl = make_base(None, Clock(), source='REMOTE')
        drive(legacy, Clock(), None, 0.3, 1.5)
        self.assertEqual(b.outputs, legacy.outputs)
        self.assertGreaterEqual(max(abs(v) for v in b.outputs[-1]), 80)

    def test_broken_enabled_config_fails_closed_for_autonomy_only(self):
        for text in ('speed_loop:\n  enabled: true\n  params: {max_pwm: 150}\n',
                     'speed_loop:\n  enabled: true\n  params: {kp: 3}\n', 'speed_loop: [1, 2\n'):
            clock = Clock()
            b, _ = make_base(text, clock)
            self.assertTrue(b._speed_loop_enabled)
            drive(b, clock, Rover(50, 40), 0.15, 1.0)
            self.assertTrue(all(o == (0, 0, 0, 0) for o in b.outputs), text)
            self.assertIn('fail_closed', json.loads(b._pub_speed_loop.msgs[-1])['reason'])
            b._drive_source = 'REMOTE'
            drive(b, clock, None, 0.3, 1.5)
            self.assertGreaterEqual(max(abs(v) for v in b.outputs[-1]), 80, text)

    def test_stale_or_invalid_feedback_gives_zero(self):
        for kwargs in ({'feed_ok': False}, {'odom': False}):
            clock = Clock()
            b, _ = make_base(ENABLED, clock)
            drive(b, clock, Rover(50, 40), 0.15, 1.0, **kwargs)
            self.assertTrue(all(o == (0, 0, 0, 0) for o in b.outputs), kwargs)

    def test_feedback_lost_while_moving_cuts_at_once(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        rover = Rover(50, 40)
        drive(b, clock, rover, 0.15, 4.0)
        self.assertNotEqual(b.outputs[-1], (0, 0, 0, 0))
        drive(b, clock, rover, 0.15, 0.3, odom=False)     # odometry stops -> > 0.25 s old within 3 ticks
        self.assertEqual(b.outputs[-1], (0, 0, 0, 0))

    def test_overspeed_cut_in_base(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        for _ in range(4):
            clock.t += 0.1
            b._speed_feedback.feed(0.03, True, clock.t)    # 0.30 m/s measured for a 0.10 command
            b._drive_pwm(0.10, 0.0)
        self.assertEqual(b.outputs[-1], (0, 0, 0, 0))
        self.assertTrue(json.loads(b._pub_speed_loop.msgs[-1])['reason'].startswith('overspeed'))

    def test_turn_has_no_80_pwm_inside_floor(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        tr = drive(b, clock, Rover(50, 40), 0.10, 6.0, wz=0.2)
        self.assertLessEqual(max(p for _, p in tr), 83)        # 75 + TURN_PWM_BIAS
        self.assertLess(min(min(abs(v) for v in o) for o in b.outputs if any(o)), 80)

    def test_misaligned_steering_waits_at_zero(self):
        clock = Clock()
        b, ns = make_base(ENABLED, clock)
        b._front_applied_angle = ns['FRONT_STEER_CENTER'] + 30     # steering still far from target
        b._step_toward = lambda c, t, s: c if abs(c - t) > 0 else t  # keep it misaligned in this stub
        for _ in range(10):
            clock.t += 0.1
            b._speed_feedback.feed(0.0, True, clock.t)
            b._front_applied_angle = ns['FRONT_STEER_CENTER'] + 30
            b._drive_pwm(0.10, 0.0)
        self.assertTrue(all(o == (0, 0, 0, 0) for o in b.outputs))
        self.assertEqual(b._speed_loop.integrator, 0.0)

    def test_jitter_tick_holds_but_zero_command_still_stops(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        rover = Rover(50, 40)
        drive(b, clock, rover, 0.10, 4.0)
        before = b.outputs[-1]
        clock.t += 0.05
        b._drive_pwm(0.10, 0.0)                              # no new odometry sample yet
        self.assertEqual(b.outputs[-1], before)
        clock.t += 0.05
        b._drive_pwm(0.0, 0.0)
        self.assertEqual(b.outputs[-1], (0, 0, 0, 0))

    def test_switch_to_remote_resets_loop(self):
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        drive(b, clock, Rover(50, 40), 0.10, 3.0)
        b._drive_source = 'REMOTE'
        drive(b, clock, None, 0.0, 0.2)
        self.assertEqual(b._speed_loop.integrator, 0.0)
        self.assertFalse(b._speed_loop.rolling)


class FeedbackTests(unittest.TestCase):
    def test_feedback_accumulates_and_flags(self):
        f = sl.SpeedFeedback()
        self.assertFalse(f.take(0.0)[2])                     # nothing yet
        f.feed(0.01, True, 0.05); f.feed(0.005, True, 0.08)
        d, dt, ok, has = f.take(0.1)
        self.assertAlmostEqual(d, 0.015); self.assertAlmostEqual(dt, 0.1); self.assertTrue(ok and has)
        f.feed(0.01, False, 0.15)
        self.assertFalse(f.take(0.2)[2])
        f.feed(math.nan, True, 0.25)
        self.assertFalse(f.take(0.3)[2])

    def test_config_loader(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.yaml'
            self.assertEqual(sl.load_speed_loop_config(p), (False, None, ''))
            p.write_text('speed_loop:\n  enabled: "yes"\n')
            self.assertEqual(sl.load_speed_loop_config(p)[0], False)       # only a literal true enables
            p.write_text('speed_loop:\n  enabled: true\n  params: {max_pwm: 70}\n')
            en, loop, err = sl.load_speed_loop_config(p)
            self.assertTrue(en); self.assertEqual(loop.p['max_pwm'], 70); self.assertEqual(err, '')

    def test_repo_config_enabled_and_valid(self):
        # 2026-11-15: ground-validated (Speed check PASS x2) and deployed enabled; the repo matches the rover.
        en, loop, err = sl.load_speed_loop_config(SCRIPTS.parent / 'config' / 'speed_loop.yaml')
        self.assertTrue(en); self.assertIsNotNone(loop); self.assertEqual(err, '')

    def test_heading_loop_corrects_autonomous_only(self):
        from atlas_heading_loop import HeadingLoop
        clock = Clock()
        b, _ = make_base(ENABLED, clock)
        b._heading_loop = HeadingLoop(); b._imu_gz = -0.08; b._imu_gz_t = clock.monotonic()
        b._heading_t = None
        out = b._heading_corrected_wz(0.15, 0.0)
        self.assertEqual(out, 0.0)                     # speed loop not rolling yet -> measured 0 -> no correction
        b._speed_loop.measured_speed = lambda: 0.15
        clock.t += 0.1
        out = b._heading_corrected_wz(0.15, 0.0)
        self.assertGreater(out, 0.0)                   # drifting right (gz < 0) -> steer left
        b._drive_source = 'REMOTE'
        self.assertEqual(b._heading_corrected_wz(0.15, 0.0), 0.0)
        b._drive_source = 'NAV'; b._heading_loop = None
        self.assertEqual(b._heading_corrected_wz(0.15, 0.2), 0.2)

    def test_autonomous_left_turn_uses_mirrored_servo_side(self):
        # 2026-11-15: ROS +wz (left) must command the servo side that physically turned the rover LEFT, i.e. the
        # mirror of the old mapping (front below centre). 2026-11-15 owner: REMOTE mirrored the same way.
        clock = Clock()
        b, ns = make_base(ENABLED, clock)
        b._drive_pwm(0.15, 0.3)
        self.assertLess(b._front_target_angle, ns['FRONT_STEER_CENTER'])
        r, ns = make_base(ENABLED, Clock(), source='REMOTE')
        r._drive_pwm(0.3, 0.3)
        self.assertLess(r._front_target_angle, ns['FRONT_STEER_CENTER'])

    def test_turn_split(self):
        self.assertEqual(sl.turn_split(0, 8, 100), (0, 0))
        self.assertEqual(sl.turn_split(50, 8, 100), (42, 58))
        self.assertEqual(sl.turn_split(5, 8, 100), (0, 13))


if __name__ == '__main__':
    unittest.main()
