#!/usr/bin/env python3
"""Compare ATLAS wheel odometry, fused odometry, IMU and steering in a bag."""

import argparse
import json
import math
import statistics

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def yaw(q):
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def unwrap(values):
    if not values:
        return []
    out = [values[0]]
    for value in values[1:]:
        delta = math.atan2(math.sin(value - out[-1]), math.cos(value - out[-1]))
        out.append(out[-1] + delta)
    return out


def series_summary(samples):
    if not samples:
        return {"samples": 0}
    angles = unwrap([item[1] for item in samples])
    return {
        "samples": len(samples),
        "duration_s": round((samples[-1][0] - samples[0][0]) * 1e-9, 3),
        "start_deg": round(math.degrees(angles[0]), 2),
        "end_deg": round(math.degrees(angles[-1]), 2),
        "net_change_deg": round(math.degrees(angles[-1] - angles[0]), 2),
        "range_deg": round(math.degrees(max(angles) - min(angles)), 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    wanted = {
        "/odom", "/yahboom/odom", "/imu/data",
        "/steering/front_angle_deg", "/steering/rear_angle_deg",
    }
    messages = {name: get_message(types[name]) for name in wanted if name in types}
    heading = {"fused_odom": [], "wheel_odom": [], "imu": []}
    yaw_rate = {"fused_odom": [], "wheel_odom": [], "imu": []}
    steering = {"front": [], "rear": []}
    stamp_lag_ms = {"fused_odom": [], "wheel_odom": [], "imu": []}
    frames = {}
    while reader.has_next():
        topic, raw, recorded = reader.read_next()
        if topic not in messages:
            continue
        msg = deserialize_message(raw, messages[topic])
        if topic in ("/odom", "/yahboom/odom"):
            key = "fused_odom" if topic == "/odom" else "wheel_odom"
            heading[key].append((recorded, yaw(msg.pose.pose.orientation)))
            yaw_rate[key].append((recorded, float(msg.twist.twist.angular.z)))
            stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            stamp_lag_ms[key].append((recorded - stamp) / 1_000_000.0)
            frames[key] = {"frame": msg.header.frame_id, "child": msg.child_frame_id}
        elif topic == "/imu/data":
            heading["imu"].append((recorded, yaw(msg.orientation)))
            yaw_rate["imu"].append((recorded, float(msg.angular_velocity.z)))
            stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            stamp_lag_ms["imu"].append((recorded - stamp) / 1_000_000.0)
            frames["imu"] = {"frame": msg.header.frame_id}
        else:
            key = "front" if "front" in topic else "rear"
            steering[key].append(float(msg.data))

    result = {"heading": {key: series_summary(value) for key, value in heading.items()}}
    result["yaw_rate"] = {
        key: {
            "samples": len(values),
            "mean": round(statistics.fmean(v for _, v in values), 4) if values else None,
            "min": round(min(v for _, v in values), 4) if values else None,
            "max": round(max(v for _, v in values), 4) if values else None,
            "integrated_change_deg": round(math.degrees(sum(
                0.5 * (first[1] + second[1]) * (second[0] - first[0]) * 1e-9
                for first, second in zip(values, values[1:])
            )), 2) if values else None,
        }
        for key, values in yaw_rate.items()
    }
    result["steering_deg"] = {
        key: {
            "samples": len(values),
            "mean": round(statistics.fmean(values), 2) if values else None,
            "min": round(min(values), 2) if values else None,
            "max": round(max(values), 2) if values else None,
        }
        for key, values in steering.items()
    }
    result["timestamp_lag_ms"] = {
        key: {
            "median": round(statistics.median(values), 2) if values else None,
            "p95": round(sorted(values)[int(0.95 * (len(values) - 1))], 2) if values else None,
            "max": round(max(values), 2) if values else None,
        }
        for key, values in stamp_lag_ms.items()
    }
    result["frames"] = frames
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
