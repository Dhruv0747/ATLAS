#!/bin/bash
# OFFLINE (isolated ROS domain 95, localhost only): replay a mapping drive into slam_toolbox with a parameter variant and
# measure how much map->odom jumps. The bag's own map->odom (from the live SLAM) is stripped first.
# Usage: bash replay_slam.sh BASE_BAG NAME "extra -p params"   -> /tmp/slam_replay/NAME.csv (receipt,stamp,x,y,yaw)
BAG=$1; NAME=$2; EXTRA=$3; W=/tmp/slam_replay; mkdir -p $W
export ROS_DOMAIN_ID=95 ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash
F=$W/filtered_$(basename $BAG)
if [ ! -d $F ]; then
python3 - "$BAG" "$F" <<'PY'
import sys, rosbag2_py
from rclpy.serialization import deserialize_message, serialize_message
from rosidl_runtime_py.utilities import get_message
src, dst = sys.argv[1], sys.argv[2]
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=src, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
types = {t.name: t.type for t in r.get_all_topics_and_types()}
keep = ['/scan', '/tf', '/tf_static']
r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/tf_static', '/odom']))   # odom->base_link TF rebuilt from /odom
w = rosbag2_py.SequentialWriter(); w.open(rosbag2_py.StorageOptions(uri=dst, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
for i, n in enumerate(keep):
    w.create_topic(rosbag2_py.TopicMetadata(name=n, type=types[n], serialization_format='cdr',
                   offered_qos_profiles=('- history: 3\n  depth: 0\n  reliability: 1\n  durability: 1\n  deadline: {sec: 2147483647, nsec: 4294967295}\n  lifespan: {sec: 2147483647, nsec: 4294967295}\n  liveliness: 1\n  liveliness_lease_duration: {sec: 2147483647, nsec: 4294967295}\n  avoid_ros_namespace_conventions: false\n' if n == '/tf_static' else '')))
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import TransformStamped
O = get_message(types['/odom'])
n_tf = 0
while r.has_next():
    name, data, t = r.read_next()
    if name == '/odom':
        # The recorded /tf odom->base_link arrived ~11 s late (overload); rebuild it from /odom at its own stamp.
        m = deserialize_message(data, O); ts = TransformStamped()
        ts.header = m.header; ts.header.frame_id = 'odom'; ts.child_frame_id = 'base_link'
        ts.transform.translation.x = m.pose.pose.position.x; ts.transform.translation.y = m.pose.pose.position.y
        ts.transform.rotation = m.pose.pose.orientation
        stamp_ns = m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
        w.write('/tf', serialize_message(TFMessage(transforms=[ts])), max(stamp_ns, t - 200000000)); n_tf += 1
        continue
    w.write(name, data, t)
del w
print('filtered bag written; odom->base_link TF rebuilt from /odom:', n_tf)
PY
fi
setsid /opt/ros/humble/lib/slam_toolbox/async_slam_toolbox_node --ros-args -r __node:=slam_toolbox -r /map:=/map_raw \
  -p use_sim_time:=true -p odom_frame:=odom -p map_frame:=map -p base_frame:=base_link -p scan_topic:=/scan -p mode:=mapping \
  -p min_laser_range:=0.20 -p max_laser_range:=8.0 -p transform_timeout:=1.5 -p tf_buffer_duration:=30.0 \
  -p use_scan_matching:=true -p do_loop_closing:=true $EXTRA > $W/$NAME.slam.log 2>&1 &
SLAM=$!
setsid python3 - "$W/$NAME.csv" > $W/$NAME.rec.log 2>&1 <<'PY' &
import sys, math, rclpy
from tf2_msgs.msg import TFMessage
rclpy.init(); n = rclpy.create_node('slam_rec', parameter_overrides=[rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
f = open(sys.argv[1], 'w')
def cb(m):
    for x in m.transforms:
        if x.header.frame_id == 'map' and x.child_frame_id == 'odom':
            q = x.transform.rotation; y = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            now = n.get_clock().now().nanoseconds * 1e-9
            f.write(f'{now:.3f},{x.header.stamp.sec + x.header.stamp.nanosec*1e-9:.3f},{x.transform.translation.x:.4f},{x.transform.translation.y:.4f},{y:.5f}\n'); f.flush()
n.create_subscription(TFMessage, '/tf', cb, 100)
rclpy.spin(n)
PY
REC=$!
sleep 6
ros2 bag play $F --clock 100 > $W/$NAME.play.log 2>&1
sleep 5
kill -INT -- -$SLAM -$REC 2>/dev/null; sleep 3; kill -KILL -- -$SLAM -$REC 2>/dev/null
python3 - "$W/$NAME.csv" <<'PY'
import sys, numpy as np, math, time
a = np.loadtxt(sys.argv[1], delimiter=',', ndmin=2)
u = a[np.r_[True, np.diff(a[:, 1]) != 0]]
st = np.hypot(np.diff(u[:, 2]), np.diff(u[:, 3])); dy = np.degrees(np.abs(np.angle(np.exp(1j*np.diff(u[:, 4])))))
lag = a[:, 0] - a[:, 1]
print(f'{sys.argv[1].split("/")[-1]}: {len(u)} SLAM updates | max step {st.max():.3f} m at {time.strftime("%H:%M:%S", time.localtime(u[np.argmax(st)+1,1]))} '
      f'| steps > 0.15 m: {(st > 0.15).sum()} | max yaw step {dy.max():.1f} deg, > 5 deg: {(dy > 5).sum()} '
      f'| total correction path {st.sum():.2f} m | TF lag median {np.median(lag):.2f} s')
PY
