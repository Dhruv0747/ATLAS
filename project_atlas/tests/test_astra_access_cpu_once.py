"""Offline: no sudo, profiler attachment, ROS, USB operation or network calls."""
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest

PATH = Path(__file__).parents[1]/'tools/diagnostics/astra_access_cpu_once.py'
spec = importlib.util.spec_from_file_location('access_once', PATH)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class Tests(unittest.TestCase):
    def test_command_bounded_nonblocking_single_pid(self):
        args = M.profiler_command(Path('/tmp/py-spy'), 42, Path('/tmp/stacks'))
        self.assertIn('--nonblocking', args)
        self.assertIn('--threads', args)
        self.assertEqual(args[args.index('--duration')+1], '10')
        self.assertEqual(args[args.index('--rate')+1], '20')
        self.assertEqual(args[args.index('--pid')+1], '42')
        self.assertIn('12s', args)
        for option in ('--native','--locals','--subprocesses','--gil','--idle'):
            self.assertNotIn(option, args)

    def test_off_states(self):
        M.require_camera_off({'state':'OFF'}, 1)
        M.require_camera_off({'state':'RESOURCE BLOCKED','driver_stopped':True}, 1)
        for value, rc in [({'state':'ACTIVE'},1), ({'state':'OFF'},0),
                          ({'state':'OFF'},2), ({'state':'RESOURCE BLOCKED'},1)]:
            with self.assertRaises(RuntimeError):
                M.require_camera_off(value, rc)

    def sensors(self):
        ros = {k: {'age': .1, 'value': 0} for k in ('lidar','imu_full','enc_m1','enc_m2',
               'enc_m3','enc_m4','camera_info','drive_pid','mission_status','motor_speed')}
        ros['drive_pid']['value'] = {'wheels':[{'output':0,'target_mps':0} for _ in range(4)]}
        ros['mission_status']['value'] = 'READY'
        ros['camera_info']['value'] = {'publisher_count':1}
        return ros

    def test_sensor_freshness(self):
        M.require_sensors(self.sensors())
        for value in (None, -1, 2.01, math.nan, math.inf):
            ros = self.sensors();ros['lidar']['age'] = value
            with self.assertRaises(RuntimeError):
                M.require_sensors(ros)

    def test_nonzero_wheel_and_mission_rejected(self):
        ros = self.sensors();ros['drive_pid']['value']['wheels'][0]['output'] = 1
        with self.assertRaises(RuntimeError):M.require_sensors(ros)
        ros = self.sensors();ros['mission_status']['value'] = 'MOVING'
        with self.assertRaises(RuntimeError):M.require_sensors(ros)

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'file';p.write_bytes(b'a')
            M.verified_hash(p, hashlib.sha256(b'a').hexdigest())
            with self.assertRaises(RuntimeError):M.verified_hash(p, '0'*64)

    def usb(self, directory):
        for topology, (pid, node) in M.DEVICES.items():
            p = directory/topology;p.mkdir()
            for key,value in {'idVendor':'2bc5','idProduct':pid,'busnum':'1',
                              'devnum':str(int(node.rsplit('/',1)[1]))}.items():
                (p/key).write_text(value)

    @unittest.skipUnless(hasattr(os, 'makedev'), 'Linux device numbers required')
    def test_exact_usb_identity_and_renumber_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.usb(root)
            inspect=lambda n:SimpleNamespace(st_mode=stat.S_IFCHR,st_ino=100,
                                            st_rdev=os.makedev(189,int(n.rsplit('/',1)[1])-1))
            self.assertEqual(len(M.usb_identity(root, inspect)),2)
            (root/'1-2.3.1.2'/'devnum').write_text('22')
            with self.assertRaisesRegex(RuntimeError,'renumbered'):M.usb_identity(root,inspect)

    def test_missing_or_extra_device_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(RuntimeError):M.usb_identity(root)
            p=root/'1-9';p.mkdir();(p/'idVendor').write_text('2bc5');(p/'idProduct').write_text('0403')
            with self.assertRaisesRegex(RuntimeError,'ambiguous'):M.usb_identity(root)


if __name__ == '__main__':unittest.main()
