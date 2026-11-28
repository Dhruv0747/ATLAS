"""Mux-only policy lifecycle checks with fake systemd and a controllable boot clock."""
from pathlib import Path
import tempfile
import unittest

from mux_restart_policy import DROPIN, MuxPolicy, UNIT
from restart_policy import save


class FakeMux(MuxPolicy):
    def __init__(self, root, clock, manager):
        super().__init__(root, root/'units')
        self.clock = clock
        self.manager = manager

    def now(self):
        return self.clock[0]

    def boot(self):
        return self.manager['boot']

    def independent_check(self):
        if not self.manager['safe']:
            raise ValueError('verified independent maintenance protection unavailable')

    def _service_identity(self):
        if self.manager['Id'] != UNIT:
            raise ValueError('Mux unit identity mismatch')

    def _pid_identity(self, pid):
        return [int(pid), self.manager['start_ticks']]

    def command(self, *args):
        self.checkpoint()
        if args[0] == 'show':
            return self.manager[args[3]]
        self.manager['operations'].append(args)
        if args == ('daemon-reload',):
            self.manager['Restart'] = 'no' if self.path.exists() else 'always'
        elif args == ('restart', UNIT):
            self.manager.update(MainPID='9012', start_ticks=980)
        elif args == ('stop', UNIT):
            self.manager.update(MainPID='0', ActiveState='inactive')
        else:
            raise AssertionError(args)
        return ''


class DeadlineAndPolicyTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.clock = [100.]
        self.manager = dict(Id=UNIT, boot='boot-a', safe=True, ActiveState='active', Restart='always',
                            MainPID='1000', start_ticks=400, Job='', operations=[])
        self.policy = self.reconstruct()

    def reconstruct(self):
        return FakeMux(self.root, self.clock, self.manager)

    def test_delays_before_initial_io_and_reconstruction_consume_same_budget(self):
        self.clock[0] = 109
        self.policy.begin_budget(started=100)
        self.assertEqual(self.policy.limits(), (160, 190))
        self.clock[0] = 159
        other = self.reconstruct()
        other.resume_budget(cleanup=True)
        self.assertEqual(other.deadline, 189)
        self.clock[0] = 170
        third = self.reconstruct()
        third.resume_budget(cleanup=True)
        self.assertEqual(third.deadline, 189)
        self.clock[0] = 189
        with self.assertRaises(TimeoutError):
            self.reconstruct().resume_budget(cleanup=True)
        self.assertEqual(self.manager['operations'], [])

    def test_late_cleanup_cannot_add_time_to_outer_bound(self):
        self.policy.begin_budget()
        self.clock[0] = 180
        self.reconstruct().resume_budget(cleanup=True)
        self.clock[0] = 190
        with self.assertRaises(TimeoutError):
            self.reconstruct().cleanup()
        self.assertEqual(self.manager['operations'], [])

    def test_cleanup_before_journal_io_counts_toward_first_cleanup_deadline(self):
        self.policy.begin_budget()
        self.clock[0] = 135
        self.policy.resume_budget(cleanup=True, cleanup_started=120)
        self.assertEqual(self.policy.deadline, 150)
        self.clock[0] = 144
        other = self.reconstruct()
        other.resume_budget(cleanup=True, cleanup_started=144)
        self.assertEqual(other.deadline, 150)
        self.clock[0] = 150
        with self.assertRaises(TimeoutError):
            other.checkpoint()

    def test_changed_boot_fails_closed(self):
        self.policy.begin_budget()
        self.manager['boot'] = 'boot-b'
        with self.assertRaises(ValueError):
            self.reconstruct().resume_budget(cleanup=True)
        self.assertEqual(self.manager['operations'], [])

    def test_crash_before_override_rollback_preserves_original_process(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.path.unlink()  # matching on-disk boundary before creation or after unlink
        self.manager['Restart'] = 'always'
        self.reconstruct().cleanup()
        self.assertEqual(self.manager['MainPID'], '1000')
        self.assertTrue(self.policy.load()['restored'])
        self.assertNotIn(('stop', UNIT), self.manager['operations'])

    def test_changed_original_pid_rejects_pre_activation_rollback(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.manager.update(start_ticks=401)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.reconstruct().cleanup()
        self.assertTrue(self.policy.path.exists())
        self.assertNotIn(('stop', UNIT), self.manager['operations'])

    def test_restart_reservation_survives_crash_and_rejects_second_start(self):
        self.policy.begin_budget()
        self.policy.prepare()
        state = self.policy.load()
        state['activation'] = True
        save(self.policy.state, state)  # crash after write-ahead intent, job status ambiguous
        with self.assertRaisesRegex(ValueError, 'budget consumed'):
            self.policy.restart('activation')
        self.reconstruct().cleanup()
        self.assertEqual(self.manager['MainPID'], '0')
        self.assertEqual(self.manager['Restart'], 'always')
        self.assertNotIn(('restart', UNIT), self.manager['operations'])

    def test_rollback_after_restart_stops_new_pid_and_restarts_nothing(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.restart('activation')
        self.manager['safe'] = False
        self.reconstruct().cleanup()
        self.reconstruct().cleanup()
        self.assertEqual(self.manager['MainPID'], '0')
        self.assertEqual(self.manager['Restart'], 'always')
        self.assertEqual(self.manager['operations'].count(('restart', UNIT)), 1)
        self.assertEqual(self.manager['operations'].count(('stop', UNIT)), 1)

    def test_acceptance_requires_new_identity_and_guard_before_policy_restore(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.restart('activation')
        with self.assertRaises(ValueError):
            self.policy.restore_healthy()
        self.policy.accept_new_process('9012')
        self.manager['start_ticks'] += 1
        with self.assertRaisesRegex(ValueError, 'identity drift'):
            self.policy.restore_healthy()
        self.assertEqual(self.policy.path.read_bytes(), DROPIN)

    def test_reload_interruption_rollback_quiesces_accepted_service(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.restart('activation')
        self.policy.accept_new_process('9012')
        self.policy.restore_healthy()
        self.reconstruct().cleanup()  # success receipt not yet committed by outer transaction
        self.assertEqual(self.manager['MainPID'], '0')
        self.assertEqual(self.manager['Restart'], 'always')

    def test_changed_dropin_bytes_block_healthy_restoration(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.restart('activation')
        self.policy.accept_new_process('9012')
        self.policy.path.write_bytes(DROPIN.replace(b'\n', b'\r\n'))
        with self.assertRaisesRegex(ValueError, 'ownership mismatch'):
            self.policy.restore_healthy()
        self.assertEqual(self.manager['Restart'], 'no')

    def test_foreign_identical_dropin_is_preserved(self):
        self.policy.begin_budget()
        self.policy.prepare()
        self.policy.path.unlink()
        self.policy.path.write_bytes(DROPIN)
        foreign_inode = self.policy.path.stat().st_ino
        with self.assertRaisesRegex(ValueError, 'ownership mismatch'):
            self.reconstruct().cleanup()
        self.assertEqual(self.policy.path.stat().st_ino, foreign_inode)
        self.assertEqual(self.manager['MainPID'], '1000')

    def test_wrong_unit_never_installs_override(self):
        self.manager['Id'] = 'rover-base-telemetry.service'
        self.policy.begin_budget()
        with self.assertRaises(ValueError):
            self.policy.prepare()
        self.assertFalse(self.policy.state.exists())
        self.assertEqual(self.manager['operations'], [])


if __name__ == '__main__':
    unittest.main()
