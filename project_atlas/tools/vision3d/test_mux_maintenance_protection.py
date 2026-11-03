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

WINDOW_END = 1090.0  # start 1000 + 60 s worker + 30 s cleanup


def evidence(**over):
    dead = {'volts': 0.0, 'pwm_detected': False}
    e = {'schema': M.SCHEMA, 'boot_id': 'boot-a', 'valid_from_boottime': 900.0, 'valid_until_boottime': 1200.0,
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


def attested(raw, pin, boot='boot-a', end=WINDOW_END):
    return M.AttestedIsolation(raw, pin, boot, end)


class ProtectionTests(unittest.TestCase):
    def test_default_still_refuses_with_original_message(self):
        with self.assertRaisesRegex(ValueError, '^verified independent maintenance protection unavailable$'):
            M.Unavailable().verify(1000.0, 'boot-a')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'independent maintenance'):
                MuxPolicy(Path(d)/'tx', Path(d)/'units').independent_check()

    def test_complete_measured_evidence_covers_window_only(self):
        p = attested(*evidence())
        for now in (900.0, 1000.0, 1200.0):
            p.verify(now, 'boot-a')
        for now, boot in ((899.9, 'boot-a'), (1200.1, 'boot-a'), (1000.0, 'boot-b'), (float('nan'), 'boot-a')):
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
