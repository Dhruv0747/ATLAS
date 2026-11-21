"""Native/PC fake-root regression matrix; never contacts a service manager."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from stage20_install_evidence import Evidence,sanitize,file_state
from stage20_public_install import deploy,UNIT
from stage20_public_package import prepare
from stage20_public_preflight import validate
from stage20_install_guard import sha
from stage20_package_transaction import rollback
import stage20_package_transaction as transaction


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'root';self.root.mkdir()
        self.units=self.base/'units';self.package=self.base/'package'
        repo=Path(__file__).resolve().parents[3] if len(Path(__file__).resolve().parents)>3 else Path('/')
        installer_source=Path(os.environ.get('STAGE20_INSTALLER_SOURCE',str(repo/'project_atlas/tools/diagnostics')))
        approved=os.environ.get('STAGE20_APPROVED_CAPSULE')
        if approved:
            shutil.copytree(approved,self.package)
            self.m=json.loads((self.package/'MANIFEST.json').read_text())
            # Only diagnostic installer code changes. All nine qualified payloads stay exact.
            from stage20_public_package import INSTALLER
            self.m['installer_hashes']={}
            for name in INSTALLER:
                dest=self.package/'installer'/name
                shutil.copyfile(installer_source/name,dest)
                self.m['installer_hashes']['installer/'+name]=sha(dest)
            self.assertTrue(all(sha(self.package/f['path'])==f['after'] for f in self.m['files']))
            self.m['live_preflight_hashes']={} # Fake root has its own protected sentinel below.
        else:
            self.m=prepare(repo,self.package,{'identities':{},'dependencies':['fixture=1']},'fixture')
        self.m['deployment_ready']=True
        self.sentinel=self.root/'existing-diagnostic.db3';self.sentinel.write_bytes(b'preserve evidence')
        self.m['live_preflight_hashes'][str(self.sentinel)]=sha(self.sentinel)
        self.deps=self.m['dependency_pins'];self.calls=[]
        self.events=[]
    def event(self,step,**data):self.events.append((step,data))
    def runner(self,args):
        self.calls.append(args)
        self.assertFalse(any(x in args for x in ('start','enable','restart','stop')))
    def run_deploy(self,**kw):
        options=dict(owner_approved=True,runner=self.runner,event=self.event);options.update(kw)
        return deploy(self.m,self.package,self.root,self.units,self.deps,**options)
    def unchanged(self):
        self.assertEqual(self.sentinel.read_bytes(),b'preserve evidence')
        self.assertFalse((self.units/UNIT).exists())
        self.assertTrue(all(not (self.root/f['path']).exists() for f in self.m['files']))
    def test_install_hashes_off_duplicate_and_rollback(self):
        result=self.run_deploy()
        self.assertFalse(result['activated']);self.assertFalse(result['autostart'])
        self.assertTrue(all(sha(self.root/f['path'])==f['after'] for f in self.m['files']))
        self.assertEqual(sha(self.units/UNIT),sha(self.root/'tools/stage20_public'/UNIT))
        self.assertNotIn('[Install]',[x.strip() for x in (self.units/UNIT).read_text().splitlines()])
        with self.assertRaisesRegex(ValueError,'existing user unit'):self.run_deploy()
        rollback(result['backup'],self.root)
        (self.units/UNIT).unlink() # Exact isolated unit, manager is simulated.
        self.unchanged();self.assertTrue((Path(result['backup'])/'transaction.json').exists())
    def test_missing_approval(self):
        with self.assertRaisesRegex(ValueError,'approval'):self.run_deploy(owner_approved=False)
        self.unchanged()
    def test_payload_hash_mismatch(self):
        (self.package/self.m['files'][0]['path']).write_text('tampered')
        with self.assertRaisesRegex(ValueError,'package hash'):self.run_deploy()
        self.unchanged()
    def test_installer_hash_mismatch(self):
        (self.package/'installer/stage20_public_install.py').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'installer checksum'):self.run_deploy()
        self.unchanged()
    def test_missing_dependency(self):
        self.deps=[]
        with self.assertRaisesRegex(ValueError,'dependency drift'):self.run_deploy()
        self.unchanged()
    def test_permission_failure(self):
        with patch.object(transaction,'atomic_copy',side_effect=PermissionError('injected EACCES')):
            with self.assertRaises(PermissionError):self.run_deploy()
        self.unchanged();self.assertIn('payload_rollback_complete',[x[0] for x in self.events])
    @unittest.skipIf(os.name=='nt' or getattr(os,'geteuid',lambda:0)()==0,'native unprivileged POSIX permission check')
    def test_native_permission_refusal(self):
        target=self.root/'tools';target.mkdir();target.chmod(0o500)
        try:
            with self.assertRaises(PermissionError):self.run_deploy()
            self.unchanged()
        finally:target.chmod(0o700)
    def test_target_collision(self):
        target=self.root/self.m['files'][0]['path'];target.parent.mkdir(parents=True);target.write_text('user edit')
        with self.assertRaisesRegex(ValueError,'live-file drift'):self.run_deploy()
        self.assertEqual(target.read_text(),'user edit')
        self.assertFalse((self.root/'data/backups').exists())
    def test_low_disk(self):
        with patch('stage20_public_install.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):
            with self.assertRaisesRegex(OSError,'reserve'):self.run_deploy()
        self.unchanged()
    def test_resource_refusal(self):
        status={'ros':{'control_policy':{'age':.1,'value':{'source':'STOPPED','stop_latched':True}},
                       'cmd_vel':{'age':.1,'value':{'lin':0,'ang':0}}},
                'system':{'cpu_percent':76,'ram_percent':70,'temp':'59 C'}}
        with self.assertRaisesRegex(ValueError,'headroom'):validate(status)
        self.unchanged()
    def test_registration_failure_restores_targets(self):
        count=0
        def runner(args):
            nonlocal count
            self.runner(args)
            if 'daemon-reload' in args:
                count+=1
                if count==1:raise subprocess.CalledProcessError(1,args,stderr='simulated registration failure')
        with self.assertRaises(subprocess.CalledProcessError):self.run_deploy(runner=runner)
        self.unchanged();self.assertEqual(count,2)
        self.assertIn('unit_rollback_complete',[x[0] for x in self.events])
    def test_partial_copy_rollback(self):
        original=transaction.atomic_copy;count=0
        def copy_file(*args):
            nonlocal count
            count+=1
            if count==3:raise OSError('third file failure')
            return original(*args)
        with patch.object(transaction,'atomic_copy',side_effect=copy_file):
            with self.assertRaisesRegex(OSError,'third'):self.run_deploy()
        self.unchanged();self.assertIn('payload_rollback_complete',[x[0] for x in self.events])
    def test_evidence_sink_failure_still_rolls_back(self):
        def event(step,**data):
            if step=='unit_registration' or 'rollback' in step:raise OSError('evidence disk unavailable')
        with self.assertRaises(OSError):self.run_deploy(event=event)
        self.unchanged()
    def test_failed_child_stderr_is_retained_and_redacted(self):
        path=self.base/'failure.jsonl';e=Evidence(path,{'manifest_sha256':'identity'},[self.sentinel])
        e.phase('child_preflight')
        try:e.runner([sys.executable,'-c',"import sys; print('token=hidden',file=sys.stderr); sys.exit(7)"])
        except subprocess.CalledProcessError as exc:e.finish(exc)
        records=[json.loads(x) for x in path.read_text().splitlines()]
        self.assertEqual(records[-1]['exit_code'],7)
        self.assertEqual(records[-1]['step'],'child_preflight')
        self.assertIn('[REDACTED]',records[-1]['stderr']);self.assertNotIn('hidden',records[-1]['stderr'])
        # The command in CalledProcessError also contains the synthetic secret; sanitized too.
        self.assertNotIn('token=hidden',path.read_text())
        self.assertFalse(records[-1]['net_target_change'])
        self.assertTrue(records[-1]['traceback'])
    def test_redacts_common_secret_formats(self):
        out=sanitize({'password':'hidden','message':'Bearer abc password="hello world" pin=1234 https://user:pass@host/'})
        self.assertNotIn('hidden',str(out));self.assertNotIn('hello world',str(out));self.assertNotIn('1234',str(out))
    def test_existing_evidence_refused(self):
        path=self.base/'old.jsonl';path.write_text('old evidence')
        with self.assertRaises(FileExistsError):Evidence(path,{})
        self.assertEqual(path.read_text(),'old evidence')
    def test_cli_manifest_refusal_is_durable(self):
        path=self.base/'cli.jsonl'
        result=subprocess.run([sys.executable,str(self.package/'installer/stage20_public_install.py'),
            '--package',str(self.package),'--root',str(self.root),'--install','--owner-approved-install',
            '--expected-manifest-sha256','0'*64,'--evidence-output',str(path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        last=json.loads(path.read_text().splitlines()[-1])
        self.assertEqual(last['failing_step'],'manifest_identity')
        self.assertFalse(last['filesystem_write_attempted']);self.assertFalse(last['rollback_attempted'])
        self.assertIn('checksum mismatch',last['error']);self.unchanged()
    def test_cli_requires_evidence_before_action(self):
        result=subprocess.run([sys.executable,str(self.package/'installer/stage20_public_install.py'),
            '--package',str(self.package),'--root',str(self.root),'--install','--owner-approved-install'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.unchanged()
    def test_rollback_evidence_retains_origin(self):
        path=self.base/'rollback.jsonl'
        e=Evidence(path,{'manifest':'fixture'},[self.root/f['path'] for f in self.m['files']]+[self.units/UNIT])
        count=0
        def runner(args):
            nonlocal count
            if 'daemon-reload' in args:
                count+=1
                if count==1:raise subprocess.CalledProcessError(9,args,stderr='registration denied')
        try:self.run_deploy(runner=runner,event=e.phase)
        except subprocess.CalledProcessError as exc:e.finish(exc)
        last=json.loads(path.read_text().splitlines()[-1])
        self.assertEqual(last['failing_step'],'unit_registration')
        self.assertTrue(last['filesystem_write_attempted']);self.assertTrue(last['rollback_attempted'])
        self.assertEqual(last['rollback_result'],'restored');self.assertFalse(last['net_target_change'])
        self.unchanged()

if __name__=='__main__':unittest.main()
