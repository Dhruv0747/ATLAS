import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_remote_arbiter_model as A  # noqa: E402

OK = dict(link_verified=True, age_s=0.05, fresh_since_s=5.0)


def inp(**kw):
    return A.SourceInput(**{**OK, **kw})


class Arbitration(unittest.TestCase):
    def test_default_is_existing_remote_only(self):
        a = A.Arbiter()
        d = a.step({A.EXISTING: inp(linear=0.4, deadman=True), A.FLYSKY: inp()})
        self.assertEqual((d.source, d.linear, d.reason), (A.EXISTING, 0.4, 'driving'))

    def test_flysky_drive_is_disabled_and_cannot_be_selected(self):
        self.assertFalse(A.FLYSKY_DRIVE_ENABLED)
        a = A.Arbiter(); a.stop_latched = True
        ok, why = a.select(A.FLYSKY, {A.FLYSKY: inp()})
        self.assertFalse(ok); self.assertIn('disabled', why); self.assertEqual(a.active, A.EXISTING)

    def test_flysky_stays_disabled_even_if_state_is_forced(self):
        a = A.Arbiter(active=A.FLYSKY)                       # bypasses select()
        d = a.step({A.EXISTING: inp(), A.FLYSKY: inp(linear=1.0, deadman=True)})
        self.assertEqual((d.linear, d.angular), (0.0, 0.0)); self.assertIn('disabled', d.reason)

    def test_only_one_source_commands_and_other_is_reported_as_conflict(self):
        a = A.Arbiter()
        d = a.step({A.EXISTING: inp(linear=0.3, deadman=True), A.FLYSKY: inp(linear=-1.0, deadman=True)})
        self.assertEqual(d.linear, 0.3); self.assertTrue(d.conflict)

    def test_estop_wins_from_any_source_and_dashboard(self):
        for kw in ({'dashboard_stop': True}, {}):
            a = A.Arbiter(); ins = {A.EXISTING: inp(linear=0.5, deadman=True), A.FLYSKY: inp(stop_request=not kw)}
            d = a.step(ins, **kw)
            self.assertEqual((d.linear, d.angular, d.stop_latched), (0.0, 0.0, True))
            d = a.step({A.EXISTING: inp(linear=0.5, deadman=True)})           # stop request gone: still latched
            self.assertEqual((d.linear, d.stop_latched), (0.0, True))

    def test_nothing_in_the_model_can_release_the_stop(self):
        a = A.Arbiter(); a.step({}, dashboard_stop=True)
        with self.assertRaises(NotImplementedError):
            a.release_stop_existing_path_only()
        ok, _ = a.select(A.EXISTING, {A.EXISTING: inp()})        # switching does not clear the latch
        self.assertTrue(a.stop_latched)
        self.assertEqual(a.step({A.EXISTING: inp(linear=0.5, deadman=True)}).linear, 0.0)

    def test_stale_command_yields_zero(self):
        a = A.Arbiter()
        d = a.step({A.EXISTING: inp(linear=0.5, deadman=True, age_s=A.COMMAND_TIMEOUT_S + 0.01)})
        self.assertEqual((d.linear, d.angular), (0.0, 0.0))

    def test_unverified_link_yields_zero(self):
        a = A.Arbiter()
        self.assertEqual(a.step({A.EXISTING: inp(linear=0.5, deadman=True, link_verified=False)}).linear, 0.0)

    def test_loss_of_active_source_fails_closed_and_does_not_resume(self):
        a = A.Arbiter()
        self.assertEqual(a.step({A.EXISTING: inp(linear=0.5, deadman=True)}).linear, 0.5)
        d = a.step({A.EXISTING: inp(linear=0.5, deadman=True, age_s=2.0)})
        self.assertEqual(d.linear, 0.0); self.assertIn('lost', d.reason)
        d = a.step({A.EXISTING: inp(linear=0.5, deadman=True)})          # link back, still must not drive
        self.assertEqual(d.linear, 0.0); self.assertIn('select', d.reason)

    def test_no_automatic_fallback_to_other_source(self):
        a = A.Arbiter()
        d = a.step({A.EXISTING: inp(deadman=True, age_s=5.0), A.FLYSKY: inp(linear=0.9, deadman=True)})
        self.assertEqual(d.linear, 0.0); self.assertEqual(a.active, A.EXISTING)

    def test_deadman_required(self):
        a = A.Arbiter(); self.assertEqual(a.step({A.EXISTING: inp(linear=0.5, deadman=False)}).linear, 0.0)

    def test_switch_preconditions(self):
        a = A.Arbiter(active=None); a.stop_latched = True
        self.assertFalse(a.select(A.EXISTING, {A.EXISTING: inp(link_verified=False)})[0])
        self.assertFalse(a.select(A.EXISTING, {A.EXISTING: inp(fresh_since_s=0.2)})[0])
        self.assertFalse(a.select(A.EXISTING, {A.EXISTING: inp(linear=0.4)})[0])
        self.assertTrue(a.select(A.EXISTING, {A.EXISTING: inp()})[0])
        b = A.Arbiter(); self.assertFalse(b.select('nonsense', {})[0])

    def test_switch_refused_while_driving(self):
        a = A.Arbiter(); ins = {A.EXISTING: inp(linear=0.5, deadman=True), A.FLYSKY: inp()}
        ok, why = a.select(A.EXISTING, ins); self.assertFalse(ok); self.assertIn('E-STOP', why)

    def test_output_is_clamped(self):
        a = A.Arbiter(); d = a.step({A.EXISTING: inp(linear=7.0, angular=-9.0, deadman=True)})
        self.assertEqual((d.linear, d.angular), (1.0, -1.0))

    def test_model_is_not_imported_by_production_code(self):
        root = Path(__file__).resolve().parents[1] / 'scripts'
        users = [p.name for p in root.glob('*.py') if 'atlas_remote_arbiter_model' in p.read_text() and p.name != 'atlas_remote_arbiter_model.py']
        self.assertEqual(users, [])


if __name__ == '__main__':
    unittest.main()
