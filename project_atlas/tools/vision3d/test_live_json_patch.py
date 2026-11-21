import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from prepare_live_json_patch import prepare,OLD,NEW,sha,BASE_SHA
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'diagnostics'))
from test_dashboard_json_cost import ResponseTests,load_response,Sink

@unittest.skipUnless(os.environ.get('ATLAS_JSON_BASE'),'Set exact live baseline path')
class LiveJson(ResponseTests):
    def setUp(self):
        self.original=Path(os.environ['ATLAS_JSON_BASE']).read_bytes()
        self.candidate=prepare(self.original)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'candidate.py';self.path.write_bytes(self.candidate)
        self.response=load_response(self.path)
    def test_exact_reverse_and_reject_drift(self):
        self.assertEqual(self.candidate.replace(NEW,OLD,1),self.original)
        with self.assertRaises(ValueError):prepare(self.original+b'\n')
    def test_install_rollback_copy(self):
        self.path.write_bytes(self.original);self.assertEqual(sha(self.path.read_bytes()),BASE_SHA)
        self.path.write_bytes(self.candidate);self.assertEqual(self.path.read_bytes(),self.candidate)
        self.path.write_bytes(self.original);self.assertEqual(sha(self.path.read_bytes()),BASE_SHA)
    def test_retained_payload_equivalence(self):
        folder=os.environ.get('ATLAS_JSON_PAYLOADS')
        if not folder:self.skipTest('retained private payloads unavailable')
        oldpath=Path(self.tmp.name)/'old.py';oldpath.write_bytes(self.original);before=load_response(oldpath)
        for name in ('status','map','lidar-view','radar'):
            data=json.loads((Path(folder)/(name+'.json')).read_text(encoding='utf-8'))
            a,b=Sink(),Sink();before(a,200,data);self.response(b,200,data)
            self.assertEqual(json.loads(a.wfile.getvalue()),json.loads(b.wfile.getvalue()))
            self.assertEqual(a.status,b.status)
            self.assertEqual({k:v for k,v in a.headers.items() if k!='Content-Length'},
                             {k:v for k,v in b.headers.items() if k!='Content-Length'})
del ResponseTests
if __name__=='__main__':unittest.main()
