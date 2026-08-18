#!/usr/bin/env python3
"""Summarize ATLAS odometry and LiDAR timing from a teaching rosbag."""

import argparse
import json
import math
from collections import defaultdict

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def yaw_of(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def summarize_odom(samples):
    if not samples:
        return {"samples": 0}
    distance = 0.0
    max_step = 0.0
    yaw_values = []
    for first, second in zip(samples, samples[1:]):
        step = math.hypot(second[1] - first[1], second[2] - first[2])
        distance += step
        max_step = max(max_step, step)
    for sample in samples:
        yaw_values.append(sample[3])
    first = samples[0]
    last = samples[-1]
    return {
        "samples": len(samples),
        "start": {"x": round(first[1], 3), "y": round(first[2], 3), "yaw_deg": round(math.degrees(first[3]), 2)},
        "end": {"x": round(last[1], 3), "y": round(last[2], 3), "yaw_deg": round(math.degrees(last[3]), 2)},
        "net_distance_m": round(math.hypot(last[1] - first[1], last[2] - first[2]), 3),
        "integrated_distance_m": round(distance, 3),
        "max_position_step_m": round(max_step, 4),
        "yaw_min_deg": round(math.degrees(min(yaw_values)), 2),
        "yaw_max_deg": round(math.degrees(max(yaw_values)), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    args = parser.parse_args()

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    topic_types = {
        item.name: item.type for item in reader.get_all_topics_and_types()
    }
    wanted = {"/odom", "/yahboom/odom", "/scan"}
    messages = {name: get_message(topic_types[name]) for name in wanted if name in topic_types}
    odometry = defaultdict(list)
    scan_lag_ms = []

    while reader.has_next():
        topic, raw, recorded_ns = reader.read_next()
        if topic not in messages:
            continue
        msg = deserialize_message(raw, messages[topic])
        if topic in ("/odom", "/yahboom/odom"):
            pose = msg.pose.pose
            odometry[topic].append(
                (recorded_ns, pose.position.x, pose.position.y, yaw_of(pose.orientation))
            )
        elif topic == "/scan":
            stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            scan_lag_ms.append((recorded_ns - stamp_ns) / 1_000_000.0)

    result = {name: summarize_odom(values) for name, values in odometry.items()}
    if scan_lag_ms:
        ordered = sorted(scan_lag_ms)
        result["scan_timing"] = {
            "samples": len(ordered),
            "lag_min_ms": round(ordered[0], 2),
            "lag_median_ms": round(ordered[len(ordered) // 2], 2),
            "lag_p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 2),
            "lag_max_ms": round(ordered[-1], 2),
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
