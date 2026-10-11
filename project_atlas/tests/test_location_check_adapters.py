import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from email.message import Message
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_location_check_web as web


class Handler:
    path='/api/location-check'
    def __init__(self,body,origin='http://localhost',action_header='1'):
        self.headers=Message();self.headers['Host']='localhost';self.headers['Origin']=origin
        self.headers['X-Atlas-Location']=action_header;self.headers['Content-Type']='application/json'
        self.headers['Content-Length']=str(len(body));self.rfile=io.BytesIO(body);self.wfile=io.BytesIO()
    def send_response(self,status):self.status=status
    def send_header(self,*a):pass
    def end_headers(self):pass


class WebTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.ros=N(request_location_check=lambda op:self.calls.append(op) or dict(accepted=True,state='CHECKING'))
    def test_start(self):
        h=Handler(b'{"action":"start"}');web.serve(h,self.ros,True)
        self.assertEqual(h.status,202);self.assertEqual(self.calls,['start'])
    def test_no_reseed_or_user_pose(self):
        for body in (b'{"action":"reseed"}',b'{"action":"start","pose":[1,2,3]}'):
            h=Handler(body);web.serve(h,self.ros,True);self.assertEqual(h.status,400)
        self.assertEqual(self.calls,[])
    def test_foreign_origin(self):
        h=Handler(b'{"action":"start"}',origin='https://evil.example');web.serve(h,self.ros,True)
        self.assertEqual(h.status,403);self.assertEqual(self.calls,[])
    def test_no_csrf_header(self):
        h=Handler(b'{"action":"start"}',action_header='');web.serve(h,self.ros,True)
        self.assertEqual(h.status,403)
    def test_oversized(self):
        h=Handler(b' '*129);web.serve(h,self.ros,True);self.assertEqual(h.status,400)
    def test_stale_and_other_boot(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state';b=Path(d)/'boot';b.write_text('current')
            for timestamp,boot in ((90,'current'),(100,'old')):
                p.write_text(json.dumps(dict(state='VERIFIED',written_unix=timestamp,boot_id=boot)))
                self.assertEqual(web.status(p,100,b)['state'],'STALE')
    def test_never_grants_authority_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state';b=Path(d)/'boot';b.write_text('current')
            p.write_text(json.dumps(dict(state='VERIFIED',written_unix=100,boot_id='current',navigation_authorized=True,correction_enabled=True)))
            result=web.status(p,101,b)
            self.assertFalse(result['navigation_authorized']);self.assertFalse(result['correction_enabled'])


@unittest.skipUnless(importlib.util.find_spec('numpy'),'numpy required for ROS snapshot geometry tests')
class GeometryTests(unittest.TestCase):
    def test_snapshot_clock_is_sampled_after_lock_acquisition(self):
        import math
        import threading
        from atlas_location_check_ros import ManualLocationCheck
        from atlas_localization_verify_core import VerifyPolicy
        clock=[10.]
        class ContendedLock:
            def __enter__(self):clock[0]=11.
            def __exit__(self,*args):pass
        header=N(stamp=N(sec=10,nanosec=500000000),frame_id='laser_frame')
        zero=lambda:N(x=0.,y=0.,z=0.)
        cmd=N(linear=zero(),angular=zero())
        scan=N(header=header,ranges=[2.]*360,angle_min=-math.pi,angle_increment=math.pi/180,range_min=.15,range_max=12.)
        tf=N(transform=N(translation=zero(),rotation=N(x=0.,y=0.,z=0.,w=1.)))
        n=N(data_lock=threading.Lock(),scans=[(10.5,scan)],amcl=(0.,0.,0.),amcl_at=10.5,amcl_stamp=10.5,amcl_covariance=[0.]*36,
            get_clock=lambda:N(now=lambda:N(nanoseconds=int(clock[0]*1e9))),logic=N(policy=VerifyPolicy()),tf=N(lookup_transform=lambda *args:tf))
        a=ManualLocationCheck.__new__(ManualLocationCheck)
        a.node=n;a.lock=ContendedLock();a.map_id=a.loaded_id='map';a.motion_epoch=0;a.map_epoch=1;a.last_motion=0.
        a.values={'odom':(10.5,N(header=header,twist=N(twist=cmd))),'imu':(10.5,N(header=header)),
                  'policy':(10.5,N(data='{"stop_latched":true}')),'cmd':(10.5,cmd)}
        with patch.dict(sys.modules,{'rclpy.time':N(Time=N(from_msg=lambda msg:None))}),patch('atlas_location_check_ros.time.monotonic',side_effect=lambda:clock[0]):
            evidence,_=a.evidence()
        self.assertEqual(evidence['odom_age_s'],.5)
        self.assertTrue(evidence['tf_at_scan'])
    def test_future_timestamps_cannot_hide_behind_receipt_age(self):
        from atlas_location_check_ros import checked_age
        self.assertEqual(checked_age(.2,.3),.3)
        for value in (-.01,float('nan'),float('inf')):
            with self.assertRaises(ValueError):checked_age(.2,value)
    def test_all_command_axes_must_be_zero(self):
        from atlas_location_check_ros import command_zero
        cmd=N(linear=N(x=0.,y=0.,z=0.),angular=N(x=0.,y=0.,z=0.))
        self.assertTrue(command_zero(cmd))
        cmd.linear.y=.1;self.assertFalse(command_zero(cmd))
        cmd.linear.y=float('nan');self.assertFalse(command_zero(cmd))
    def test_scan_coverage(self):
        import math
        from atlas_location_check_ros import scan_coverage
        from atlas_localization_verify_core import VerifyPolicy
        scan=N(header=N(frame_id='laser_frame'),ranges=[2.]*360,angle_min=-math.pi,angle_increment=math.pi/180,range_min=.15,range_max=12.)
        self.assertTrue(scan_coverage(scan,VerifyPolicy())[0])
        scan.ranges=[2.]*180+[math.inf]*180
        self.assertFalse(scan_coverage(scan,VerifyPolicy())[0])
        scan.ranges=[math.inf]*360
        self.assertFalse(scan_coverage(scan,VerifyPolicy())[0])
    def test_map_content_and_metadata(self):
        import numpy as np
        from atlas_location_check_ros import loaded_map_matches
        m=dict(w=2,h=2,res=.05,origin=[0.,0.],occupied=np.array([[True,False],[False,False]]),free=np.array([[False,True],[False,True]]))
        msg=N(header=N(frame_id='map'),info=N(width=2,height=2,resolution=.05,origin=N(position=N(x=0.,y=0.),orientation=N(x=0.,y=0.,z=0.,w=1.))),data=[100,0,-1,0])
        self.assertTrue(loaded_map_matches(m,msg))
        msg.data=[100,0,0,0];self.assertFalse(loaded_map_matches(m,msg))

if __name__=='__main__':unittest.main()
