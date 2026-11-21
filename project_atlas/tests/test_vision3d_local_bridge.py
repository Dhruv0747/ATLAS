import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import local_bridge_observer as B
import stationary_bridge_guard as G


class LocalBridgeTests(unittest.TestCase):
    def data(self):
        return {'updated_monotonic':10,'last_receive_monotonic':{k:10 for k in B.REQUIRED},'errors':[],
                'values':{'/atlas/control_policy':{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'},
                          '/cmd_vel':{'lin':0,'ang':0},'/atlas/mission_status':'READY',
                          '/atlas/drive_pid/diagnostics':{'wheels':[{'output':0,'target_mps':0} for _ in range(4)]}}}
    def test_only_receive_operations(self):
        self.assertEqual(json.loads(B.wire('subscribe',{1:10}))['subscriptions'],[{'id':1,'channelId':10}])
        for op in ('publish','advertise','callService','setParameters'):
            with self.assertRaises(ValueError):B.wire(op,{})
    def test_schema_mismatch_rejected(self):
        with self.assertRaises(ValueError):B.select_new([{'topic':'/scan','encoding':'cdr','schemaName':'bad','id':1}],{})
    def test_direct_safety_pass(self):self.assertTrue(G.direct_safety(self.data(),10.1)['outputs_zero'])
    def test_stale_and_motion_fail(self):
        for kind in ('stale','output','stop','command'):
            data=self.data()
            if kind=='stale':data['last_receive_monotonic']['/scan']=0
            if kind=='output':data['values']['/atlas/drive_pid/diagnostics']['wheels'][0]['output']=1
            if kind=='stop':data['values']['/atlas/control_policy']['stop_latched']=False
            if kind=='command':data['values']['/cmd_vel']['lin']=.1
            with self.assertRaises(RuntimeError):G.direct_safety(data,10.1)
    def test_no_ros_initialization_or_pixel_storage(self):
        code=Path(B.__file__).read_text()
        self.assertNotIn('rclpy.init(',code);self.assertNotIn('create_publisher(',code)
        self.assertNotIn('write_bytes(',code);self.assertIn('127.0.0.1:8765',code)
        self.assertIn('foxglove.sdk.v1',code)
    def test_uncalibrated_manifest_cannot_enable_xyz(self):
        manifest=json.loads((Path(__file__).resolve().parents[1]/'config/vision3d_stage29_depth_verified.json').read_text())
        self.assertEqual(manifest['topics'],{'depth':'/astra/depth/image_raw','rgb':'/astra/color/image_raw'})
        self.assertNotIn('depth_info',manifest['topics']);self.assertNotIn('cloud',manifest['topics'])
        self.assertFalse(manifest['deployment_verified'])
