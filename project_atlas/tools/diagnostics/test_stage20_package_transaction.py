import tempfile
from pathlib import Path
import unittest
from stage20_install_guard import sha
from stage20_package_transaction import install,rollback
class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.pkg=self.base/'package';self.live=self.base/'live'
        for r in (self.pkg,self.live):(r/'scripts').mkdir(parents=True)
        (self.pkg/'scripts/diagnostic.py').write_text('new')
        (self.live/'scripts/diagnostic.py').write_text('old')
        (self.pkg/'scripts/observer.py').write_text('added')
        self.m={'deployment_ready':True,'files':[
            {'path':'scripts/diagnostic.py','before':sha(self.live/'scripts/diagnostic.py'),'after':sha(self.pkg/'scripts/diagnostic.py')},
            {'path':'scripts/observer.py','before':None,'after':sha(self.pkg/'scripts/observer.py')}]}
    def test_backup_rollback_exact_and_idempotent(self):
        result=install(self.m,self.pkg,self.live,owner_approved=True)
        self.assertEqual(install(self.m,self.pkg,self.live,owner_approved=True)['status'],'already_installed')
        rollback(result['backup'],self.live)
        self.assertEqual((self.live/'scripts/diagnostic.py').read_text(),'old')
        self.assertFalse((self.live/'scripts/observer.py').exists())
    def test_failure_rolls_back(self):
        with self.assertRaises(OSError):install(self.m,self.pkg,self.live,owner_approved=True,fail_after=1)
        self.assertEqual((self.live/'scripts/diagnostic.py').read_text(),'old')
    def test_no_approval_no_writes(self):
        with self.assertRaises(ValueError):install(self.m,self.pkg,self.live)
        self.assertFalse((self.live/'data').exists())
    def test_later_edits_not_overwritten(self):
        result=install(self.m,self.pkg,self.live,owner_approved=True)
        (self.live/'scripts/diagnostic.py').write_text('later user edit')
        with self.assertRaises(ValueError):rollback(result['backup'],self.live)
if __name__=='__main__':unittest.main()
