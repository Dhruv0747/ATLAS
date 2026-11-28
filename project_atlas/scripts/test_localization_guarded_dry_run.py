import json,math,os,signal,sys,tempfile,time,unittest,multiprocessing
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import atlas_localization_dry_run as d
import snapshot_benchmark_once as guard
from test_snapshot_benchmark_once import status

class Tests(unittest.TestCase):
    def msg(self,sec=10): return NS(header=NS(stamp=NS(sec=sec,nanosec=0),frame_id='laser'))
    def test_sensor_freshness_and_duplicates(self):
        self.assertEqual(d.require_fresh(self.msg(),10.5),10)
        for now,prev in [(12,None),(9,None),(float('nan'),None),(10.5,10)]:
            with self.assertRaises(ValueError): d.require_fresh(self.msg(),now,prev)
    def test_invalid_transform(self):
        t=NS(header=NS(frame_id='base_link'),child_frame_id='laser',transform=NS(translation=NS(x=0,y=0,z=0),rotation=NS(x=0,y=0,z=0,w=1)))
        self.assertEqual(d.require_transform(t,'laser'),(0,0,0))
        for value in (0,float('nan'),2):
            t.transform.rotation.w=value
            with self.assertRaises(ValueError): d.require_transform(t,'laser')
    def simulated(self,fail=None,verdict='UNKNOWN'):
        clock=[0.]; reads=[(100,50),(200,100),(300,150)]
        samples=0; started=[]; ended=[]
        class Proc:
            exitcode=None
            def __init__(self,target,args): self.args=args
            def start(self):
                started.append(1)
                Path(self.args[3]).write_text(json.dumps(dict(state=verdict,seeded=False,navigation_authorized=False)))
                if fail is None:self.exitcode=0
            def terminate(self):ended.append(1);self.exitcode=-15
            def kill(self):self.exitcode=-9
            def join(self,timeout):pass
            def is_alive(self):return self.exitcode is None
        def resources():
            nonlocal samples
            samples+=1
            return ((80 if fail=='ram' and samples==2 else 50), {k:(70 if fail=='temp' and samples==2 else 50) for k in guard.THERMAL})
        def fetch(_):
            if samples==2 and fail=='api':raise TimeoutError('API timeout')
            s=status()
            if samples==2 and fail=='estop': s['ros']['control_policy']['value']['stop_latched']=False
            if samples==2 and fail=='stale': s['ros']['encoder_health']['age']=2
            return s
        real_window = guard.run_window
        def window(sample,launch,seconds,**kwargs):
            def sleep(delay): clock[0] += delay
            return real_window(sample,launch,seconds,clock=kwargs.get('clock',lambda:clock[0]),sleep=sleep)
        with patch.object(d.time,'monotonic',side_effect=lambda:clock[0]),patch('stationary_gate.ticks',side_effect=reads),patch('stationary_gate.cpu_delta',side_effect=[50,75 if fail=='cpu' else 50]),patch.object(guard,'resources',side_effect=resources),patch.object(guard,'fetch',side_effect=fetch),patch.object(guard,'run_window',side_effect=window),patch.object(d.multiprocessing,'get_context',return_value=NS(Process=Proc,Value=lambda *a:NS(value=clock[0]))),patch('builtins.print'):
            result=d.run(NS(),NS(map='unused'),{'place':'dhruv room'})
        return result,started,ended
    def test_ambiguity_not_retried(self):
        r,start,_=self.simulated();self.assertEqual(r['state'],'UNKNOWN');self.assertEqual(len(start),1)
    def test_valid_result_still_never_seeded(self):
        r,start,_=self.simulated(verdict='VERIFIED');self.assertEqual(r['state'],'VERIFIED');self.assertFalse(r['seeded']);self.assertFalse(r['navigation_authorized'])
    def test_continuous_safety_failures_kill_only_child(self):
        for failure in ('cpu','ram','temp','estop','stale','api'):
            with self.subTest(failure=failure):
                r,start,end=self.simulated(fail=failure);self.assertEqual(r['state'],'UNKNOWN');self.assertEqual(len(start),1);self.assertEqual(len(end),1);self.assertIn('reason',r)
    def test_os_alarm_interrupts_blocked_processing(self):
        if sys.platform!='linux':self.skipTest('Linux OS deadline')
        # No ROS: block BEFORE any node can be constructed.
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'LIMIT_S',.2):
            p=multiprocessing.get_context('fork').Process(target=d.worker,args=(NS(rclpy=NS(init=lambda:time.sleep(10))),None,None,str(Path(tmp)/'result'),NS(value=0),os.getpid()))
            p.start();p.join(2)
            try:self.assertEqual(p.exitcode,-signal.SIGALRM)
            finally:
                if p.is_alive():p.kill();p.join()
    def test_sensor_watch_rejects_stale_and_missing_tf_during_processing(self):
        inp=object.__new__(d.StrictInputs)
        inp.error=None;inp.last={'scan':10.,'odom':10.};inp.arrival={'scan':time.monotonic(),'odom':time.monotonic()}
        inp.node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=10_500_000_000)))
        inp.scans=[self.msg()];inp.heartbeat=NS(value=0)
        inp.buffer=NS(lookup_transform=lambda *a,**k:(_ for _ in ()).throw(ValueError('TF unavailable')))
        with patch.dict(sys.modules,{'rclpy.time':NS(Time=NS(from_msg=lambda s:s)),'rclpy.duration':NS(Duration=lambda **k:None)}):
            with self.assertRaisesRegex(ValueError,'TF unavailable'):inp.check()
            inp.last['scan']=8
            with self.assertRaisesRegex(ValueError,'stale'):inp.check()
            inp.last={}
            with self.assertRaisesRegex(ValueError,'missing'):inp.check()
        self.assertEqual(inp.heartbeat.value,0)
    def test_named_dry_path_precedes_ros_init(self):
        text=Path(__file__).with_name('seed_atlas_localization.py').read_text()
        main=text[text.index('def main():'):]
        self.assertLess(main.index('return run('),main.index('rclpy.init()'))
        self.assertIn('attempts=1',Path(d.__file__).read_text())

if __name__=='__main__':unittest.main()