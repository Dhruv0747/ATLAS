"""Native isolated initialization/capture demonstration. Synthetic map and sensors.

No controller, motor driver, steering, production graph or accepted map access.
"""
import collections
import json
import math
import os
import resource
from pathlib import Path
import subprocess
import sys
import time
import uuid
from stage19_contract import require_isolation
from stage20_event_audit import audit_events
from stage20_compare import compare_ekf

require_isolation()
import rclpy
import rosbag2_py
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from rclpy.serialization import deserialize_message
from geometry_msgs.msg import PoseWithCovarianceStamped,TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu,LaserScan
from std_msgs.msg import String
from lifecycle_msgs.srv import ChangeState
from nav2_msgs.srv import SetInitialPose
from std_srvs.srv import Empty
from tf2_ros import StaticTransformBroadcaster,TransformBroadcaster
from rosgraph_msgs.msg import Clock
from builtin_interfaces.msg import Time

root=Path('/tmp/replay');run=root/('demo_'+uuid.uuid4().hex[:8]);run.mkdir()
# New synthetic room, never substitute it for ATLAS's accepted map.
pgm=b'P5\n100 100\n255\n'+bytes(0 if x in (0,99) or y in (0,99) else 254 for y in range(100) for x in range(100))
(run/'room.pgm').write_bytes(pgm)
(run/'room.yaml').write_text('image: room.pgm\nresolution: 0.05\norigin: [-2.5, -2.5, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
(run/'config.yaml').write_text('''/**:
  ros__parameters:
    use_sim_time: true
    frequency: 20.0
    two_d_mode: true
    publish_tf: true
    odom0: /yahboom/odom
    odom0_relative: true
    odom0_config: [true, true, false, false, false, false, true, true, false, false, false, false, false, false, false]
    imu0: /im10a/imu/bias_corrected_candidate
    imu0_config: [false, false, false, false, false, false, false, false, false, false, false, true, false, false, false]
    base_frame_id: base_link
    base_link_frame: base_link
    odom_frame_id: odom
    global_frame_id: map
    min_particles: 100
    max_particles: 500
    max_beams: 30
    update_min_d: 0.05
    update_min_a: 0.05
    robot_model_type: nav2_amcl::DifferentialMotionModel
    resample_interval: 1
    set_initial_pose: false
'''+f'    yaml_filename: {run}/room.yaml\n')
ready=run/'ready.json';env=dict(os.environ,ATLAS_CHECKPOINT_EVENTS='1')
children=[];started=time.monotonic();peaks=collections.defaultdict(int)
capture=subprocess.Popen([sys.executable,str(root/'tools/diagnostics/stage20_capture.py'),
    '--record','--root',str(run/'captures'),'--duration','70','--sim-time','--ready-file',str(ready),
    '--identity-file',str(run/'config.yaml')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
children.append(capture)
try:
    deadline=time.monotonic()+15
    while not ready.exists() and time.monotonic()<deadline:
        if capture.poll() is not None:raise RuntimeError(capture.communicate())
        time.sleep(.1)
    assert ready.exists(),'collector readiness missing'
    ready_data=json.loads(ready.read_text());producer_started=time.monotonic_ns()
    assert ready_data['monotonic_ns']<producer_started
    rclpy.init();node=rclpy.create_node('stage20_fixture',enable_rosout=False)
    wheel=node.create_publisher(Odometry,'/yahboom/odom',10)
    gyro=node.create_publisher(Imu,'/im10a/imu/bias_corrected_candidate',10)
    scan=node.create_publisher(LaserScan,'/scan',10)
    clock=node.create_publisher(Clock,'/clock',10)
    static=StaticTransformBroadcaster(node);dynamic=TransformBroadcaster(node)
    tf=TransformStamped();tf.header.stamp=node.get_clock().now().to_msg()
    tf.header.frame_id='base_link';tf.child_frame_id='laser';tf.transform.rotation.w=1.;static.sendTransform(tf)
    log=(run/'children.log').open('w')
    for command in (
        [str(root/'ekf_build_r3/ekf_node'),'--ros-args','-r','__node:=atlas_ekf','--params-file',str(run/'config.yaml'),'-r','odometry/filtered:=/odom'],
        ['/opt/ros/humble/lib/nav2_map_server/map_server','--ros-args','--params-file',str(run/'config.yaml')],
        [str(root/'amcl_install_r3/lib/nav2_amcl/amcl'),'--ros-args','--params-file',str(run/'config.yaml')],
    ):children.append(subprocess.Popen(command,env=env,stdout=log,stderr=log))
    # Original-library observer remains on its original ABI and a separate output TF topic.
    original_env=dict(env,LD_LIBRARY_PATH='/opt/ros/humble/lib')
    children.append(subprocess.Popen(['/tmp/original_observer/build/stage20_ekf_observer',
        '--ros-args','-r','__node:=atlas_ekf_reference','--params-file',str(run/'config.yaml'),
        '-r','odometry/filtered:=/reference/odom','-r','/tf:=/reference/tf'],
        env=original_env,stdout=log,stderr=log))
    def call(name,typ,request):
        client=node.create_client(typ,name)
        if not client.wait_for_service(timeout_sec=10):raise RuntimeError('missing service '+name)
        f=client.call_async(request);rclpy.spin_until_future_complete(node,f,timeout_sec=10)
        if not f.done() or f.exception():raise RuntimeError('service failed '+name)
        result=f.result();node.destroy_client(client);return result
    for name in ('map_server','amcl'):
        for transition in (1,3):
            req=ChangeState.Request();req.transition.id=transition
            assert call('/'+name+'/change_state',ChangeState,req).success
    motion_start=time.monotonic();seeded=False;lastscan=0.;lastnomotion=0.;tick=0
    while time.monotonic()-motion_start<62:
        elapsed=time.monotonic()-motion_start;tick+=1
        sim_ns=tick*50000000
        stamp=Time(sec=sim_ns//1000000000,nanosec=sim_ns%1000000000)
        o=Odometry();o.header.stamp=stamp;o.header.frame_id='odom';o.child_frame_id='base_link'
        o.pose.pose.position.x=18.;o.pose.pose.position.y=-3.;o.pose.pose.orientation.w=1.
        for k in (0,7,14,21,28,35):o.pose.covariance[k]=.1;o.twist.covariance[k]=.1
        i=Imu();i.header.stamp=stamp;i.header.frame_id='base_link';i.orientation_covariance[0]=-1.;i.angular_velocity_covariance[8]=.01
        wheel.publish(o)
        # Explicit synthetic startup ordering, not a production sensor change.
        if elapsed>.5:gyro.publish(i)
        if elapsed-lastscan>.125:
            s=LaserScan();s.header.stamp=stamp;s.header.frame_id='laser'
            s.angle_min=-math.pi;s.angle_max=math.pi;s.angle_increment=2*math.pi/360
            s.range_min=.05;s.range_max=10.
            s.ranges=[2.45/max(abs(math.cos(s.angle_min+k*s.angle_increment)),abs(math.sin(s.angle_min+k*s.angle_increment))) for k in range(361)]
            scan.publish(s);lastscan=elapsed
        # Allow sensor callbacks to enqueue before advancing the private ROS clock.
        time.sleep(.01);clock.publish(Clock(clock=stamp))
        rclpy.spin_once(node,timeout_sec=.005)
        if elapsed>2 and not seeded:
            req=SetInitialPose.Request();req.pose.header.stamp=stamp;req.pose.header.frame_id='map'
            req.pose.pose.pose.orientation.w=1.
            req.pose.pose.covariance[0]=.01;req.pose.pose.covariance[7]=.01;req.pose.pose.covariance[35]=.01
            call('/set_initial_pose',SetInitialPose,req);seeded=True
        if seeded and elapsed-lastnomotion>1:
            call('/request_nomotion_update',Empty,Empty.Request());lastnomotion=elapsed
        # Linux process counters: peak memory for ALL diagnostic children, not just collector.
        for child in children:
            try:
                text=Path('/proc/'+str(child.pid)+'/status').read_text()
                rss=int(next(line.split()[1] for line in text.splitlines() if line.startswith('VmRSS:')))
                peaks[child.pid]=max(peaks[child.pid],rss)
            except (OSError,StopIteration):pass
        time.sleep(.04)
    # Stop producers first, allow consumers to drain, then stop only private consumers.
    time.sleep(1)
    for child in children[1:]:
        child.terminate();child.wait(timeout=10)
    time.sleep(1)
    if capture.poll() is None:capture.terminate()
    stdout,stderr=capture.communicate(timeout=30)
    if capture.returncode:raise RuntimeError('capture failed: '+stderr)
    result=json.loads(stdout.strip().splitlines()[-1]);bag=Path(result['path'])
    evidence=json.loads((bag/'stage20_evidence.json').read_text())
    reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    ekf=[];amcl=[];sources=set();receipts=0;original_states=[];bootstrap=[]
    while reader.has_next():
        topic,raw,stamp=reader.read_next()
        if topic in ('/atlas/diagnostics/ekf_event','/atlas/diagnostics/amcl_event','/atlas/diagnostics/capture_receipt','/atlas/diagnostics/ekf_state','/atlas/diagnostics/ekf_bootstrap'):
            e=json.loads(deserialize_message(raw,String).data)
            if topic.endswith('ekf_event'):ekf.append(e)
            elif topic.endswith('amcl_event'):amcl.append(e)
            elif topic.endswith('ekf_state'):original_states.append(e)
            elif topic.endswith('ekf_bootstrap'):bootstrap.append(e)
            else:
                receipts+=1
                if e['source_ns'] is not None:sources.add((e['topic'],e['source_ns']))
    snapshot=evidence['parameter_snapshots']['/atlas_ekf']
    params=dict(zip(snapshot['names'],snapshot['values']['values']))
    aliases={k:params[k]['string_value'] for k in ('odom0','imu0')}
    recovered_bootstrap=False
    if bootstrap and not any(e['phase']=='constructed_uninitialized' for e in ekf):
        ekf=[bootstrap[0]]+ekf;recovered_bootstrap=True
    audit=audit_events(ekf,amcl,sources,ready_data['monotonic_ns'],aliases)
    final_by_stamp={e['source_ns']:e for e in ekf if e['phase']=='measurement_after'}
    reference_by_stamp={e['last_measurement_ns']:e for e in original_states if e['initialized']}
    common=sorted(final_by_stamp.keys() & reference_by_stamp.keys())
    native_comparison={'status':'NO_MATCHED_NATIVE_SAMPLES','fidelity_verified':False}
    if common:
        native_comparison=compare_ekf([reference_by_stamp[t] for t in common],
            [dict(final_by_stamp[t],last_measurement_ns=t) for t in common])
        native_comparison.update(reference_unique_samples=len(reference_by_stamp),
            common_source_time_samples=len(common),
            reference_coverage=len(common)/max(1,len(reference_by_stamp)),
            limitation='stationary synthetic matched subset; not complete historical replay')
    summary={'audit':audit,'producer_after_ready':True,'collector':result,
        'native_ekf_matched_subset':native_comparison,
        'bootstrap_recovered_via_readonly_service':recovered_bootstrap,
        'synthetic_first_input_order':'wheel then gyro after 0.5 s',
        'clock_mode':'private simulated clock; no host or production clock changed',
        'counts':evidence['counts'],'drops':evidence['drops'],'all_children_peak_rss_kib_sum':sum(peaks.values()),
        'logical_record_bytes':sum(p.stat().st_size for p in bag.iterdir() if p.is_file()),
        'wall_seconds':time.monotonic()-started,'amcl_phases':sorted(set(e['phase'] for e in amcl)),
        'ekf_phases':sorted(set(e['phase'] for e in ekf)),'receipt_count':receipts,
        'production_changed':False,'historical_failure_reproduced':False}
    (run/'result.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
    assert audit['startup_ledger_mechanics_verified'],audit
finally:
    for child in children:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
    if 'node' in locals():node.destroy_node();rclpy.shutdown()
    if 'summary' in locals():
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        summary['all_children_cpu_seconds']=usage.ru_utime+usage.ru_stime
        summary['all_children_exited']=all(c.poll() is not None for c in children)
        (run/'result.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps({'all_children_cpu_seconds':summary['all_children_cpu_seconds'],
            'all_children_exited':summary['all_children_exited']}))
