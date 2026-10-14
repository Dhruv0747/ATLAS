import tempfile
from pathlib import Path
import unittest
from stage20_install_guard import check,sha

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.pkg=self.root/'package';self.live=self.root/'live'
        for d in (self.pkg,self.live):(d/'scripts').mkdir(parents=True)
        (self.pkg/'scripts/diagnostic.py').write_text('new')
        (self.live/'scripts/diagnostic.py').write_text('old')
        self.m={'deployment_ready':True,'files':[{'path':'scripts/diagnostic.py',
            'before':sha(self.live/'scripts/diagnostic.py'),'after':sha(self.pkg/'scripts/diagnostic.py')}]}
    def test_matching_does_not_write(self):
        self.assertEqual(check(self.m,self.pkg,self.live)['status'],'identities_match')
        self.assertEqual((self.live/'scripts/diagnostic.py').read_text(),'old')
    def test_drift_rejected(self):
        (self.live/'scripts/diagnostic.py').write_text('unexpected')
        with self.assertRaises(ValueError):check(self.m,self.pkg,self.live)
    def test_idempotent(self):
        (self.live/'scripts/diagnostic.py').write_text('new')
        self.assertEqual(check(self.m,self.pkg,self.live)['status'],'already_installed')
    def test_unready_rejected(self):
        self.m['deployment_ready']=False
        with self.assertRaises(ValueError):check(self.m,self.pkg,self.live)
    def test_tampered_package_rejected(self):
        (self.pkg/'scripts/diagnostic.py').write_text('tampered')
        with self.assertRaises(ValueError):check(self.m,self.pkg,self.live)
    def test_control_scope_rejected(self):
        self.m['files'][0]['path']='scripts/yahboom_base.py'
        with self.assertRaises(ValueError):check(self.m,self.pkg,self.live)
if __name__=='__main__':unittest.main()
