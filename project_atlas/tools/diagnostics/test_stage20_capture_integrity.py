import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from stage20_capture_integrity import inspect
class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name)
    def fixture(self):
        (self.p/'data.db3').write_bytes(b'fixture')
        (self.p/'atlas_capture_manifest.json').write_text(json.dumps({'reason':'sigterm'}))
        e={'drops':{},'writer':{'error':None},'files':{'data.db3':hashlib.sha256(b'fixture').hexdigest()}}
        (self.p/'stage20_evidence.json').write_text(json.dumps(e));return e
    def test_interrupted_is_not_deleted(self):
        (self.p/'data.db3').write_bytes(b'partial')
        self.assertFalse(inspect(self.p)['complete']);self.assertTrue((self.p/'data.db3').exists())
    def test_finalized_not_fidelity(self):
        self.fixture();r=inspect(self.p);self.assertTrue(r['complete']);self.assertFalse(r['replay_fidelity_verified'])
    def test_tamper_rejected(self):
        self.fixture();(self.p/'data.db3').write_bytes(b'changed');self.assertFalse(inspect(self.p)['complete'])
    def test_drop_rejected(self):
        e=self.fixture();e['drops']={'scan':1};(self.p/'stage20_evidence.json').write_text(json.dumps(e))
        self.assertFalse(inspect(self.p)['complete'])
    def test_restart_preserves_prior_evidence(self):
        self.fixture();before=(self.p/'data.db3').read_bytes();inspect(self.p);inspect(self.p)
        self.assertEqual((self.p/'data.db3').read_bytes(),before)
if __name__=='__main__':unittest.main()
