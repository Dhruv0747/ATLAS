"""Requires the privately retained exact live source, never contacts Jetson."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'/'vision3d'))
from prepare_live_snapshot_patch import prepare, sha, BASE_SHA, unrelated_ast, REPLACEMENTS
from test_status_web_snapshot_cost import SnapshotTests, load


@unittest.skipUnless(os.environ.get('ATLAS_LIVE_SNAPSHOT_BASE'),
                     'Set ATLAS_LIVE_SNAPSHOT_BASE to verified private live source')
class LiveMethods(SnapshotTests):
    def setUp(self):
        # Reuse every behavioural test against the actual live bytes, not Git's file.
        super().setUp()
        self.original=Path(os.environ['ATLAS_LIVE_SNAPSHOT_BASE']).read_bytes()
        self.candidate=prepare(self.original)
        self.old=load(self.original,self.clock,self.fallback)
        self.new=load(self.candidate,self.clock,self.fallback)

    def test_all_unrelated_code_identical(self):
        self.assertEqual(unrelated_ast(self.original),unrelated_ast(self.candidate))

    def test_baseline_drift_rejected(self):
        with self.assertRaises(ValueError): prepare(self.original+b'\n')

    def test_install_and_rollback_on_isolated_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'atlas_status_web.py';backup=root/'backup.py'
            target.write_bytes(self.original);backup.write_bytes(target.read_bytes())
            self.assertEqual(sha(backup.read_bytes()),BASE_SHA)
            target.write_bytes(self.candidate)
            self.assertEqual(sha(target.read_bytes()),sha(self.candidate))
            target.write_bytes(backup.read_bytes())
            self.assertEqual(target.read_bytes(),self.original)

    def test_only_two_exact_byte_replacements(self):
        restored=self.candidate
        for old,new in reversed(REPLACEMENTS):
            self.assertEqual(restored.count(new),1)
            restored=restored.replace(new,old,1)
        self.assertEqual(restored,self.original)


# Avoid unittest rediscovering the imported base class in this module.
del SnapshotTests
if __name__=='__main__': unittest.main()
