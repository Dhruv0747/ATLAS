"""Offline tests for tools/drive/stage3_autonomy_check.py (pure evaluate(); no ROS)."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'tools' / 'drive'))
from stage3_autonomy_check import evaluate  # noqa: E402


def trip(home_err=0.1, stop_still_after=0.6, stop=True, opposite=0, enc_bad=False, home_status=4, out_status=4):
    """Synthetic round trip: out leg 0..30 s, home leg 40..70 s, owner stop at 20 s while driving."""
    mission = [(0.0, 'NAMED GOAL DISPATCHED name=hall'), (30.0, f'NAMED GOAL FINISHED name=hall status={out_status}'),
               (40.0, 'NAMED GOAL DISPATCHED name=dhruv room'),
               (70.0, f'NAMED GOAL FINISHED name=dhruv room status={home_status}')]
    amcl = [(0.5, 0.0, 0.0, 0.0), (35.0, 3.0, 0.0, 180.0), (70.5, home_err, 0.0, 5.0)]
    odom, cmd, imu = [], [], []
    t = 0.0
    while t < 70.0:
        driving = (1 <= t < 29) or (41 <= t < 69)
        stopped = stop and 20.0 <= t < 20.0 + stop_still_after
        v = 0.15 if driving and (not stop or t < 20.0 or t >= 20.0 + stop_still_after + 2) else (0.1 if stopped else 0.0)
        odom.append((t, v))
        wz = 0.3 if driving and int(t) % 10 < 3 else 0.0
        cmd.append((t, 0.15 if driving else 0.0, wz))
        imu.append((t, (-0.2 if len(imu) < opposite else 0.2) if wz else 0.0))
        t = round(t + 0.1, 1)
    safety = [(20.0, 'REMOTE STOP: E-STOP latched')] if stop else []
    encoder = [(t, 'CRITICAL' if enc_bad and 10 <= t < 11 else 'DEGRADED') for t in range(0, 70)]
    return dict(mission=mission, safety=safety, encoder=encoder, amcl=amcl, odom=odom, cmd=cmd, imu=imu)


class Stage3Tests(unittest.TestCase):
    def test_good_round_trip_passes(self):
        r = evaluate('Dhruv Room', **trip())
        self.assertEqual(r['verdict'], 'PASS', r['checks'])
        self.assertEqual(len(r['stops']), 1)

    def test_missing_home_leg_or_failed_leg_fails(self):
        self.assertFalse(evaluate('dhruv room', **trip(home_status=6))['checks']['legs']['ok'])
        self.assertFalse(evaluate('dhruv room', **trip(out_status=5))['checks']['legs']['ok'])

    def test_not_back_home_fails(self):
        self.assertFalse(evaluate('dhruv room', **trip(home_err=0.6))['checks']['return_home']['ok'])

    def test_no_stop_or_slow_stop_fails(self):
        self.assertFalse(evaluate('dhruv room', **trip(stop=False))['checks']['safe_stop']['ok'])
        self.assertFalse(evaluate('dhruv room', **trip(stop_still_after=2.5))['checks']['safe_stop']['ok'])

    def test_wrong_turn_sign_fails(self):
        self.assertFalse(evaluate('dhruv room', **trip(opposite=10**6))['checks']['turn_sign']['ok'])

    def test_critical_encoder_while_moving_fails(self):
        self.assertFalse(evaluate('dhruv room', **trip(enc_bad=True))['checks']['encoders']['ok'])

    def test_empty_input_fails_closed(self):
        r = evaluate('dhruv room', [], [], [], [], [], [], [])
        self.assertEqual(r['verdict'], 'FAIL')


class TurnSignAutonomyOnlyTests(unittest.TestCase):
    """2026-11-19: remote reverse turns and lock-to-lock steering swings are not autonomy turn-sign errors."""
    def test_remote_samples_are_excluded(self):
        d = trip()
        # the owner drives by remote from 41 to 52 s with car-like reverse steering: gyro opposite to cmd wz
        d['cmd'] = [(t, -0.15, 0.4) if 41 <= t < 52 else (t, v, w) for t, v, w in d['cmd']]
        d['imu'] = [(t, -0.3) if 41 <= t < 52.3 else (t, g) for t, g in d['imu']]
        bad = evaluate('dhruv room', **d)['checks']['turn_sign']
        self.assertFalse(bad['ok'])                                      # without /cmd_vel_joy: counted
        self.assertIn('cannot be separated', bad['detail'])
        joy = [(t, 41 <= t < 52) for t, _v, _w in d['cmd']]
        ok = evaluate('dhruv room', joy=joy, **d)['checks']['turn_sign']
        self.assertTrue(ok['ok'], ok['detail'])
        self.assertIn('remote', ok['detail'])

    def test_samples_right_after_a_yaw_flip_are_skipped(self):
        d = trip()
        cmd, imu = [], []
        for t, v, w in d['cmd']:
            if 1 <= t < 29:                                                # weave: flip yaw sign every 2 s
                w = 0.3 if int(t // 2) % 2 == 0 else -0.3
                prev = 0.3 if int((t - 0.6) // 2) % 2 == 0 else -0.3     # steering still on the old side for 0.6 s
                cmd.append((t, 0.15, w)); imu.append((t, prev))
            else:
                cmd.append((t, v, w)); imu.append((t, 0.2 if w else 0.0))
        d['cmd'], d['imu'] = cmd, imu
        r = evaluate('dhruv room', joy=[], **d)['checks']['turn_sign']
        self.assertTrue(r['ok'], r['detail'])
        self.assertIn('steering-flip', r['detail'])


if __name__ == '__main__':
    unittest.main()
