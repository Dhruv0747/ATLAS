import json
import subprocess
import sys
import unittest
from pathlib import Path
from snapshot_benchmark_once import validate,THERMAL,run_window,terminate


def status():
    return {'ros':{'control_policy':{'age':.01,'value':{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'}},'cmd_vel':{'age':.01,'value':{'lin':0,'ang':0}},'encoder_health':{'age':.01,'value':{'packet_fresh':True,'link_state':'LIVE','packet_age_s':.01,'encoder_interval_delta_m':[0]*4}}}}

class Tests(unittest.TestCase):
    def test_resource_boundaries(self):
        temps=dict.fromkeys(THERMAL,60)
        self.assertTrue(validate(status(),75,80,temps)['stationary'])
        for cpu,ram,t in [(75.01,60,60),(60,80.01,60),(60,60,70),(float('nan'),60,60)]:
            with self.assertRaises(ValueError):validate(status(),cpu,ram,dict.fromkeys(THERMAL,t))
    def test_missing_and_stale_telemetry(self):
        for j in ({},status(),status()):
            if 'ros' in j:j['ros']['encoder_health']['age']=2
            with self.assertRaises((KeyError,ValueError)):validate(j,60,60,dict.fromkeys(THERMAL,60))
    def test_unsafe_policy_and_motion(self):
        for field in ('policy','command','encoder'):
            j=status()
            if field=='policy':j['ros']['control_policy']['value']['stop_latched']=False
            if field=='command':j['ros']['cmd_vel']['value']['ang']=.01
            if field=='encoder':j['ros']['encoder_health']['value']['encoder_interval_delta_m'][0]=.01
            with self.assertRaises((ValueError,RuntimeError)):validate(j,60,60,dict.fromkeys(THERMAL,60))
    def test_timeout_failure_and_interruption_kill_child(self):
        for error in (None,ValueError('guard'),KeyboardInterrupt()):
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
            clock=[0.0]
            def sleep(dt):clock[0]+=dt
            def sample():
                if error:raise error
                return {}
            with self.assertRaises((TimeoutError,ValueError,KeyboardInterrupt)):
                run_window(sample,lambda:child,1,lambda:clock[0],sleep)
            self.assertIsNotNone(child.poll())
    def test_safe_window(self):
        clock=[0.0]
        def sleep(dt):clock[0]+=dt
        self.assertEqual(len(run_window(lambda:{},None,3,lambda:clock[0],sleep)),3)
    def test_no_production_activation(self):
        source=Path(__file__).with_name('snapshot_benchmark_once.py').read_text()
        self.assertNotIn('ATLAS_RESTART_SNAPSHOT',source)
        self.assertNotIn('systemctl',source)
        self.assertNotIn('rclpy',source)

    def test_full_native_wrapper_simulated_telemetry(self):
        import hashlib
        import tempfile
        import time
        from unittest.mock import patch
        import snapshot_benchmark_once as m
        # Run in separate interpreter: resource limits and signal handlers must
        # never affect the test runner. Real child; simulated resources/HTTP only.
        code='''
import hashlib,json,sys,time
from pathlib import Path
from unittest.mock import patch
import snapshot_benchmark_once as m
from test_snapshot_benchmark_once import status
root=Path(sys.argv[1])
units={'fake':{'ActiveState':'active','MainPID':'1'}}
def ticks():
 t=int(time.monotonic()*10000);return t,int(t*.8)
with patch.object(m,'ROOT',root),patch.object(sys,'argv',['wrapper','--approved-once']),patch.object(m,'services',return_value=units),patch.object(m,'verify_camera_off',return_value={'state':'OFF'}),patch.object(m,'fetch',return_value=status()),patch.object(m,'resources',return_value=(50,dict.fromkeys(m.THERMAL,50))),patch.object(m,'ticks',side_effect=ticks):
 sys.exit(m.main())
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('benchmark_safety_snapshot.py','existing_safety_snapshot.py','restart_safety_observer.py'):
                (root/name).write_bytes(Path(__file__).with_name(name).read_bytes())
            (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in root.iterdir()))
            out=subprocess.run([sys.executable,'-B','-c',code,str(root)],capture_output=True,text=True,timeout=30)
            self.assertEqual(out.returncode,0,out.stdout+out.stderr)
            result=json.loads((root/'evidence/result.json').read_text())
            self.assertEqual(result['cleanup'],'VERIFIED')
            self.assertFalse(Path(result['scratch']).exists())
            self.assertTrue((root/'ATTEMPT_USED').exists())
            benchmark=json.loads((root/'evidence/benchmark.json').read_text())
            self.assertEqual(len(benchmark['rows']),6)

if __name__=='__main__':unittest.main()
