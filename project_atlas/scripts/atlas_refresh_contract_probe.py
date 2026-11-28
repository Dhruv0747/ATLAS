"""Exercise production guard/callback methods without constructing a motor mux.

Only an isolated AMCL measurement service may be called; no motor publishers.
"""
import ast
import math
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Optional
from atlas_amcl_processing_health import ProcessingHealth
from atlas_localization_refresh_gate import RefreshRequestGate


def methods(filename, names, scope):
    path=Path(__file__).with_name(filename)
    tree=ast.parse(path.read_text())
    selected=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in selected} != set(names): raise ValueError('source method missing')
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),scope)
    return scope


class RefreshContractProbe:
    def __init__(self,node):
        if os.environ.get('ROS_DOMAIN_ID')!='188' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':
            raise RuntimeError('isolated domain required')
        from std_srvs.srv import Empty as Service
        from std_msgs.msg import String, Empty
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
        from rclpy.clock import Clock, ClockType
        from rclpy.qos import QoSProfile, DurabilityPolicy
        scope=dict(math=math,json=json,time=time,Optional=Optional,
            String=String,Empty=Empty,Odometry=Odometry,Twist=Twist,
            PoseWithCovarianceStamped=PoseWithCovarianceStamped,EmptyService=Service)
        mux=methods('atlas_cmd_vel_mux.py',{'navigation_localization_guard','localization_guard',
            'on_localization','on_amcl_processing','on_refresh_odom'},dict(scope))
        mission=methods('atlas_mission_control.py',{'on_guarded_localization_refresh'},dict(scope))
        self.requests=0; self.blocked_requests=0; self.accepted_fresh=0; self.accepted_stale=0
        self.poses=0
        self.accepted_after_refresh=0
        self.state=NS(localization_rx=0.,localization_timeout=2.5,operating_mode='LOCALIZATION',
            localization_jump_fault=None,localization_pose=None,
            localization_xy_std_m=float('inf'),localization_yaw_std_deg=float('inf'),
            localization_max_xy_std_m=.25,localization_max_yaw_std_deg=20.,
            localization_jump_base_m=.20,localization_jump_max_speed_mps=.22,
            localization_jump_margin_m=.10,localization_jump_base_yaw_deg=15.,
            localization_jump_max_yaw_rate_deg_s=55.,localization_jump_yaw_margin_deg=8.,
            amcl_processing_gate_enabled=True,amcl_processing=ProcessingHealth(),
            localization_refresh_gate=RefreshRequestGate(),get_clock=node.get_clock,
            moving=lambda command:bool(command),amcl_guarded_refresh_enabled=True,
            guarded_refresh_key=None,localization_update_future=None,
            nomotion_client=node.create_client(Service,'/request_nomotion_update'))
        self.state.localization_guard=lambda now:mux['localization_guard'](self.state,now)
        self.state.localization_refresh_pub=NS(publish=lambda _msg:self.request(mission))
        def pose(msg):
            self.poses+=1
            mux['on_localization'](self.state,msg)
        node.create_subscription(PoseWithCovarianceStamped,'/amcl_pose',pose,
            QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        node.create_subscription(String,'/atlas_amcl/processing',
            lambda msg:mux['on_amcl_processing'](self.state,msg),1)
        node.create_subscription(Odometry,'/odom',lambda msg:mux['on_refresh_odom'](self.state,msg),10)
        def tick():
            before=self.requests
            now=time.monotonic()
            reason=mux['navigation_localization_guard'](self.state,True,now)
            if self.requests>before and reason: self.blocked_requests+=1
            if reason is None:
                if now-self.state.localization_rx<=2.5:
                    self.accepted_fresh+=1
                    if self.requests and self.poses>=2:
                        self.accepted_after_refresh+=1
                else: self.accepted_stale+=1
        self.clock=Clock(clock_type=ClockType.STEADY_TIME)
        node.create_timer(.1,tick,clock=self.clock)

    def request(self,mission):
        self.requests+=1
        mission['on_guarded_localization_refresh'](self.state,None)

    def result(self):
        return dict(requests=self.requests,request_ticks_still_blocked=self.blocked_requests,
            pose_messages=self.poses,fresh_pose_guard_passes=self.accepted_fresh,
            stale_pose_guard_passes=self.accepted_stale,
            fresh_pose_guard_passes_after_refresh=self.accepted_after_refresh,
            passed=(self.requests==1 and self.blocked_requests==1 and self.poses>=2
                    and self.accepted_after_refresh>0 and self.accepted_stale==0),
            motor_publishers_created=False,physical_pose_accuracy_tested=False)
