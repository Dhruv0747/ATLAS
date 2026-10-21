"""Offline runtime/HTTP gates. No camera, services or robot process is started."""
import io
import json
import math
from email.message import Message
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from unittest.mock import MagicMock
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_runtime as R
import atlas_vision3d_web as W
from test_vision3d import image,info_with_stamp


class LiveDeploymentTests(unittest.TestCase):
    def test_limits_keep_original_policy(self):
        R.limits(75,80,70)
        for values in ((75.01,50,60),(50,80.01,60),(50,50,70.01),(math.nan,50,60)):
            with self.assertRaises(ValueError):R.limits(*values)

    def test_only_supported_viewer_modes_no_cloud(self):
        for mode in ('depth','concurrent'):
            args=R.driver_args(mode)
            for setting in ('enable_point_cloud:=false','enable_colored_point_cloud:=false',
                            'publish_tf:=false','depth_registration:=false'):
                self.assertIn(setting,args)
        for mode in ('cloud','ir','drive',''):
            with self.assertRaises(ValueError):R.driver_args(mode)

    def test_live_manifest_exact_topics(self):
        with patch.dict('os.environ',{'ATLAS_VISION3D_MANIFEST':str(Path(__file__).parents[1]/'config/vision3d_live.json')}):
            m=W.read_manifest()
        self.assertTrue(m['viewer_runtime'])
        self.assertEqual(set(m['topics'].values()),{'/astra/depth/image_raw','/astra/color/image_raw',
                         '/astra/depth/camera_info','/astra/color/camera_info'})

    def test_fallback_camera_info_cannot_unlock_xyz(self):
        s=W.VisionService({'viewer_runtime':True},clock=lambda:100,wall=lambda:100)
        s.ingest('depth',image());s.ingest('depth_info',info_with_stamp())
        self.assertIsNone(s.pixel(0,0)['xyz_m'])
        with self.assertRaises(ValueError):s.cloud()

    def test_runtime_does_not_start_on_status_or_get(self):
        s=W.VisionService({'viewer_runtime':True,'topics':{'depth':'/astra/depth/image_raw'}})
        with patch.object(R.SESSION,'status',return_value={'state':'OFF'}),patch.object(R.SESSION,'start') as start:
            s.touch();s.status();start.assert_not_called()
        self.assertIsNone(s.transport)

    def handler(self,payload,origin='http://localhost:8088',header='1',route='viewer'):
        class H:
            path='/api/vision3d/'+route
            wfile=io.BytesIO();rfile=io.BytesIO(json.dumps(payload).encode());headers=Message()
            def send_response(self,c):self.code=c
            def send_header(*a):pass
            def end_headers(*a):pass
        h=H();h.headers['Host']='localhost:8088';h.headers['Origin']=origin
        h.headers['X-Atlas-Vision3D']=header;h.headers['Content-Type']='application/json'
        h.headers['Content-Length']=str(len(json.dumps(payload).encode()));return h

    def test_cross_origin_and_missing_custom_header_denied(self):
        for origin,header in (('http://other','1'),('http://localhost:8088','')):
            h=self.handler({'action':'start','mode':'depth'},origin,header)
            with patch.object(R.SESSION,'start') as start:
                W.serve(h,W.VisionService({'viewer_runtime':True}),post=True)
                self.assertEqual(h.code,403);start.assert_not_called()

    def test_only_explicit_post_can_start(self):
        h=self.handler({'action':'start','mode':'depth'})
        with patch.object(R.SESSION,'start') as start,patch.object(R.SESSION,'status',return_value={'state':'CHECKING'}):
            W.serve(h,W.VisionService({'viewer_runtime':True}),post=True)
            start.assert_called_once_with('depth');self.assertEqual(h.code,202)

    def test_unknown_operation_denied(self):
        for payload in ({'action':'record'},{'action':'start','mode':'cloud','extra':True}):
            h=self.handler(payload)
            with patch.object(R.SESSION,'start') as start:
                W.serve(h,W.VisionService({'viewer_runtime':True}),post=True)
                self.assertEqual(h.code,409);start.assert_not_called()

    def test_pause_cancels_only_owned_viewer(self):
        h=self.handler({'action':'stop'})
        with patch.object(R.SESSION,'stop') as stop:
            W.serve(h,W.VisionService({'viewer_runtime':True}),post=True)
            stop.assert_called_once();self.assertEqual(h.code,202)

    def test_worker_bounds_and_no_production_restart(self):
        source=Path(R.__file__).read_text()
        self.assertEqual(R.MAX_SECONDS,60)
        self.assertIn('last_lease>4',source)
        self.assertIn('signal.SIGKILL',source)
        self.assertNotIn("['systemctl'",source)
        self.assertNotIn('cpu-report-only',source)

    def test_install_rollback_rehearsal(self):
        sys.path.insert(0,str(Path(__file__).parents[1]/'tools/vision3d'))
        import deploy_vision_lab as D
        with tempfile.TemporaryDirectory() as tmp:
            D.rehearsal(Path(tmp)/'root',Path(tmp)/'backup',
                        {'scripts/atlas_status_web.py':b'candidate','web/v2/vision3d.html':b'new'})
            self.assertEqual((Path(tmp)/'root/scripts/atlas_status_web.py').read_bytes(),b'prior fixture\n')
            self.assertFalse((Path(tmp)/'root/web/v2/vision3d.html').exists())

    def test_live_patch_refuses_wrong_anchor(self):
        import deploy_vision_lab as D
        with self.assertRaises(ValueError):D.patch_baseline('scripts/atlas_status_web.py',b'unrecognized source')

    def worker_fixture(self,tmp,cpu):
        runtime=Path(tmp)/'runtime';runtime.mkdir();entries=[]
        import hashlib
        for i in range(458):
            (runtime/str(i)).write_bytes(b'fixture');entries.append({'path':str(i),'sha256':hashlib.sha256(b'fixture').hexdigest()})
        (runtime/'manifest.json').write_text(json.dumps({'files':entries}))
        class AdmissionError(RuntimeError):
            evidence={'cpu':cpu,'ram':50,'temp':60}
        def check(*_,**kwargs):
            if cpu>75:raise AdmissionError('CPU limit')
            return {'ram_percent':50,'thermal_c':{'test':60}}
        gate=SimpleNamespace(services=lambda:{},ticks=lambda:(1,1),cpu_delta=lambda *_:cpu,
                             check=check,require_cpu=check,AdmissionError=AdmissionError)
        return runtime,gate

    def test_worker_resource_failure_never_opens_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime,gate=self.worker_fixture(tmp,90)
            with patch.object(R,'RUNTIME',runtime),patch.object(R,'STATE',Path(tmp)/'state.json'),\
                 patch.dict(sys.modules,{'stationary_gate':gate,'stationary_ros_probe':SimpleNamespace(extra_safety=lambda **_:None,safety_snapshot=lambda:{'ros':{}})}),\
                 patch.object(R.time,'sleep'),patch.object(R.signal,'signal'),patch.object(R.subprocess,'Popen') as launch:
                R.worker('depth');launch.assert_not_called()
                self.assertEqual(json.loads((Path(tmp)/'state.json').read_text())['state'],'RESOURCE BLOCKED')

    def test_worker_lease_eof_stops_owned_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime,gate=self.worker_fixture(tmp,50)
            child=MagicMock(pid=98765);child.poll.return_value=None
            with patch.object(R,'RUNTIME',runtime),patch.object(R,'STATE',Path(tmp)/'state.json'),\
                 patch.dict(sys.modules,{'stationary_gate':gate,'stationary_ros_probe':SimpleNamespace(extra_safety=lambda **_:None,safety_snapshot=lambda:{'ros':{}})}),\
                 patch.object(R.time,'sleep'),patch.object(R.signal,'signal'),\
                 patch.object(R.subprocess,'run',return_value=SimpleNamespace(returncode=1)),\
                 patch.object(R.subprocess,'Popen',return_value=child),\
                 patch('select.select',return_value=([1],[],[])),patch.object(R.os,'read',return_value=b''),\
                 patch.object(R.os,'killpg') as kill:
                R.worker('depth');kill.assert_called_once_with(98765,R.signal.SIGINT)
                data=json.loads((Path(tmp)/'state.json').read_text())
                self.assertTrue(data['driver_stopped']);self.assertIn('paused',data['reason'])

    def test_process_metrics_preserves_unknown_exit(self):
        row,previous=R.process_metrics(999999999)
        self.assertEqual(row['state'],'unavailable');self.assertIsNone(previous)


if __name__=='__main__':unittest.main()
