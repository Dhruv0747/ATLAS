import ast
import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from atlas_lidar_availability import LidarAvailability

def scan():
    return NS(header=NS(frame_id='laser_frame',stamp=NS(sec=100,nanosec=0)),
        range_min=.15,range_max=12.,angle_min=-math.pi,angle_increment=math.pi/180,ranges=[3.]*360)

def twist(x=0.,z=0.):
    return NS(linear=NS(x=x,y=0.,z=0.),angular=NS(x=0.,y=0.,z=z))

def mux(source='NAV2',msg=None):
    tree=ast.parse((Path(__file__).parents[1]/'scripts/atlas_cmd_vel_mux.py').read_text())
    methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ('watchdog','lidar_command_guard')]
    scope=dict(time=NS(monotonic=lambda:10.1),Twist=twist,String=lambda data:NS(data=data))
    exec(compile(ast.Module(body=methods,type_ignores=[]),'mux','exec'),scope)
    m=NS(remote_stop=NS(check=lambda now:False),channels={'COMMISSION':NS(engaged=False)},
        commission_until=0.,active_name=None,encoder_health_rx=10.,encoder_health={'state':'HEALTHY','autonomy_ready':True},
        last_blocked_reason=None,output=Mock(),safety_output=Mock(),last_sent=twist(),
        navigation_localization_guard=lambda *a:None,autonomous_guard=lambda *a:None,
        get_clock=lambda:NS(now=lambda:NS(nanoseconds=100100000000)),lidar_availability=LidarAvailability(),
        ultrasonic_validity=NS(reading=lambda *a:(None,'UNKNOWN')),ultrasonic_enabled=False,
        radar_gate_enabled=False,copy_twist=copy.deepcopy,publish=Mock(),hold_remote_stop=Mock(),
        get_logger=lambda:Mock())
    m.live_channel=lambda now:NS(name=source,command=msg or twist(.15))
    m.lidar_command_guard=lambda *a:scope['lidar_command_guard'](m,*a)
    m.watchdog=lambda:scope['watchdog'](m)
    return m

class Availability(unittest.TestCase):
    def test_no_scan_vetoes_nav2_and_recovery(self):
        for source in ('NAV2','RECOVERY'):
            m=mux(source);m.watchdog()
            self.assertEqual(m.output.publish.call_args.args[0].linear.x,0.)
            m.publish.assert_not_called()
    def test_good_scan_preserves_command(self):
        m=mux();m.lidar_availability.update(scan(),10.);m.watchdog()
        self.assertEqual(m.publish.call_args.args[0].linear.x,.15)
    def test_manual_remote_unchanged_without_scan(self):
        m=mux('REMOTE',twist(-.2,.4));m.watchdog()
        self.assertEqual(m.publish.call_args.args[0].linear.x,-.2)
        self.assertEqual(m.publish.call_args.args[0].angular.z,.4)
    def test_estop_preempts_guard_and_all_commands(self):
        m=mux();m.remote_stop.check=lambda now:True;m.watchdog()
        m.hold_remote_stop.assert_called_once();m.publish.assert_not_called()
    def test_unknown_rear_blocks_reverse_not_observed_forward(self):
        s=scan();s.ranges[135:225]=[math.nan]*90 # yaw 180 => rear
        g=LidarAvailability();g.update(s,10.)
        self.assertIsNotNone(g.reason(-.15,0.,100.1,10.1))
        self.assertIsNone(g.reason(.15,0.,100.1,10.1))
    def test_unknown_side_blocks_turn(self):
        s=scan();s.ranges[85:96]=[math.nan]*11
        g=LidarAvailability();g.update(s,10.)
        self.assertIsNotNone(g.reason(.15,.2,100.1,10.1))
    def test_close_returns_not_filtered_or_interpreted_as_direction_block(self):
        s=scan();s.ranges[315]=.51;before=list(s.ranges)
        g=LidarAvailability();g.update(s,10.)
        self.assertEqual(s.ranges,before);self.assertIsNone(g.reason(.15,0.,100.1,10.1))
    def test_acquisition_and_receipt_stale(self):
        g=LidarAvailability();g.update(scan(),10.)
        self.assertIsNotNone(g.reason(.15,0.,101.,10.1))
        self.assertIsNotNone(g.reason(.15,0.,100.1,11.))
    def test_repeated_stamp_does_not_renew_progress(self):
        g=LidarAvailability();g.update(scan(),10.);g.update(scan(),11.)
        self.assertIsNotNone(g.reason(.15,0.,100.1,11.))
    def test_wrong_frame_future_and_backward_stamp(self):
        s=scan();g=LidarAvailability();g.update(s,10.)
        self.assertIsNotNone(g.reason(.15,0.,99.,10.1))
        s.header.stamp.sec=99;g.update(s,10.1)
        self.assertIsNotNone(g.reason(.15,0.,100.1,10.1))
        s.header.frame_id='unexpected';g.update(s,10.2)
        self.assertIsNotNone(g.reason(.15,0.,100.1,10.2))
    def test_invalid_values_cannot_supply_observations(self):
        for v in (math.nan,math.inf,-1.,100.):
            s=scan();s.ranges=[v]*360;g=LidarAvailability();g.update(s,10.)
            self.assertIsNotNone(g.reason(.15,0.,100.1,10.1))
    def test_zero_is_always_permitted(self):
        self.assertIsNone(LidarAvailability().reason(0.,0.,100.,10.))

if __name__=='__main__':unittest.main()
