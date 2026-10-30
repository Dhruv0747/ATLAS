"""Read-only ROS bag extraction for existing Astra recordings; never starts a driver.

Produces the bounded capture format for offline admission/replay. This command
does not publish ROS topics, invent RGB, transform depth or create calibration.
"""
import argparse
from pathlib import Path
import json
import sqlite3
from calibration_capture import Evidence

TOPICS={'/astra/depth/image_raw':'depth','/astra/color/image_raw':'rgb',
        '/astra/depth/camera_info':'depth_info','/astra/color/camera_info':'rgb_info'}


def inventory(path):
    with sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True) as db:
        return db.execute('select name,type,count(messages.id) from topics left join messages on topics.id=messages.topic_id group by topics.id').fetchall()


def extract(path, output):
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image, CameraInfo
    rows=inventory(path)
    missing=[t for t in TOPICS if not any(n==t and count>0 for n,typ,count in rows)]
    if missing: raise ValueError('No replayable RGB-D bundle; missing '+','.join(missing))
    store=Evidence(output)
    count=0; first=None
    try:
        with sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True) as db:
            for name,typ,recorded,cdr in db.execute('select topics.name,topics.type,messages.timestamp,messages.data from messages join topics on topics.id=messages.topic_id order by messages.timestamp'):
                if name not in TOPICS:continue
                key=TOPICS[name];expected='sensor_msgs/msg/CameraInfo' if 'info' in key else 'sensor_msgs/msg/Image'
                if typ!=expected:raise ValueError('unexpected ROS type')
                if first is None:first=recorded
                if recorded-first>60*10**9:break
                if count>=7200:raise ValueError('message count budget exceeded')
                msg=deserialize_message(cdr,CameraInfo if 'info' in key else Image)
                m=dict(stamp_sec=msg.header.stamp.sec,stamp_nanosec=msg.header.stamp.nanosec,
                       frame_id=msg.header.frame_id,width=msg.width,height=msg.height,
                       recorded_timestamp_ns=recorded,cdr=bytes(cdr))
                if 'info' in key:
                    m.update(k=[float(v) for v in msg.k],d=[float(v) for v in msg.d],r=[float(v) for v in msg.r],p=[float(v) for v in msg.p],distortion_model=msg.distortion_model)
                else:
                    m.update(encoding=msg.encoding,step=msg.step,is_bigendian=msg.is_bigendian,data_bytes=len(msg.data))
                    if key=='depth':
                        if msg.encoding not in ('16UC1','32FC1'):raise ValueError('unknown depth units')
                        m['units_to_m']=.001 if msg.encoding=='16UC1' else 1.
                store.write({key:m});count+=1
        store.finish(dict(status='EXTRACTED_UNVALIDATED',messages=count,reason='requires synchronized admission; no map accuracy claimed'))
    except Exception as e:
        store.finish(dict(status='ABORTED',messages=count,reason=str(e)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bag',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.output:extract(a.bag,a.output)
    else:print(json.dumps(inventory(a.bag),indent=2))

