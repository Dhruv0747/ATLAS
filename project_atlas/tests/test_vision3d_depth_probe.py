"""Offline C ABI/mode-policy checks. No vendor library is loaded by these tests."""
import ctypes as C
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import depth_stationary_smoke as D


class ProbeTests(unittest.TestCase):
    def fixture(self):
        return {'kind':'REAL ASTRA DEPTH; no saved frames',
                'selected_mode':{'pixelFormat':100,'resolutionX':160,'resolutionY':120,'fps':30},
                'frames':[{'width':160,'height':120,'frame_index':i,'sdk_timestamp_us':i*33333,
                           'sampled_valid':150} for i in range(15)]}
    def test_native_warning_preserved(self):
        data,messages=D.parse_vendor_result(json.dumps(self.fixture())+'\nWarning: USB priority\n')
        self.assertEqual(len(data['frames']),15);self.assertEqual(messages,['Warning: USB priority'])
    def test_truncated_duplicate_wrong_kind_rejected(self):
        valid=json.dumps(self.fixture())
        for text in (valid[:-2],valid+'\n'+valid,'{"kind":"wrong"}','warning only'):
            with self.assertRaises(ValueError):D.parse_vendor_result(text)
    def test_nonmonotonic_incomplete_invalid_rejected(self):
        for change in ('time','count','pixels'):
            value=self.fixture()
            if change=='time':value['frames'][1]['sdk_timestamp_us']=0
            if change=='count':value['frames'].pop()
            if change=='pixels':
                for f in value['frames']:f['sampled_valid']=0
            with self.assertRaises(ValueError):D.parse_vendor_result(json.dumps(value))
    def test_mode_abi(self):self.assertEqual(C.sizeof(D.Mode),16)
    def test_device_abi(self):self.assertEqual(C.sizeof(D.DeviceInfo),772)
    @unittest.skipUnless(C.sizeof(C.c_void_p)==8,'64-bit layout')
    def test_frame_abi(self):self.assertEqual(C.sizeof(D.Frame),80)
    def test_lowest_advertised_bandwidth(self):
        x=D.choose_mode([D.Mode(100,640,480,30),D.Mode(100,320,240,30)]);self.assertEqual(x.resolutionX,320)
    def test_no_invented_fps(self):
        x=D.choose_mode([D.Mode(100,320,240,30)]);self.assertEqual(x.fps,30)
    def test_units_and_budget_rejected(self):
        for x in [D.Mode(101,320,240,30),D.Mode(100,1280,720,30),D.Mode(100,320,240,60)]:
            with self.assertRaises(RuntimeError):D.choose_mode([x])
    def test_no_recording_or_ros_interface(self):
        s=Path(D.__file__).read_text(encoding='utf8')
        for text in ('oniCreateRecorder(', 'create_publisher(', 'VideoCapture('):self.assertNotIn(text,s)
