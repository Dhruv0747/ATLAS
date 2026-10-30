"""Native PC processes with synthetic model/messages; no Jetson/ROS/API traffic."""
import hashlib,json,shutil,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from atlas_vision_feature_lab import Lab


class Lifecycle(unittest.TestCase):
    def exercise(self,mode):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('atlas_vision_feature_worker.py','atlas_vision_features.py'):
                shutil.copyfile(ROOT/'scripts'/name,root/name)
            (root/'trt_yolo_detector.py').write_text('class TensorRTYOLO:\n def __init__(self,*a):pass\n def close(self):pass\n def infer(self,image):return [(0,0,2,2,0,.9)]\n')
            model=root/'model';model.write_bytes(b'synthetic')
            lab=Lab(root/'reports');lab.settings=lambda:dict(duration_s=2,model_path=str(model),model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
            viewer=NS(lock=threading.RLock(),received={},clock=time.monotonic)
            def frame(kind):
                stamp=time.time_ns();viewer.received[kind]=time.monotonic()
                return NS(width=2,height=2,step=6,encoding='rgb8',data=bytes(12),header=NS(stamp=NS(sec=stamp//10**9,nanosec=stamp%10**9)))
            viewer._fresh=frame;observations=[]
            def observe(cpu,window):
                observations.append(window)
                if mode=='guard_failure' and len(observations)>1:raise ValueError('synthetic CPU rejection')
                return dict(cpu=60,ram=50,temperature=50)
            real_popen=subprocess.Popen;children=[]
            def spawn(args,**kwargs):
                args=list(args);args[1]=str(root/'atlas_vision_feature_worker.py')
                child=real_popen(args,**kwargs);children.append(child);return child
            fake_guard=NS(observe=observe,ticks=lambda:0,cpu_delta=lambda *a:60)
            fake_session=NS(status=lambda:dict(state='ACTIVE',driver_pid=123,startup_guard_baseline_monotonic_s=1))
            with patch.dict(sys.modules,{'atlas_vision_feature_guard':fake_guard,'atlas_vision3d_runtime':NS(SESSION=fake_session)}),patch('subprocess.Popen',side_effect=spawn):
                r=lab.start('object',viewer)
                with self.assertRaisesRegex(ValueError,'one test'):lab.start('target',viewer)
                if mode=='stop':
                    until=time.monotonic()+4
                    while not children and time.monotonic()<until:time.sleep(.02)
                    lab.stop()
                lab.thread.join(timeout=8)
                self.assertFalse(lab.thread.is_alive());self.assertIsNone(lab.active)
                self.assertTrue(children);self.assertTrue(all(c.poll() is not None for c in children))
                raw,h=lab.download('object');self.assertEqual(hashlib.sha256(raw).hexdigest(),h)
                result=json.loads(raw)
                if mode=='complete':
                    self.assertEqual(result['state'],'READY',result['reason']);self.assertGreaterEqual(result['frames'],2)
                    self.assertIsNone(result['manual_verdict'])
                else:self.assertEqual(result['state'],'FAILED')
                if mode=='guard_failure':self.assertIn('CPU rejection',result['reason'])

    def test_complete(self):self.exercise('complete')
    def test_operator_stop(self):self.exercise('stop')
    def test_safety_abort(self):self.exercise('guard_failure')


if __name__=='__main__':unittest.main()
