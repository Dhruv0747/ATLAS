"""Private native public-sidecar qualification; synthetic traffic, no real devices.

50 Hz wheel/IMU/raw encoder/control, 10 Hz 1080-ray scans, 10 Hz 2000 particles.
Reports sender-vs-bag receipts; no claim about private consumer behavior.
"""
import collections
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from stage19_contract import require_isolation
from stage20_capture_integrity import inspect

require_isolation()
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=30)
parser.add_argument('--capture-seconds',type=int,default=40);args=parser.parse_args()
if not 5<=args.seconds<=110 or not args.seconds+5<=args.capture_seconds<=120:
    parser.error('bounded qualification profile required')
import rclpy
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from nav_msgs.msg import Odometry
from nav2_msgs.msg import ParticleCloud,Particle
from sensor_msgs.msg import Imu,LaserScan
from geometry_msgs.msg import PoseWithCovarianceStamped,Twist,TransformStamped
from tf2_msgs.msg import TFMessage
from std_msgs.msg import Int32,String,Float32

root=Path('/tmp/replay')/('public_'+uuid.uuid4().hex[:8]);root.mkdir()
ready=root/'ready.json';script=Path('/tmp/replay/tools/diagnostics/stage20_capture.py')
child=subprocess.Popen([sys.executable,str(script),'--record','--public-only',
    '--root',str(root/'captures'),'--duration',str(args.capture_seconds),'--ready-file',str(ready)],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
    deadline=time.monotonic()+15
    while not ready.exists() and time.monotonic()<deadline:
        if child.poll() is not None:raise RuntimeError(child.communicate())
        time.sleep(.05)
    assert ready.exists()
    rclpy.init();node=rclpy.create_node('stage20_public_fixture',enable_rosout=False)
    messages={
        '/scan':LaserScan(),'/scan_raw':LaserScan(),'/yahboom/odom':Odometry(),
        '/odom':Odometry(),'/amcl_pose':PoseWithCovarianceStamped(),
        '/im10a/imu/bias_corrected_candidate':Imu(),'/im10a/imu/unvalidated':Imu(),
        '/particle_cloud':ParticleCloud(),'/tf':TFMessage(),'/tf_static':TFMessage(),
        '/atlas/control_policy':String(data='{"source":"STOPPED","stop_latched":true}'),
        '/atlas/encoder_update':String(data='{"counts":[1,2,3,4],"synthetic":true}'),
        '/atlas/encoder_health':String(data='{"synthetic":true}'),
        '/steering/front_angle_deg':Float32(data=90.),'/steering/rear_angle_deg':Float32(data=90.),
        '/cmd_vel':Twist(),'/cmd_vel_joy':Twist(),'/cmd_vel_nav':Twist(),
    }
    for i in range(1,5):messages['/yahboom/encoder/m'+str(i)]=Int32(data=i)
    for topic in ('/scan','/scan_raw'):
        m=messages[topic];m.ranges=[2.]*1080;m.angle_min=-3.14159
        m.angle_increment=6.28318/1080;m.range_min=.1;m.range_max=8.
    messages['/particle_cloud'].particles=[Particle() for _ in range(2000)]
    transform=TransformStamped();transform.header.frame_id='odom';transform.child_frame_id='base_link'
    transform.transform.rotation.w=1.
    messages['/tf'].transforms=[transform];messages['/tf_static'].transforms=[transform]
    pubs={}
    for topic,m in messages.items():
        q=QoSProfile(depth=200,reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL if topic=='/tf_static' else DurabilityPolicy.VOLATILE)
        pubs[topic]=node.create_publisher(type(m),topic,q)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and any(p.get_subscription_count()<1 for p in pubs.values()):
        rclpy.spin_once(node,timeout_sec=.05)
    assert all(p.get_subscription_count()>=1 for p in pubs.values())
    start=time.monotonic();sent=collections.Counter();tick=0;next_tick=start
    while time.monotonic()-start<args.seconds:
        now=time.monotonic()
        if now<next_tick:rclpy.spin_once(node,timeout_sec=min(.005,next_tick-now));continue
        next_tick+=.02;tick+=1;stamp=node.get_clock().now().to_msg()
        for topic,m in messages.items():
            if topic in ('/scan','/scan_raw','/particle_cloud','/amcl_pose') and tick%5:continue
            if topic=='/tf_static' and tick>1:continue
            if hasattr(m,'header'):m.header.stamp=stamp
            if isinstance(m,TFMessage):m.transforms[0].header.stamp=stamp
            pubs[topic].publish(m);sent[topic]+=1
    node.destroy_node();rclpy.shutdown()
    stdout,stderr=child.communicate(timeout=25)
    assert child.returncode==0,stderr
    result=json.loads(stdout.strip().splitlines()[-1]);capture=Path(result['path'])
    evidence=json.loads((capture/'stage20_evidence.json').read_text())
    received=evidence['counts'];loss={t:sent[t]-received.get(t,0) for t in sent}
    assert not any(v for v in loss.values()),loss
    assert inspect(capture)['complete']
    report={'capture':str(capture),'sent':dict(sent),'sender_receipt_difference':loss,
        'particle_count':2000,'synthetic_duration_s':args.seconds,'cpu_seconds':evidence['cpu_seconds'],
        'wall_seconds':evidence['wall_seconds'],'peak_rss_kib':evidence['peak_rss_kib'],
        'free_bytes':evidence['free_bytes'],'io':evidence['io_after'],
        'callback_timing':evidence['callback_timing'],'drops':evidence['drops'],
        'writer':evidence['writer'],'logical_bytes':sum(p.stat().st_size for p in capture.iterdir() if p.is_file()),
        'partial_history_explicit':evidence['initial_state_history']=='NOT_CAPTURED',
        'kernel_cpu_limits_s':__import__('resource').getrlimit(__import__('resource').RLIMIT_CPU),
        'replay_fidelity_verified':False,'production_changed':False}
    (root/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if child.poll() is None:child.terminate();child.wait(timeout=25)
