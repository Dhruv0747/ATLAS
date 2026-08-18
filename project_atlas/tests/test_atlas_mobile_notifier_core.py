import unittest

from atlas_mobile_notifier_core import BatteryAlertState


class BatteryAlertStateTests(unittest.TestCase):
    def test_low_alert_has_hysteresis(self):
        state = BatteryAlertState()
        self.assertEqual(state.update(21), [])
        self.assertEqual(state.update(20), ["battery_low"])
        self.assertEqual(state.update(19), [])
        self.assertEqual(state.update(24), [])
        self.assertEqual(state.update(25), [])
        self.assertEqual(state.update(20), ["battery_low"])

    def test_full_requires_stable_samples(self):
        state = BatteryAlertState(full_samples_required=3)
        self.assertEqual(state.update(99), [])
        self.assertEqual(state.update(100), [])
        self.assertEqual(state.update(99), ["battery_full"])
        self.assertEqual(state.update(100), [])
        state.update(95)
        self.assertEqual(state.update(99), [])
        self.assertEqual(state.update(99), [])
        self.assertEqual(state.update(99), ["battery_full"])

    def test_invalid_values_do_not_alert(self):
        state = BatteryAlertState()
        self.assertEqual(state.update(-1), [])
        self.assertEqual(state.update(101), [])


if __name__ == "__main__":
    unittest.main()
