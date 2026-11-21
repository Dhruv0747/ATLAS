"""Offline AMCL replay (isolated ROS domain, sim time). Publishes /clock, /scan, /tf (WITHOUT the recorded map->odom),
/tf_static from a bag segment; sends the live AMCL pose at segment start as /initialpose; records the replayed
/amcl_pose plus the recorded live /amcl_pose as JSON lines. Usage: replay.py BAG T_START T_END OUT"""
import json, math, sys, time
import rclpy, rosbag2_py
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rclpy.serialization import deserialize_message
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import PoseWithCovarianceStamped

bag, t_start, t_end, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]


def row(kind, t, m):
    p = m.pose.pose; c = m.pose.covariance
    return json.dumps({'kind': kind, 't': t, 'x': p.position.x, 'y': p.position.y,
                       'yaw': math.degrees(2 * math.atan2(p.orientation.z, p.orientation.w)),
                       'sd_xy': math.sqrt(max(c[0], c[7], 0.0)), 'sd_yaw': math.degrees(math.sqrt(max(c[35], 0.0)))})


r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/tf', '/tf_static', '/amcl_pose']))
msgs = []; t0 = None; static = []; init = None
while r.has_next():
    topic, data, ts = r.read_next()
    t0 = ts / 1e9 if t0 is None else t0
    rel = ts / 1e9 - t0
    if topic == '/tf_static':
        static.append(deserialize_message(data, TFMessage)); continue
    if topic == '/amcl_pose':
        m = deserialize_message(data, PoseWithCovarianceStamped)
        if rel <= t_start: init = m
        if t_start <= rel <= t_end: msgs.append((ts, topic, m))
        continue
    if not (t_start - 2.0 <= rel <= t_end): continue
    if topic == '/scan':
        msgs.append((ts, topic, deserialize_message(data, LaserScan)))
    else:
        m = deserialize_message(data, TFMessage)
        m.transforms = [x for x in m.transforms if not (x.header.frame_id == 'map' and x.child_frame_id == 'odom')]
        if m.transforms: msgs.append((ts, topic, m))
if init is None:
    sys.exit('no live /amcl_pose before T_START')

rclpy.init()
n = Node('atlas_amcl_replay')
latched = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
p_clock = n.create_publisher(Clock, '/clock', 10)
p_scan = n.create_publisher(LaserScan, '/scan', QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT))
p_tf = n.create_publisher(TFMessage, '/tf', 100)
p_static = n.create_publisher(TFMessage, '/tf_static', latched)
p_init = n.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
f = open(out, 'w')
n.create_subscription(PoseWithCovarianceStamped, '/amcl_pose',
                      lambda m: f.write(row('replay', m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m) + '\n'),
                      latched)
for ts, topic, m in msgs:
    if topic == '/amcl_pose':
        f.write(row('live', m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m) + '\n')
first = msgs[0][0]


def clock(ts):
    c = Clock(); c.clock.sec = int(ts // 1_000_000_000); c.clock.nanosec = int(ts % 1_000_000_000); p_clock.publish(c)


for st in static:
    for x in st.transforms:
        x.header.stamp.sec = int(first // 1_000_000_000); x.header.stamp.nanosec = int(first % 1_000_000_000)
    p_static.publish(st)
for _ in range(40):
    clock(first); rclpy.spin_once(n, timeout_sec=0.05)
init.header.stamp.sec = int(first // 1_000_000_000); init.header.stamp.nanosec = int(first % 1_000_000_000)
for _ in range(3):
    p_init.publish(init); clock(first); rclpy.spin_once(n, timeout_sec=0.2)
wall0 = time.monotonic()
for ts, topic, m in msgs:
    if topic == '/amcl_pose': continue
    while time.monotonic() - wall0 < (ts - first) / 1e9:
        rclpy.spin_once(n, timeout_sec=0.005)
    clock(ts)
    (p_scan if topic == '/scan' else p_tf).publish(m)
end = time.monotonic() + 2.0
while time.monotonic() < end:
    rclpy.spin_once(n, timeout_sec=0.05)
f.close(); n.destroy_node(); rclpy.shutdown()
