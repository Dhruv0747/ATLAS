import unittest
from unittest.mock import patch
from atlas_web_diagnostics import parse_units, service_logs, redact, DiagnosticCache


class DiagnosticsTests(unittest.TestCase):
    def test_service_fields_not_dependent_on_property_order(self):
        units = parse_units('ActiveState=active\nNRestarts=9\nId=rover-base-telemetry.service\nSubState=running\nResult=success\n\nId=atlas-slam-fast.service\nActiveState=inactive')
        base = next(x for x in units if x['unit'] == 'rover-base-telemetry')
        self.assertEqual(base['restarts'], '9')
        self.assertEqual(base['active'], 'active')
        self.assertEqual(next(x for x in units if x['unit'] == 'atlas-slam-fast')['mode'], 'on demand')

    def test_no_arbitrary_unit_or_command(self):
        with patch('atlas_web_diagnostics.command') as command:
            for name in ('../../etc/passwd', 'ssh; reboot', 'unknown'):
                with self.assertRaises(ValueError):
                    service_logs(name)
            command.assert_not_called()

    def test_logs_bounded_and_redacted(self):
        with patch('atlas_web_diagnostics.command', return_value=('token=abc123 password=xyz sk-proj-01234567890123456789', '')):
            log = service_logs('atlas-gnss')['log']
        self.assertNotIn('abc123', log)
        self.assertNotIn('xyz', log)
        self.assertNotIn('012345', log)

    def test_snapshot_collection_is_cached(self):
        cache = DiagnosticCache()
        with patch('atlas_web_diagnostics.threading.Thread') as worker:
            cache.snapshot()
            cache.snapshot()
        self.assertEqual(worker.call_count, 1)


if __name__ == '__main__':
    unittest.main()
