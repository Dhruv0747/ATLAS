#!/usr/bin/env python3
"""Summarize a manually measured ATLAS ground-drive rosbag."""

import argparse
import json
import math
from collections import defaultdict

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


ENCODER_TOPICS = tuple(f"/yahboom/encoder/m{index}" for index in range(1, 5))


def yaw_of(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    parser.add_argument("--measured-distance-m", type=float)
    args = parser.parse_args()

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    topic_types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    wanted = set(ENCODER_TOPICS) | {"/cmd_vel", "/cmd_vel_joy", "/odom", "/yahboom/odom", "/imu/data"}
    messages = {name: get_message(topic_types[name]) for name in wanted if name in topic_types}
    encoders = defaultdict(list)
    commands = defaultdict(list)
    odometry = defaultdict(list)
    imu_yaw = []

    while reader.has_next():
        topic, raw, recorded_ns = reader.read_next()
        if topic not in messages:
            continue
        msg = deserialize_message(raw, messages[topic])
        if topic in ENCODER_TOPICS:
            encoders[topic].append((recorded_ns, int(msg.data)))
        elif topic in ("/cmd_vel", "/cmd_vel_joy"):
            commands[topic].append((recorded_ns, float(msg.linear.x), float(msg.angular.z)))
        elif topic in ("/odom", "/yahboom/odom"):
            pose = msg.pose.pose
            odometry[topic].append((recorded_ns, float(pose.position.x), float(pose.position.y)))
        elif topic == "/imu/data":
            imu_yaw.append((recorded_ns, yaw_of(msg.orientation)))

    result = {"encoders": {}, "commands": {}, "odometry": {}}
    for topic in ENCODER_TOPICS:
        values = encoders.get(topic, [])
        if not values:
            result["encoders"][topic] = {"samples": 0}
            continue
        first, last = values[0][1], values[-1][1]
        delta = last - first
        steps = [second[1] - first_sample[1] for first_sample, second in zip(values, values[1:])]
        item = {
            "samples": len(values),
            "first": first,
            "last": last,
            "delta": delta,
            "minimum": min(value for _, value in values),
            "maximum": max(value for _, value in values),
            "max_abs_sample_step": max((abs(step) for step in steps), default=0),
            "opposite_direction_steps": sum(
                1 for step in steps if delta and step and (step > 0) != (delta > 0)
            ),
        }
        if args.measured_distance_m and args.measured_distance_m > 0:
            item["counts_per_metre"] = round(abs(delta) / args.measured_distance_m, 1)
        result["encoders"][topic] = item

    for topic, values in commands.items():
        moving = [sample for sample in values if abs(sample[1]) > 1.0e-4 or abs(sample[2]) > 1.0e-4]
        result["commands"][topic] = {
            "samples": len(values),
            "moving_samples": len(moving),
            "moving_duration_s": round((moving[-1][0] - moving[0][0]) / 1e9, 3) if len(moving) > 1 else 0.0,
            "max_abs_linear": round(max((abs(sample[1]) for sample in values), default=0.0), 3),
            "max_abs_angular": round(max((abs(sample[2]) for sample in values), default=0.0), 3),
            "final_linear": round(values[-1][1], 3) if values else None,
            "final_angular": round(values[-1][2], 3) if values else None,
        }

    for topic, values in odometry.items():
        first, last = values[0], values[-1]
        result["odometry"][topic] = {
            "samples": len(values),
            "delta_x_m": round(last[1] - first[1], 4),
            "delta_y_m": round(last[2] - first[2], 4),
            "net_distance_m": round(math.hypot(last[1] - first[1], last[2] - first[2]), 4),
        }

    if imu_yaw:
        result["imu"] = {
            "samples": len(imu_yaw),
            "yaw_change_deg": round(math.degrees(imu_yaw[-1][1] - imu_yaw[0][1]), 3),
            "yaw_span_deg": round(math.degrees(max(yaw for _, yaw in imu_yaw) - min(yaw for _, yaw in imu_yaw)), 3),
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
