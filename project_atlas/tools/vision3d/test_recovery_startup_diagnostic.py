import json,os,platform,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import recovery_startup_diagnostic as m
from restart_policy import save

class TrackingTests(unittest.TestCase):
    def test_no_pid_then_membership_then_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);proc=root/'proc';(proc/'7').mkdir(parents=True);(proc/'self').mkdir()
            fields=['0']*22;fields[0]='S';fields[19]='123';fields[21]='5'
            (proc/'7'/'stat').write_text('7 (recovery) '+' '.join(fields))
            (proc/'7'/'cgroup').write_text('0::/system.slice/fake.service\n')
            (proc/'self'/'mountinfo').write_text('1 0 0:1 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n')
            self.assertEqual(m.target_groups(root,[],proc)[1]['state'],'PID_NOT_YET_OBSERVED')
            save(root/'target.json',{'pid':'7','start_ticks':123})
            groups,state=m.target_groups(root,[],proc)
            self.assertEqual(state['state'],'MEMBERSHIP_OBSERVED');self.assertIn('fake.service',groups[0][1])
            (proc/'7'/'stat').unlink();self.assertEqual(m.target_groups(root,groups,proc)[1]['state'],'TARGET_EXITED')
    def test_pid_reuse_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);proc=root/'proc';(proc/'7').mkdir(parents=True)
            f=['0']*22;f[0]='S';f[19]='999';(proc/'7'/'stat').write_text('7 (fake) '+' '.join(f))
            save(root/'target.json',{'pid':'7','start_ticks':123})
            with self.assertRaisesRegex(ValueError,'reused'):m.target_groups(root,[],proc)
    def test_integrated_rejected_first_interval_has_pid_and_cgroup(self):
        import copy
        from test_startup_cpu_attribution import row
        old=row();current=copy.deepcopy(old);current['mono']=2;current['cpu']=[200,0,0,100,0,0,0,0]
        current['processes']['7'].update(mono=2,user_ticks=60)
        current['groups']['recovery'].update(mono=2,usage_ns=600000000)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=root/'evidence';e.mkdir();save(e/'baseline.json',old);save(e/'groups.json',[])
            with patch.object(m.time,'sleep'),patch.object(m,'target_groups',return_value=([],{'state':'MEMBERSHIP_OBSERVED'})),patch.object(m.counters,'snapshot',return_value=current):
                with self.assertRaisesRegex(ValueError,'CPU guard'):m.observe(root)
            saved=json.loads((e/'001.json').read_text());self.assertFalse(saved['safe'])
            self.assertEqual(saved['delta']['processes']['7']['delta_ticks'],50)
            self.assertEqual(saved['delta']['groups']['recovery']['usage_ns'],500000000)
            self.assertEqual(saved['previous_mono'],1)
    def test_target_exit_fails_closed_with_saved_endpoint(self):
        import copy
        from test_startup_cpu_attribution import row
        old=row();current=copy.deepcopy(old);current.update(mono=2,processes={},groups={});current['cpu'][3]+=100
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e=root/'evidence';e.mkdir();save(e/'baseline.json',old);save(e/'groups.json',[])
            with patch.object(m.time,'sleep'),patch.object(m,'target_groups',return_value=([],{'state':'TARGET_EXITED'})),patch.object(m.counters,'snapshot',return_value=current),patch.object(m.passive,'check',return_value={}):
                with self.assertRaisesRegex(ValueError,'Recovery exited'):m.observe(root)
            self.assertFalse(json.loads((e/'001.json').read_text())['safe'])
    def test_observer_failure_health_closes_actor(self):
        class Child:
            def poll(self):return None
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'evidence').mkdir()
            for value in ({'safe':False,'mono':time.monotonic()},{'safe':True,'mono':time.monotonic()-3}):
                save(p/'evidence'/'health.json',value)
                with self.assertRaises(ValueError):m.health(p,Child())

@unittest.skipUnless('microsoft' in platform.release().lower() and os.geteuid()==0,'PC WSL root fake units ONLY')
class NativeTests(unittest.TestCase):
    def cmd(self,*args):return subprocess.check_output(['systemctl',*args],text=True,stderr=subprocess.STDOUT).strip()
    def fixture(self,root,suffix):
        name='atlas-diag-offline-'+str(os.getpid())+'-'+suffix+'.service';unit=Path('/run/systemd/system')/name
        unit.write_text('[Service]\nType=exec\nExecStart=/usr/bin/sleep infinity\nRestart=always\nRestartSec=0.1\n')
        self.cmd('daemon-reload')
        def clean():
            subprocess.run(['systemctl','stop',name],capture_output=True)
            (unit.parent/(name+'.d')/'99-atlas-snapshot-runtime.conf').unlink(missing_ok=True)
            unit.unlink(missing_ok=True);self.cmd('daemon-reload')
        self.addCleanup(clean)
        return name
    def test_one_start_tracking_and_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);name=self.fixture(root,'success');tx=m.DiagnosticTransaction(root,name,'/run/systemd/system',False)
            tx.prepare();pid=tx.start_once();self.assertEqual(json.loads((root/'target.json').read_text())['pid'],pid)
            with self.assertRaises(ValueError):tx.start_once()
            groups,state=m.target_groups(root,[]);self.assertEqual(state['state'],'MEMBERSHIP_OBSERVED')
            tx.finish();tx.cleanup();self.assertEqual(tx.prop('Restart'),'always');self.assertEqual(tx.prop('MainPID'),pid)
    def test_guard_failure_stops_and_restores_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);name=self.fixture(root,'guard');tx=m.DiagnosticTransaction(root,name,'/run/systemd/system',False)
            tx.prepare();tx.start_once();tx.check=lambda:(_ for _ in ()).throw(ValueError('CPU >75'))
            with self.assertRaises(ValueError):tx.finish()
            tx.cleanup();tx.cleanup();self.assertEqual(tx.prop('MainPID',False),'0');self.assertEqual(tx.prop('Restart',False),'always')
            self.assertTrue(tx.load()['activation']);self.assertFalse(tx.load()['rollback'])
    def test_native_sigkill_and_timeout_execstoppost(self):
        for mode in ('killed','timeout'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);name=self.fixture(root,mode);helper=str(Path(m.__file__).parent)
                prefix=f"import sys,os,signal,time;from pathlib import Path;sys.path.insert(0,{helper!r});from recovery_startup_diagnostic import DiagnosticTransaction;tx=DiagnosticTransaction(Path({d!r}),{name!r},'/run/systemd/system',False);"
                (root/'run.py').write_text(prefix+"tx.prepare();tx.start_once();"+("os.kill(os.getpid(),signal.SIGKILL)" if mode=='killed' else 'time.sleep(15)'))
                (root/'clean.py').write_text(prefix+"tx.cleanup();(tx.root/'cleaned').write_text('yes')")
                outer=Path('/run/systemd/system')/('outer-'+name)
                outer.write_text(f'[Service]\nType=exec\nExecStart=/usr/bin/python3 {root}/run.py\nExecStopPost=/usr/bin/python3 {root}/clean.py\nRestart=no\nRuntimeMaxSec=3\nTimeoutStopSec=15\nKillMode=control-group\n')
                try:
                    self.cmd('daemon-reload');self.cmd('start',outer.name)
                    deadline=time.monotonic()+20
                    while not (root/'cleaned').exists() and time.monotonic()<deadline:time.sleep(.1)
                    self.assertTrue((root/'cleaned').exists());self.assertEqual(self.cmd('show',name,'-p','MainPID','--value'),'0')
                    self.assertEqual(self.cmd('show',name,'-p','Restart','--value'),'always')
                    self.assertEqual(self.cmd('show',name,'-p','NRestarts','--value'),'0')
                finally:
                    subprocess.run(['systemctl','stop',outer.name],capture_output=True);outer.unlink(missing_ok=True);self.cmd('daemon-reload')

if __name__=='__main__':unittest.main()
