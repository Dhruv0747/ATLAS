import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import recovery_attribution_trial as m
from test_startup_cpu_attribution import row

class Tests(unittest.TestCase):
    def test_rejected_first_interval_preserves_processes(self):
        a=row();b=copy.deepcopy(a);b['mono']=2;b['cpu']=[200,0,0,100,0,0,0,0];b['groups']={};b['processes']['7'].update(mono=2,user_ticks=45)
        with tempfile.TemporaryDirectory() as d,patch.object(m,'resources',side_effect=AssertionError('no post-rejection probes')):
            p=Path(d)
            with self.assertRaisesRegex(ValueError,'CPU guard'):m.sample(p,1,a,collect=lambda **_:b)
            saved=json.loads((p/'001.json').read_text())
            self.assertEqual(saved['delta']['cpu_pct'],100)
            self.assertEqual(saved['delta']['processes']['7']['delta_ticks'],35)
            self.assertFalse(saved['safe']);self.assertFalse(json.loads((p/'health.json').read_text())['safe'])
    def test_missing_process_retains_gap(self):
        a=row();b=copy.deepcopy(a);b.update(mono=2,processes={},groups={});b['cpu'][3]+=100
        with tempfile.TemporaryDirectory() as d:
            m.sample(Path(d),1,a,collect=lambda **_:b,safety=lambda *_:{'ok':True})
            self.assertEqual(json.loads((Path(d)/'001.json').read_text())['delta']['exited'],['7'])
    def test_observer_failure_retains_endpoint(self):
        a=row();b=copy.deepcopy(a);b.update(mono=2,processes={},groups={});b['cpu'][3]+=100
        for error in (TimeoutError('HTTP'),ValueError('missing safety'),ValueError('stale telemetry')):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(type(error)):m.sample(Path(d),1,a,collect=lambda **_:b,safety=lambda *_:(_ for _ in ()).throw(error))
                self.assertFalse(json.loads((Path(d)/'001.json').read_text())['safe'])
    def test_invalid_time_does_not_pass(self):
        a=row();b=copy.deepcopy(a);b.update(mono=3,processes={},groups={});b['cpu'][3]+=100
        with self.assertRaisesRegex(ValueError,'interval'):m.check(b,a)
    def test_supervisor_missing_observer_timeout(self):
        class Child:
            def poll(self):return None
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(TimeoutError):m.supervise(Child(),Path(d),0,clock=lambda:2,sleep=lambda _:None)
    def test_dead_observer_no_success_file(self):
        class Child:
            returncode=0
            def poll(self):return 0
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):m.supervise(Child(),Path(d),0)
    def test_native_supervisor_sigkill_kills_child_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            code='''import os,subprocess,sys,time
from pathlib import Path
import recovery_attribution_trial as m
p=Path(sys.argv[1]);m.collector.persist(p,0,{'baseline':'durable'})
parent=os.getpid()
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(25)'],preexec_fn=lambda:m.child_limits(parent))
(p/'pid').write_text(str(child.pid))
time.sleep(25)
'''
            parent=subprocess.Popen([sys.executable,'-c',code,d],cwd=Path(m.__file__).parent)
            childpid=None
            try:
                deadline=time.monotonic()+3
                while not (p/'pid').exists() and time.monotonic()<deadline:time.sleep(.01)
                childpid=int((p/'pid').read_text());parent.kill();parent.wait(timeout=1)
                deadline=time.monotonic()+2;alive=True
                while time.monotonic()<deadline:
                    stat=Path('/proc',str(childpid),'stat')
                    if not stat.exists() or stat.read_text().split(') ')[1].startswith('Z'):alive=False;break
                    time.sleep(.02)
                self.assertFalse(alive);self.assertEqual(json.loads((p/'000.json').read_text()),{'baseline':'durable'})
            finally:
                if parent.poll() is None:parent.kill();parent.wait()
                if childpid:
                    try:os.kill(childpid,signal.SIGKILL)
                    except ProcessLookupError:pass
    def test_safety_rejections_use_existing_predicates(self):
        from test_snapshot_benchmark_once import status
        from snapshot_benchmark_once import THERMAL
        a=row();b=copy.deepcopy(a);b.update(mono=2,processes={},groups={});b['cpu'][3]+=100
        for case in ('estop','command','stale','ram','temperature','missing'):
            data=status();ram=50;temps=dict.fromkeys(THERMAL,60)
            if case=='estop':data['ros']['control_policy']['value']['stop_latched']=False
            if case=='command':data['ros']['cmd_vel']['value']['lin']=1
            if case=='stale':data['ros']['encoder_health']['age']=2
            if case=='ram':ram=80.01
            if case=='temperature':temps=dict.fromkeys(THERMAL,70)
            if case=='missing':data={}
            with patch.object(m,'resources',return_value=(ram,temps)),patch.object(m,'fetch',return_value=data):
                with self.assertRaises((ValueError,KeyError,RuntimeError)):m.check(b,a)
    def test_cgroup_discovery_missing_recovery_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mountinfo';p.write_text('1 0 0:1 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n')
            groups,gaps=m.discover_groups({'atlas-localization.service':{'ControlGroup':'/system.slice/localization'}},p)
            self.assertEqual(groups,[('atlas-localization.service','/sys/fs/cgroup/system.slice/localization',2)])
            self.assertTrue(any(x['unit']=='atlas-sensor-recovery.service' for x in gaps))
    def test_package_hashes_reject_tampering(self):
        from build_recovery_attribution_package import build
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'package';build(p)
            with patch.object(m,'ROOT',p):
                m.verify_package();(p/'startup_cpu_attribution.py').write_text('broken')
                with self.assertRaises(ValueError):m.verify_package()
    def test_parent_death_race_exits_without_work(self):
        out=subprocess.run([sys.executable,'-c','import os;import recovery_attribution_trial as m;m.child_limits(os.getppid()+12345)'],cwd=Path(m.__file__).parent)
        self.assertEqual(out.returncode,125)
    def test_native_full_wrapper_simulated_safety(self):
        # Real /proc, child interpreter, parent-death protection, persistence and
        # supervision; HTTP/thermal/service identities are simulated, no ROS.
        code=r"""
import json,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
import recovery_attribution_trial as m
from build_recovery_attribution_package import build
from test_snapshot_benchmark_once import status
from snapshot_benchmark_once import THERMAL
with tempfile.TemporaryDirectory() as d:
    root=Path(d)/'package';build(root);m.ROOT=root
    original=subprocess.Popen
    def launch(cmd,**kwargs):
        script="import sys;from pathlib import Path;import recovery_attribution_trial as m;from test_snapshot_benchmark_once import status;from snapshot_benchmark_once import THERMAL;m.resources=lambda:(50,dict.fromkeys(THERMAL,60));m.fetch=lambda _:status();m.observe(Path(sys.argv[1]),[])"
        return original([sys.executable,'-c',script,str(root/'evidence')],**kwargs)
    with patch.object(m,'units',return_value={'fake':'unchanged'}),patch.object(m,'verify_camera_off'),patch.object(m,'discover_groups',return_value=([],[])),patch.object(m,'resources',return_value=(50,dict.fromkeys(THERMAL,60))),patch.object(m,'fetch',return_value=status()),patch.object(m.subprocess,'Popen',side_effect=launch):
        assert m.run()==0
    first=json.loads((root/'evidence'/'001.json').read_text())
    last=json.loads((root/'evidence'/'012.json').read_text())
    assert .9<=first['delta']['interval']<=1.1
    assert first['previous_mono']==json.loads((root/'evidence'/'baseline.json').read_text())['mono']
    print(json.dumps({'first_interval':first['delta']['interval'],'first_second_observer_cpu_s':first['collector_cpu_s'],'observer_cpu_s_including_imports':last['collector_cpu_s'],'peak_rss_kib':last['collector_peak_rss_kib']}))
"""
        out=subprocess.run([sys.executable,'-c',code],cwd=Path(m.__file__).parent,capture_output=True,text=True,timeout=25)
        self.assertEqual(out.returncode,0,out.stdout+out.stderr)
        print(out.stdout.strip())
    def test_limits_exact_boundary(self):
        # Reuse production validation; CPU and RAM comparisons are inclusive,
        # temperature70 is never accepted. Missing safety never becomes PASS.
        with self.assertRaises(ValueError):m.validate({},75,80,{k:70 for k in m.validate.__globals__['THERMAL']})

if __name__=='__main__':unittest.main()
