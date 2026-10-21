"""Offline admission and cross-build contract checks; never opens a camera."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import stationary_ros_probe as P
import read_astra_intrinsics as I
import ctypes


class ExtraSafetyTests(unittest.TestCase):
    def test_intrinsics_abi_and_rejection(self):
        self.assertEqual(ctypes.sizeof(I.CameraParams),120)
        self.assertTrue(I.valid_intrinsics([570,570,320,240]))
        for values in ([0,570,320,240],[570,float('nan'),320,240],[570,570,900,240]):self.assertFalse(I.valid_intrinsics(values))
    def test_default_cpu_guard_preserved(self):
        with patch.object(P.gate,'check',return_value={}) as check:
            P.resource_sample(90);check.assert_called_once_with(90)
    def test_explicit_cpu_exception_keeps_other_checks(self):
        with patch.object(P.gate,'check',return_value={}) as check:
            self.assertEqual(P.resource_sample(90,True)['cpu_percent'],90);check.assert_called_once_with(None)
        with patch.object(P.gate,'check',side_effect=RuntimeError('thermal failed')):
            with self.assertRaises(RuntimeError):P.resource_sample(90,True)
    def fixture(self):
        keys=('lidar','imu_full','enc_m1','enc_m2','enc_m3','enc_m4','camera_info','drive_pid','mission_status','motor_speed')
        ros={k:{'age':.2,'value':{}} for k in keys}
        ros['drive_pid']['value']={'wheels':[{'output':0,'target_mps':0} for _ in range(4)]}
        ros['mission_status']['value']='READY';ros['motor_speed']['value']=0
        return {'ros':ros}
    def run_check(self,value):
        with patch('urllib.request.urlopen'),patch('json.load',return_value=value),patch.object(P.subprocess,'check_output',return_value='2bc5:0403 2bc5:0501'),patch.object(P.os,'access',return_value=True):return P.extra_safety()
    def test_zero_and_fresh(self):self.assertTrue(self.run_check(self.fixture())['required_fresh'])
    def test_motion_rejected(self):
        value=self.fixture();value['ros']['drive_pid']['value']['wheels'][0]['output']=1
        with self.assertRaises(RuntimeError):self.run_check(value)
    def test_stale_sensor_rejected(self):
        for key in ('lidar','imu_full','camera_info','enc_m4'):
            value=self.fixture();value['ros'][key]['age']=3
            with self.assertRaises(RuntimeError):self.run_check(value)
    def test_active_mission_rejected(self):
        value=self.fixture();value['ros']['mission_status']['value']='RUNNING'
        with self.assertRaises(RuntimeError):self.run_check(value)
    def test_unknown_wheel_rejected(self):
        value=self.fixture();value['ros']['drive_pid']['value']['wheels'].pop()
        with self.assertRaises(RuntimeError):self.run_check(value)
    def test_no_publisher_or_recording_api(self):
        code=Path(P.__file__).read_text()
        for token in ('create_publisher(', 'VideoWriter(', 'rosbag2_py', 'create_client('):self.assertNotIn(token,code)
        self.assertIn("'publish_tf':'false'",code)
    def test_private_dependencies_are_download_only(self):
        code=(Path(P.__file__).parent/'arm64_dependencies.sh').read_text()
        self.assertIn('--download-only',code);self.assertIn('Dir::State::status=/dev/null',code)
        self.assertNotIn('dpkg --add-architecture',code)
