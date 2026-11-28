#!/usr/bin/env python3
"""Read-only comparison of production and TF-disabled shadow AMCL bag poses."""

import argparse
import json
import math

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def summarize(poses):
    if not poses:
        return {"count": 0}
    x0, y0, h0 = poses[0][1:]
    distances = [math.hypot(x - x0, y - y0) for _, x, y, _ in poses]
    steps = [math.hypot(b[1] - a[1], b[2] - a[2])
             for a, b in zip(poses, poses[1:])]
    return {"count": len(poses), "start": [round(x0, 3), round(y0, 3), round(h0, 3)],
            "end": [round(v, 3) for v in poses[-1][1:]],
            "max_displacement_m": round(max(distances), 3),
            "max_step_m": round(max(steps, default=0), 3),
            "last_step_m": round(steps[-1], 3) if steps else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    selected = ("/amcl_pose", "/atlas_shadow/amcl_pose")
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()
             if t.name in selected}
    poses = {name: [] for name in selected}
    while reader.has_next():
        name, raw, receipt = reader.read_next()
        if name not in types:
            continue
        msg = deserialize_message(raw, types[name])
        p = msg.pose.pose
        poses[name].append((receipt, p.position.x, p.position.y, yaw(p.orientation)))
    print(json.dumps({name: summarize(poses[name]) for name in selected}, indent=2))


if __name__ == "__main__":
    main()
