import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/vision3d'));sys.path.insert(0,str(ROOT/'scripts'))
from onboard_adapter import configuration,checked_images
from onboard_store import atomic,budget,finalize,recover
from onboard_supervisor import adapter_health,stop_camera
from atlas_map3d_web import payload


class OnboardTests(unittest.TestCase):
    def test_default_cannot_activate(self):
        with self.assertRaisesRegex(ValueError,'disabled'):
            configuration(json.loads((ROOT/'config/onboard_mapping.json').read_text()))

    def test_domains_cannot_collide(self):
        c=json.loads((ROOT/'config/onboard_mapping.json').read_text());c.update(enabled=True,production_domain=77)
        with self.assertRaisesRegex(ValueError,'separate'):configuration(c)

    def test_native_image_admission(self):
        from sensor_msgs.msg import Image,CameraInfo
        docs={k:dict(width=2,height=2,frame_id='astra_optical_frame',k=[2.,0.,1.,0.,2.,1.,0.,0.,1.],d=[0.]*5,distortion_model='plumb_bob') for k in ('rgb','depth')}
        messages={}
        for key in ('rgb','depth','rgb_info','depth_info'):
            m=CameraInfo() if 'info' in key else Image();m.width=m.height=2
            m.header.frame_id='astra_optical_frame';m.header.stamp.sec=100
            if 'info' in key:m.k=docs['rgb']['k'];m.d=[0.]*5;m.distortion_model='plumb_bob'
            else:m.encoding='rgb8' if key=='rgb' else '16UC1';m.step=6 if key=='rgb' else 4;m.data=bytes(m.step*2)
            messages[key]=m
        self.assertEqual(len(checked_images(messages,docs,100100000000)),4)
        with self.assertRaisesRegex(ValueError,'stale'):checked_images(messages,docs,101000000000)
        bad=copy.deepcopy(messages);bad['depth'].encoding='mono16'
        with self.assertRaises(ValueError):checked_images(bad,docs,100100000000)
        bad=copy.deepcopy(messages);bad['rgb_info'].k[0]=0
        with self.assertRaises(ValueError):checked_images(bad,docs,100100000000)
        del bad['depth']
        with self.assertRaisesRegex(ValueError,'missing'):checked_images(bad,docs,100100000000)

    def test_adapter_missing_stale(self):
        a=dict(observed_mono=11,error=None,last_bundle=None,last_odom=None,last_scan=None)
        with self.assertRaisesRegex(ValueError,'timeout'):adapter_health(a,11,0)
        a.update(last_bundle=9,last_odom=11,last_scan=11)
        with self.assertRaisesRegex(ValueError,'stale'):adapter_health(a,11,0)
        a.update(last_bundle=11);adapter_health(a,11,0)

    def test_storage_integrity_and_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'20261030T120000-12345678';p.mkdir()
            atomic(p/'status.json',{'state':'RUNNING'});recover(d)
            self.assertEqual(json.loads((p/'status.json').read_text())['state'],'QUARANTINED')
            self.assertEqual(finalize(p,'test')['state'],'QUARANTINED')
            db=sqlite3.connect(p/'map.db');db.execute('create table Node(id integer)');db.commit();db.close()
            self.assertEqual(finalize(p,'test')['state'],'CLOSED')
            with self.assertRaisesRegex(ValueError,'budget'):budget(p,1,0)
            with self.assertRaisesRegex(ValueError,'reserve'):budget(p,10**9,10**18)

    def test_api_offline_and_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'20261030T120000-12345678';p.mkdir()
            atomic(p/'status.json',{'state':'CLOSED'})
            atomic(p/'cloud.json',dict(label='SYNTHETIC TEST ONLY',frame='map_3d',points=[[1,2,3]]))
            self.assertEqual(len(payload('/api/map3d/sessions',root)['sessions']),1)
            self.assertEqual(payload('/api/map3d/cloud?id='+p.name,root)['points'],[[1,2,3]])
            with self.assertRaises(ValueError):payload('/api/map3d/cloud?id=../../etc/passwd',root)

    def test_cleanup_refuses_other_camera_session(self):
        with tempfile.TemporaryDirectory() as d:
            c={'storage':d};atomic(Path(d)/'camera-owner.json',dict(driver_pid=100,startup=1))
            with patch('onboard_supervisor.read_json',return_value={'runtime':dict(state='RUNNING',driver_pid=101,startup_guard_baseline_monotonic_s=2)}):
                with self.assertRaisesRegex(ValueError,'different'):stop_camera(c)
            self.assertTrue((Path(d)/'camera-owner.json').exists())


if __name__=='__main__':unittest.main()
