#!/usr/bin/env python3
"""Compare original and isolated-replay AMCL pose jumps by message time."""

import argparse
import json
import math

import rosbag2_py
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.serialization import deserialize_message


def read_poses(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    poses = []
    while reader.has_next():
        topic, raw, _ = reader.read_next()
        if topic != "/amcl_pose":
            continue
        msg = deserialize_message(raw, PoseWithCovarianceStamped)
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        poses.append((stamp, msg.pose.pose.position.x, msg.pose.pose.position.y,
                      math.sqrt(max(0.0, msg.pose.covariance[0] + msg.pose.covariance[7]))))
    return poses


def summarize(poses, stop_s):
    jumps = []
    for first, second in zip(poses, poses[1:]):
        dt = second[0] - first[0]
        step = math.hypot(second[1] - first[1], second[2] - first[2])
        if 0 < dt <= 2 and step > 0.5:
            jumps.append({"stamp_s": round(second[0], 3),
                          "after_stop_s": round(second[0] - stop_s, 3),
                          "step_m": round(step, 3),
                          "xy_std_m": round(second[3], 3)})
    post = [p for p in poses if p[0] > stop_s]
    return {"poses": len(poses), "post_stop_poses": len(post),
            "large_jumps": jumps,
            "post_stop_large_jumps": sum(j["after_stop_s"] > 0 for j in jumps),
            "max_jump_m": max((j["step_m"] for j in jumps), default=0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("replay")
    parser.add_argument("--stop-ns", type=int, required=True)
    args = parser.parse_args()
    stop_s = args.stop_ns * 1e-9
    print(json.dumps({"original": summarize(read_poses(args.original), stop_s),
                      "replay": summarize(read_poses(args.replay), stop_s)}, indent=2))


if __name__ == "__main__":
    main()
