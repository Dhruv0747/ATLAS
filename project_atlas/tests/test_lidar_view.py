import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
import ast
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from atlas_lidar_view import project


class ProjectionTests(unittest.TestCase):
    def scan(self):
        return NS(ranges=[1,2,3,4,float('nan'),float('inf'),0],range_min=.1,range_max=10,angle_min=0,angle_increment=math.pi/2)
    def tf(self,yaw=0):
        return NS(translation=NS(x=0,y=0),rotation=NS(x=0,y=0,z=math.sin(yaw/2),w=math.cos(yaw/2)))
    def test_identity_directions_and_invalid(self):
        p=project(self.scan(),self.tf())
        self.assertEqual(p['closest'],dict(front=1,left=2,rear=3,right=4))
        self.assertEqual((p['valid'],p['invalid']),(4,3))
    def test_rotated_sensor_not_assumed_forward(self):
        p=project(self.scan(),self.tf(math.pi/2))
        self.assertAlmostEqual(p['closest']['left'],1)
        self.assertAlmostEqual(p['closest']['front'],4)
    def test_no_returns_unknown_not_zero_clear(self):
        s=self.scan();s.ranges=[float('inf')]
        self.assertTrue(all(x is None for x in project(s,self.tf())['closest'].values()))
    def test_translation_is_included(self):
        s=self.scan();s.ranges=[1];t=self.tf();t.translation.x=.3
        self.assertAlmostEqual(project(s,t)['closest']['front'],1.3)
    def test_invalid_quaternion_rejected(self):
        t=self.tf();t.rotation.w=0
        with self.assertRaises(ValueError):project(self.scan(),t)

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'scripts/atlas_status_web.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='surround_snapshot')
        ns={'time':NS(time=lambda:100.),'rclpy':NS(time=NS(Time=NS(from_msg=lambda x:x)))}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'snapshot','exec'),ns)
        self.snapshot=ns['surround_snapshot']
        self.node=NS(node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=100_000_000_000))),tf_buffer=Mock())
        scan=ProjectionTests().scan();scan.header=NS(stamp=NS(sec=100,nanosec=0),frame_id='laser')
        self.node.surround_scan=(scan,100.,10)
        self.node.tf_buffer.lookup_transform.return_value=NS(transform=ProjectionTests().tf())
    def test_exact_stamp_and_frame(self):
        self.assertEqual(self.snapshot(self.node)['state'],'LIVE')
        args=self.node.tf_buffer.lookup_transform.call_args.args
        self.assertEqual(args[:2],('base_link','laser'))
        self.assertIs(args[2],self.node.surround_scan[0].header.stamp)
    def test_stale_header_not_refreshed_by_receipt(self):
        self.node.surround_scan[0].header.stamp.sec=80
        self.assertEqual(self.snapshot(self.node)['state'],'STALE')
        self.node.tf_buffer.lookup_transform.assert_not_called()
    def test_missing_tf_no_guessed_orientation(self):
        self.node.tf_buffer.lookup_transform.side_effect=RuntimeError('no TF')
        result=self.snapshot(self.node)
        self.assertEqual(result['state'],'TF UNAVAILABLE')
        self.assertEqual(result['points'],[])
    def test_missing_scan_no_clearance(self):
        del self.node.surround_scan
        self.assertEqual(self.snapshot(self.node)['state'],'MISSING')
