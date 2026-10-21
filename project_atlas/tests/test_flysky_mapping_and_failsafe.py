import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_flysky_mapping as M          # noqa: E402
import atlas_remote_arbiter_model as A    # noqa: E402


def good():
    return {'reviewed_by_owner': True, 'roles': {
        'throttle': {'channel': 3, 'min': 200, 'centre': 1000, 'max': 1800, 'deadband': 0.05},
        'steering': {'channel': 1, 'min': 200, 'centre': 1000, 'max': 1800, 'deadband': 0.05, 'reversed': True},
        'estop': {'channel': 5, 'active_above': 1500}}}


class Mapping(unittest.TestCase):
    def test_valid_mapping_passes(self):
        self.assertEqual(M.validate(good()), [])

    def test_unreviewed_missing_duplicate_and_bad_values_are_rejected(self):
        c = good(); c['reviewed_by_owner'] = False; self.assertTrue(M.validate(c))
        c = good(); del c['roles']['estop']; self.assertIn('missing role: estop', M.validate(c))
        c = good(); c['roles']['steering']['channel'] = 3; self.assertTrue(any('share channel' in e for e in M.validate(c)))
        c = good(); c['roles']['throttle']['min'] = 1100; self.assertTrue(M.validate(c))
        c = good(); c['roles']['throttle']['deadband'] = 0.9; self.assertTrue(M.validate(c))
        c = good(); c['roles']['steering']['channel'] = 17; self.assertTrue(M.validate(c))
        c = good(); c['roles']['steering']['channel'] = True; self.assertTrue(M.validate(c))
        c = good(); c['roles']['estop'] = {'channel': 5}; self.assertTrue(M.validate(c))

    def test_no_default_channel_assignment_exists(self):
        self.assertTrue(M.validate({}) and M.validate({'roles': {}}))

    def test_axis_centre_deadband_ends_and_reversal(self):
        t = good()['roles']['throttle']; s = good()['roles']['steering']
        self.assertEqual(M.axis_value(1000, t), 0.0)
        self.assertEqual(M.axis_value(1030, t), 0.0)           # inside deadband
        self.assertAlmostEqual(M.axis_value(1800, t), 1.0)
        self.assertAlmostEqual(M.axis_value(200, t), -1.0)
        self.assertAlmostEqual(M.axis_value(1800, s), -1.0)    # reversed in software only
        self.assertGreater(M.axis_value(1400, t), 0.0)

    def test_invalid_or_impossible_raw_fails_to_neutral(self):
        t = good()['roles']['throttle']
        for bad in (None, 'x', 5000, -3, 2047, 90):
            self.assertEqual(M.axis_value(bad, t), 0.0, bad)

    def test_switch_threshold(self):
        e = good()['roles']['estop']
        self.assertTrue(M.switch_active(1600, e)); self.assertFalse(M.switch_active(1400, e)); self.assertFalse(M.switch_active(None, e))

    def test_frozen_receiver_is_detected_but_jitter_is_not(self):
        f = M.FrozenDetector(window=10)
        self.assertFalse(any(f.update((1000,) * 16) for _ in range(9)))
        self.assertTrue(f.update((1000,) * 16))
        f = M.FrozenDetector(window=10)
        self.assertFalse(any(f.update((1000 + k % 3,) * 16) for k in range(30)))

    def test_mapping_module_has_no_io_or_ros(self):
        src = (Path(M.__file__)).read_text()
        for bad in ('import rclpy', 'serial', 'open(', 'publish', 'cmd_vel', 'subprocess'):
            self.assertNotIn(bad, src)


class FailsafeMatrixAgainstArbiter(unittest.TestCase):
    """Every Phase F failure path must end at zero output.  FlySky driving is disabled, so the arbiter is exercised with
    the flag forced on ONLY inside these tests to prove the fail-closed logic is already in place for a later approval."""

    def setUp(self):
        self._saved = A.FLYSKY_DRIVE_ENABLED
        A.FLYSKY_DRIVE_ENABLED = True

    def tearDown(self):
        A.FLYSKY_DRIVE_ENABLED = self._saved

    def driving(self):
        arb = A.Arbiter(active=None)
        fresh = A.SourceInput(link_verified=True, age_s=0.05, fresh_since_s=5.0)
        arb.stop_latched = True
        ok, _ = arb.select(A.FLYSKY, {A.FLYSKY: fresh})
        self.assertTrue(ok)
        arb.stop_latched = False                       # operator deliberately recovered via the existing path
        go = A.SourceInput(link_verified=True, age_s=0.05, linear=0.4, angular=0.1, deadman=True, fresh_since_s=5.0)
        self.assertEqual(arb.step({A.FLYSKY: go}).linear, 0.4)
        return arb, go

    def assertSafe(self, arb, inputs, **kw):
        d = arb.step(inputs, **kw); self.assertEqual((d.linear, d.angular), (0.0, 0.0), d.reason); return d

    def test_transmitter_off_stale_or_receiver_disconnected(self):
        for age in (0.6, 5.0, None):
            arb, go = self.driving()
            self.assertSafe(arb, {A.FLYSKY: A.SourceInput(link_verified=True, age_s=age, linear=0.4, deadman=True)})

    def test_failsafe_or_unverified_link_bridge_crash_usb_unplug(self):
        arb, go = self.driving()
        self.assertSafe(arb, {A.FLYSKY: A.SourceInput(link_verified=False, age_s=0.05, linear=0.4, deadman=True)})

    def test_loss_latches_and_returning_link_does_not_rearm(self):
        arb, go = self.driving()
        self.assertSafe(arb, {A.FLYSKY: A.SourceInput(link_verified=False, age_s=None)})
        self.assertSafe(arb, {A.FLYSKY: go})                 # link is back, sticks deflected: still zero
        self.assertTrue(arb.source_lost)

    def test_estop_from_any_source_or_dashboard_beats_everything(self):
        arb, go = self.driving()
        self.assertSafe(arb, {A.FLYSKY: go, A.EXISTING: A.SourceInput(stop_request=True)})
        arb, go = self.driving()
        self.assertSafe(arb, {A.FLYSKY: go}, dashboard_stop=True)

    def test_xbox_never_takes_over_automatically(self):
        arb, go = self.driving()
        xbox = A.SourceInput(link_verified=True, age_s=0.05, linear=0.9, deadman=True, fresh_since_s=9.0)
        self.assertSafe(arb, {A.FLYSKY: A.SourceInput(link_verified=False), A.EXISTING: xbox})
        self.assertEqual(arb.active, A.FLYSKY)

    def test_simultaneous_xbox_is_a_reported_conflict_and_dropped(self):
        arb, go = self.driving()
        xbox = A.SourceInput(link_verified=True, age_s=0.05, linear=0.9, deadman=True, fresh_since_s=9.0)
        d = arb.step({A.FLYSKY: go, A.EXISTING: xbox})
        self.assertTrue(d.conflict); self.assertEqual(d.source, A.FLYSKY); self.assertEqual(d.linear, 0.4)

    def test_default_flag_remains_disabled(self):
        self.assertFalse(self._saved)


if __name__ == '__main__':
    unittest.main()
