"""Offline tests for scripts/atlas_heading_loop.py. Plant: 4WS rover whose yaw rate follows the commanded wz with a
servo/steering lag, plus a constant disturbance yaw rate (weight imbalance / side slope)."""
import math
from pathlib import Path
import random
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_heading_loop import HeadingLoop

DT = 0.1


def simulate(loop, drift, wz_cmd=0.0, speed=0.15, seconds=10.0, gain=1.0, tau=0.3, noise=0.01, seed=0, imu_age=0.05):
    rng = random.Random(seed)
    wz = 0.0; heading = 0.0; trace = []
    for k in range(int(seconds / DT)):
        meas = wz + rng.gauss(0, noise)
        out = loop.update(wz_cmd, meas, speed, DT, imu_age) if loop else wz_cmd
        target = gain * out + drift
        wz += (target - wz) * (1 - math.exp(-DT / tau))
        heading += wz * DT
        trace.append((k * DT, wz, heading, out))
    return trace


class HeadingLoopTests(unittest.TestCase):
    def test_cancels_constant_drift(self):
        for drift in (-0.08, -0.04, 0.05):
            for gain in (0.6, 1.0, 1.4):           # unknown steering effectiveness
                open_h = simulate(None, drift, gain=gain)[-1][2]
                tr = simulate(HeadingLoop(), drift, gain=gain)
                with self.subTest(drift=drift, gain=gain):
                    late = [w for t, w, _, _ in tr if t >= 5]
                    self.assertLess(abs(sum(late) / len(late)), 0.012)
                    self.assertLess(abs(tr[-1][2]), abs(open_h) * 0.35)

    def test_tracks_commanded_turn_with_drift(self):
        tr = simulate(HeadingLoop(), -0.06, wz_cmd=0.3, gain=0.8)
        late = [w for t, w, _, _ in tr if t >= 5]
        self.assertLess(abs(sum(late) / len(late) - 0.3), 0.02)

    def test_correction_bounded(self):
        loop = HeadingLoop()
        tr = simulate(loop, -1.0, seconds=8)              # impossible disturbance
        self.assertTrue(all(abs(out) <= 0.35 + 1e-9 for _, _, _, out in tr))

    def test_stale_imu_falls_back_to_command(self):
        loop = HeadingLoop()
        simulate(loop, -0.08, seconds=3)
        self.assertNotEqual(loop.integrator, 0.0)
        self.assertEqual(loop.update(0.1, 0.0, 0.15, DT, 1.0), 0.1)
        self.assertEqual(loop.integrator, 0.0)
        self.assertEqual(loop.update(0.1, None, 0.15, DT, 0.05), 0.1)

    def test_not_rolling_applies_nothing_but_keeps_learned_drift(self):
        loop = HeadingLoop()
        simulate(loop, -0.08, seconds=4)
        learned = loop.integrator
        self.assertEqual(loop.update(0.0, 0.0, 0.0, DT, 0.05), 0.0)
        self.assertEqual(loop.integrator, learned)

    def test_bad_inputs(self):
        loop = HeadingLoop()
        self.assertEqual(loop.update(float('nan'), 0.0, 0.1, DT, 0.05), 0.0)
        self.assertEqual(loop.update(0.2, 0.0, 0.1, 0.0, 0.05), 0.2)
        with self.assertRaises(ValueError):
            HeadingLoop({'kp': -1})


if __name__ == '__main__':
    unittest.main()
