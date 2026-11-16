"""Offline tests for scripts/atlas_battery_eta.py (pure, no ROS). Dashboard text is English (owner 2026-11-16)."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_battery_eta import BatteryEta, charge_speed, format_minutes  # noqa: E402


def feed(eta, t0, seconds, soc0, current, cap_ah=20.0, dt=5.0):
    """Simulated Daly: SOC follows the coulomb count of a cap_ah pack."""
    t, soc = t0, soc0
    while t <= t0 + seconds:
        eta.update(t, soc, current)
        soc = max(0.0, min(100.0, soc + current * dt / 3600.0 / cap_ah * 100.0))
        t += dt
    return t - dt, soc


def has_devanagari(text):
    return any('ऀ' <= ch <= 'ॿ' for ch in text)


class BatteryEtaTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_minutes(130), '≈ 2 h 10 min')
        self.assertEqual(format_minutes(45), '≈ 45 min')
        self.assertEqual(format_minutes(120), '≈ 2 h')
        self.assertEqual(format_minutes(0.2), '< 1 min')
        self.assertIsNone(format_minutes(float('nan')))

    def test_discharge_time_left_with_config_capacity(self):
        e = BatteryEta(capacity_ah=20.0)
        t, soc = feed(e, 1000, 300, 60.0, -4.0)
        est = e.estimate(now=t)
        self.assertEqual(est['mode'], 'discharging')
        expect = (soc - 10.0) / 100 * 20.0 / 4.0 * 60
        self.assertAlmostEqual(est['minutes_to_reserve'], expect, delta=2.0)
        self.assertIn('left (to 10%)', est['text'])

    def test_charge_time_to_full_includes_taper(self):
        e = BatteryEta(capacity_ah=20.0)
        t, soc = feed(e, 1000, 200, 40.0, 5.0)
        est = e.estimate(now=t)
        cc = (95 - soc) / 100 * 20 / 5 * 60
        tail = 5 / 100 * 20 / (5 * 0.4) * 60
        self.assertAlmostEqual(est['minutes_to_full'], cc + tail, delta=2.0)
        self.assertIn('to full', est['text'])

    def test_capacity_is_learned_and_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cap.json'
            e = BatteryEta(state_path=path)
            self.assertEqual(e.capacity, (None, 'learning'))
            feed(e, 1000, 3600, 30.0, 5.0, cap_ah=24.0)
            cap, src = e.capacity
            self.assertEqual(src, 'learned')
            self.assertAlmostEqual(cap, 24.0, delta=1.5)
            e2 = BatteryEta(state_path=path)
            self.assertAlmostEqual(e2.capacity[0], cap, delta=0.01)

    def test_no_time_until_enough_data_or_capacity(self):
        e = BatteryEta()
        t, _ = feed(e, 1000, 100, 50.0, -3.0)
        self.assertIn('learning', e.estimate(now=t)['text'])
        e2 = BatteryEta(capacity_ah=20.0)
        e2.update(1000, 50.0, -3.0)
        self.assertIsNone(e2.estimate(now=1000)['minutes_to_reserve'])

    def test_idle_stale_and_bad_input(self):
        e = BatteryEta(capacity_ah=20.0)
        feed(e, 1000, 100, 50.0, 0.1)
        self.assertEqual(e.estimate(now=1100)['mode'], 'idle')
        self.assertEqual(e.estimate(now=2000)['mode'], 'unknown')
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

    def test_all_dashboard_text_is_english(self):
        cases = []
        for current in (-4.0, 0.1, 5.0, 16.0):
            e = BatteryEta(capacity_ah=15.0)
            t, _ = feed(e, 1000, 300, 50.0, current, cap_ah=15.0)
            cases.append(e.estimate(now=t)['text'])
        e = BatteryEta()
        t, _ = feed(e, 1000, 300, 50.0, 3.0)
        cases.append(e.estimate(now=t)['text'])
        cases.append(BatteryEta().estimate(now=1)['text'])
        e = BatteryEta(capacity_ah=15.0)
        e.update(1000, 50.0, 4.0)
        cases.append(e.estimate(now=1000)['text'])
        for text in cases:
            self.assertFalse(has_devanagari(text), text)


class ChargeSpeedTests(unittest.TestCase):
    def test_by_c_rate(self):
        self.assertEqual(charge_speed(2.0, 15.0)[0], 'Slow')        # 0.13C
        self.assertEqual(charge_speed(4.6, 15.0)[0], 'Normal')      # 0.31C
        self.assertEqual(charge_speed(9.0, 15.0)[0], 'Fast')        # 0.60C
        self.assertEqual(charge_speed(4.6, 15.0)[1], '0.31C')
        self.assertTrue(charge_speed(16.0, 15.0)[0].startswith('Very fast'))   # 1.07C on the 15 Ah pack

    def test_repo_config_is_the_owner_pack(self):
        text = (Path(__file__).parents[1] / 'config' / 'battery_eta.yaml').read_text(encoding='utf-8')
        line = [l for l in text.splitlines() if l.startswith('capacity_ah:')][0]
        self.assertEqual(float(line.split(':', 1)[1]), 15.0)

    def test_by_power_until_capacity_known(self):
        self.assertEqual(charge_speed(1.5, None, 13.4)[0], 'Slow')       # 20 W
        self.assertEqual(charge_speed(4.6, None, 13.4)[0], 'Normal')     # 62 W
        self.assertEqual(charge_speed(7.0, None, 13.4)[0], 'Fast')       # 94 W
        self.assertEqual(charge_speed(-3.0, 15.0), (None, ''))

    def test_estimate_text_shows_speed(self):
        e = BatteryEta(capacity_ah=15.0)
        t, _ = feed(e, 1000, 200, 40.0, 9.0, cap_ah=15.0)
        est = e.estimate(now=t)
        self.assertEqual(est['charge_speed'], 'Fast')
        self.assertTrue(est['text'].startswith('Fast charging (0.60C)'), est['text'])



class ChargerRatingTests(unittest.TestCase):
    def test_label_follows_charger_and_shows_net_and_load(self):
        e2 = BatteryEta(capacity_ah=15.0, charger_current_a=5.1, charger_voltage_v=14.8)
        t2, _ = feed(e2, 1000, 200, 30.0, 2.2, cap_ah=15.0)
        self.assertTrue(e2.estimate(now=t2)['text'].startswith('Normal charger (14.8 V 5.1 A ≈ 75 W, 0.34C)'),
                        e2.estimate(now=t2)['text'])
        e = BatteryEta(capacity_ah=15.0, charger_current_a=5.1)
        t, _ = feed(e, 1000, 200, 30.0, 2.2, cap_ah=15.0)
        est = e.estimate(now=t)
        self.assertEqual(est['charge_speed'], 'Normal')               # 5.1 A / 15 Ah = 0.34C
        self.assertEqual(est['charge_rate'], '0.34C')
        self.assertAlmostEqual(est['rover_load_a'], 2.9, delta=0.01)
        self.assertTrue(est['text'].startswith('Normal charger (5.1 A, 0.34C) · battery gets 2.2 A, rover uses 2.9 A'),
                        est['text'])
        self.assertIn('to full', est['text'])                          # time still from the NET current
        self.assertFalse(has_devanagari(est['text']))

if __name__ == '__main__':
    unittest.main()
