import tempfile
from pathlib import Path
import unittest
from restore_original_recovery_once import prepare,TEXT
from restart_policy import save

class Fake:
    def __init__(self,root):
        self.root=Path(root);self.state=self.root/'transaction.json';self.override=self.root/'unit.d/99.conf';self.unit='fake';self.calls=[];self.values={'MainPID':'0','ActiveState':'failed','Job':'','Restart':'always'}
    def check(self):pass
    def prop(self,k):return self.values[k]
    def command(self,*a):
        self.calls.append(a)
        if a==('daemon-reload',):self.values['Restart']='no'

class Tests(unittest.TestCase):
    def test_stopped_policy_bound_without_start(self):
        with tempfile.TemporaryDirectory() as d:
            tx=Fake(d);prepare(tx)
            self.assertEqual(tx.override.read_text(),TEXT)
            self.assertNotIn('ATLAS_RESTART_SNAPSHOT',tx.override.read_text())
            self.assertEqual(tx.calls,[('daemon-reload',)])
            self.assertTrue(tx.state.exists())
            with self.assertRaises(ValueError):prepare(tx)
    def test_running_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            tx=Fake(d);tx.values['MainPID']='123'
            with self.assertRaises(ValueError):prepare(tx)
            self.assertFalse(tx.state.exists());self.assertEqual(tx.calls,[])

if __name__=='__main__':unittest.main()
