"""Approved offline, calibrated bag replay into RTAB-Map's isolated inputs.

No driver or production participant. Provisional unregistered RGB-D is rejected:
a label alone cannot make mismatched image pixels valid RGB-D input.
"""
import argparse
import json
from pathlib import Path
import subprocess
from rtabmap_offline import admit, isolated_env
from astra_bag_adapter import inventory, TOPICS
import sqlite3


def validate_recorded_bundles(bag, manifest):
    """Check all recorded image inputs before any replay publisher is created."""
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image, CameraInfo
    from calibration_capture import bundle
    expected={k:(manifest['rgb' if k.startswith('rgb') else 'depth']['width'],
                 manifest['rgb' if k.startswith('rgb') else 'depth']['height'],
                 manifest['rgb' if k.startswith('rgb') else 'depth']['frame_id']) for k in TOPICS.values()}
    pending={}; count=0; last={}
    with sqlite3.connect('file:'+str(Path(bag).resolve())+'?mode=ro',uri=True) as db:
        for topic,recorded,cdr in db.execute('select topics.name,messages.timestamp,messages.data from messages join topics on topics.id=messages.topic_id order by messages.timestamp'):
            if topic not in TOPICS:continue
            k=TOPICS[topic];msg=deserialize_message(cdr,CameraInfo if 'info' in k else Image)
            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            if stamp<=last.get(k,-1):raise ValueError('regressing source timestamps')
            last[k]=stamp
            m=dict(stamp_sec=msg.header.stamp.sec,stamp_nanosec=msg.header.stamp.nanosec,
                   width=msg.width,height=msg.height,frame_id=msg.header.frame_id,cdr=bytes(cdr))
            if 'info' in k:m['k']=[float(v) for v in msg.k]
            else:
                m.update(encoding=msg.encoding,step=msg.step,data_bytes=len(msg.data))
                if k=='depth':m['units_to_m']=manifest['units_to_m']
            if k in pending:raise ValueError('unpaired stream frame; explicit offline selection required')
            pending[k]=m
            if len(pending)==4:
                bundle(pending,recorded,expected);pending={};count+=1
    if pending or not count:raise ValueError('incomplete synchronized recording')
    return count


def command(bag, manifest):
    admit(manifest)
    topics={name:typ for name,typ,count in inventory(bag) if count}
    mapping={**{topic:'/atlas_offline/input/'+{'rgb_info':'camera_info','depth_info':'depth_camera_info'}.get(key,key)
                for topic,key in TOPICS.items()},
             manifest['odom_topic']:'/atlas_offline/input/odom',
             manifest['scan_topic']:'/atlas_offline/input/scan'}
    for topic in mapping:
        if topic not in topics:raise ValueError('required recorded input missing: '+topic)
    if topics[manifest['odom_topic']]!='nav_msgs/msg/Odometry' or topics[manifest['scan_topic']]!='sensor_msgs/msg/LaserScan':
        raise ValueError('wrong odometry/scan type')
    for topic,key in TOPICS.items():
        wanted='sensor_msgs/msg/CameraInfo' if 'info' in key else 'sensor_msgs/msg/Image'
        if topics[topic]!=wanted:raise ValueError('wrong image/info type')
    if '/tf_static' not in topics:raise ValueError('recorded mounting TF missing')
    cmd=['ros2','bag','play',str(bag),'--clock','--topics',*mapping,'/tf_static','/tf','--remap']
    cmd.extend(k+':='+v for k,v in mapping.items())
    return cmd


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag',type=Path);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--execute',action='store_true',help='offline replay only; otherwise validate and print')
    a=p.parse_args();cmd=command(a.bag,json.loads(a.manifest.read_text()))
    if not a.execute:print(json.dumps(cmd))
    else:
        validate_recorded_bundles(a.bag,json.loads(a.manifest.read_text()))
        child=subprocess.Popen(cmd,env=isolated_env())
        try:child.wait(timeout=60)
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait()

