"""Native ROS2 Humble pub/sub and SQLite smoke test, isolated PC only."""
import os
import json
import time
import resource
import hashlib
import sqlite3
from pathlib import Path
import tempfile

assert os.environ['ROS_DOMAIN_ID']=='187'
assert os.environ['ROS_LOCALHOST_ONLY']=='1'
assert os.readlink('/proc/self/ns/net')!=os.environ['ATLAS_PC_HOST_NET_NS']
import rclpy
from rclpy.serialization import serialize_message, deserialize_message
from std_msgs.msg import Int32
import rosbag2_py
import psutil

base=Path('/root/atlas_pc_diagnostics')
base.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='native-',dir=base))
bag=root/'bag'
writer=rosbag2_py.SequentialWriter()
writer.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),
            rosbag2_py.ConverterOptions('cdr','cdr'))
writer.create_topic(rosbag2_py.TopicMetadata(name='/atlas_pc_test',type='std_msgs/msg/Int32',serialization_format='cdr'))
rclpy.init()
node=rclpy.create_node('atlas_pc_isolated_smoke',enable_rosout=False,start_parameter_services=False)
publisher_node=rclpy.create_node('atlas_pc_isolated_publisher',enable_rosout=False,start_parameter_services=False)
pub=publisher_node.create_publisher(Int32,'/atlas_pc_test',100)
received=[]
def receive(msg):
    raw=serialize_message(msg)
    stamp=time.time_ns()
    writer.write('/atlas_pc_test',raw,stamp)
    received.append((msg.data,stamp,hashlib.sha256(raw).hexdigest()))
sub=node.create_subscription(Int32,'/atlas_pc_test',receive,100)
deadline=time.monotonic()+10
while pub.get_subscription_count()!=1:
    assert time.monotonic()<deadline,'discovery timeout'
    rclpy.spin_once(node,timeout_sec=.05)
start=time.monotonic();cpu=time.process_time();system=[];n=0
psutil.cpu_percent()
while time.monotonic()-start<30:
    pub.publish(Int32(data=n));n+=1
    until=time.monotonic()+.02
    while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.001)
    if n%50==0:system.append(psutil.cpu_percent())
deadline=time.monotonic()+3
while len(received)<n and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.01)
wall=time.monotonic()-start;used=time.process_time()-cpu
node.destroy_node();publisher_node.destroy_node();rclpy.shutdown();del writer
with sqlite3.connect(next(bag.glob('*.db3'))) as db:
    integrity=db.execute('pragma integrity_check').fetchone()[0]
reader=rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('cdr','cdr'))
actual=[]
while reader.has_next():
    topic,raw,stamp=reader.read_next()
    assert topic=='/atlas_pc_test'
    actual.append((deserialize_message(raw,Int32).data,stamp,hashlib.sha256(raw).hexdigest()))
assert integrity=='ok' and actual==received
assert [x[0] for x in actual]==list(range(n)), 'lost/duplicated sequence'
result={'duration_s':wall,'process_cpu_s':used,'cpu_one_core_percent':100*used/wall,
        'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'wsl_system_cpu_mean_percent':sum(system)/len(system),'wsl_system_cpu_peak_percent':max(system),
        'sent':n,'received':len(received),'missing':n-len(received),'sqlite_integrity':integrity,
        'payload_timestamp_roundtrip':True,'bytes':sum(p.stat().st_size for p in bag.iterdir()),
        'evidence':str(root),'network_namespace':os.readlink('/proc/self/ns/net'),
        'live_jetson_connections':False}
(root/'result.json').write_text(json.dumps(result,indent=2))
import shutil
shutil.copytree(root,Path('/mnt/c/Users/Dhruv/Documents/Codex/2026-07-24/h/atlas_wsl_install_evidence')/root.name)
print(json.dumps(result,indent=2))
