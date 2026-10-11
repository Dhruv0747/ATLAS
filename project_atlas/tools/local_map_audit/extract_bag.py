"""Read-only: extract scans, odometry, map->odom TF, AMCL and maps from a rosbag2 to .npz."""
import math, sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

bag, out = sys.argv[1], sys.argv[2]
want = {'/scan', '/odom', '/tf', '/tf_static', '/amcl_pose', '/lidar/odom', '/map', '/yahboom/odom', '/cmd_vel'}
r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=bag, storage_id=''), rosbag2_py.ConverterOptions('cdr', 'cdr'))
types = {t.name: t.type for t in r.get_all_topics_and_types()}
topics = [t for t in want if t in types]
r.set_filter(rosbag2_py.StorageFilter(topics=topics))
T = {k: get_message(types[k]) for k in topics}
yaw = lambda q: math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
scan_t, scan_r, odom, tfm, amcl, lodom, yodom, cmd, maps, static = [], [], [], [], [], [], [], [], [], {}
scan_meta = None
while r.has_next():
    topic, raw, t = r.read_next()
    m = deserialize_message(raw, T[topic]); t = t / 1e9
    if topic == '/scan':
        scan_t.append(t); scan_r.append(np.asarray(m.ranges, dtype=np.float32))
        scan_meta = (m.angle_min, m.angle_increment, m.range_min, m.range_max, m.header.frame_id)
    elif topic in ('/odom', '/lidar/odom', '/yahboom/odom'):
        p, tw = m.pose.pose, m.twist.twist
        row = (t, p.position.x, p.position.y, yaw(p.orientation), tw.linear.x, tw.angular.z)
        {'/odom': odom, '/lidar/odom': lodom, '/yahboom/odom': yodom}[topic].append(row)
    elif topic in ('/tf', '/tf_static'):
        for tr in m.transforms:
            q = tr.transform
            row = (t, q.translation.x, q.translation.y, yaw(q.rotation))
            if topic == '/tf_static':
                static[(tr.header.frame_id, tr.child_frame_id)] = row[1:]
            elif tr.header.frame_id == 'map' and tr.child_frame_id == 'odom':
                tfm.append(row)
    elif topic == '/amcl_pose':
        p = m.pose.pose; amcl.append((t, p.position.x, p.position.y, yaw(p.orientation), m.pose.covariance[0]))
    elif topic == '/cmd_vel':
        cmd.append((t, m.linear.x, m.angular.z))
    elif topic == '/map':
        i = m.info
        maps.append((t, i.resolution, i.width, i.height, i.origin.position.x, i.origin.position.y,
                     np.asarray(m.data, dtype=np.int8).reshape(i.height, i.width)))
n = max((len(x) for x in scan_r), default=0)
R = np.full((len(scan_r), n), np.nan, dtype=np.float32)
for i, x in enumerate(scan_r): R[i, :len(x)] = x
keep = sorted(set([0, len(maps) - 1] + list(range(0, len(maps), max(1, len(maps) // 12))))) if maps else []
mp = {}
for j, k in enumerate(keep):
    t, res, w, h, ox, oy, data = maps[k]
    mp[f'map{j}'] = data; mp[f'mapinfo{j}'] = np.array([t, res, w, h, ox, oy])
np.savez_compressed(out, scan_t=np.array(scan_t), scan_r=R,
    scan_meta=np.array(scan_meta[:4] if scan_meta else [0, 0, 0, 0]), scan_frame=str(scan_meta[4] if scan_meta else ''),
    odom=np.array(odom), lodom=np.array(lodom), yodom=np.array(yodom), tfm=np.array(tfm), amcl=np.array(amcl), cmd=np.array(cmd),
    static=np.array([[*k, *v] for k, v in static.items()], dtype=object), nmaps=len(keep), **mp)
print(out, 'scans', len(scan_t), 'odom', len(odom), 'tfm', len(tfm), 'amcl', len(amcl), 'maps', len(keep), 'static', list(static))
