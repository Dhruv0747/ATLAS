"""Native PC WSL fake systemd units only; no production unit operations."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from recovery_snapshot_runtime import Transaction

@unittest.skipUnless('microsoft' in platform.release().lower() and os.geteuid()==0,'WSL fake units only')
class NativeTests(unittest.TestCase):
    def cmd(self,*args):return subprocess.check_output(['systemctl',*args],text=True).strip()
    def fixture(self,root,suffix):
        name=f'atlas-offline-snapshot-{os.getpid()}-{suffix}.service'
        unit=Path('/run/systemd/system')/name
        unit.write_text('[Service]\nExecStart=/usr/bin/sleep infinity\nExecStop=/usr/bin/sleep 1\nRestart=always\nRestartSec=0.1\n')
        self.cmd('daemon-reload');self.cmd('start',name)
        def clean():
            subprocess.run(['systemctl','stop',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            (unit.parent/(name+'.d')/'99-atlas-snapshot-runtime.conf').unlink(missing_ok=True)
            unit.unlink(missing_ok=True);self.cmd('daemon-reload')
        self.addCleanup(clean)
        return name
    def test_nonblocking_observation_and_budget_and_healthy_restore(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);name=self.fixture(root,'healthy');checks=[]
            tx=Transaction(root,name,'/run/systemd/system',False,lambda:checks.append(time.monotonic()))
            tx.prepare();start=len(checks);tx.restart('activation')
            self.assertGreater(len(checks)-start,8)
            with self.assertRaises(ValueError):tx.restart('activation')
            tx.remove_optin();tx.restart('rollback')
            with self.assertRaises(ValueError):tx.restart('rollback')
            tx.finish();tx.cleanup()
            self.assertEqual(tx.prop('Restart'),'always')
            self.assertNotEqual(tx.prop('MainPID'),'0')
            self.assertNotIn('ATLAS_RESTART_SNAPSHOT',tx.prop('Environment'))
    def test_guard_failure_during_restart_and_idempotent_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);name=self.fixture(root,'guard');tx=Transaction(root,name,'/run/systemd/system',False)
            tx.prepare();calls=[0]
            def fail():
                calls[0]+=1
                if calls[0]>8:raise ValueError('independent safety failed')
            tx.check=fail
            with self.assertRaises(ValueError):tx.restart('activation')
            tx.cleanup();tx.cleanup()
            self.assertEqual(tx.prop('MainPID',False),'0')
            self.assertEqual(tx.prop('Restart',False),'always')
            self.assertNotIn('ATLAS_RESTART_SNAPSHOT',tx.prop('Environment',False))
    def test_systemd_timeout_and_sigkill_execstoppost(self):
        helpers=str(Path(__file__).resolve().parent)
        for phase in ('prepared','activated','timeout'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                root=Path(d);name=self.fixture(root,phase)
                original=root/'unchanged.py';original.write_bytes(b'original installed file')
                outer=Path('/run/systemd/system')/('supervisor-'+name)
                prefix=f"import sys,os,signal,time;from pathlib import Path;sys.path.insert(0,{helpers!r});from recovery_snapshot_runtime import Transaction;tx=Transaction(Path({d!r}),{name!r},'/run/systemd/system',False);"
                recovery=root/'cleanup.py';recovery.write_text(prefix+"tx.cleanup();tx.cleanup();(tx.root/'done').write_text('ok')")
                action='tx.prepare();'
                if phase!='prepared':action+="tx.restart('activation');"
                action+="time.sleep(30)" if phase=='timeout' else 'os.kill(os.getpid(),signal.SIGKILL)'
                driver=root/'driver.py';driver.write_text(prefix+action)
                outer.write_text(f'[Service]\nExecStart=/usr/bin/python3 {driver}\nExecStopPost=/usr/bin/python3 {recovery}\nRestart=no\nRuntimeMaxSec=3\nTimeoutStopSec=15\n')
                try:
                    self.cmd('daemon-reload');self.cmd('start',outer.name)
                    deadline=time.monotonic()+15
                    while not (root/'done').exists() and time.monotonic()<deadline:time.sleep(.1)
                    self.assertTrue((root/'done').exists())
                    self.assertEqual(original.read_bytes(),b'original installed file')
                    tx=Transaction(root,name,'/run/systemd/system',False)
                    self.assertEqual(tx.prop('Restart'),'always')
                    self.assertNotIn('ATLAS_RESTART_SNAPSHOT',tx.prop('Environment'))
                    if phase!='prepared':self.assertEqual(tx.prop('MainPID'),'0')
                    state=tx.load();self.assertTrue(state['restored']);self.assertFalse(state['rollback'])
                    self.assertEqual(tx.prop('NRestarts'),'0')
                finally:
                    subprocess.run(['systemctl','stop',outer.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    outer.unlink(missing_ok=True);self.cmd('daemon-reload')

    def test_full_supervisor_with_native_fake_recovery_and_independent_watcher(self):
        from unittest.mock import patch
        import recovery_snapshot_supervisor as supervisor
        from test_snapshot_benchmark_once import status
        from snapshot_benchmark_once import THERMAL
        helpers=str(Path(__file__).resolve().parent)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runtime=root/'runtime';stage=root/'stage';stage.mkdir()
            (stage/'SHA256SUMS').write_text('')  # no production package in fixture
            name=f'atlas-offline-snapshot-{os.getpid()}-endtoend.service'
            unit=Path('/run/systemd/system')/name
            producer=root/'producer.py'
            producer.write_text(f'''import os,sys,time
from pathlib import Path
sys.path.insert(0,{helpers!r})
from existing_safety_snapshot import Producer
from test_existing_safety_snapshot import observations
p=Producer(Path({str(runtime/'state.json')!r}),Path('/proc/sys/kernel/random/boot_id').read_text().strip())
while True:
 t=time.monotonic()
 if os.environ.get('ATLAS_RESTART_SNAPSHOT')=='1':
  p.values=observations(t);p.receive('command',[0]*6,t)
 time.sleep(.1)
''')
            unit.write_text(f'[Service]\nExecStart=/usr/bin/python3 -B {producer}\nRestart=always\nRestartSec=.1\n')
            self.cmd('daemon-reload');self.cmd('start',name)
            real_popen=subprocess.Popen;real_output=subprocess.check_output
            watcher_code=f'''import sys,time
from pathlib import Path
sys.path.insert(0,{helpers!r})
from restart_policy import save
while True:
 save(Path({str(stage/'health.json')!r}),dict(safe=True,mono=time.monotonic(),estop=True,stationary=True,cpu=60,ram=60,temp=60))
 time.sleep(.2)
'''
            def popen(args,**kw):
                if args[-1]=='--watch':return real_popen([sys.executable,'-B','-c',watcher_code],**kw)
                return real_popen(args,**kw)
            def output(args,**kw):
                if 'atlas-sensor-recovery.service' in args and 'Environment' in args:return ''
                return real_output(args,**kw)
            def identities():return {name:{'MainPID':self.cmd('show',name,'-p','MainPID','--value')}}
            try:
                with patch.object(supervisor,'fetch',return_value=status()),patch.object(supervisor,'resources',return_value=(60,dict.fromkeys(THERMAL,60))),patch.object(supervisor,'ticks',side_effect=lambda:(int(time.monotonic()*10000),int(time.monotonic()*6000))),patch.object(supervisor,'RUNTIME',runtime),patch.object(supervisor,'original_files'),patch.object(supervisor,'units',side_effect=identities),patch.object(supervisor,'verify_camera_off',return_value={'state':'OFF'}),patch.object(supervisor,'Transaction',side_effect=lambda r,**kw:Transaction(r,name,'/run/systemd/system',False,**kw)),patch.object(subprocess,'Popen',side_effect=popen),patch.object(subprocess,'check_output',side_effect=output):
                    supervisor.run(stage)
                self.assertEqual(json.loads((stage/'result.json').read_text())['result'],'PASS')
                self.assertFalse(runtime.exists())
                self.assertEqual(self.cmd('show',name,'-p','Restart','--value'),'always')
                self.assertNotIn('ATLAS_RESTART_SNAPSHOT',self.cmd('show',name,'-p','Environment','--value'))
                self.assertEqual(self.cmd('show',name,'-p','NRestarts','--value'),'0')
            finally:
                subprocess.run(['systemctl','stop',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                (unit.parent/(name+'.d')/'99-atlas-snapshot-runtime.conf').unlink(missing_ok=True)
                unit.unlink(missing_ok=True);self.cmd('daemon-reload')

if __name__=='__main__':unittest.main()
