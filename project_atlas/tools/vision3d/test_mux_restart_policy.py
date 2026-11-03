"""Focused offline checks; no real systemctl, ROS or hardware."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mux_restart_policy import MuxPolicy, UNIT

class MuxBindingTests(unittest.TestCase):
    def make(self, root):
        return MuxPolicy(Path(root)/'tx', Path(root)/'units')
    def test_pinned_unit_and_inert_construction(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d)
            self.assertEqual(p.unit,UNIT)
            self.assertFalse(p.state.exists())
    def test_unverified_protection_blocks_before_any_command(self):
        with tempfile.TemporaryDirectory() as d, patch('mux_restart_policy.subprocess.Popen') as proc:
            with self.assertRaisesRegex(ValueError,'independent maintenance'):
                self.make(d).prepare()
            proc.assert_not_called()
    def test_restoration_restart_prohibited(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'restoration restart'):
                self.make(d).restart('rollback')
    def test_resource_boundaries_and_invalid(self):
        for cpu,ram,temp in [(75,50,50),(50,80,50),(50,50,70),(float('nan'),50,50),(None,50,50)]:
            with self.subTest(values=(cpu,ram,temp)), self.assertRaises(ValueError):
                MuxPolicy.resources(cpu,ram,temp)
        MuxPolicy.resources(74.99,79.99,69.99)
    def test_cleanup_requires_existing_durable_budget(self):
        with tempfile.TemporaryDirectory() as d, patch('mux_restart_policy.subprocess.Popen') as proc:
            with self.assertRaisesRegex(ValueError,'missing or unsafe Mux budget'):
                self.make(d).cleanup()
            proc.assert_not_called()
    def test_expired_cleanup_does_not_spawn(self):
        with tempfile.TemporaryDirectory() as d, patch('mux_restart_policy.subprocess.Popen') as proc:
            p=self.make(d);p.cleaning=True;p.deadline=0
            with self.assertRaises(TimeoutError):p.command('stop',UNIT)
            proc.assert_not_called()
    def test_cleanup_never_allows_restart_or_live_policy_restore(self):
        with tempfile.TemporaryDirectory() as d, patch('mux_restart_policy.subprocess.Popen') as proc:
            p=self.make(d);p.cleaning=True
            for action in (lambda:p.command('restart',UNIT),lambda:p.restart('activation'),p.restore_healthy,p.restore_untouched):
                with self.assertRaises(ValueError):action()
            proc.assert_not_called()
    def test_unrelated_unit_command_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch('mux_restart_policy.subprocess.Popen') as proc:
            p=self.make(d);p.cleaning=True
            with self.assertRaises(ValueError):p.command('stop','rover-base-telemetry.service')
            proc.assert_not_called()

if __name__=='__main__':unittest.main()
