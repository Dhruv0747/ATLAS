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


SAFETY_CHANNELS = {'/atlas/control_policy': 'policy', '/atlas/encoder_health': 'encoders'}

class SafetyTransport:
    """Bounded source-only mode; legacy diagnostic mode is not safety authority."""
    def __init__(self, path, boot_id, identities):
        from existing_safety_snapshot import SourceConsumer
        self.consumer = SourceConsumer(boot_id, identities)
        self.path, self.boot_id = Path(path), boot_id
        self.channels = {}
        self.by_sid = {}

    def text(self, frame):
        msg = json.loads(frame)
        if msg.get('op') == 'unadvertise':
            if set(msg['channelIds']) & set(self.channels.values()):
                raise ValueError('safety source unadvertised')
        if msg.get('op') != 'advertise': return None
        pending = {}
        for c in msg['channels']:
            topic = c.get('topic')
            if topic not in SAFETY_CHANNELS: continue
            if topic in self.channels or c.get('encoding') != 'cdr' or c.get('schemaName') != 'std_msgs/msg/String':
                raise ValueError('duplicate/invalid safety channel')
            cid = c['id']
            if type(cid) is not int or cid < 0 or cid in self.channels.values():
                raise ValueError('invalid safety channel identity')
            sid = len(self.by_sid)+1
            self.channels[topic] = cid; self.by_sid[sid] = SAFETY_CHANNELS[topic]; pending[sid] = cid
        return wire('subscribe', pending) if pending else None

    def binary(self, frame, now):
        if not 21 <= len(frame) <= 16384: raise ValueError('safety frame size')
        op, sid, _bridge_timestamp = struct.unpack_from('<BIQ', frame)
        if op != 1 or sid not in self.by_sid: raise ValueError('unknown safety frame')
        raw = frame[13:]
        if raw[:4] not in (b'\x00\x01\x00\x00', b'\x00\x00\x00\x00'):
            raise ValueError('unsupported CDR encapsulation')
        length = struct.unpack_from('<I' if raw[1] else '>I', raw, 4)[0]
        if length < 1 or len(raw) != 8+length or raw[-1] != 0:
            raise ValueError('invalid CDR string length')
        payload = json.loads(raw[8:-1].decode('utf-8'))
        self.consumer.receive(self.by_sid[sid], payload, now)

    def emit(self, now):
        from existing_safety_snapshot import publish
        self.consumer.check(now, now)
        p = self.consumer.latest['policy']; e = self.consumer.latest['encoders']
        cmd = p[2]['published_command']
        # Preserve source times, never receipt or bridge timestamps.
        observations = {'policy':[p[2],p[1]], 'command':[cmd['values'],cmd['published_mono']],
                        'encoders':[e[2],e[1]]}
        publish(self.path, observations, now, self.boot_id)

    def close(self):
        self.consumer.disconnect()
        self.path.unlink(missing_ok=True)  # consumer fails closed on missing output


def observe_safety(path, boot_id, identities, duration=30, socket_factory=None):
    """Explicitly invoked only after approval; never used by the diagnostic CLI.

    Identities must come from independent /proc and service checks by the existing
    supervisor. No reconnect/retry. No rclpy import, camera topic, publisher or service.
    """
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0 < duration <= 180:
        raise ValueError('safety session duration')
    path=Path(path)
    if path.exists() or path.is_symlink(): raise ValueError('fresh safety output required')
    if socket_factory is None:
        wheel=STAGE/'websocket_client-1.9.0-py3-none-any.whl'
        if hashlib.sha256(wheel.read_bytes()).hexdigest()!='af248a825037ef591efbf6ed20cc5faa03d3b47b9e5a2230a529eeee1c1fc3ef':
            raise ValueError('observer dependency hash mismatch')
        sys.path.insert(0,str(wheel))
    import websocket
    factory = socket_factory or websocket.create_connection
    transport=SafetyTransport(path,boot_id,identities); ws=None
    start=time.monotonic(); last_emit=start
    try:
        ws=factory('ws://127.0.0.1:8765',subprotocols=['foxglove.sdk.v1','foxglove.websocket.v1'],
                   timeout=.5,http_proxy_host=None)
        ws.settimeout(.1)
        while time.monotonic()-start < duration:
            try: frame=ws.recv()
            except websocket.WebSocketTimeoutException: frame=None
            now=time.monotonic()
            if frame == '' or frame == b'': raise ValueError('safety socket disconnected')
            if isinstance(frame,str):
                if len(frame)>65536: raise ValueError('advertisement size')
                request=transport.text(frame)
                if request: ws.send(request)
            elif isinstance(frame,bytes): transport.binary(frame,now)
            if len(transport.consumer.latest)==2:
                if now-last_emit>=.1: transport.emit(now);last_emit=now
            elif now-start>=1: raise ValueError('missing safety sources')
    finally:
        transport.close()
        if ws is not None: ws.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);a=p.parse_args()
    if a.snapshot.parent!=STAGE or a.snapshot.exists():raise SystemExit('new isolated scalar-statistics file required')
    observe(a.snapshot)
