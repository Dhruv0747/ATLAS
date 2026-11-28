import importlib.util
import pathlib
import unittest

P = pathlib.Path(__file__).resolve().parents[1] / 'tools' / 'diagnostics' / 'encoder_hand_test.py'
spec = importlib.util.spec_from_file_location('encoder_hand_test', P)
eht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eht)
C = eht.CIRCUMFERENCE_M


def run(wheel, fwd, rev, pace='slow'):
    """fwd/rev: counted fraction of one turn for the tested wheel."""
    out = []
    for d, f in (('forward', fwd), ('reverse', -rev)):
        deltas = [0.0] * 4
        deltas[wheel - 1] = f * C
        r = eht.evaluate_step(wheel, d, deltas)
        r['pace'] = pace
        out.append(r)
    return out


class HandTestLogic(unittest.TestCase):
    def test_healthy_wheel_passes(self):
        self.assertEqual(eht.summarize(run(1, 1.0, 1.0))[1]['verdict'], 'PASS')

    def test_stage25_m3_forward_loss_is_flagged(self):
        # Stage 25 recording: M3 counted ~0.1 of M1/M4 going forward but ~0.96 in reverse
        v = eht.summarize(run(3, 0.1, 0.96))[3]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertTrue(any('DIRECTION_ASYMMETRY' in n for n in v['notes']))

    def test_stage25_m2_wrong_direction_is_flagged(self):
        r = run(2, -0.6, 0.0)
        self.assertEqual(r[0]['status'], 'WRONG_DIRECTION')
        self.assertEqual(eht.summarize(r)[2]['verdict'], 'FAIL')

    def test_no_count_and_crosstalk(self):
        self.assertEqual(eht.evaluate_step(4, 'forward', [0, 0, 0, 0.0])['status'], 'NO_COUNT')
        r = eht.evaluate_step(4, 'forward', [0.2 * C, 0, 0, C])
        self.assertTrue(r['crosstalk_warn'])

    def test_slow_pace_loss_reported_even_if_fast_passes(self):
        r = run(1, 0.5, 0.5, 'slow') + run(1, 1.0, 1.0, 'fast')
        self.assertTrue(any('LOSS_AT_SLOW' in n for n in eht.summarize(r)[1]['notes']))

    def test_script_is_read_only(self):
        src = P.read_text()
        for banned in ('create_publisher', '.publish(', 'cmd_vel', 'Twist', 'create_client', 'subprocess', 'os.system'):
            self.assertNotIn(banned, src.replace('sends no motor/steering/cmd_vel', ''), banned)


if __name__ == '__main__':
    unittest.main()
