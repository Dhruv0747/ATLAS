"""Read one isolated capture's mismatch evidence; no new replay or publishers."""
import json
import sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from std_msgs.msg import String
r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=sys.argv[1],storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
events=[];sources=set()
while r.has_next():
    t,raw,ns=r.read_next()
    if t=='/atlas/diagnostics/ekf_event':events.append(json.loads(deserialize_message(raw,String).data))
    elif t=='/atlas/diagnostics/capture_receipt':
        e=json.loads(deserialize_message(raw,String).data)
        if e['source_ns'] is not None:sources.add((e['topic'],e['source_ns']))
missing=[]
for e in events:
    if e['phase']!='measurement_before':continue
    topic=e['source'].removesuffix('_pose').removesuffix('_twist').removesuffix('_acceleration')
    if (topic,e['source_ns']) not in sources:missing.append({'source':e['source'],'source_ns':e['source_ns'],'seq':e['seq']})
print(json.dumps({'event_sources':sorted(set(e.get('source','') for e in events)),
    'missing_count':len(missing),'first_missing':missing[:5], 'last_events':[
        {k:e.get(k) for k in ('seq','source','source_ns','phase')} for e in events[-5:]]},indent=2))
