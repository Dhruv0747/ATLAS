"""Jetson-local topic-only bridge. No camera driver/control or production publisher."""
import argparse
import json
import math
import os
from pathlib import Path
import struct
import threading
import time
from calibration_validation import validate_calibration
from onboard_store import atomic


def configuration(c):
    if c.get('enabled') is not True:raise ValueError('mapping package disabled')
    domains=[c[k] for k in ('camera_domain','mapping_domain','production_domain')]
    if any(type(v) is not int or not 0<=v<=232 for v in domains) or len(set(domains))!=3:
        raise ValueError('explicit separate ROS domains required')
    for key in ('registered_depth_topic','registration_evidence','tf_evidence','odom_topic'):
        if not c.get(key):raise ValueError(key+' unverified')
    if not c.get('tf_edges'):raise ValueError('verified TF edge allowlist missing')
    if not 1<=c['duration_s']<=60:raise ValueError('bounded test only, at most60s')
    if not 0<c['max_session_bytes']<=2*1024**3 or c['free_reserve_bytes']<1024**3:
        raise ValueError('invalid storage budget')
    docs={}
    for k in ('rgb','depth'):
        d=json.loads(Path(c[k+'_calibration']).read_text())
        validate_calibration(d,c['serial'],d['width'],d['height'],d['frame_id']);docs[k]=d
    if (docs['rgb']['width'],docs['rgb']['height'],docs['rgb']['frame_id']) != (docs['depth']['width'],docs['depth']['height'],docs['depth']['frame_id']):
        raise ValueError('registered RGB-D must share geometry/frame')
    return docs


def ns(msg):return msg.header.stamp.sec*10**9+msg.header.stamp.nanosec


def checked_images(messages,docs,now_ns):
    if set(messages)!=set(('rgb','depth','rgb_info','depth_info')):raise ValueError('missing image/info')
    stamps=[ns(m) for m in messages.values()]
    if any(not 0<=now_ns-s<=500000000 for s in stamps):raise ValueError('stale/future camera frame')
    if max(stamps)-min(stamps)>30000000:raise ValueError('RGB-D skew exceeds30ms')
    for k,m in messages.items():
        d=docs['rgb' if k.startswith('rgb') else 'depth']
        if (m.width,m.height,m.header.frame_id)!=(d['width'],d['height'],d['frame_id']):raise ValueError('image identity mismatch')
        if k.endswith('info'):
            if list(m.k)!=d['k'] or list(m.d)!=d['d'] or m.distortion_model!=d['distortion_model']:
                raise ValueError('live CameraInfo differs from reviewed calibration')
        else:
            choices={'rgb8':3,'bgr8':3} if k=='rgb' else {'16UC1':2,'32FC1':4}
            if m.encoding not in choices or m.step<m.width*choices[m.encoding] or len(m.data)!=m.step*m.height:
                raise ValueError('image encoding/stride/depth units invalid')
    return stamps


def main():
    p=argparse.ArgumentParser();p.add_argument('config');p.add_argument('session');a=p.parse_args()
    c=json.loads(Path(a.config).read_text());docs=configuration(c);out=Path(a.session)
    # No network discovery server or inherited remote DDS profiles.
    for key in ('ROS_DISCOVERY_SERVER','FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE','CYCLONEDDS_URI'):
        os.environ.pop(key,None)
    os.environ.update(ROS_LOCALHOST_ONLY='1',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',SKIP_DEFAULT_XML='1')
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
    from sensor_msgs.msg import Image,CameraInfo,LaserScan,PointCloud2
    from nav_msgs.msg import Odometry
    from tf2_msgs.msg import TFMessage
    from tf2_ros import Buffer,TransformListener
    contexts=[];nodes=[];executors=[];threads=[]
    for name,domain in [('camera',c['camera_domain']),('sensors',c['production_domain']),('mapping',c['mapping_domain'])]:
        ctx=Context();rclpy.init(context=ctx,domain_id=domain);contexts.append(ctx)
        node=rclpy.create_node('atlas_map_'+name,context=ctx);nodes.append(node)
        ex=SingleThreadedExecutor(context=ctx);ex.add_node(node);executors.append(ex)
    cam,sensors,dst=nodes
    state={'last_bundle':None,'last_odom':None,'last_scan':None,'bundles':0,'error':None}
    lock=threading.Lock();pending={};last_stamps=None
    types={'rgb':Image,'depth':Image,'rgb_info':CameraInfo,'depth_info':CameraInfo}
    pubs={k:dst.create_publisher(t,'/atlas_mapping/input/'+('camera_info' if k=='rgb_info' else k),qos_profile_sensor_data) for k,t in types.items()}
    buffer=Buffer();listener=TransformListener(buffer,dst,spin_thread=False)
    def fail(e):
        with lock:state['error']=str(e)
    def receive(k,msg):
        nonlocal last_stamps
        try:
            with lock:
                if state['error']:return
                pending[k]=msg
                if len(pending)<4:return
                # Arrival order is not synchronization failure. Drop only the
                # oldest unmatched candidate; supervisor bounds missing pairs.
                stamps0={key:ns(m) for key,m in pending.items()}
                if max(stamps0.values())-min(stamps0.values())>30000000:
                    del pending[min(stamps0,key=stamps0.get)];return
                stamps=checked_images(pending,docs,dst.get_clock().now().nanoseconds)
                if last_stamps and any(x<=y for x,y in zip(stamps,last_stamps)):return
                stamp=rclpy.time.Time.from_msg(pending['rgb'].header.stamp)
                if not buffer.can_transform('base_link',pending['rgb'].header.frame_id,stamp):
                    return  # no publication; supervisor's bundle deadline fails closed
                if not buffer.can_transform('odom','base_link',stamp):return
                for key,m in pending.items():pubs[key].publish(m)
                last_stamps=stamps;pending.clear();state['last_bundle']=time.monotonic();state['bundles']+=1
        except Exception as e:fail(e)
    for key,typ in types.items():
        topic=c[{'rgb':'rgb_topic','depth':'registered_depth_topic','rgb_info':'rgb_info_topic','depth_info':'depth_info_topic'}[key]]
        cam.create_subscription(typ,topic,lambda m,k=key:receive(k,m),qos_profile_sensor_data)
    def relay(msg,pub,key):
        try:
            age=(sensors.get_clock().now().nanoseconds-ns(msg))/1e9
            if not 0<=age<=.5:raise ValueError(key+' stale/future')
            if key=='odom' and (msg.header.frame_id!='odom' or msg.child_frame_id!='base_link'):
                raise ValueError('unexpected odometry frames')
            if key=='odom' and any(not math.isfinite(v) or v<=0 for v in [msg.pose.covariance[i] for i in (0,7,14,21,28,35)]):
                raise ValueError('invalid odometry covariance')
            pub.publish(msg)
            with lock:state['last_'+key]=time.monotonic()
        except Exception as e:fail(e)
    for key,typ in [('odom',Odometry),('scan',LaserScan)]:
        pub=dst.create_publisher(typ,'/atlas_mapping/input/'+key,qos_profile_sensor_data)
        sensors.create_subscription(typ,c[key+'_topic'],lambda m,p=pub,k=key:relay(m,p,k),qos_profile_sensor_data)
    edges={tuple(e) for e in c['tf_edges']}
    if any(child in ('map','odom') for parent,child in edges):raise ValueError('map/odom parent transforms prohibited')
    for topic,qos in [('/tf',100),('/tf_static',QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL))]:
        pub=dst.create_publisher(TFMessage,topic,qos)
        def tfrelay(msg,pub=pub):
            selected=[t for t in msg.transforms if (t.header.frame_id,t.child_frame_id) in edges]
            if selected:pub.publish(TFMessage(transforms=selected))
        sensors.create_subscription(TFMessage,topic,tfrelay,qos)
    last_cloud=0.
    def cloud(msg):
        nonlocal last_cloud
        if time.monotonic()-last_cloud<5:return
        try:
            if msg.header.frame_id!='map_3d':raise ValueError('unexpected cloud frame')
            fields={f.name:f for f in msg.fields};offsets=[fields[k].offset for k in ('x','y','z')]
            if any(fields[k].datatype!=7 for k in ('x','y','z')):raise ValueError('cloud requires float32 XYZ')
            total=msg.width*msg.height;stride=max(1,(total+19999)//20000);points=[]
            for i in range(0,total,stride):
                row,col=divmod(i,msg.width);base=row*msg.row_step+col*msg.point_step
                xyz=[struct.unpack_from(('>' if msg.is_bigendian else '<')+'f',msg.data,base+o)[0] for o in offsets]
                if all(math.isfinite(v) for v in xyz):points.append(xyz)
            atomic(out/'cloud.json',dict(label='PROVISIONAL — PHYSICAL ACCURACY NOT VERIFIED',frame=msg.header.frame_id,stamp_ns=ns(msg),points=points))
            last_cloud=time.monotonic()
        except Exception as e:fail(e)
    dst.create_subscription(PointCloud2,'/atlas_mapping/cloud_map',cloud,10)
    try:
        start=time.monotonic();last_write=0
        while time.monotonic()-start<c['duration_s']:
            for ex in executors:
                for _ in range(5):ex.spin_once(timeout_sec=0)
            if len(pending)==4:receive('rgb',pending['rgb'])  # TF may arrive after images
            with lock:snapshot=dict(state,observed_mono=time.monotonic())
            if time.monotonic()-last_write>=.1:
                atomic(out/'adapter.json',snapshot);last_write=time.monotonic()
            if snapshot['error']:raise RuntimeError(snapshot['error'])
            time.sleep(.01)
    finally:
        for ex in executors:ex.shutdown(timeout_sec=1)
        for node in nodes:node.destroy_node()
        for ctx in contexts:rclpy.shutdown(context=ctx)


if __name__=='__main__':main()
