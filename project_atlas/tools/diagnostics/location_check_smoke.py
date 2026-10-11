#!/usr/bin/env python3
"""Finite ROS-domain-173 manual-location adapter smoke test. No live ROS/control.

Recorded ranges are replayed with explicit synthetic stationary timestamps and
AMCL pose. This validates the request pipeline, not physical pose accuracy.
"""
import os
os.environ['ROS_DOMAIN_ID']='173'
os.environ['ROS_LOCALHOST_ONLY']='1'
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse
import copy
import json
import math
from pathlib import Path
import resource
import threading
import time
from types import SimpleNamespace as NS
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from geometry_msgs.msg import TransformStamped,Twist,PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid,Odometry
from sensor_msgs.msg import LaserScan,Imu
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer,TransformListener,StaticTransformBroadcaster
import atlas_localization_verify_core as core
import atlas_location_check_ros as adapter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map',required=True,type=Path)
    parser.add_argument('--capture',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():parser.error('new output directory required')
    args.output.mkdir();adapter.STATE_FILE=args.output/'status.json'
    rows=json.loads(args.capture.read_text())['samples']
    row=next(r for r in reversed(rows) if 'transform' in r and 'filtered_scan' in r)
    payload=row['filtered_scan']
    rclpy.init();n=Node('atlas_location_check_isolated_fixture')
    n.map=core.load_map(args.map);n.logic=NS(policy=core.VerifyPolicy());n.search_lock=threading.Lock();n.data_lock=threading.Lock()
    n.scans=[];n.amcl=None;n.amcl_at=None;n.amcl_stamp=None;n.amcl_covariance=None
    n.tf=Buffer();listener=TransformListener(n.tf,n);broadcaster=StaticTransformBroadcaster(n)
    transforms=[]
    for parent,child,x,y,z,angle in [('map','odom',0.,0.,0.,0.),('odom','base_link',0.,0.,0.,0.),('base_link','laser_frame',-.05,0.,.18,math.pi)]:
        t=TransformStamped();t.header.frame_id=parent;t.child_frame_id=child;t.transform.translation.x=x;t.transform.translation.y=y;t.transform.translation.z=z
        t.transform.rotation.z=math.sin(angle/2);t.transform.rotation.w=math.cos(angle/2);transforms.append(t)
    broadcaster.sendTransform(transforms)
    manual=adapter.ManualLocationCheck(n,args.map)
    qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
    pubs={key:n.create_publisher(cls,topic,qos if key=='map' else 10) for key,cls,topic in [('scan',LaserScan,'/scan'),('map',OccupancyGrid,'/map'),('odom',Odometry,'/odom'),('imu',Imu,'/imu/data'),('amcl',PoseWithCovarianceStamped,'/amcl_pose'),('cmd',Twist,'/cmd_vel'),('policy',String,'/atlas/control_policy')]}
    def scan_callback(msg):
        with n.data_lock:n.scans=[(time.monotonic(),msg)]
    def amcl_callback(msg):
        with n.data_lock:
            n.amcl=(0.,0.,0.);n.amcl_at=time.monotonic();n.amcl_stamp=adapter.stamp(msg);n.amcl_covariance=list(msg.pose.covariance)
    n.create_subscription(LaserScan,'/scan',scan_callback,10);n.create_subscription(PoseWithCovarianceStamped,'/amcl_pose',amcl_callback,10)
    def publish():
        now=n.get_clock().now().to_msg()
        scan=LaserScan();scan.header.frame_id='laser_frame';scan.header.stamp=now
        for key in ('angle_min','angle_increment','range_min','range_max','time_increment','scan_time'):setattr(scan,key,float(payload[key]))
        scan.angle_max=scan.angle_min+scan.angle_increment*(len(payload['ranges'])-1);scan.ranges=[float(v) for v in payload['ranges']]
        odom=Odometry();odom.header.stamp=now;imu=Imu();imu.header.stamp=now
        amcl=PoseWithCovarianceStamped();amcl.header.stamp=now;amcl.header.frame_id='map';amcl.pose.pose.orientation.w=1.
        grid=OccupancyGrid();grid.header.frame_id='map';grid.info.width=n.map['w'];grid.info.height=n.map['h'];grid.info.resolution=n.map['res'];grid.info.origin.position.x=n.map['origin'][0];grid.info.origin.position.y=n.map['origin'][1];grid.info.origin.orientation.w=1.
        import numpy as np
        grid.data=np.where(n.map['occupied'],100,np.where(n.map['free'],0,-1)).astype(np.int8).ravel().tolist()
        for key,msg in [('scan',scan),('odom',odom),('imu',imu),('amcl',amcl),('map',grid),('cmd',Twist()),('policy',String(data='{"stop_latched":true}'))]:pubs[key].publish(msg)
    timer=n.create_timer(.15,publish)
    def spin(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.02)
    try:
        spin(4.)
        start=time.monotonic();cpu=time.process_time()
        reply=manual.start(Trigger.Request(),Trigger.Response());assert reply.success,reply.message
        token=json.loads(reply.message)['request_id']
        while manual.jobs.worker_id is not None and time.monotonic()-start<35:spin(.05)
        result=manual.jobs.snapshot()
        assert result['state'] in ('VERIFIED','MISMATCH','UNCERTAIN','LOST'),result
        assert not result['navigation_authorized'] and not result['correction_enabled']
        measurements=dict(wall_s=time.monotonic()-start,cpu_s=time.process_time()-cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        spin(2.)
        reply=manual.start(Trigger.Request(),Trigger.Response());assert reply.success,reply.message
        manual.cancel(Trigger.Request(),Trigger.Response())
        spin(1.)
        assert manual.jobs.snapshot()['state']=='CANCELLED'
        assert manual.jobs.worker_id is None
        manual.loaded_id=None
        spin(2.)
        # Explicit map mismatch assertion independent of periodic fixture map.
        manual.loaded_id=None
        reply=manual.start(Trigger.Request(),Trigger.Response());assert not reply.success,reply.message
        rejected={}
        def reject(name,change):
            spin(2.2)
            change()
            reply=manual.start(Trigger.Request(),Trigger.Response())
            assert not reply.success,(name,reply.message)
            rejected[name]=json.loads(reply.message)['reason']
        reject('missing_imu',lambda:manual.values.pop('imu'))
        def stale_imu():
            at,msg=manual.values['imu'];msg=copy.deepcopy(msg);msg.header.stamp.sec-=4
            manual.values['imu']=(at,msg)
        reject('stale_imu',stale_imu)
        saved_tf=n.tf
        def missing_tf():
            def fail(*args):raise RuntimeError('fixture: scan-time TF unavailable')
            n.tf=NS(lookup_transform=fail)
        reject('missing_tf',missing_tf);n.tf=saved_tf
        def moving():
            msg=Twist();msg.linear.y=.1;manual.receive('cmd',msg)
        reject('motion_observed',moving)
        reject('concurrent_search',lambda:n.search_lock.acquire(False));n.search_lock.release()
        report=dict(result=result,measurements=measurements,cancel_pass=True,map_mismatch_rejected=True,
                    rejected=rejected,domain=173,synthetic_timestamps=True)
        (args.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        if manual.jobs.worker_id is not None:
            manual.jobs.cancel(manual.jobs.worker_id)
            spin(.5)
        n.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
