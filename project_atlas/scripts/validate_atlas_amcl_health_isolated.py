#!/usr/bin/env python3
"""Bounded saved-data health integration test in localhost-only ROS domain 188.

Launches localization ONLY. Never plays actuator topics or starts navigation.
Requires the separately built health overlay in the calling environment.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import LaserScan
import yaml
from atlas_amcl_recorded_odom_replay import prepare
from atlas_amcl_offline_replay import localization_params, recorded_seed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag',type=Path)
    parser.add_argument('config',type=Path)
    parser.add_argument('map',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--drop-tf-after-s', type=float,
                        help='Fault injection in generated input only, preserving scan flow')
    args=parser.parse_args()
    if args.drop_tf_after_s is not None and not 5 <= args.drop_tf_after_s <= 20:
        parser.error('TF fault offset must be between 5 and 20 seconds')
    if os.environ.get('ROS_DOMAIN_ID') != '188' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
        parser.error('requires explicit isolated domain 188 and localhost-only')
    if 'atlas_amcl_health_ws/install' not in os.environ.get('AMENT_PREFIX_PATH',''):
        parser.error('source isolated health overlay first')
    args.output.mkdir(parents=True,exist_ok=False)
    meta=yaml.safe_load((args.bag/'metadata.yaml').read_text())['rosbag2_bagfile_information']
    start=meta['starting_time']['nanoseconds_since_epoch']
    end=start+meta['duration']['nanoseconds']
    prepare(args.bag,args.output/'input',start,end)
    fault_ns = None
    if args.drop_tf_after_s is not None:
        fault_ns=start+int(args.drop_tf_after_s*1e9)
        # Only the freshly generated diagnostic copy is edited, never the bag.
        generated=list((args.output/'input').glob('*.db3'))
        if len(generated)!=1: raise RuntimeError('unexpected generated bag layout')
        with sqlite3.connect(generated[0]) as db:
            db.execute("DELETE FROM messages WHERE topic_id IN "
                       "(SELECT id FROM topics WHERE name='/tf') AND timestamp>?",(fault_ns,))
    params=localization_params(args.config.read_text(),args.map,recorded_seed(args.bag,start))
    (args.output/'params.yaml').write_text(yaml.safe_dump(params))
    processes=[]; logs=[]; messages=[]; raw=[]; fault_scans=[]
    rclpy.init()
    node=Node('atlas_health_validation_observer')
    node.create_subscription(String,'/atlas/localization_health',
        lambda msg: messages.append((time.monotonic(),json.loads(msg.data))),10)
    node.create_subscription(String,'/atlas_amcl/processing',
        lambda msg: raw.append(json.loads(msg.data)),10)
    def receive_scan(msg):
        if fault_ns is not None and msg.header.stamp.sec*10**9+msg.header.stamp.nanosec>fault_ns:
            fault_scans.append(time.monotonic())
    from rclpy.qos import qos_profile_sensor_data
    node.create_subscription(LaserScan,'/scan',receive_scan,qos_profile_sensor_data)
    def launch(name,command):
        log=(args.output/(name+'.log')).open('w'); logs.append(log)
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        processes.append(process)
        return process
    def spin(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
    def stop(process):
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGINT)
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=5)
    try:
        launch('localization',['ros2','launch','nav2_bringup','localization_launch.py',
            'map:='+str(args.map),'use_sim_time:=true','autostart:=true',
            'params_file:='+str(args.output/'params.yaml')])
        launch('reporter',['python3',str(Path(__file__).with_name('atlas_amcl_health_reporter.py')),
            '--ros-args','-p','use_sim_time:=true'])
        spin(10)
        player=launch('player',['ros2','bag','play',str(args.output/'input'),'--clock','50',
            '--rate','1.0','--topics','/scan','/tf','/tf_static','/odom'])
        spin(35)
        stop(player)
        stopped=time.monotonic()
        spin(3)
        result=dict(processing_events=len(raw),reports=len(messages),
            processing_without_recent_pose=sum(d['processing_state']=='PROCESSING' and
                d['pose_publication_state']=='NO_RECENT_PUBLICATION' for _,d in messages),
            unavailable_after_playback=sum(t>stopped+1 and d['processing_state']=='UNAVAILABLE'
                for t,d in messages),
            any_navigation_authorized=any(d['navigation_authorized'] for _,d in messages),
            pose_sequences=sorted(set(d['pose_seq'] for d in raw)),
            domain=188,production_changed=False)
        if fault_ns is not None:
            result['scans_after_tf_fault']=len(fault_scans)
            result['unavailable_while_scans_continue']=sum(
                bool(fault_scans) and fault_scans[0]+2<t<stopped and d['processing_state']=='UNAVAILABLE'
                for t,d in messages)
        result['passed']=(result['processing_events']>10 and
            result['processing_without_recent_pose']>0 and result['unavailable_after_playback']>0
            and not result['any_navigation_authorized'])
        if fault_ns is not None:
            result['passed'] = result['passed'] and len(fault_scans)>10 and result['unavailable_while_scans_continue']>5
        (args.output/'result.json').write_text(json.dumps(result,indent=2))
        (args.output/'observations.json').write_text(json.dumps(dict(raw=raw,reports=messages)))
        print(json.dumps(result,indent=2),flush=True)
        if not result['passed']:
            raise RuntimeError('health contract not demonstrated; inspect isolated logs')
    finally:
        for process in reversed(processes): stop(process)
        for log in logs: log.close()
        node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
