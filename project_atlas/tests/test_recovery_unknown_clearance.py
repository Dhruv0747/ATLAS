"""Run actual recovery decision methods without ROS, publishers or motors."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from enum import Enum, auto
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from atlas_scan_geometry import ray_in_base_sector

class Phase(Enum):
    IDLE=auto();CLEARING=auto();PULSE=auto();SETTLE=auto();LOCKOUT=auto()

def recovery():
    tree=ast.parse((Path(__file__).parents[1]/'scripts/atlas_tight_space_recovery.py').read_text())
    names=('sector_min','choose_motion','still_safe','sensors_fresh','tick','stop')
    methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
    ns={'math':math,'ray_in_base_sector':ray_in_base_sector,'Phase':Phase}
    exec(compile(ast.Module(body=methods,type_ignores=[]),'recovery','exec'),ns)
    r=NS(scan=NS(header=NS(stamp=NS(sec=100,nanosec=0)),ranges=[math.inf]*360,range_min=.15,range_max=12.,angle_min=-math.pi,angle_increment=math.pi/180),scan_time=100.,now_s=lambda:100.1,avoid_forward=False,ultra=dict.fromkeys(('front','rear','left','right'),math.inf),direction=-.12,angular=0.)
    values=dict(sensor_timeout_s=1.5,laser_yaw_deg=0.,front_clear_m=.6,rear_clear_m=.55,side_clear_m=.28,pulse_speed=.12,side_balance_for_straight_m=.06)
    r.get_parameter=lambda k:NS(value=values[k])
    r.outputs=[];r.publish_cmd=lambda x=0.,y=0.:r.outputs.append((x,y));r.report=lambda text:None
    for name in names:setattr(r,name,lambda *a,_n=name:ns[_n](r,*a))
    return r

class UnknownClearance(unittest.TestCase):
    def test_all_missing_cannot_choose_motion(self):
        self.assertIsNone(recovery().choose_motion())
    def test_missing_rear_cannot_continue_reverse(self):
        self.assertFalse(recovery().still_safe())
    def test_blocked_front_unknown_rear_cannot_reverse(self):
        r=recovery();r.scan.ranges[180]=.2
        self.assertIsNone(r.choose_motion())
    def test_out_of_range_not_clearance(self):
        r=recovery();r.scan.ranges=[100.]*360
        self.assertIsNone(r.choose_motion())
    def test_valid_open_sectors_preserve_choice(self):
        r=recovery();r.scan.ranges=[2.]*360
        self.assertEqual(r.choose_motion()[:2],(.12,0.))
    def test_genuine_close_return_preserved(self):
        r=recovery();r.scan.ranges=[2.]*360;r.scan.ranges[180]=.2
        self.assertEqual(r.sector_min(0,35),.2)
        self.assertLess(r.choose_motion()[0],0)
    def test_old_header_with_fresh_arrival_denied(self):
        r=recovery();r.scan.ranges=[2.]*360;r.scan.header.stamp.sec=90
        self.assertIsNone(r.choose_motion());self.assertFalse(r.still_safe())
    def test_expired_arrival_denied_before_first_pulse(self):
        r=recovery();r.scan.ranges=[2.]*360;r.scan_time=90.
        self.assertIsNone(r.choose_motion())
    def test_zero_and_future_stamps_denied(self):
        for stamp in (0,101):
            r=recovery();r.scan.header.stamp.sec=stamp
            self.assertFalse(r.sensors_fresh())
    def test_missing_scan_denied(self):
        r=recovery();r.scan=None
        self.assertIsNone(r.choose_motion());self.assertFalse(r.still_safe())
    def test_invalid_geometry_denied(self):
        for key,value in [('angle_increment',0.),('angle_min',math.nan),('range_max',math.inf),('range_min',20.)]:
            r=recovery();setattr(r.scan,key,value)
            self.assertFalse(r.sensors_fresh())
    def test_expired_scan_after_clearing_emits_only_zero(self):
        r=recovery();r.scan.ranges=[2.]*360;r.scan.header.stamp.sec=90
        r.phase=Phase.CLEARING;r.deadline=100.;r.tick()
        self.assertEqual(r.outputs,[(0.,0.)]);self.assertEqual(r.phase,Phase.LOCKOUT)
    def test_expired_scan_during_pulse_emits_only_zero(self):
        r=recovery();r.scan.ranges=[2.]*360;r.scan.header.stamp.sec=90
        r.phase=Phase.PULSE;r.odom_discontinuity=False;r.lidar_odom_discontinuity=False;r.tick()
        self.assertEqual(r.outputs,[(0.,0.)]);self.assertEqual(r.phase,Phase.LOCKOUT)

if __name__=='__main__':unittest.main()
