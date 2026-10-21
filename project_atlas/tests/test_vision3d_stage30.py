"""Observer-overhead regression checks; never contacts robot/starts camera."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import stationary_ros_probe as P
import stationary_gate as G


def safe_ros():
    r={k:{'age':.1,'value':0} for k in ('lidar','imu_full','enc_m1','enc_m2','enc_m3','enc_m4',
                                     'camera_info','drive_pid','mission_status','motor_speed')}
    r['drive_pid']['value']={'wheels':[{'output':0,'target_mps':0} for _ in range(4)]}
    r['mission_status']['value']='READY';r['camera_info']['value']={'publisher_count':1}
    return r


class SharedSafetyTests(unittest.TestCase):
    def verify(self,r):
        with patch.object(P.os,'access',return_value=True),\
             patch.object(P.subprocess,'check_output',side_effect=['2bc5:0403','2bc5:0501']),\
             patch('urllib.request.urlopen') as http:
            value=P.extra_safety(ros=r);http.assert_not_called();return value

    def test_provided_fresh_snapshot_has_no_duplicate_get(self):
        self.assertTrue(self.verify(safe_ros())['required_fresh'])

    def test_every_original_sensor_still_required(self):
        for key in safe_ros():
            r=safe_ros();r[key]['age']=2.01
            with self.assertRaises(RuntimeError,msg=key):self.verify(r)

    def test_each_wheel_output_still_zero(self):
        for wheel in range(4):
            r=safe_ros();r['drive_pid']['value']['wheels'][wheel]['output']=1
            with self.assertRaises(RuntimeError):self.verify(r)

    def test_mission_and_motor_state_not_ignored(self):
        for key,value in [('mission_status','NAVIGATING'),('motor_speed',.01)]:
            r=safe_ros();r[key]['value']=value
            with self.assertRaises(RuntimeError):self.verify(r)

    def test_batched_query_is_one_systemctl(self):
        raw='\n\n'.join('Id='+u+'\nMainPID=1\nNRestarts=0\nActiveState=active' for u in G.UNITS)
        with patch.object(G.subprocess,'check_output',return_value=raw) as call:
            self.assertEqual(len(G.services()),6);call.assert_called_once()

    def test_snapshot_reads_existing_light_endpoint(self):
        import io
        response=io.BytesIO(json.dumps({'ros':safe_ros()}).encode())
        with patch('urllib.request.urlopen',return_value=response) as http,\
             patch.object(P.Path,'read_text',return_value='MemTotal: 1000 kB\nMemAvailable: 300 kB\n'):
            value=P.safety_snapshot()
        self.assertEqual(value['system']['ram_percent'],70)
        self.assertEqual(http.call_args.args[0],'http://127.0.0.1:8088/api/commissioning')
        self.assertEqual(http.call_args.kwargs['timeout'],3)

    def test_failed_cpu_never_waits_for_http(self):
        for value in (75.001,float('nan'),float('inf')):
            with patch.object(G.urllib.request,'urlopen') as http:
                with self.assertRaises(G.AdmissionError):G.check(value)
                http.assert_not_called()

    def test_cpu_boundary_is_not_raised(self):
        G.require_cpu(75)
        with self.assertRaises(G.AdmissionError):G.require_cpu(75.00001)


if __name__=='__main__':unittest.main()
