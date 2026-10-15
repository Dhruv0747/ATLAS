"""Isolated native full-contract fixture; never run on production ROS graph."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import tempfile
import time

from offboard_native import Recorder, TYPES, REQUIRED, qos, isolation, verify


def main():
    isolation()
    parser=argparse.ArgumentParser()
    parser.add_argument('--fault',choices=['none','missing','disconnect','cancel','queue'],default='none')
    args=parser.parse_args()
    import rclpy
    from rosidl_runtime_py.utilities import get_message
    from rclpy.serialization import serialize_message
    from geometry_msgs.msg import TransformStamped
    from nav2_msgs.msg import Particle
    from rclpy.qos import ReliabilityPolicy
    root=Path('/root/atlas_pc_diagnostics');root.mkdir(exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='full_'+args.fault+'_',dir=root))
    rclpy.init()
    node=rclpy.create_node('isolated_full_contract_source',enable_rosout=False,start_parameter_services=False)
    messages={t:get_message(k)() for t,k in TYPES.items()}
    for t in ('/scan','/scan_raw'):
        m=messages[t];m.ranges=[2.]*1080;m.range_min=.1;m.range_max=8.;m.angle_min=-3.14;m.angle_increment=6.28/1080
    messages['/particle_cloud'].particles=[Particle() for _ in range(2000)]
    for t in ('/tf','/tf_static'):
        m=TransformStamped();m.header.frame_id='synthetic_odom';m.child_frame_id='synthetic_base';m.transform.rotation.w=1.
        messages[t].transforms=[m]
    pubs={}
    for t,m in messages.items():
        q=qos(t);q.reliability=ReliabilityPolicy.RELIABLE
        pubs[t]=node.create_publisher(type(m),t,q)
    # Publish retained static TF BEFORE subscriber creation, prove late join works.
    static=messages['/tf_static'];static.transforms[0].header.stamp.sec=123
    static_raw=serialize_message(static)
    pubs['/tf_static'].publish(static_raw)
    sent=Counter();digests={t:[] for t in REQUIRED}
    digests['/tf_static'].append(hashlib.sha256(static_raw).hexdigest());sent['/tf_static']=1
    recorder=Recorder(output)
    if args.fault=='queue':
        # Sink budget is fixed at construction; inject a valid oversize raw enqueue
        # to exercise bounded queue rejection without filling disk.
        recorder.receive('/scan',TYPES['/scan'],bytes(9*1024**2))
    start=time.monotonic();cpu=time.process_time();step=0
    try:
        while recorder.tick():
            elapsed=time.monotonic()-start
            if args.fault=='cancel' and elapsed>2:
                recorder.stop_reason='cancelled';break
            if elapsed<.5:
                rclpy.spin_once(recorder.node,timeout_sec=.01);continue
            if not (args.fault=='disconnect' and elapsed>2):
                for t,m in messages.items():
                    if t=='/tf_static' or (args.fault=='missing' and t=='/scan_raw'):continue
                    if t in ('/scan','/scan_raw') and step%5:continue
                    if t in ('/particle_cloud','/amcl_pose') and step%25:continue
                    stamp=node.get_clock().now().to_msg()
                    if hasattr(m,'header'):m.header.stamp=stamp
                    if hasattr(m,'transforms'):m.transforms[0].header.stamp=stamp
                    if t.startswith('/yahboom/encoder/m'):m.data=step
                    raw=serialize_message(m)
                    pubs[t].publish(raw)
                    sent[t]+=1;digests[t].append(hashlib.sha256(raw).hexdigest())
            step+=1
            until=time.monotonic()+.02
            while time.monotonic()<until and not recorder.stop_reason:
                rclpy.spin_once(recorder.node,timeout_sec=.001)
    finally:
        path,result=recorder.close();node.destroy_node();rclpy.shutdown()
    wall=time.monotonic()-start;used=time.process_time()-cpu
    integrity=verify(path)
    received={t:[] for t in REQUIRED}
    for line in (path/'pc_receipts.jsonl').read_text().splitlines():
        row=json.loads(line);received[row['topic']].append(row['sha256'])
    for t,values in received.items():
        if values!=digests[t][:len(values)]:raise AssertionError('payload order/drop mismatch '+t)
    delta={t:sent[t]-len(received[t]) for t in REQUIRED}
    if args.fault=='none':
        assert result['capture_complete'],result
        assert all(v==0 for v in delta.values()),delta
    else:assert not result['capture_complete'],result
    if args.fault=='missing':assert '/scan_raw' in result['missing']
    summary={'fault':args.fault,'path':str(path),'required_topics':len(REQUIRED),
             'cpu_seconds':used,'wall_seconds':wall,'cpu_one_core_pct':100*used/wall,
             'peak_process_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
             'received':dict(recorder.counts),'sent_minus_received':delta,
             'source_cdr_exact':True,'reason':result['reason'],'complete':result['capture_complete'],
             'integrity':integrity}
    (output/'test_result.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
