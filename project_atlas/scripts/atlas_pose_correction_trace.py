"""Read-only temporal correction/odometry trace; SLAM is not ground truth."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from atlas_scan_map_jump_audit import compose, pose


def wrapped(value):
    return math.atan2(math.sin(value), math.cos(value))


def sample(series, timestamp):
    if timestamp < series[0,0] or timestamp > series[-1,0]:
        return None
    return np.array([np.interp(timestamp,series[:,0],series[:,i]) for i in range(1,series.shape[1])])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    args=parser.parse_args()
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag,storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    corrections, tf, gyro, health=[],[],[],[]
    odometry={'/odom':[], '/yahboom/odom':[]}
    allowed=set(odometry)|{'/tf','/im10a/imu/bias_corrected_candidate','/atlas/encoder_health'}
    start=None
    while reader.has_next():
        topic,data,record=reader.read_next()
        receipt=record*1e-9
        if start is None: start=receipt
        if topic not in allowed: continue
        m=deserialize_message(data,types[topic])
        if topic=='/tf':
            for t in m.transforms:
                pair=(t.header.frame_id.strip('/'),t.child_frame_id.strip('/'))
                stamp=t.header.stamp.sec+t.header.stamp.nanosec*1e-9
                if pair==('map','odom'): corrections.append((receipt,pose(t.transform)))
                elif pair==('odom','base_link'): tf.append((stamp,*pose(t.transform)))
        elif topic=='/atlas/encoder_health':
            try: health.append((receipt,json.loads(m.data)))
            except json.JSONDecodeError: pass
        else:
            stamp=m.header.stamp.sec+m.header.stamp.nanosec*1e-9
            if topic in odometry:
                q=m.pose.pose.orientation
                angle=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                odometry[topic].append((stamp,m.pose.pose.position.x,m.pose.pose.position.y,angle))
            else: gyro.append((stamp,m.angular_velocity.z))
    def array(rows):
        a=np.asarray(sorted(rows))
        if not len(a): raise ValueError('Missing required series')
        if a.shape[1]==4: a[:,3]=np.unwrap(a[:,3])
        return a
    tf=array(tf)
    odometry={k:array(v) for k,v in odometry.items()}
    gyro=array(gyro)
    events=[]
    for before,after in zip(corrections,corrections[1:]):
        t=after[0]
        base=sample(tf,t)
        if base is None: continue
        a,b=compose(before[1],base),compose(after[1],base)
        translation=float(np.linalg.norm(b[:2]-a[:2]))
        angle=math.degrees(wrapped(b[2]-a[2]))
        if translation<.02 and abs(angle)<2: continue
        changes={}
        for name,series in odometry.items():
            first,last=sample(series,t-5),sample(series,t)
            if first is not None and last is not None:
                changes[name]={'yaw_deg':math.degrees(last[2]-first[2]),
                               'endpoint_distance_m':float(np.linalg.norm(last[:2]-first[:2]))}
        integrated=None
        if gyro[0,0]<=t-5 and gyro[-1,0]>=t:
            times=np.r_[t-5,gyro[(gyro[:,0]>t-5)&(gyro[:,0]<t),0],t]
            integrated=math.degrees(float(np.trapz(np.interp(times,gyro[:,0],gyro[:,1]),times)))
        unhealthy=[{'relative_s':round(ts-start,3),'state':h.get('state',h.get('status')),'reason':h.get('reason')}
                   for ts,h in health if t-5<=ts<=t and
                   (str(h.get('state',h.get('status',''))).upper() in {'CRITICAL','FAULT','DEGRADED'} or h.get('scale',1)==0)]
        events.append({'seconds_from_start':t-start,'position_correction_m':translation,
                       'yaw_correction_deg':angle,'preceding_5s':changes,'imu_5s_deg':integrated,
                       'unhealthy_encoder_samples':len(unhealthy),'encoder_examples':unhealthy[:2]})
    events.sort(key=lambda e:e['seconds_from_start'])
    report={'bag':args.bag,'events_over_2cm_or_2deg':len(events),
            'top_position_events':sorted(events,key=lambda e:e['position_correction_m'],reverse=True)[:10],
            'events':events,
            'limitations':'Same-time map/base corrections evaluated at receipt time using recorded future-stamped TF. Five-second windows overlap; endpoint distance is not traveled distance. SLAM is not ground truth; correlation does not prove encoder or gyro fault.'}
    with Path(args.output).open('x') as destination: json.dump(report,destination,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='events'},indent=2))


if __name__=='__main__': main()
