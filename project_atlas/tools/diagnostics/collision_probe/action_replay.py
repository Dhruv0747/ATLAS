"""Finite domain-173 Nav2 controller-server replay. Never connects to live ROS.

Uses installed controller server, actual obstacle/inflation plugins, LaserScan
callbacks, TF, lifecycle and FollowPath action. Synthetic fixtures, no motors.
"""
import os
os.environ['ROS_DOMAIN_ID']='173'
os.environ['ROS_LOCALHOST_ONLY']='1'
import argparse
import json
import math
from pathlib import Path
import signal
import subprocess
import time
import yaml
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import TransformStamped, Twist, PoseStamped, PoseWithCovarianceStamped
from sensor_msgs.msg import LaserScan, Joy
from std_msgs.msg import String
from std_srvs.srv import Trigger
from nav_msgs.msg import Odometry, Path as RosPath
from nav2_msgs.action import FollowPath
from lifecycle_msgs.srv import ChangeState
from tf2_ros import StaticTransformBroadcaster

def assess(results):
    """No messages is NOT proof that the final motor command became zero."""
    gates={}
    for name in ('straight','left_clear','right_clear','corner_straight','after_clearing'):
        if name in results:gates[name]=results[name]['nonzero']>0
    for name in ('left_blocked','right_blocked','rear_blocked','rear_unknown',
                 'scan_absent_after_timeout','old_timestamp_stream'):
        if name in results:
            row=results[name]
            gates[name]=row['nonzero']==0 and tuple(row['last'] or ())==(0.,0.)
            if name in ('left_blocked','right_blocked','rear_blocked') and row['messages']==0:
                # The mux deliberately does not republish unchanged zero.
                # Require the observed zero state BEFORE submission, a fresh
                # controller zero, and an actual aborted FollowPath result.
                gates[name]=(tuple(row.get('initial_final') or ())==(0.,0.)
                    and row.get('controller_zeros',0)>0 and row.get('action_status')==6)
    if 'obstacle_appearing' in results:gates['obstacle_appearing']=tuple(results['obstacle_appearing']['last'] or ())==(0.,0.)
    gates['cancel_final_zero']=tuple(results.get('cancel_final_zero') or ())==(0.,0.)
    return gates

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scan-timeout',type=float,default=0.)
    p.add_argument('--freshness-only',action='store_true')
    p.add_argument('--mux',type=Path)
    a=p.parse_args()
    if a.output.exists(): raise SystemExit('New isolated output required')
    a.output.mkdir(parents=True)
    config=yaml.safe_load(a.config.read_text())
    config={k:config[k] for k in ('controller_server','local_costmap')}
    cp=config['local_costmap']['local_costmap']['ros__parameters']
    cp['obstacle_layer']['scan']['expected_update_rate']=a.scan_timeout
    (a.output/'params.yaml').write_text(yaml.safe_dump(config))
    rclpy.init();n=Node('atlas_isolated_controller_fixture')
    scanpub=n.create_publisher(LaserScan,'/scan',qos_profile_sensor_data)
    odompub=n.create_publisher(Odometry,'/odom',10)
    rows=[];raw_rows=[];mode=['clear'];emit=[True];stamp_offset=[0.];press_b=[False];manual=[None]
    children=[];resources={}
    n.create_subscription(Twist,'/isolated_final' if a.mux else '/cmd_vel',lambda m:rows.append((time.monotonic(),m.linear.x,m.angular.z)),10)
    n.create_subscription(Twist,'/cmd_vel_nav' if a.mux else '/cmd_vel',lambda m:raw_rows.append((time.monotonic(),m.linear.x,m.angular.z)),10)
    joypub=n.create_publisher(Joy,'/joy',qos_profile_sensor_data)
    healthpub=n.create_publisher(String,'/atlas/encoder_health',10)
    ultrasonics=n.create_publisher(String,'/ultrasonic/validity',1)
    sequence=[0]
    posepub=n.create_publisher(PoseWithCovarianceStamped,'/amcl_pose',10)
    manualpub=n.create_publisher(Twist,'/cmd_vel_joy',10)
    broadcaster=StaticTransformBroadcaster(n)
    transforms=[]
    for parent,child in [('odom','base_link'),('base_link','laser')]:
        t=TransformStamped();t.header.stamp=n.get_clock().now().to_msg();t.header.frame_id=parent;t.child_frame_id=child;t.transform.rotation.w=1.;transforms.append(t)
    broadcaster.sendTransform(transforms)
    def sensor():
        for proc in children:
            try:
                status=Path(f'/proc/{proc.pid}/status').read_text()
                rss=next(int(s.split()[1]) for s in status.splitlines() if s.startswith('VmRSS:'))
                stat=Path(f'/proc/{proc.pid}/stat').read_text().split(') ',1)[1].split()
                old=resources.setdefault(str(proc.pid),{'peak_rss_kib':0,'cpu_s':0.})
                old['peak_rss_kib']=max(old['peak_rss_kib'],rss);old['cpu_s']=(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
            except (FileNotFoundError,ProcessLookupError,StopIteration):pass
        if a.mux:
            sequence[0]+=1
            ultrasonics.publish(String(data=json.dumps(dict(schema_version=1,source='uno_r4_uvalid1',stream_id='isolated-fixture',host_monotonic_s=time.monotonic(),reason='SAMPLE_REPORT',mcu_uptime_ms=sequence[0]*100,sensors={side:dict(state='VALID',range_mm=3000,sample_sequence=sequence[0],sample_age_s=0.) for side in ('front','rear','left','right')}))))
            joy=Joy();joy.axes=[0.]*6;joy.buttons=[0]*8;joy.buttons[1]=int(press_b[0]);joypub.publish(joy)
            healthpub.publish(String(data=json.dumps({'state':'HEALTHY','autonomy_ready':True,'packet_fresh':True,'selected_encoders':['M1','M2','M4']})))
            pose=PoseWithCovarianceStamped();pose.header.stamp=n.get_clock().now().to_msg();pose.header.frame_id='map';pose.pose.pose.orientation.w=1.;posepub.publish(pose)
            if manual[0] is not None:manualpub.publish(manual[0])
        od=Odometry();od.header.stamp=n.get_clock().now().to_msg();od.header.frame_id='odom';od.child_frame_id='base_link';od.pose.pose.orientation.w=1.;odompub.publish(od)
        if not emit[0]: return
        msg=LaserScan();msg.header.frame_id='laser';msg.header.stamp=(n.get_clock().now()-rclpy.duration.Duration(seconds=stamp_offset[0])).to_msg()
        msg.angle_min=-math.pi;msg.angle_max=math.pi-math.pi/180;msg.angle_increment=math.pi/180;msg.range_min=.15;msg.range_max=12.;msg.scan_time=.1;msg.ranges=[3.]*360
        fixtures={'front':(.30,0.),'rear':(-.30,0.),'left':(.27,.20),'right':(.27,-.20),'corner':(.3618828573,-.358044129)}
        if mode[0] in fixtures:
            x,y=fixtures[mode[0]];index=round((math.atan2(y,x)+math.pi)/msg.angle_increment)%360;msg.ranges[index]=math.hypot(x,y)
        if mode[0]=='unknown_rear':
            for i in list(range(0,46))+list(range(315,360)):msg.ranges[i]=math.nan
        scanpub.publish(msg)
    n.create_timer(.1,sensor)
    def spin(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.025)
    def wait(future,timeout=12):
        end=time.monotonic()+timeout
        while not future.done() and time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.025)
        if not future.done():raise TimeoutError('isolated request timed out')
        return future.result()
    log=open(a.output/'controller.log','w')
    command=['/opt/ros/humble/lib/nav2_controller/controller_server','--ros-args','--params-file',str(a.output/'params.yaml')]
    if a.mux:command+=['-r','cmd_vel:=/cmd_vel_nav']
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,ROS_LOG_DIR=str(a.output/'roslogs')))
    children.append(child);muxlog=None
    if a.mux:
        muxlog=open(a.output/'mux.log','w')
        childmux=subprocess.Popen(['python3',str(a.mux),'--ros-args','-p','lidar_guard_frame:=laser','-p','lidar_guard_yaw_deg:=0.0','-r','/cmd_vel:=/isolated_final'],stdout=muxlog,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONPATH='/home/jetson/project_atlas/scripts:'+os.environ.get('PYTHONPATH',''),ATLAS_MANUAL_ONLY='0',ROS_LOG_DIR=str(a.output/'roslogs')))
        children.append(childmux)
    results={}
    try:
        change=n.create_client(ChangeState,'/controller_server/change_state')
        if not change.wait_for_service(timeout_sec=12):raise TimeoutError('controller absent')
        for transition in (1,3):
            req=ChangeState.Request();req.transition.id=transition
            if not wait(change.call_async(req)).success:raise RuntimeError('lifecycle failed')
        ac=ActionClient(n,FollowPath,'/follow_path')
        if not ac.wait_for_server(timeout_sec=5):raise RuntimeError('action absent')
        spin(1.)
        if a.mux:
            reset=n.create_client(Trigger,'/atlas/remote_stop/reset')
            if not reset.wait_for_service(timeout_sec=5):raise RuntimeError('isolated mux absent')
            spin(1.2)
            response=wait(reset.call_async(Trigger.Request()))
            if not response.success:raise RuntimeError('isolated stop reset failed: '+response.message)
        def start(curve=0,reverse=False):
            goal=FollowPath.Goal();goal.controller_id='FollowPath';goal.goal_checker_id='general_goal_checker';goal.path=RosPath();goal.path.header.frame_id='odom';goal.path.header.stamp=n.get_clock().now().to_msg()
            for i in range(61):
                s=i*.01*(-1 if reverse else 1);theta=curve*s/.35
                pose=PoseStamped();pose.header=goal.path.header;pose.pose.position.x=.35*math.sin(theta)/curve if curve else s;pose.pose.position.y=.35*(1-math.cos(theta))/curve if curve else 0.;pose.pose.orientation.z=math.sin(theta/2);pose.pose.orientation.w=math.cos(theta/2);goal.path.poses.append(pose)
            handle=wait(ac.send_goal_async(goal))
            if not handle.accepted:raise RuntimeError('isolated goal rejected')
            return handle
        def measure(name,seconds=1.,since=None):
            start_time=time.monotonic() if since is None else since;spin(seconds)
            data=[r for r in rows if r[0]>=start_time]
            results[name]={'messages':len(data),'nonzero':sum(abs(r[1])+abs(r[2])>1e-6 for r in data),'last':data[-1][1:] if data else None}
        scenarios=[] if a.freshness_only else [('straight','clear',0,False),('left_clear','clear',1,False),('right_clear','clear',-1,False),('corner_straight','corner',0,False),('left_blocked','left',1,False),('right_blocked','right',-1,False),('rear_blocked','rear',0,True),('rear_unknown','unknown_rear',0,True)]
        for name,fixture,curve,reverse in scenarios:
            mode[0]='clear';spin(.5);mode[0]=fixture;spin(.5)
            initial=rows[-1][1:] if rows else None;begin=time.monotonic()
            handle=start(curve,reverse);measure(name,since=begin)
            if name in ('left_blocked','right_blocked','rear_blocked'):
                result=wait(handle.get_result_async())
                results[name].update(initial_final=initial,action_status=result.status,
                    controller_zeros=sum(r[0]>=begin and r[1:]==(0.,0.) for r in raw_rows))
            wait(handle.cancel_goal_async());spin(.2)
        if not a.freshness_only:
            mode[0]='clear';spin(.5);handle=start();measure('before_obstacle');mode[0]='front';measure('obstacle_appearing',1.2);wait(handle.cancel_goal_async());spin(.2)
        mode[0]='clear';spin(.5);handle=start();measure('after_clearing');emit[0]=False;spin(1.);measure('scan_absent_after_timeout');emit[0]=True;spin(.5);wait(handle.cancel_goal_async());spin(.2)
        stamp_offset[0]=5.;spin(.6);handle=start();measure('old_timestamp_stream');stamp_offset[0]=0.;spin(.5);wait(handle.cancel_goal_async());spin(.2)
        results['cancel_final_zero']=rows[-1][1:] if rows else None
        if a.mux:
            emit[0]=False;manual[0]=Twist();manual[0].linear.x=.15;manual[0].angular.z=.2
            measure('manual_without_scan');press_b[0]=True;spin(.25);measure('estop_latched',.5)
            manual[0]=None
    finally:
        for proc in children:
            proc.send_signal(signal.SIGINT)
        for proc in children:
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if muxlog:muxlog.close()
        log.close();n.destroy_node();rclpy.shutdown()
        results['_acceptance']=assess(results)
        if a.mux and 'manual_without_scan' in results and 'estop_latched' in results:
            results['_acceptance']['manual_preserved']=results['manual_without_scan']['nonzero']>0
            results['_acceptance']['estop_enforced']=results['estop_latched']['nonzero']==0 and tuple(results['estop_latched']['last'] or ())==(0.,0.)
        results['_process_resources']=resources
        results['_deployment_gate_passed']=bool(results['_acceptance']) and all(results['_acceptance'].values())
        (a.output/'result.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
    # Failure is evidence, not a reason to label an unsafe replay successful.
    if not results['_deployment_gate_passed']:raise SystemExit(2)

if __name__=='__main__':main()
