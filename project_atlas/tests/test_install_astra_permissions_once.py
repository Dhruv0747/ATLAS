"""Offline transaction tests; no administrator or USB operations."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

PATH=Path(__file__).parents[1]/'tools/diagnostics/install_astra_permissions_once.py'
spec=importlib.util.spec_from_file_location('install_astra',PATH)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class Tests(unittest.TestCase):
    def test_success_sequence(self):
        ops=Mock()
        M.install_transaction(ops)
        self.assertEqual([c[0] for c in ops.mock_calls],
                         ['preflight','install_group','install_rule','restore_current_access','postflight'])

    def test_every_failed_stage_rolls_back_without_retry(self):
        stages=['preflight','install_group','install_rule','restore_current_access','postflight']
        for index,stage in enumerate(stages):
            ops=Mock();getattr(ops,stage).side_effect=RuntimeError(stage)
            with self.subTest(stage=stage),self.assertRaisesRegex(RuntimeError,stage):
                M.install_transaction(ops)
            self.assertEqual([c[0] for c in ops.mock_calls],stages[:index+1]+['rollback'])

    def test_no_mutations_to_undo_after_failed_preflight(self):
        ops=M.Installer()
        with patch.object(M,'run') as call:
            ops.rollback()
        call.assert_not_called()
        self.assertEqual(ops.report['rollback_errors'],[])

    def test_changed_usb_refuses_acl_restore(self):
        ops=M.Installer();ops.acl_touched=True
        ops.helper=Mock();ops.helper.usb_identity.return_value={'changed':True}
        ops.before={'identities':{'old':True}}
        with patch.object(M,'run') as call:ops.rollback()
        call.assert_not_called()
        self.assertIn('changed device',ops.report['rollback_errors'][0])

    def test_group_used_by_other_user_rejected(self):
        group=Mock(gr_gid=1999,gr_mem=['someone_else'])
        with patch.object(M.grp,'getgrnam',return_value=group),patch.object(M.pwd,'getpwall',return_value=[]):
            with self.assertRaisesRegex(RuntimeError,'other users'):M.group_state()

    def test_rule_candidate_hash_is_exact(self):
        rule=PATH.parents[2]/'config/udev/99-atlas-astra-access.rules.candidate'
        self.assertEqual(M.digest(rule),M.RULE_SHA)


if __name__=='__main__':unittest.main()
