#!/usr/bin/env python3
"""Native Humble EKF/AMCL experiment. REQUIRES bubblewrap private net/pid/dev.

No control nodes, serial access, production graph or command topics. Original
payload/header and receipt ordering preserved; AMCL initial mean is not a PF
checkpoint. A/B comparison is diagnostic until global fidelity is established.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from stage19_contract import INPUTS,OUTPUTS,CRITERIA,validate_map,variants,keep_transform,require_isolation,candidate_gate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag');p.add_argument('ekf');p.add_argument('nav');p.add_argument('map')
    p.add_argument('output');p.add_argument('--variant',choices=('A','B'),required=True)
    p.add_argument('--rate',type=float,default=1)
    p.add_argument('--baseline-attestation',help='required verified baseline-fidelity report for a correction comparison')
    a=p.parse_args()
    isolation=require_isolation()
    if a.variant!='A':
        attestation=json.loads(Path(a.baseline_attestation).read_text()) if a.baseline_attestation else None
        if not candidate_gate(attestation):raise RuntimeError('FIDELITY BLOCKED: correction comparison not authorized by evidence gate')
    if not .25<=a.rate<=1: p.error('bounded replay rate .25..1 required')
    import yaml
    import rclpy
    import rosbag2_py
    from rclpy.serialization import deserialize_message,serialize_message
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
    from rosidl_runtime_py.utilities import get_message
    from rosgraph_msgs.msg import Clock
    from std_srvs.srv import Empty
    from lifecycle_msgs.srv import GetState
    from geometry_msgs.msg import PoseWithCovarianceStamped
    out=Path(a.output);out.mkdir(parents=False,exist_ok=False)
    map_hashes=validate_map(a.map)
    ekfraw=Path(a.ekf).read_bytes();navraw=Path(a.nav).read_bytes()
    config=variants(yaml.safe_load(ekfraw))[a.variant]
    nav=yaml.safe_load(navraw)
    # Only localization nodes are retained; Nav2 controller config never launched.
    nav={k:nav[k] for k in ('amcl','map_server')}
    for k in nav:nav[k]['ros__parameters']['use_sim_time']=True
    nav['amcl']['ros__parameters']['set_initial_pose']=False
    nav['map_server']['ros__parameters']['yaml_filename']=a.map
    nav['lifecycle_manager_localization']={'ros__parameters':{
        'use_sim_time':True,'autostart':True,'node_names':['map_server','amcl']}}
    configpath=out/'ekf.yaml';configpath.write_text(yaml.safe_dump(config))
    navpath=out/'localization.yaml';navpath.write_text(yaml.safe_dump(nav))
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=a.bag,storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    metadata={t.name:t for t in reader.get_all_topics_and_types()}
    required=INPUTS-{'/tf'}
    if not required.issubset(metadata):raise RuntimeError('required sources missing: '+str(required-metadata.keys()))
    types={n:get_message(t.type) for n,t in metadata.items() if n in INPUTS|{'/amcl_pose'}}
    inputs=[];seed=None;first=last=None;inputcounts=collections.Counter();headerstats={}
    while reader.has_next():
        name,raw,received=reader.read_next()
        if first is None:first=received
        last=received
        if name=='/amcl_pose' and seed is None:seed=(received,deserialize_message(raw,types[name]))
        if name not in INPUTS:continue
        if name in ('/tf','/tf_static'):
            m=deserialize_message(raw,types[name])
            m.transforms=[tr for tr in m.transforms if keep_transform(tr.header.frame_id,tr.child_frame_id)]
            if not m.transforms:continue
            raw=serialize_message(m)
        inputs.append((received,name,raw));inputcounts[name]+=1
    if seed is None:raise RuntimeError('recorded AMCL initial mean absent')
    if not inputs or any(not inputcounts[n] for n in required):raise RuntimeError('empty required source')
    if len(inputs)>200000:raise RuntimeError('bounded input capacity exceeded')
    inputs.sort(key=lambda v:v[0])
    manifest={'isolation':isolation,'variant':a.variant,'criteria':CRITERIA,
        'ekf_source_sha256':hashlib.sha256(ekfraw).hexdigest(),'nav_source_sha256':hashlib.sha256(navraw).hexdigest(),
        'map_sha256':map_hashes,'source_bag':a.bag,'input_counts':dict(inputcounts),
        'first_ns':first,'last_ns':last,'seed_receipt_ns':seed[0],
        'particle_state_restored':False,'runtime_parameter_history_available':False,
        'ekf_prior_filter_state_restored':False,'ekf_prior_relative_anchor_restored':False,
        'nomotion_phase_ns':578000000,'adaptations':['sim time','remove recorded map/odom TF',
            'native EKF owns /odom and odom TF','accepted map file location','seed original first pose mean/covariance at its receipt time',
            'nomotion requests reconstructed from prior journal, not service-event bag'],
        'actuator_topics':[],'status':'RUNNING_DIAGNOSTIC_ONLY'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rclpy.init();node=rclpy.create_node('atlas_stage19_replay')
    q=QoSProfile(depth=100,reliability=ReliabilityPolicy.RELIABLE)
    be=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT)
    transient=QoSProfile(depth=10,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
    pubs={n:node.create_publisher(types[n],n,transient if n=='/tf_static' else q) for n in inputcounts}
    clockpub=node.create_publisher(Clock,'/clock',be)
    seedpub=node.create_publisher(PoseWithCovarianceStamped,'/initialpose',q)
    nomotion=node.create_client(Empty,'/request_nomotion_update')
    lifecycle={n:node.create_client(GetState,'/'+n+'/get_state') for n in ('amcl','map_server')}
    writer=rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(out/'result'),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    output_types={'/odom':'nav_msgs/msg/Odometry','/amcl_pose':'geometry_msgs/msg/PoseWithCovarianceStamped',
        '/particle_cloud':'nav2_msgs/msg/ParticleCloud','/tf':'tf2_msgs/msg/TFMessage',
        '/map':'nav_msgs/msg/OccupancyGrid','/diagnostics':'diagnostic_msgs/msg/DiagnosticArray'}
    for name in set(inputcounts)|OUTPUTS:
        typ=metadata[name].type if name in inputcounts else output_types[name]
        writer.create_topic(rosbag2_py.TopicMetadata(name=name,type=typ,serialization_format='cdr'))
    now_ns=first;receivedcounts=collections.Counter();sampled_nodes=[]
    def output(name):
        def callback(msg):
            receivedcounts[name]+=1
            writer.write(name,serialize_message(msg),now_ns)
        return callback
    subscriptions=[node.create_subscription(get_message(typ),name,output(name),transient if name=='/map' else be)
                   for name,typ in output_types.items()]
    def clock(t):
        msg=Clock();msg.clock.sec=t//1000000000;msg.clock.nanosec=t%1000000000;clockpub.publish(msg)
    processes=[];logs=[];resources=[]
    def launch(name,path,params):
        log=(out/(name+'.log')).open('x');logs.append(log)
        proc=subprocess.Popen([path,'--ros-args','-r','__node:='+name,'--params-file',str(params)],stdout=log,stderr=subprocess.STDOUT)
        processes.append(proc);return proc
    def stats():
        for proc in processes:
            try:
                fields=Path('/proc/'+str(proc.pid)+'/stat').read_text().split(') ',1)[1].split()
                status=Path('/proc/'+str(proc.pid)+'/status').read_text()
                rss=int(next(x.split()[1] for x in status.splitlines() if x.startswith('VmRSS:')))*1024
                resources.append({'wall':time.monotonic(),'pid':proc.pid,'cpu_ticks':int(fields[11])+int(fields[12]),'rss_bytes':rss})
            except (OSError,StopIteration):pass
    try:
        clock(first)
        # Default EKF output needs the established /odom remap.
        log=(out/'ekf_native.log').open('x');logs.append(log)
        processes.append(subprocess.Popen(['/opt/ros/humble/lib/robot_localization/ekf_node','--ros-args',
            '-r','__node:=atlas_ekf','--params-file',str(configpath),'-r','odometry/filtered:=/odom'],stdout=log,stderr=subprocess.STDOUT))
        launch('map_server','/opt/ros/humble/lib/nav2_map_server/map_server',navpath)
        launch('amcl','/opt/ros/humble/lib/nav2_amcl/amcl',navpath)
        launch('lifecycle_manager_localization','/opt/ros/humble/lib/nav2_lifecycle_manager/lifecycle_manager',navpath)
        timeout=time.monotonic()+40;active=False;ready=False;checks={}
        while time.monotonic()<timeout:
            clock(first);rclpy.spin_once(node,timeout_sec=.02)
            for name,client in lifecycle.items():
                if client.service_is_ready() and name not in checks: checks[name]=client.call_async(GetState.Request())
                if name in checks and checks[name].done() and checks[name].result().current_state.id!=3:del checks[name]
            active=all(n in checks and checks[n].done() and checks[n].result().current_state.id==3 for n in lifecycle)
            ready=active and nomotion.service_is_ready() and all(p.get_subscription_count()>0 for n,p in pubs.items() if n!='/tf')
            if ready:break
        if not ready:raise RuntimeError('localization lifecycle/subscriber readiness failed')
        sampled_nodes=node.get_node_names_and_namespaces()
        allowed={'atlas_stage19_replay','atlas_ekf','amcl','map_server','lifecycle_manager_localization'}
        if any(name not in allowed and not name.startswith('transform_listener_impl') for name,_ in sampled_nodes):
            raise RuntimeError('unexpected node in sandbox: '+str(sampled_nodes))
        start=time.monotonic();index=0;seeded=False;next_request=None;sent=0;responses=0;futures=[];laststat=0;maxlateness=0;lastprogress=0
        while index<len(inputs) or now_ns<last:
            if any(p.poll() is not None for p in processes):raise RuntimeError('native component exited')
            now_ns=min(last,first+int((time.monotonic()-start)*a.rate*1e9));clock(now_ns)
            while index<len(inputs) and inputs[index][0]<=now_ns:
                timestamp,name,raw=inputs[index];maxlateness=max(maxlateness,(now_ns-timestamp)/1e9)
                pubs[name].publish(deserialize_message(raw,types[name]))
                if name not in OUTPUTS:writer.write(name,raw,timestamp)
                index+=1
            if not seeded and now_ns>=seed[0]:
                seedpub.publish(seed[1]);seeded=True
                next_request=(now_ns//1000000000)*1000000000+578000000
                if next_request<=now_ns:next_request+=1000000000
            if seeded and now_ns>=next_request:
                if not nomotion.service_is_ready():raise RuntimeError('nomotion service lost')
                futures.append(nomotion.call_async(Empty.Request()));sent+=1
                next_request+=1000000000
            for _ in range(4):rclpy.spin_once(node,timeout_sec=0)
            done=[f for f in futures if f.done()];responses+=sum(f.result() is not None for f in done)
            futures=[f for f in futures if not f.done()]
            if time.monotonic()-laststat>=1:stats();laststat=time.monotonic()
            if time.monotonic()-lastprogress>=30:
                print(json.dumps({'variant':a.variant,'replay_s':(now_ns-first)/1e9,
                    'published':index,'amcl':receivedcounts['/amcl_pose'],'odom':receivedcounts['/odom']}),flush=True)
                lastprogress=time.monotonic()
            time.sleep(.005)
        # Drain responses without inventing additional scan/clock/motion evidence.
        until=time.monotonic()+3
        while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.02)
        stats()
        manifest.update(status='TESTED_NATIVE_DIAGNOSTIC',output_counts=dict(receivedcounts),
            published_input_counts=dict(inputcounts),nomotion_requests_sent=sent,nomotion_responses=responses,
            seed_published=seeded,observed_nodes=sampled_nodes,max_publish_lateness_s=maxlateness,
            resource_samples=resources,clock_monotonic=True)
        manifest['global_correction_acceptance']='FIDELITY BLOCKED: inspect original/replay initial EKF references and unrecorded PF state'
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()
        del writer
        node.destroy_node();rclpy.shutdown()
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='resource_samples'},indent=2))


if __name__=='__main__':main()
