import json
from pathlib import Path
import tempfile
import unittest
import hashlib
import uuid
from unittest.mock import patch
from stage20_production_gate import verify_approval,IDENTITY_FILES,PUBLIC_RUNTIME_FILES
class ApprovalTests(unittest.TestCase):
    def test_profile_authority_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'approval.json'
            base={'enabled':True,'owner_approved':True,'deployment_ready':True}
            p.write_text(json.dumps(base))
            with self.assertRaisesRegex(ValueError,'stationary_30_v1'):
                verify_approval(p,Path(d),stationary_30=True)
            p.write_text(json.dumps(dict(base,capture_profile='stationary_30_v1')))
            with self.assertRaisesRegex(ValueError,'legacy'):
                verify_approval(p,Path(d))
    def test_default_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'approval';p.write_text(json.dumps({'enabled':False}))
            with self.assertRaises(ValueError):verify_approval(p,Path(d))
    def test_unqualified_package_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'approval';p.write_text(json.dumps({'enabled':True,'owner_approved':True,'deployment_ready':False}))
            with self.assertRaises(ValueError):verify_approval(p,Path(d))
    def test_wrong_scope_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'approval';p.write_text(json.dumps({'enabled':True,'owner_approved':True,'deployment_ready':True,'mode':'drive'}))
            with self.assertRaises(ValueError):verify_approval(p,Path(d))
    def test_future_boot_grant_consumed_once_without_services(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);identity={}
            for name in IDENTITY_FILES:
                f=root/name;f.parent.mkdir(exist_ok=True);f.write_bytes(b'preserved')
                identity[name]=hashlib.sha256(b'preserved').hexdigest()
            p=root/'approval.json';p.write_text(json.dumps({'enabled':True,'owner_approved':True,
                'deployment_ready':True,'mode':'read_only_stationary_startup','source_commit':'fixture',
                'boot_policy':'next_normal_boot_once','approved_before_boot_id':'previous',
                'grant_id':str(uuid.uuid4()),'identity':identity}))
            with patch('stage20_production_gate.current_boot_id',return_value='previous'):
                with self.assertRaises(ValueError):verify_approval(p,root)
            with patch('stage20_production_gate.current_boot_id',return_value='next'):
                self.assertEqual(verify_approval(p,root)['control_authority'],'NONE')
                with self.assertRaises(FileExistsError):verify_approval(p,root)
    def test_partial_current_boot_grant_one_use(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);identity={}
            for name in IDENTITY_FILES:
                f=root/name;f.parent.mkdir(exist_ok=True);f.write_bytes(b'preserved')
                identity[name]=hashlib.sha256(b'preserved').hexdigest()
            (root/'data/diagnostics/stage20_public').mkdir(parents=True)
            runtime={}
            for name in PUBLIC_RUNTIME_FILES:
                f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'capsule')
                runtime[name]=hashlib.sha256(b'capsule').hexdigest()
            p=root/'approval.json';p.write_text(json.dumps({'enabled':True,'owner_approved':True,
                'deployment_ready':True,'mode':'read_only_partial_public','source_commit':'fixture',
                'expires_after_boot_session':'current','grant_id':str(uuid.uuid4()),'identity':identity,
                'runtime_identity':runtime}))
            with patch('stage20_production_gate.current_boot_id',return_value='current'):
                result=verify_approval(p,root)
                self.assertEqual(result['capture_root'],str(root/'data/diagnostics/stage20_public'))
                with self.assertRaises(FileExistsError):verify_approval(p,root)
if __name__=='__main__':unittest.main()
