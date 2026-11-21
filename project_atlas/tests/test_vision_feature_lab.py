import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import shutil
import time
import base64
from email.message import Message
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from atlas_vision_features import rgb_array,detections,Tracker
from atlas_vision_feature_lab import Lab


class Features(unittest.TestCase):
    def test_rgb_payload_and_stale(self):
        m=NS(width=2,height=1,step=8,encoding='bgr8',data=bytes([1,2,3,4,5,6,0,0]),header=NS(stamp=NS(sec=1,nanosec=42)))
        a,stamp=rgb_array(m,1_000_000_043)
        self.assertEqual(a.tolist(),[[[3,2,1],[6,5,4]]]);self.assertEqual(stamp,1_000_000_042)
        with self.assertRaisesRegex(ValueError,'stale'):rgb_array(m,2_000_000_000)
        m.encoding='mono8'
        with self.assertRaises(ValueError):rgb_array(m,1_000_000_043)

    def test_detection_validation_person_filter(self):
        rows=detections([(0,0,20,20,0,.8),(1,1,10,10,2,.5)],40,40,True)
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['distance_m'])
        with self.assertRaises(ValueError):detections([(0,0,20,20,0,float('nan'))],40,40)

    def test_tracking_ids_and_no_false_identity(self):
        t=Tracker();rows=detections([(0,0,20,20,0,.8)],40,40)
        first=t.update(rows,1_000_000_000)[0]['track_id']
        self.assertEqual(t.update(rows,1_100_000_000)[0]['track_id'],first)
        with self.assertRaises(ValueError):t.update(rows,1_100_000_000)
        self.assertNotEqual(t.update(rows,3_000_000_000)[0]['track_id'],first)

    def test_disabled_and_unimplemented_and_concurrency(self):
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d)
            with self.assertRaisesRegex(ValueError,'disabled'):lab.start('object',None)
            with self.assertRaisesRegex(ValueError,'not installed'):lab.start('gesture',None)
            lab.active='object'
            with self.assertRaisesRegex(ValueError,'one test'):lab.start('target',None)
            self.assertFalse(lab.status()['pan_tilt_allowed'])

    def test_manual_pass_requires_evidence_and_restart_load(self):
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d)
            r=dict(id='a'*32,feature='object',state='READY',reason='complete',frames=2,detections_seen=0)
            lab.reports['object']=r
            with self.assertRaises(ValueError):lab.verdict('object','PASS')
            r['detections_seen']=1
            result=lab.verdict('object','PASS')
            self.assertEqual(result['state'],'PHYSICALLY VERIFIED')
            self.assertEqual(Lab(d).reports['object']['manual_verdict'],'PASS')

    def test_quota_and_atomic_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d);r=dict(id='b'*32,feature='object',state='FAILED',reason='stale',frames=0)
            digest=lab.save(r);path=Path(d)/(r['id']+'.json')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
            with self.assertRaisesRegex(ValueError,'size'):lab.save(dict(r,data='x'*140000))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_guard_rejection_no_optional_process(self):
        fake=NS(status=lambda:dict(state='OFF'))
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,{
            'atlas_vision_feature_guard':NS(observe=lambda *args:None,ticks=lambda:None,cpu_delta=lambda *args:0),
            'atlas_vision3d_runtime':NS(SESSION=fake)}), patch('subprocess.Popen') as spawn:
            lab=Lab(d);r=dict(id='c'*32,feature='object',state='RUNNING',frames=0)
            lab.active='object';lab.reports['object']=r
            lab.run('object',{},None,r)
            spawn.assert_not_called();self.assertEqual(r['state'],'FAILED');self.assertIsNone(lab.active)
            self.assertIn('approved RGB',r['reason'])

    def test_interrupted_session_not_resumed(self):
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d);lab.save(dict(id='d'*32,feature='target',state='RUNNING',reason='old',frames=1))
            loaded=Lab(d)
            self.assertIsNone(loaded.active);self.assertEqual(loaded.reports['target']['state'],'FAILED')

    def test_ui_and_no_actuator_imports(self):
        text=(ROOT/'web/v2/vision_features.js').read_text()
        for feature in ('face','gesture','body','target','object','mapping'):self.assertIn(feature+':',text)
        for file in ('atlas_vision_features.py','atlas_vision_feature_lab.py','atlas_vision_feature_worker.py'):
            source=(ROOT/'scripts'/file).read_text()
            for forbidden in ('create_publisher','create_subscription','servo_cmd','cmd_vel','SESSION.start'):
                self.assertNotIn(forbidden,source)

    def test_native_worker_rejects_hash_before_inference(self):
        with tempfile.TemporaryDirectory() as d:
            model=Path(d)/'model';model.write_bytes(b'not a model')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/atlas_vision_feature_worker.py'),
                                   'object',str(model),'0'*64],capture_output=True,text=True,timeout=8)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('model hash mismatch',result.stdout)

    def test_http_no_touch_and_cross_origin_rejection(self):
        import atlas_vision3d_web as web
        class Handler:
            path='/api/vision3d/features'
            def __init__(self):
                self.headers=Message();self.headers['Host']='localhost:8770'
                self.rfile=io.BytesIO(b'{}');self.wfile=io.BytesIO();self.code=None
            def send_response(self,code):self.code=code
            def send_header(self,*args):pass
            def end_headers(self):pass
        with tempfile.TemporaryDirectory() as d,patch('atlas_vision_feature_lab.LAB',Lab(d)):
            h=Handler();self.assertTrue(web.serve(h,service=NS(touch=lambda:self.fail('viewer touched'))))
            self.assertEqual(h.code,200);self.assertEqual(len(json.loads(h.wfile.getvalue())['features']),6)
            h=Handler();web.serve(h,post=True);self.assertEqual(h.code,403)

    def test_native_ipc_and_hung_inference_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('atlas_vision_feature_worker.py','atlas_vision_features.py'):
                shutil.copyfile(ROOT/'scripts'/name,root/name)
            model=root/'engine';model.write_bytes(b'synthetic test')
            digest=hashlib.sha256(model.read_bytes()).hexdigest()
            for hang in (False,True):
                (root/'trt_yolo_detector.py').write_text(
                    'import time\nclass TensorRTYOLO:\n def __init__(self,*a):pass\n def close(self):pass\n def infer(self,image):\n'+
                    ('  time.sleep(10)\n' if hang else '')+'  return [(0,0,2,2,0,.9)]\n')
                process=subprocess.Popen([sys.executable,'-B',str(root/'atlas_vision_feature_worker.py'),'target',str(model),digest],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                self.assertEqual(json.loads(process.stdout.readline()),{'ready':True})
                packet=dict(width=2,height=2,stamp_ns=time.time_ns(),guard_expires_mono=time.monotonic()+2,rgb=base64.b64encode(bytes(12)).decode())
                output,error=process.communicate(json.dumps(packet)+'\n',timeout=8)
                if hang:self.assertEqual(process.returncode,-14)
                else:
                    self.assertEqual(process.returncode,0,error+output)
                    value=json.loads(output);self.assertEqual(value['stamp_ns'],packet['stamp_ns'])
                    self.assertEqual(value['detections'][0]['track_id'],1)

    def test_stop_kills_only_optional_worker(self):
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d)
            from unittest.mock import Mock
            lab.process=Mock();lab.process.poll.return_value=None
            lab.stop();lab.process.kill.assert_called_once();self.assertTrue(lab.stop_event.is_set())


if __name__=='__main__':unittest.main()
