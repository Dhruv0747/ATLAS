import tempfile
from pathlib import Path
import unittest
from existing_safety_snapshot import publish
from test_existing_safety_snapshot import observations
from recovery_snapshot_validation import Validation

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.v=Validation(self.root/'budget.json',self.root/'snapshot','boot')
    def safe(self,t):self.v.independent(t,{'estop':True,'stationary':True,'cpu':60,'ram':60,'temp':60})
    def test_missing_warmup_is_not_admission_then_fails(self):
        self.safe(10);self.v.reserve_restart('activation',10)
        self.assertFalse(self.v.snapshot_check(10)['ready'])
        self.safe(15)
        with self.assertRaises(ValueError):self.v.snapshot_check(15)
    def test_producer_shutdown_and_recovery_stays_latched(self):
        self.safe(10);self.v.reserve_restart('activation',10)
        publish(self.root/'snapshot',observations(10),10,'boot')
        self.assertTrue(self.v.snapshot_check(10.1)['ready'])
        self.safe(11)
        with self.assertRaises(ValueError):self.v.snapshot_check(11)
        publish(self.root/'snapshot',observations(11),11,'boot')
        with self.assertRaises(ValueError):self.v.snapshot_check(11.1)
    def test_http_loss_rejects_even_fresh_snapshot(self):
        self.safe(10);self.v.reserve_restart('activation',10)
        publish(self.root/'snapshot',observations(12),12,'boot')
        with self.assertRaises(ValueError):self.v.snapshot_check(12)
    def test_durable_restart_budget_survives_supervisor_loss(self):
        self.safe(10);self.v.reserve_restart('activation',10)
        other=Validation(self.root/'budget.json',self.root/'snapshot','boot')
        other.independent(11,{'estop':True,'stationary':True,'cpu':60,'ram':60,'temp':60})
        other.reserve_restart('rollback',11)
        with self.assertRaises(ValueError):other.reserve_restart('rollback',11)
        self.safe(12)
        with self.assertRaises(ValueError):self.v.reserve_restart('activation',12)
    def test_progress_and_deadline(self):
        self.safe(10);self.v.reserve_restart('activation',10)
        for t in (10,10.2,10.4):
            publish(self.root/'snapshot',observations(t),t,'boot');self.v.snapshot_check(t)
        self.assertEqual(self.v.updates,3)
        self.safe(51)
        with self.assertRaises(ValueError):self.v.snapshot_check(51)
    def test_strict_resource_admission(self):
        for key,value in [('cpu',75),('ram',80),('temp',70),('estop',False)]:
            row={'estop':True,'stationary':True,'cpu':60,'ram':60,'temp':60};row[key]=value
            with self.assertRaises(ValueError):self.v.independent(10,row)

if __name__=='__main__':unittest.main()
