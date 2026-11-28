"""Offline tests for scripts/atlas_speed_loop.py (no ROS, no hardware). 2026-11-15.

The motor model reproduces the 2026-11-15 recordings: ~0.27 m/s at 62 PWM and ~0.37 m/s at 84 PWM, onset only after
the base slew (start 45, +8 PWM per 0.1 s tick), coasting at ~0.45 m/s^2 after a zero command (0.37 m/s -> stop in
~0.8 s). The breakaway PWM below 60 is UNKNOWN, so every closed-loop test sweeps it.
"""
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_speed_loop import SpeedLoop

DT = 0.1
LOW_HOLD, RAMP = 45, 8          # yahboom_base LOW_SPEED_HOLD_PWM / PWM_RAMP_STEP


def steady_speed(pwm, hold):
    if pwm < hold:
        return 0.0
    if pwm < 60:
        return 0.05 + (pwm - hold) / max(60 - hold, 1) * 0.22
    return 0.27 + 0.004 * (pwm - 60)


class Rover:
    """1-D plant: base slew -> 1 tick latency -> breakaway/hold friction -> first-order spin-up, coasting decel."""
    def __init__(self, breakaway, hold, seed=0):
        self.b, self.h = breakaway, hold
        self.v = 0.0; self.applied = 0; self.prev_applied = 0; self.x = 0.0
        self.rng = random.Random(seed); self.pending = 0.0

    def slew(self, target):
        if target == 0:
            return 0
        if self.applied != 0 and (self.applied > 0) != (target > 0):
            return 0
        if self.applied == 0:
            s = min(abs(target), LOW_HOLD)
            return s if target > 0 else -s
        step = max(-RAMP, min(RAMP, target - self.applied))
        return self.applied + step

    def step(self, pwm_cmd):
        self.prev_applied, self.applied = self.applied, self.slew(pwm_cmd)
        pwm = abs(self.prev_applied)            # one tick of latency
        sign = 1 if self.prev_applied > 0 else -1 if self.prev_applied < 0 else 0
        moving = abs(self.v) > 0.01
        if pwm and (moving or pwm >= self.b) and (self.v == 0 or math.copysign(1, self.v) == sign):
            target = sign * steady_speed(pwm, self.h)
            self.v += (target - self.v) * (1 - math.exp(-DT / 0.2))
        else:
            dv = 0.45 * DT
            self.v = 0.0 if abs(self.v) <= dv else self.v - math.copysign(dv, self.v)
        d = self.v * DT
        self.x += d
        # encoder bursts: counts sometimes arrive one tick late (quantized to 1 mm)
        self.pending += d
        if self.rng.random() < 0.3:
            return 0.0
        out = round(self.pending, 3); self.pending -= out
        return out


def run(loop, rover, target_fn, seconds):
    trace = []
    for k in range(int(seconds / DT)):
        t = k * DT
        delta = rover.step(loop.last_output)
        pwm = loop.update(target_fn(t), delta, DT, True)
        trace.append((t, rover.v, pwm, loop.last_reason))
    return trace


class SpeedLoopTests(unittest.TestCase):
    def test_tracks_slow_targets_for_unknown_breakaway(self):
        for breakaway in (45, 50, 55, 60):
            for tgt in (0.075, 0.10, 0.15):     # 0.075 = Nav2 0.15 after the mux DEGRADED x0.5 scale
                # (0.05 is below the slowest steady crawl of this plant: it can only stop-go; not a gate speed)
                for seed in range(3):
                    loop, rover = SpeedLoop(), Rover(breakaway, breakaway - 10, seed)
                    tr = run(loop, rover, lambda t: tgt, 10.0)
                    late = [v for t, v, _, _ in tr if t >= 5.0]
                    mean = sum(late) / len(late)
                    peak = max(v for t, v, _, _ in tr if t >= 1.5)   # after the breakaway surge (ground-check window)
                    start = next(t for t, v, _, _ in tr if v > 0.02)
                    with self.subTest(breakaway=breakaway, target=tgt, seed=seed):
                        self.assertLess(start, 2.5, f'start {start:.1f} s')
                        self.assertLess(abs(mean - tgt), 0.035, f'mean {mean:.3f}')
                        self.assertLess(peak, max(1.5 * tgt, tgt + 0.08) + 0.12, f'peak {peak:.3f}')

    def test_single_encoder_burst_is_not_breakaway(self):
        # 2026-11-15 ground check: one ~0.017 m/s burst at PWM ~43 was taken as breakaway; PWM fell to ~37 and the
        # rover never rolled. A lone burst must not release the search.
        loop = SpeedLoop()
        out = [loop.update(0.075, 0.0, DT, True) for _ in range(3)]
        out.append(loop.update(0.075, 0.0017, DT, True))          # one bursty tick
        out += [loop.update(0.075, 0.0, DT, True) for _ in range(6)]
        self.assertFalse(loop.rolling)
        self.assertEqual(out, sorted(out))                         # still ramping up, never released
        self.assertGreater(out[-1], out[2])

    def test_worst_case_plateau_motor_stays_bounded(self):
        # if the board itself holds ~0.27 m/s for any PWM above breakaway (no slow rolling band at all), the loop
        # can only pulse: it must never sustain overspeed and the average must not exceed the target band.
        m = sys.modules[__name__]
        orig = m.steady_speed
        m.steady_speed = lambda pwm, hold: 0.0 if pwm < hold else 0.27 + 0.004 * max(0, pwm - 60)
        try:
            for breakaway in (45, 55, 60):
                loop, rover = SpeedLoop(), Rover(breakaway, breakaway - 10, 1)
                tr = run(loop, rover, lambda t: 0.10, 10.0)
                late = [v for t, v, _, _ in tr if t >= 3.0]
                with self.subTest(breakaway=breakaway):
                    self.assertLess(max(late), 0.32)
                    self.assertLess(sum(late) / len(late), 0.13)
                    above = sum(1 for v in late if v > 0.18) / len(late)
                    self.assertLess(above, 0.35)
        finally:
            m.steady_speed = orig

    def test_open_loop_reference_is_much_faster(self):
        # documents the problem being fixed: open loop 0.07 m/s -> PWM 62
        rover = Rover(55, 45)
        for _ in range(60):
            rover.step(62)
        self.assertGreater(rover.v, 0.25)

    def test_stop_from_slow_speed_coasts_little(self):
        for breakaway in (45, 60):
            loop, rover = SpeedLoop(), Rover(breakaway, breakaway - 10)
            run(loop, rover, lambda t: 0.10, 8.0)
            x0 = rover.x
            tr = run(loop, rover, lambda t: 0.0, 3.0)
            self.assertTrue(all(p == 0 for _, _, p, _ in tr))
            self.assertLess(rover.x - x0, 0.05)
            self.assertEqual(rover.v, 0.0)

    def test_overspeed_cut(self):
        loop = SpeedLoop()
        for _ in range(3):
            pwm = loop.update(0.10, 0.03, DT, True)      # measured 0.30 m/s
        self.assertEqual(pwm, 0)
        self.assertTrue(loop.last_reason.startswith('overspeed'))

    def test_invalid_feedback_fails_closed(self):
        for args in ((0.1, 0.01, DT, False), (0.1, math.nan, DT, True), (0.1, 0.01, 0.0, True),
                     (0.1, 0.01, 2.0, True), (math.inf, 0.01, DT, True)):
            loop = SpeedLoop(); loop.update(0.1, 0.0, DT, True)
            self.assertEqual(loop.update(*args), 0, args)
            self.assertEqual(loop.integrator, 0.0)

    def test_zero_command(self):
        loop = SpeedLoop()
        self.assertEqual(loop.update(0.0, 0.0, DT, True), 0)
        self.assertEqual(loop.update(0.015, 0.0, DT, True), 0)

    def test_reverse_goes_through_zero(self):
        loop = SpeedLoop()
        for _ in range(3):
            loop.update(0.10, 0.012, DT, True)          # moving forward 0.12 m/s
        self.assertEqual(loop.update(-0.10, 0.012, DT, True), 0)
        self.assertIn('against', loop.last_reason)
        for _ in range(3):
            pwm = loop.update(-0.10, 0.0, DT, True)     # stopped
        self.assertLess(pwm, 0)

    def test_reverse_tracks(self):
        loop, rover = SpeedLoop(), Rover(50, 40)
        tr = run(loop, rover, lambda t: -0.10, 10.0)
        late = [v for t, v, _, _ in tr if t >= 5.0]
        self.assertLess(abs(sum(late) / len(late) + 0.10), 0.06)

    def test_output_clamped(self):
        loop = SpeedLoop({'max_pwm': 70})
        for _ in range(200):
            pwm = loop.update(0.5, 0.0, DT, True)         # stalled: integrator would wind up
        self.assertLessEqual(abs(pwm), 70)

    def test_bad_parameters_rejected(self):
        for bad in ({'max_pwm': 0}, {'max_pwm': 120}, {'kp_pwm_per_mps': -1}, {'window_ticks': 0},
                    {'overspeed_ratio': 0.5}, {'ff_pwm': math.nan}):
            with self.assertRaises(ValueError):
                SpeedLoop(bad)


if __name__ == '__main__':
    unittest.main()
