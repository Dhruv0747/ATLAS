"""Offline tests for scripts/atlas_battery_eta.py (pure, no ROS)."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_battery_eta import BatteryEta, format_minutes_hi  # noqa: E402


def feed(eta, t0, seconds, soc0, current, cap_ah=20.0, dt=5.0):
    """Simulated Daly: SOC follows the coulomb count of a cap_ah pack."""
    t, soc = t0, soc0
    while t <= t0 + seconds:
        eta.update(t, soc, current)
        soc = max(0.0, min(100.0, soc + current * dt / 3600.0 / cap_ah * 100.0))
        t += dt
    return t - dt, soc


class BatteryEtaTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_minutes_hi(130), '≈ 2 घंटे 10 मिनट')
        self.assertEqual(format_minutes_hi(45), '≈ 45 मिनट')
        self.assertEqual(format_minutes_hi(120), '≈ 2 घंटे')
        self.assertEqual(format_minutes_hi(0.2), '≈ 1 मिनट से कम')
        self.assertIsNone(format_minutes_hi(float('nan')))

    def test_discharge_time_left_with_config_capacity(self):
        e = BatteryEta(capacity_ah=20.0)
        t, soc = feed(e, 1000, 300, 60.0, -4.0)
        est = e.estimate(now=t)
        self.assertEqual(est['mode'], 'discharging')
        # (soc - 10 %) of 20 Ah at 4 A
        expect = (soc - 10.0) / 100 * 20.0 / 4.0 * 60
        self.assertAlmostEqual(est['minutes_to_reserve'], expect, delta=2.0)
        self.assertIn('बाकी', est['text'])

    def test_charge_time_to_full_includes_taper(self):
        e = BatteryEta(capacity_ah=20.0)
        t, soc = feed(e, 1000, 200, 40.0, 5.0)
        est = e.estimate(now=t)
        cc = (95 - soc) / 100 * 20 / 5 * 60
        tail = 5 / 100 * 20 / (5 * 0.4) * 60
        self.assertAlmostEqual(est['minutes_to_full'], cc + tail, delta=2.0)
        self.assertIn('पूरा charge', est['text'])

    def test_capacity_is_learned_and_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cap.json'
            e = BatteryEta(state_path=path)
            self.assertEqual(e.capacity, (None, 'learning'))
            t, soc = feed(e, 1000, 3600, 30.0, 5.0, cap_ah=24.0)      # +5 Ah over an hour -> ~21 % SOC
            cap, src = e.capacity
            self.assertEqual(src, 'learned')
            self.assertAlmostEqual(cap, 24.0, delta=1.5)
            e2 = BatteryEta(state_path=path)
            self.assertAlmostEqual(e2.capacity[0], cap, delta=0.01)

    def test_no_time_until_enough_data_or_capacity(self):
        e = BatteryEta()
        t, _ = feed(e, 1000, 100, 50.0, -3.0)
        self.assertIn('सीख', e.estimate(now=t)['text'])
        e2 = BatteryEta(capacity_ah=20.0)
        e2.update(1000, 50.0, -3.0)
        self.assertIsNone(e2.estimate(now=1000)['minutes_to_reserve'])   # less than min_avg_span_s

    def test_idle_stale_and_bad_input(self):
        e = BatteryEta(capacity_ah=20.0)
        feed(e, 1000, 100, 50.0, 0.1)
        self.assertEqual(e.estimate(now=1100)['mode'], 'idle')
        self.assertEqual(e.estimate(now=2000)['mode'], 'unknown')        # stale BMS
        e.update(2000, float('nan'), -3.0)
        e.update(2001, 150.0, -3.0)
        self.assertEqual(e.estimate(now=2001)['mode'], 'unknown')

    def test_mode_switch_uses_only_latest_run(self):
        e = BatteryEta(capacity_ah=20.0)
        t, soc = feed(e, 1000, 300, 50.0, -6.0)
        t2, _ = feed(e, t + 5, 120, soc, 4.0)
        est = e.estimate(now=t2)
        self.assertEqual(est['mode'], 'charging')
        self.assertAlmostEqual(est['avg_current_a'], 4.0, delta=0.05)


class ChargeSpeedTests(unittest.TestCase):
    def test_by_c_rate(self):
        from atlas_battery_eta import charge_speed
        self.assertEqual(charge_speed(2.0, 15.0)[0], 'धीमी')       # 0.13C
        self.assertEqual(charge_speed(4.6, 15.0)[0], 'सामान्य')    # 0.31C
        self.assertEqual(charge_speed(9.0, 15.0)[0], 'तेज़')        # 0.60C
        self.assertEqual(charge_speed(4.6, 15.0)[1], '0.31C')
        self.assertTrue(charge_speed(16.0, 15.0)[0].startswith('बहुत तेज़'))    # 1.07C on the 15 Ah pack

    def test_repo_config_is_the_owner_pack(self):
        text = (Path(__file__).parents[1] / 'config' / 'battery_eta.yaml').read_text(encoding='utf-8')
        line = [l for l in text.splitlines() if l.startswith('capacity_ah:')][0]
        self.assertEqual(float(line.split(':', 1)[1]), 15.0)

    def test_by_power_until_capacity_known(self):
        from atlas_battery_eta import charge_speed
        self.assertEqual(charge_speed(1.5, None, 13.4)[0], 'धीमी')      # 20 W
        self.assertEqual(charge_speed(4.6, None, 13.4)[0], 'सामान्य')   # 62 W
        self.assertEqual(charge_speed(7.0, None, 13.4)[0], 'तेज़')       # 94 W
        self.assertEqual(charge_speed(-3.0, 15.0), (None, ''))

    def test_estimate_text_shows_speed(self):
        e = BatteryEta(capacity_ah=15.0)
        t, _ = feed(e, 1000, 200, 40.0, 9.0, cap_ah=15.0)
        est = e.estimate(now=t)
        self.assertEqual(est['charge_speed'], 'तेज़')
        self.assertTrue(est['text'].startswith('तेज़ charging (0.60C)'), est['text'])

if __name__ == '__main__':
    unittest.main()
