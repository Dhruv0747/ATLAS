import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from stage20_public_package import prepare
from stage20_public_install import deploy,UNIT

class InstallTests(unittest.TestCase):
    def setUp(self):self.repo=Path(__file__).resolve().parents[3]
    def rehearsal(self,fail=False):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);root=base/'live';root.mkdir();units=base/'user-units'
            m=prepare(self.repo,base/'package',{'identities':{},'dependencies':['fixture=1']},'fixture')
            self.assertFalse(m['deployment_ready']);m['deployment_ready']=True
            calls=[]
            def runner(args):
                calls.append(args)
                if fail and 'is-active' in args:raise RuntimeError('isolated activation failure')
            if fail:
                with self.assertRaises(RuntimeError):deploy(m,base/'package',root,units,['fixture=1'],
                    owner_approved=True,activate=True,activation_approved=True,runner=runner)
                self.assertFalse((units/UNIT).exists())
                self.assertFalse((root/'tools/stage20_public/tools/diagnostics/stage20_capture.py').exists())
                self.assertTrue(list((root/'data/backups').glob('*')))
            else:
                result=deploy(m,base/'package',root,units,['fixture=1'],owner_approved=True,runner=runner)
                self.assertTrue((units/UNIT).exists());self.assertFalse(result['activated'])
            self.assertFalse(any('enable' in a or 'restart' in a for a in calls))
            self.assertTrue(all(not a[-1].endswith('.service') or a[-1].endswith(UNIT) for a in calls))
    def test_install_default_off(self):self.rehearsal()
    def test_activation_failure_rolls_back(self):self.rehearsal(True)
    def test_no_approval_no_writes(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):deploy({},d,d,d,[],runner=lambda a:None)
            self.assertEqual(list(Path(d).iterdir()),[])
if __name__=='__main__':unittest.main()
