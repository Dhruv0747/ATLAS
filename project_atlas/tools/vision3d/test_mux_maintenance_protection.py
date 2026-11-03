"""Maintenance protection: fail-closed default and measured, boot-bound isolation evidence. Offline only."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mux_maintenance_protection as M
from mux_restart_policy import MuxPolicy
import mux_publisher_transaction as tx

WINDOW_START, WINDOW_END = 1000.0, 1090.0  # 60 s worker + 30 s cleanup


def evidence(**over):
    dead = {'volts': 0.0, 'pwm_detected': False}
    e = {'schema': M.SCHEMA, 'boot_id': 'boot-a', 'measured_boottime': 950.0,
         'valid_from_boottime': 950.0, 'valid_until_boottime': 1200.0,
         'actuators': {a: {'connector_open': True, 'battery_powered': dict(dead), 'usb_only': dict(dead)}
                       for a in sorted(M.ACTUATORS)},
         'supply_paths': {'battery_dcdc': {'isolated': True, 'method': 'battery disconnected, meter 0 V'},
                          'jetson_usb_5v': {'isolated': True, 'method': 'outputs measured open on USB only'}},
         'usb_backfeed': {'checked': True, 'mcu_alive_on_usb': True, 'outputs_open': True},
         'auto_restart_units': sorted(M.AUTO_RESTART_UNITS),
         'owner_confirmation': 'M1-M4 and S1/S2 disconnected (owner, 2026-11-03)',
         'electrical_verification': {'method': 'measured', 'instrument': 'DMM', 'measured_by': 'owner'}}
    e.update(over)
    raw = json.dumps(e, sort_keys=True).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def attested(raw, pin, boot='boot-a', start=WINDOW_START, end=WINDOW_END):
    return M.AttestedIsolation(raw, pin, boot, start, end)


class ProtectionTests(unittest.TestCase):
    def test_default_still_refuses_with_original_message(self):
        with self.assertRaisesRegex(ValueError, '^verified independent maintenance protection unavailable$'):
            M.Unavailable().verify(1000.0, 'boot-a')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'independent maintenance'):
                MuxPolicy(Path(d)/'tx', Path(d)/'units').independent_check()

    def test_complete_measured_evidence_covers_window_only(self):
        p = attested(*evidence())
        for now in (950.0, 1000.0, 1200.0):
            p.verify(now, 'boot-a')
        for now, boot in ((949.9, 'boot-a'), (1200.1, 'boot-a'), (1000.0, 'boot-b'), (float('nan'), 'boot-a')):
            with self.subTest(now=now, boot=boot), self.assertRaisesRegex(ValueError, 'expired or boot changed'):
                p.verify(now, boot)

    def test_owner_confirmation_alone_is_not_electrical_verification(self):
        for verification in ({'method': 'owner_confirmation', 'instrument': 'none', 'measured_by': 'owner'},
                             {'method': 'measured', 'instrument': '', 'measured_by': 'owner'},
                             {'method': 'photo', 'instrument': 'camera', 'measured_by': 'owner'}, None):
            with self.subTest(v=verification), self.assertRaisesRegex(ValueError, 'not electrical verification'):
                attested(*evidence(electrical_verification=verification))

    def test_incomplete_or_partial_measurements_rejected(self):
        base = json.loads(evidence()[0])
        cases = []
        a = copy.deepcopy(base['actuators']); a.pop('S2'); cases.append(('actuators', a))
        a = copy.deepcopy(base['actuators']); a['M3'].pop('usb_only'); cases.append(('actuators', a))        # one 0 V reading only
        a = copy.deepcopy(base['actuators']); a['M1']['battery_powered']['volts'] = 0.5; cases.append(('actuators', a))
        a = copy.deepcopy(base['actuators']); a['S1']['usb_only']['pwm_detected'] = True; cases.append(('actuators', a))
        a = copy.deepcopy(base['actuators']); a['M2']['connector_open'] = False; cases.append(('actuators', a))
        s = copy.deepcopy(base['supply_paths']); s.pop('jetson_usb_5v'); cases.append(('supply_paths', s))
        cases.append(('usb_backfeed', {'checked': False, 'mcu_alive_on_usb': True, 'outputs_open': True}))
        cases.append(('auto_restart_units', ['atlas-cmd-vel-mux.service']))
        for key, value in cases:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'unavailable'):
                attested(*evidence(**{key: value}))

    def test_unapproved_other_boot_or_short_validity_rejected(self):
        raw, pin = evidence()
        with self.assertRaisesRegex(ValueError, 'not owner-approved'):
            attested(raw, hashlib.sha256(raw + b' ').hexdigest())
        with self.assertRaisesRegex(ValueError, 'another boot'):
            attested(raw, pin, boot='boot-b')
        with self.assertRaisesRegex(ValueError, 'whole transaction window'):
            attested(*evidence(valid_until_boottime=WINDOW_END - 1))   # would expire during cleanup

    def test_measurement_age_bounded_validity_and_duplicate_keys(self):
        for over, why in (({'measured_boottime': 99.0, 'valid_from_boottime': 99.0}, 'too old'),          # 901 s before start
                          ({'measured_boottime': 1001.0, 'valid_from_boottime': 1001.0}, 'future'),
                          ({'valid_until_boottime': 1e15}, 'unbounded'),
                          ({'valid_from_boottime': 1001.0}, 'window')):
            with self.subTest(why=why), self.assertRaisesRegex(ValueError, 'unavailable'):
                attested(*evidence(**over))
        raw, _ = evidence()
        dup = raw.replace(b'"connector_open": true', b'"connector_open": false, "connector_open": true', 1)
        with self.assertRaisesRegex(ValueError, 'duplicate key'):
            attested(dup, hashlib.sha256(dup).hexdigest())

    def test_policy_checkpoint_uses_evidence_and_fails_closed_after_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            p = MuxPolicy(Path(d)/'tx', Path(d)/'units', attested(*evidence()))
            p.deadline = 1e12
            with patch.object(MuxPolicy, 'boot', return_value='boot-a'), patch.object(MuxPolicy, 'now', return_value=1000.0):
                p.checkpoint()
            with patch.object(MuxPolicy, 'boot', return_value='boot-a'), patch.object(MuxPolicy, 'now', return_value=1201.0):
                with self.assertRaisesRegex(ValueError, 'expired'):
                    p.independent_check()

    def test_transaction_without_pinned_evidence_reports_unavailable(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ATLAS_MUX_PROTECTION_SHA', None)
            with self.assertRaisesRegex(ValueError, '^verified independent maintenance protection unavailable$'):
                tx.protection_evidence(1000.0)
        with tempfile.TemporaryDirectory() as d, patch.object(tx, 'PROTECTION', Path(d)), \
                patch.dict(os.environ, ATLAS_MUX_PROTECTION_SHA='c' * 64):
            with self.assertRaisesRegex(ValueError, '^verified independent maintenance protection unavailable$'):
                tx.protection_evidence(1000.0)   # pinned file absent

    def test_deadline_constants_unchanged(self):
        self.assertEqual((MuxPolicy.WORKER_SECONDS, MuxPolicy.CLEANUP_SECONDS), (60, 30))


if __name__ == '__main__':
    unittest.main()


SAFE_POLICY = {'stop_latched': True, 'manual_only': True, 'commission_armed': False, 'source': 'STOPPED'}
SAFE_ENC = {'packet_fresh': True, 'link_state': 'LIVE', 'packet_age_s': 0.0, 'encoder_interval_delta_m': [0, 0, 0, 0]}


class FakePolicy:
    def boot(self):
        return 'boot-a'

    def now(self):
        import time
        return time.monotonic()

    def checkpoint(self):
        pass


def snapshots(policy=SAFE_POLICY, command=(0,) * 6, enc=SAFE_ENC, age=0.0, boot='boot-a', advance=True):
    import time
    frozen = time.monotonic()   # a fresh but never-advancing publication time

    def read(_path):
        out = time.monotonic() - age if advance else frozen
        obs = {'policy': [policy, out], 'command': [list(command), out], 'encoders': [enc, out]}
        return json.dumps({'boot_id': boot, 'published_mono': out, 'observations': obs}).encode()
    return patch.object(tx, 'read', side_effect=read)


class PreAdmissionTests(unittest.TestCase):
    def test_original_mux_safe_and_advancing_is_admitted(self):
        with snapshots():
            tx.pre_admission(FakePolicy())

    def test_any_unsafe_or_stale_condition_refuses(self):
        cases = {'unlatched': dict(policy=dict(SAFE_POLICY, stop_latched=False)),
                 'commissioning': dict(policy=dict(SAFE_POLICY, commission_armed=True)),
                 'not manual': dict(policy=dict(SAFE_POLICY, manual_only=False)),
                 'command': dict(command=(0, 0, 0, 0.01, 0, 0)),
                 'encoder motion': dict(enc=dict(SAFE_ENC, encoder_interval_delta_m=[0, 0.002, 0, 0])),
                 'link': dict(enc=dict(SAFE_ENC, link_state='STALE')),
                 'stale snapshot': dict(age=0.8), 'other boot': dict(boot='boot-b')}
        for name, kw in cases.items():
            with self.subTest(name), snapshots(**kw), self.assertRaisesRegex(ValueError, 'pre-admission|invalid'):
                tx.pre_admission(FakePolicy())

    def test_non_advancing_snapshot_is_not_admission(self):
        with snapshots(advance=False), self.assertRaisesRegex(ValueError, 'not advancing'):
            tx.pre_admission(FakePolicy(), window=0.3)


class AdmitOrderTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.mig = Path(td.name)
        for d in ('mux-attempts', 'mux-protection'):
            (self.mig / d).mkdir()
        raw, self.ppin = evidence()
        (self.mig / 'mux-protection' / (self.ppin + '.json')).write_bytes(raw)
        import mux_attempt_binding as A
        att = A.canonical({'schema': A.SCHEMA, 'package': tx.PACKAGE, 'boot_id': 'boot-a',
                           'captured_boottime': 990.0, 'services': {}})
        self.apin = hashlib.sha256(att).hexdigest()
        (self.mig / 'mux-attempts' / (self.apin + '.json')).write_bytes(att)
        self.root = self.mig / ('mux-transaction-f95c9d2-' + self.apin[:16])
        files = type('F', (), {'binding': {'boot_id': 'old', 'services': {}, 'files': {}}})()
        self.files = files
        self.patches = [patch.object(tx, 'MIGRATION', self.mig), patch.object(tx, 'ATTEMPTS', self.mig / 'mux-attempts'),
                        patch.object(tx, 'PROTECTION', self.mig / 'mux-protection'),
                        patch.object(MuxPolicy, 'boot', return_value='boot-a'),
                        patch.object(MuxPolicy, 'now', return_value=1000.0),
                        patch.dict(os.environ, ATLAS_MUX_PROTECTION_SHA=self.ppin)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_valid_admission_creates_nothing(self):
        p, binding, attempt_bytes, evidence_bytes = tx.admit(1000.0, self.apin, self.root, self.files)
        self.assertEqual(binding['boot_id'], 'boot-a')
        self.assertFalse(self.root.exists())

    def test_earlier_transaction_blocks_and_unreadable_directory_fails_closed(self):
        (self.mig / 'mux-transaction-f95c9d2-0123456789abcdef').mkdir()
        with self.assertRaisesRegex(ValueError, 'already used'):
            tx.admit(1000.0, self.apin, self.root, self.files)
        with patch.object(tx.os, 'listdir', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                tx.used_transactions()

    def test_protection_and_binding_failures_precede_any_journal(self):
        os.environ['ATLAS_MUX_PROTECTION_SHA'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'protection unavailable'):
            tx.admit(1000.0, self.apin, self.root, self.files)
        os.environ['ATLAS_MUX_PROTECTION_SHA'] = self.ppin
        with self.assertRaisesRegex(ValueError, 'not owner-approved'):
            tx.admit(1000.0, 'e' * 64, self.root, self.files)
        self.assertEqual([n for n in os.listdir(self.mig) if n.startswith('mux-transaction')], [])
