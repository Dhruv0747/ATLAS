"""Read-only metrics for an isolated SLAM replay; no ROS node is created."""
import json
import math
import sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def angle(x):
    return math.atan2(math.sin(x), math.cos(x))


def summarize(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    previous = None
    correction = None
    first_pose = None
    last_pose = None
    samples = scans = maps = 0
    max_xy = max_yaw = 0.0
    last_map = None
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        msg = deserialize_message(data, types[topic])
        if topic == '/scan':
            scans += 1
        elif topic == '/map':
            maps += 1
            last_map = {'width': msg.info.width, 'height': msg.info.height,
                        'known_cells': sum(v >= 0 for v in msg.data)}
        elif topic == '/tf':
            for t in msg.transforms:
                q = t.transform.rotation
                yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                p = (t.transform.translation.x, t.transform.translation.y, yaw)
                pair = (t.header.frame_id.strip('/'), t.child_frame_id.strip('/'))
                if pair == ('map', 'odom'):
                    samples += 1
                    if previous:
                        max_xy = max(max_xy, math.hypot(p[0]-previous[0], p[1]-previous[1]))
                        max_yaw = max(max_yaw, abs(angle(p[2]-previous[2])))
                    previous = correction = p
                elif pair == ('odom', 'base_link') and correction:
                    x, y, a = correction
                    last_pose = (x+math.cos(a)*p[0]-math.sin(a)*p[1],
                                 y+math.sin(a)*p[0]+math.cos(a)*p[1], angle(a+p[2]))
                    if first_pose is None:
                        first_pose = last_pose
    return {'bag': path, 'tf_samples': samples, 'scans': scans, 'maps': maps,
            'max_translation_jump_m': max_xy, 'max_yaw_jump_deg': math.degrees(max_yaw),
            'approx_endpoint_delta_m': math.dist(first_pose[:2], last_pose[:2]) if first_pose and last_pose else None,
            'approx_endpoint_yaw_deg': math.degrees(abs(angle(last_pose[2]-first_pose[2]))) if first_pose and last_pose else None,
            'last_map': last_map,
            'note': 'Endpoint estimate uses latest received correction, not time-interpolated TF; diagnostic only.'}


if __name__ == '__main__':
    print(json.dumps([summarize(p) for p in sys.argv[1:]], indent=2))
