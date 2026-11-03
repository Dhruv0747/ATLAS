"""Per-attempt binding: owner-approved pin, boot/PID drift and configuration drift. Offline only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import mux_attempt_binding as A
from mux_publisher_transaction import ServiceBinding, transaction_root, PACKAGE

UNITS = ('atlas-cmd-vel-mux.service', 'rover-base-telemetry.service',
         'atlas-sensor-recovery.service', 'rover-status-web.service')


def start_ticks(pid):
    text = Path('/proc', str(pid), 'stat').read_text()
    return int(text[text.rfind(')') + 2:].split()[19])


class AttemptBindingTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir = Path(td.name)
        self.units = {}
        for unit in UNITS:
            path = self.dir / unit
            path.write_text('[Service]\nExecStart=/bin/true # ' + unit + '\n')
            self.units[unit] = path
        # Sealed (historical) package binding: previous boot and PIDs, reviewed configuration.
        self.sealed = {'boot_id': 'old-boot', 'files': {'atlas_cmd_vel_mux.py': {'sha256': 'x'}}, 'services': {
            u: {'MainPID': '1897', 'start_ticks': 1537, 'NRestarts': '0', 'ActiveState': 'active',
                'FragmentPath': str(p), 'Restart': 'always' if 'mux' in u else 'on-failure',
                'unit_sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for u, p in self.units.items()}}
        pid = os.getpid()
        self.live = {u: dict(self.sealed['services'][u], MainPID=str(pid), start_ticks=start_ticks(pid),
                             NRestarts='1' if 'base' in u else '0') for u in UNITS}
        self.now = 5000.0

    def attempt(self, **over):
        data = {'schema': A.SCHEMA, 'package': PACKAGE, 'boot_id': 'this-boot',
                'captured_boottime': self.now - 60, 'services': copy.deepcopy(self.live)}
        data.update(over)
        raw = A.canonical(data)
        return raw, hashlib.sha256(raw).hexdigest()

    def load(self, raw, pin, boot='this-boot', now=None):
        return A.load(raw, pin, self.sealed, PACKAGE, boot, self.now if now is None else now)

    def test_valid_attempt_rebinds_current_boot_and_keeps_sealed_file_pins(self):
        raw, pin = self.attempt()
        b = self.load(raw, pin)
        self.assertEqual(b['boot_id'], 'this-boot')
        self.assertEqual(b['services']['atlas-cmd-vel-mux.service']['MainPID'], str(os.getpid()))
        self.assertIs(b['files'], self.sealed['files'])

    def test_hash_matching_itself_is_not_approval(self):
        raw, pin = self.attempt()
        other, other_pin = self.attempt(captured_boottime=self.now - 30)
        for bad in (None, '', other_pin, pin.upper(), pin[:-1]):
            with self.subTest(pin=bad), self.assertRaisesRegex(ValueError, 'not owner-approved'):
                self.load(raw, bad)

    def test_boot_drift_stale_future_and_package_mismatch_rejected(self):
        raw, pin = self.attempt()
        with self.assertRaisesRegex(ValueError, 'boot identity changed'):
            self.load(raw, pin, boot='rebooted')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.load(raw, pin, now=self.now + A.MAX_AGE_S)
        future, fpin = self.attempt(captured_boottime=self.now + 1)
        with self.assertRaisesRegex(ValueError, 'stale or from the future'):
            self.load(future, fpin)
        wrong, wpin = self.attempt(package={'archive_sha256': '0' * 64, 'manifest_sha256': PACKAGE['manifest_sha256']})
        with self.assertRaisesRegex(ValueError, 'different package'):
            self.load(wrong, wpin)

    def test_configuration_drift_and_schema_rejected(self):
        for unit, key, value in ((UNITS[0], 'Restart', 'no'), (UNITS[0], 'unit_sha256', '0' * 64),
                                 (UNITS[1], 'FragmentPath', '/tmp/other'), (UNITS[2], 'ActiveState', 'failed')):
            services = copy.deepcopy(self.live)
            services[unit][key] = value
            raw, pin = self.attempt(services=services)
            with self.subTest(unit=unit, key=key), self.assertRaisesRegex(ValueError, 'drift|not active'):
                self.load(raw, pin)
        services = copy.deepcopy(self.live); services.pop(UNITS[3])
        raw, pin = self.attempt(services=services)
        with self.assertRaisesRegex(ValueError, 'service set'):
            self.load(raw, pin)
        raw, pin = self.attempt(extra=1)
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.load(raw, pin)
        for bad in ('0', '1', 'abc', 7):
            services = copy.deepcopy(self.live); services[UNITS[0]]['MainPID'] = bad
            raw, pin = self.attempt(services=services)
            with self.subTest(pid=bad), self.assertRaisesRegex(ValueError, 'PID invalid'):
                self.load(raw, pin)

    def service_binding(self, boot='this-boot'):
        policy = Mock()
        policy.boot.return_value = boot
        policy.deadline, policy.now.return_value = 10.0, 1.0
        policy.path.exists.return_value = False
        sb = ServiceBinding(policy)
        sb.dependencies = lambda: None   # drop-in/environment pins are covered by existing tests
        return sb

    def show(self, rows):
        text = '\n\n'.join('\n'.join(['Id=' + u] + [k + '=' + str(r[k]) for k in
                           ('MainPID', 'ActiveState', 'NRestarts', 'FragmentPath', 'Restart')]) for u, r in rows.items())
        return patch('mux_publisher_transaction.subprocess.check_output', return_value=text)

    def test_live_identity_accepts_matching_process(self):
        raw, pin = self.attempt()
        b = self.load(raw, pin)
        with self.show(self.live):
            self.service_binding().check(b)

    def test_pid_reuse_replacement_restart_and_boot_drift_rejected_live(self):
        raw, pin = self.attempt()
        b = self.load(raw, pin)
        reused = copy.deepcopy(b); reused['services'][UNITS[0]]['start_ticks'] += 1   # same PID, new process
        with self.show(self.live), self.assertRaisesRegex(ValueError, 'process identity drift'):
            self.service_binding().check(reused)
        replaced = copy.deepcopy(self.live); replaced[UNITS[0]]['MainPID'] = str(os.getppid())
        with self.show(replaced), self.assertRaisesRegex(ValueError, 'process identity drift'):
            self.service_binding().check(b)
        restarted = copy.deepcopy(self.live); restarted[UNITS[1]]['NRestarts'] = '2'  # automatic restart
        with self.show(restarted), self.assertRaisesRegex(ValueError, 'protected service drift'):
            self.service_binding().check(b)
        with self.show(self.live), self.assertRaisesRegex(ValueError, 'boot identity changed'):
            self.service_binding(boot='rebooted').check(b)

    def test_each_attempt_has_its_own_root_and_needs_a_valid_pin(self):
        self.assertNotEqual(transaction_root('a' * 64), transaction_root('b' * 64))
        self.assertTrue(transaction_root('a' * 64).name.startswith('mux-transaction-f95c9d2-'))
        with self.assertRaises(ValueError):
            transaction_root('not-a-sha')


if __name__ == '__main__':
    unittest.main()
