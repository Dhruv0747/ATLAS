"""Run actual recovery decision methods without ROS, publishers or motors."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from atlas_scan_geometry import ray_in_base_sector

def recovery():
    tree=ast.parse((Path(__file__).parents[1]/'scripts/atlas_tight_space_recovery.py').read_text())
    methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ('sector_min','choose_motion','still_safe')]
    ns={'math':math,'ray_in_base_sector':ray_in_base_sector}
    exec(compile(ast.Module(body=methods,type_ignores=[]),'recovery','exec'),ns)
    r=NS(scan=NS(ranges=[math.inf]*360,range_min=.15,range_max=12.,angle_min=-math.pi,angle_increment=math.pi/180),avoid_forward=False,ultra=dict.fromkeys(('front','rear','left','right'),math.inf),direction=-.12,angular=0.)
    values=dict(laser_yaw_deg=0.,front_clear_m=.6,rear_clear_m=.55,side_clear_m=.28,pulse_speed=.12,side_balance_for_straight_m=.06)
    r.get_parameter=lambda k:NS(value=values[k]);r.sensors_fresh=lambda:True
    for name in ('sector_min','choose_motion','still_safe'):setattr(r,name,lambda *a,_n=name:ns[_n](r,*a))
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

if __name__=='__main__':unittest.main()
