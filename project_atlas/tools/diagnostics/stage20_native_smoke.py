"""Synthetic private-domain capture test, not a rover or localization replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from stage19_contract import require_isolation

require_isolation()
import rclpy
import rosbag2_py
from rclpy.serialization import deserialize_message
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import String
from std_srvs.srv import Empty
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_initialization_observer import InitializationObserver

rclpy.init()
n = rclpy.create_node('stage20_synthetic_sources', enable_rosout=False)
os.environ['ATLAS_CHECKPOINT_EVENTS']='1'  # isolated fixture only
events=InitializationObserver(n)
service=n.create_service(Empty,'/stage20/synthetic_service',lambda req,resp:resp)
client=n.create_client(Empty,'/stage20/synthetic_service')
called=False
wheel = n.create_publisher(Odometry, '/yahboom/odom', 10)
gyro = n.create_publisher(Imu, '/im10a/imu/bias_corrected_candidate', 10)
scan = n.create_publisher(LaserScan, '/scan', 10)
state_sub=[]
sub=n.create_subscription(String,'/atlas/diagnostics/ekf_state',
    lambda m: state_sub.append(json.loads(m.data)),10)
root=Path('/tmp/replay')
config=root/'synthetic_ekf.yaml'
config.write_text('''atlas_ekf:
  ros__parameters:
    frequency: 20.0
    two_d_mode: true
    publish_tf: false
    odom0: /yahboom/odom
    odom0_relative: true
    odom0_config: [true, true, false, false, false, false, true, true, false, false, false, false, false, false, false]
    imu0: /im10a/imu/bias_corrected_candidate
    imu0_config: [false, false, false, false, false, false, false, false, false, false, false, true, false, false, false]
''')
observer=subprocess.Popen([str(root/'build/stage20_ekf_observer'),'--ros-args',
    '-r','__node:=atlas_ekf','--params-file',str(config),
    '-r','odometry/filtered:=/odom'],stdout=subprocess.DEVNULL)
capture=subprocess.Popen([sys.executable,str(root/'tools/diagnostics/stage20_capture.py'),
    '--record','--root',str(root/'captures'),'--duration','12',
    '--identity-file',str(config)],stdout=subprocess.PIPE,text=True)
try:
    # Let graph discovery establish subscribers; complete consumer startup is NOT asserted.
    start=time.monotonic()
    while time.monotonic()-start<14:
        if not called and time.monotonic()-start>3 and client.service_is_ready():
            events.call(client,Empty.Request(),'/stage20/synthetic_service');called=True
        stamp=n.get_clock().now().to_msg()
        o=Odometry(); o.header.stamp=stamp; o.header.frame_id='odom'; o.child_frame_id='base_link'
        o.pose.pose.orientation.w=1.; o.pose.pose.position.x=18.; o.pose.pose.position.y=-3.
        for k in (0,7,14,21,28,35): o.pose.covariance[k]=.1; o.twist.covariance[k]=.1
        i=Imu(); i.header.stamp=stamp; i.header.frame_id='base_link'
        i.orientation_covariance[0]=-1.; i.angular_velocity_covariance[8]=.01
        s=LaserScan(); s.header.stamp=stamp; s.header.frame_id='laser'
        s.angle_min=-1.; s.angle_max=1.; s.angle_increment=.01
        s.range_min=.05; s.range_max=10.; s.ranges=[2.]*201
        wheel.publish(o); gyro.publish(i); scan.publish(s)
        rclpy.spin_once(n,timeout_sec=.02); time.sleep(.02)
    stdout,_=capture.communicate(timeout=30)
    if capture.returncode: raise RuntimeError('capture failed')
    result=json.loads(stdout.strip().splitlines()[-1]); print(stdout.strip())
    manifest=json.loads((Path(result['path'])/'stage20_evidence.json').read_text())
    assert manifest['complete_restorable_checkpoint'] is False
    assert manifest['drops']=={}, manifest['drops']
    assert manifest['parameter_snapshots']['/atlas_ekf'].get('names')
    assert manifest['counts']['/atlas/diagnostics/initialization_event']==2
    assert any(x['initialized'] and len(x['state'])==15 and len(x['covariance'])==225
               and x['relative_references'] for x in state_sub), 'internal anchor/state absent'
    anchor = next(x['relative_references'][0] for x in state_sub if x['relative_references'])
    assert anchor['xyz'] == [18., -3., 0.], anchor
    for topic in ('/cmd_vel','/cmd_vel_nav','/cmd_vel_recovery','/initialpose'):
        assert not n.get_publishers_info_by_topic(topic), 'unexpected control publisher: '+topic
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=result['path'],storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    lastseq=0; receipts=0; states=0
    while reader.has_next():
        topic,raw,stamp=reader.read_next()
        if topic=='/atlas/diagnostics/capture_receipt':
            e=json.loads(deserialize_message(raw,String).data)
            assert e['seq']==lastseq+1; assert e['receive_ros_ns']==stamp
            lastseq=e['seq']; receipts+=1
        if topic=='/atlas/diagnostics/ekf_state': states+=1
    assert receipts>100 and states>10
    print(json.dumps({'status':'PASS','receipt_count':receipts,'internal_state_count':states,
        'actual_relative_anchor_captured':True,'full_covariance_captured':True,
        'full_checkpoint':False,'missing_amcl':True,'control_publishers':[],
        'synthetic_sensor_publishers':['/yahboom/odom','/im10a/imu/bias_corrected_candidate','/scan']}))
finally:
    for child in (capture,observer):
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
    n.destroy_node();rclpy.shutdown()
