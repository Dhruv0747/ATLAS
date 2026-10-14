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
import sqlite3
from stage20_capture import serialized_source_stamp
from stage20_public_ledger_audit import audit
from stage19_contract import require_isolation
from stage20_capture_integrity import inspect

require_isolation()
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=30)
parser.add_argument('--capture-seconds',type=int,default=40)
parser.add_argument('--stationary-30',action='store_true')
parser.add_argument('--fault',choices=('none','scan-loss','stale-scan','cancel'),default='none');args=parser.parse_args()
if args.fault!='none' and not args.stationary_30:parser.error('fault cases require isolated stationary profile')
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
recording_ready=root/'recording_ready.json'
child=subprocess.Popen([sys.executable,str(script),'--record','--public-only',
    '--root',str(root/'captures'),'--duration',str(args.capture_seconds),'--ready-file',str(ready)]+
    (['--stationary-30','--recording-ready-file',str(recording_ready)] if args.stationary_30 else []),
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
        '/atlas/control_policy':String(data='{"source":"STOPPED","stop_latched":true,"commission_armed":false}'),
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
    if args.stationary_30:
        deadline=time.monotonic()+8
        while not recording_ready.exists() and time.monotonic()<deadline:
            stamp=node.get_clock().now().to_msg()
            for topic,m in messages.items():
                if hasattr(m,'header'):m.header.stamp=stamp
                if isinstance(m,TFMessage):m.transforms[0].header.stamp=stamp
                pubs[topic].publish(m)
            rclpy.spin_once(node,timeout_sec=.05)
        assert recording_ready.exists(),'stationary sensor preflight did not pass'
    sent_stamps=collections.Counter()
    start=time.monotonic();sent=collections.Counter();tick=0;next_tick=start
    while time.monotonic()-start<args.seconds:
        now=time.monotonic()
        if now<next_tick:rclpy.spin_once(node,timeout_sec=min(.005,next_tick-now));continue
        next_tick+=.02;tick+=1;stamp=node.get_clock().now().to_msg()
        for topic,m in messages.items():
            if topic in ('/scan','/scan_raw','/particle_cloud','/amcl_pose') and tick%5:continue
            if topic=='/tf_static' and (args.stationary_30 or tick>1):continue
            if hasattr(m,'header'):m.header.stamp=stamp
            if isinstance(m,TFMessage):m.transforms[0].header.stamp=stamp
            pubs[topic].publish(m);sent[topic]+=1
            if args.stationary_30 and hasattr(m,'header'):
                sent_stamps[(topic,m.header.stamp.sec*1000000000+m.header.stamp.nanosec)]+=1
    # Keep required sources fresh until the finite 30-second window ends. These
    # extra messages are not part of the measured sender/receipt loss comparison.
    if args.stationary_30:
        if args.fault=='cancel':child.terminate()
        stale_scan_stamp=messages['/scan'].header.stamp
        while child.poll() is None:
            stamp=node.get_clock().now().to_msg()
            for topic,m in messages.items():
                if topic=='/tf_static':continue # Retained preflight sample only.
                if topic=='/scan' and args.fault=='scan-loss':continue
                if hasattr(m,'header'):m.header.stamp=stamp
                if topic=='/scan' and args.fault=='stale-scan':m.header.stamp=stale_scan_stamp
                if isinstance(m,TFMessage):m.transforms[0].header.stamp=stamp
                pubs[topic].publish(m)
            rclpy.spin_once(node,timeout_sec=.05)
            if time.monotonic()-start>45:raise TimeoutError('collector exceeded bounded window/flush')
    node.destroy_node();rclpy.shutdown()
    stdout,stderr=child.communicate(timeout=25)
    assert child.returncode==(0 if args.fault=='none' else 2),stderr
    result=json.loads(stdout.strip().splitlines()[-1]);capture=Path(result['path'])
    evidence=json.loads((capture/'stage20_evidence.json').read_text())
    received=evidence['counts'];loss={t:sent[t]-received.get(t,0) for t in sent}
    if args.stationary_30:
        captured=collections.Counter()
        for db in capture.glob('*.db3'):
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as con:
                assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                for topic,type_name,payload in con.execute('SELECT topics.name,topics.type,messages.data FROM messages JOIN topics ON messages.topic_id=topics.id'):
                    if topic in messages and hasattr(messages[topic],'header'):
                        captured[(topic,serialized_source_stamp(payload,type_name))]+=1
        missing=sent_stamps-captured
        if args.fault!='cancel':
            assert not missing,{'missing_source_samples':sum(missing.values())}
            assert all(received.get(t,0)>=count for t,count in sent.items())
        assert received.get('/tf_static',0)>0,'retained static TF must be captured after preflight'
        ledger_audit=audit(capture)
        assert evidence['public_topic_window_complete']==(args.fault=='none')
        if args.fault!='none':
            assert evidence['end_reason']=={'scan-loss':'sensor_became_unavailable','stale-scan':'invalid_source_freshness','cancel':'sigterm'}[args.fault]
        assert evidence['recording_deadline_monotonic_s']-evidence['recording_started_monotonic_s']==30
        assert evidence['last_receipt_monotonic_s']<evidence['recording_deadline_monotonic_s']
        assert evidence['flush_elapsed_s']<10.5
    else:assert not any(v for v in loss.values()),loss
    assert inspect(capture)['complete']==(args.fault=='none')
    report={'capture':str(capture),'sent':dict(sent),'sender_receipt_difference':loss,
        'particle_count':2000,'synthetic_duration_s':args.seconds,'cpu_seconds':evidence['cpu_seconds'],
        'wall_seconds':evidence['wall_seconds'],'peak_rss_kib':evidence['peak_rss_kib'],
        'free_bytes':evidence['free_bytes'],'io':evidence['io_after'],
        'callback_timing':evidence['callback_timing'],'drops':evidence['drops'],
        'writer':evidence['writer'],'logical_bytes':sum(p.stat().st_size for p in capture.iterdir() if p.is_file()),
        'partial_history_explicit':evidence['initial_state_history']=='NOT_CAPTURED',
        'kernel_cpu_limits_s':__import__('resource').getrlimit(__import__('resource').RLIMIT_CPU),
        'replay_fidelity_verified':False,'production_changed':False}
    if args.stationary_30:
        report.update(stationary_30=True,fault=args.fault,end_reason=evidence['end_reason'],all_measured_source_stamps_preserved=not bool(missing),unreceived_measured_source_stamps=sum(missing.values()),ledger_audit=ledger_audit,
            receipt_comparison=('cancel may leave DDS messages unreceived; incomplete window, not zero loss' if args.fault=='cancel' else 'all interior header stamps and counts found')+'; exact received CDR checked against receipt ledger, not separately reserialized padding',
            recording_window_s=30,flush_elapsed_s=evidence['flush_elapsed_s'],
            receipt_span_s=evidence['last_receipt_monotonic_s']-evidence['first_receipt_monotonic_s'])
    (root/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if child.poll() is None:child.terminate();child.wait(timeout=25)
