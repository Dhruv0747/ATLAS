"""Bounded Jetson-local receive-only observer through EXISTING Foxglove bridge.

No DDS participant, ROS initialization, publishers or service calls. Keeps only
scalar statistics/health, never image/cloud buffers on disk. Used for development
validation, not a production control/safety owner.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')
TOPICS={
 '/scan':'sensor_msgs/msg/LaserScan','/im10a/imu/unvalidated':'sensor_msgs/msg/Imu',
 '/atlas/encoder_update':'std_msgs/msg/String','/camera/image_raw/compressed':'sensor_msgs/msg/CompressedImage',
 '/atlas/control_policy':'std_msgs/msg/String','/cmd_vel':'geometry_msgs/msg/Twist',
 '/atlas/drive_pid/diagnostics':'std_msgs/msg/String','/atlas/mission_status':'std_msgs/msg/String',
 '/astra/depth/image_raw':'sensor_msgs/msg/Image','/astra/depth/camera_info':'sensor_msgs/msg/CameraInfo',
 '/astra/color/image_raw':'sensor_msgs/msg/Image','/astra/color/camera_info':'sensor_msgs/msg/CameraInfo',
 '/astra/depth/points':'sensor_msgs/msg/PointCloud2'}
REQUIRED=tuple(TOPICS)[:8]


def select_new(channels,known):
    selected={}
    for c in channels:
        topic=c.get('topic')
        if topic not in TOPICS:continue
        if topic in known or topic in selected:raise ValueError('duplicate diagnostic topic')
        if c.get('encoding')!='cdr' or c.get('schemaName')!=TOPICS[topic] or type(c.get('id')) is not int:
            raise ValueError('unverified channel schema')
        selected[topic]=c['id']
    return selected


def wire(operation,subscriptions):
    if operation=='subscribe':return json.dumps({'op':'subscribe','subscriptions':[{'id':sid,'channelId':c} for sid,c in subscriptions.items()]})
    if operation=='unsubscribe':return json.dumps({'op':'unsubscribe','subscriptionIds':list(subscriptions)})
    raise ValueError('only subscribe/unsubscribe allowed')


def observe(snapshot,duration=45):
    wheel=STAGE/'websocket_client-1.9.0-py3-none-any.whl'
    if hashlib.sha256(wheel.read_bytes()).hexdigest()!='af248a825037ef591efbf6ed20cc5faa03d3b47b9e5a2230a529eeee1c1fc3ef':
        raise RuntimeError('private observer dependency hash mismatch')
    sys.path.insert(0,str(wheel))
    import websocket
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    classes={topic:get_message(kind) for topic,kind in TOPICS.items()}
    ws=websocket.create_connection('ws://127.0.0.1:8765',subprotocols=['foxglove.sdk.v1','foxglove.websocket.v1'],timeout=2,
                                    http_proxy_host=None)
    ws.settimeout(.25)
    known={};subscriptions={};by_sid={};counts={};first={};last={};gaps={};values={};metadata={};errors=[]
    start=time.monotonic();written=0;bytes_received=0
    try:
        while time.monotonic()-start<duration:
            try:frame=ws.recv()
            except websocket.WebSocketTimeoutException:frame=None
            if isinstance(frame,str):
                message=json.loads(frame)
                if message.get('op')=='advertise':
                    new=select_new(message['channels'],known);pending={}
                    for topic,channel in new.items():
                        sid=len(subscriptions)+len(pending)+1;pending[sid]=channel;by_sid[sid]=topic;known[topic]=channel
                    if pending:ws.send(wire('subscribe',pending));subscriptions.update(pending)
            elif isinstance(frame,bytes):
                if not 13<=len(frame)<=8*1024**2:raise ValueError('binary frame exceeds budget')
                opcode,sid,server_ns=struct.unpack_from('<BIQ',frame)
                if opcode!=1 or sid not in by_sid:raise ValueError('unexpected binary operation')
                topic=by_sid[sid];msg=deserialize_message(frame[13:],classes[topic]);now=time.monotonic()
                if topic in REQUIRED and not -.5<=time.time()-server_ns/1e9<=2:
                    raise ValueError('stale/invalid bridge source timestamp '+topic)
                bytes_received+=len(frame);counts[topic]=counts.get(topic,0)+1;first.setdefault(topic,now)
                if topic in last:gaps[topic]=max(gaps.get(topic,0),now-last[topic])
                last[topic]=now
                if topic in ('/atlas/control_policy','/atlas/drive_pid/diagnostics'):
                    values[topic]=json.loads(msg.data)
                elif topic=='/atlas/mission_status':values[topic]=msg.data
                elif topic=='/cmd_vel':values[topic]={'lin':msg.linear.x,'ang':msg.angular.z}
                elif topic.endswith('/camera_info'):
                    metadata[topic]={'width':msg.width,'height':msg.height,'frame':msg.header.frame_id,
                                      'k':list(msg.k),'p':list(msg.p),'d':list(msg.d),'distortion_model':msg.distortion_model}
                elif topic.endswith('/image_raw'):
                    if not(0<msg.width<=1280 and 0<msg.height<=720 and len(msg.data)==msg.step*msg.height):raise ValueError('malformed image')
                    stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
                    info={'width':msg.width,'height':msg.height,'encoding':msg.encoding,'frame':msg.header.frame_id,
                          'ros_stamp':stamp,'receipt_minus_header_s':time.time()-stamp,
                          'stamp_provenance':'vendor ROS processing time; not hardware capture timestamp'}
                    if topic=='/astra/depth/image_raw':
                        if msg.encoding!='16UC1' or msg.step<msg.width*2:raise ValueError('unsupported depth encoding')
                        sample=[struct.unpack_from(('>' if msg.is_bigendian else '<')+'H',msg.data,y*msg.step+x*2)[0]
                                for y in range(0,msg.height,8) for x in range(0,msg.width,8)]
                        valid=[v for v in sample if v not in (0,65535)]
                        info.update(sampled_valid=len(valid),sampled_pixels=len(sample),min_z_m=min(valid)/1000 if valid else None)
                    metadata[topic]=info
                elif topic.endswith('/points'):
                    metadata[topic]={'width':msg.width,'height':msg.height,'point_step':msg.point_step,'bytes':len(msg.data),
                                     'frame':msg.header.frame_id,'fields':[f.name for f in msg.fields],'is_dense':msg.is_dense}
            now=time.monotonic()
            if now-written>=.2:
                data={'updated_monotonic':now,'counts':counts,'last_receive_monotonic':last,'values':values,
                      'metadata':metadata,'errors':errors,'largest_receive_gap_s':gaps,'bytes_received':bytes_received,
                      'observed_hz':{k:(counts[k]-1)/(last[k]-first[k]) if counts[k]>1 else 0 for k in counts},
                      'advertised_channels':known,'negotiated_protocol':ws.getsubprotocol(),
                      'clock_alignment':'same Jetson local clocks; SDK hardware clock UNKNOWN'}
                temp=snapshot.with_suffix('.tmp');temp.write_text(json.dumps(data));os.replace(temp,snapshot);written=now
    except Exception as e:
        errors.append(str(e));raise
    finally:
        try:
            if subscriptions:ws.send(wire('unsubscribe',subscriptions))
        finally:ws.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);a=p.parse_args()
    if a.snapshot.parent!=STAGE or a.snapshot.exists():raise SystemExit('new isolated scalar-statistics file required')
    observe(a.snapshot)
