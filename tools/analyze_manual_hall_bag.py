#!/usr/bin/env python3
"""Read-only summary for a manual ATLAS commissioning bag."""
import argparse
import json
import math
import statistics

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def integrate(samples):
    return sum((a[1] + b[1]) * 0.5 * (b[0] - a[0])
               for a, b in zip(samples, samples[1:]))


def path_length(samples):
    return sum(math.hypot(b[1] - a[1], b[2] - a[2])
               for a, b in zip(samples, samples[1:])
               if math.hypot(b[1] - a[1], b[2] - a[2]) < 0.25)


parser = argparse.ArgumentParser()
parser.add_argument("bag")
args = parser.parse_args()
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
            rosbag2_py.ConverterOptions("", ""))
types = {x.name: x.type for x in reader.get_all_topics_and_types()}
wanted = {k: get_message(v) for k, v in types.items() if k in {
    "/im10a/imu/unvalidated", "/im10a/imu/bias_corrected_candidate", "/imu/data", "/odom", "/yahboom/odom",
    "/lidar/odom", "/atlas/encoder_health", "/atlas/control_policy",
    "/pose",
}}
gyro = {"im10a": [], "board": []}
poses = {"odom": [], "wheel": [], "lidar": [], "slam": []}
health, policy = [], []
while reader.has_next():
    topic, raw, recorded = reader.read_next()
    if topic not in wanted:
        continue
    msg = deserialize_message(raw, wanted[topic])
    if topic in ("/im10a/imu/unvalidated", "/im10a/imu/bias_corrected_candidate"):
        gyro["im10a"].append((stamp(msg), float(msg.angular_velocity.z)))
    elif topic == "/imu/data":
        gyro["board"].append((stamp(msg), float(msg.angular_velocity.z)))
    elif topic in ("/odom", "/yahboom/odom", "/lidar/odom", "/pose"):
        key = {"/odom": "odom", "/yahboom/odom": "wheel", "/lidar/odom": "lidar", "/pose": "slam"}[topic]
        p = msg.pose.pose
        poses[key].append((stamp(msg), p.position.x, p.position.y, yaw(p.orientation)))
    elif topic == "/atlas/encoder_health":
        try: health.append(json.loads(msg.data))
        except Exception: pass
    elif topic == "/atlas/control_policy":
        try: policy.append(json.loads(msg.data))
        except Exception: pass

out = {"gyro": {}, "pose": {}, "encoder": {}, "control": {}}
for key, values in gyro.items():
    gaps = [b[0] - a[0] for a, b in zip(values, values[1:])]
    out["gyro"][key] = {
        "samples": len(values),
        "rate_hz": round((len(values)-1)/(values[-1][0]-values[0][0]), 3) if len(values)>1 else None,
        "max_gap_s": round(max(gaps), 4) if gaps else None,
        "min_rad_s": round(min(v for _,v in values), 5) if values else None,
        "max_rad_s": round(max(v for _,v in values), 5) if values else None,
        "integrated_deg": round(math.degrees(integrate(values)), 2) if values else None,
    }
for key, values in poses.items():
    out["pose"][key] = {
        "samples": len(values), "path_m": round(path_length(values), 3),
        "displacement_m": round(math.hypot(values[-1][1]-values[0][1], values[-1][2]-values[0][2]), 3) if values else None,
        "yaw_change_deg": round(math.degrees((values[-1][3]-values[0][3]+math.pi)%(2*math.pi)-math.pi), 2) if values else None,
    }
states = [str(x.get("state", "")) for x in health]
faults = [x for x in health if str(x.get("state", "")).upper() in ("CRITICAL", "INVALID")]
out["encoder"] = {
    "samples": len(health), "states": {s: states.count(s) for s in sorted(set(states))},
    "critical_samples": sum(s.upper() == "CRITICAL" for s in states),
    "critical_details": faults,
    "latest": health[-1] if health else None,
}
out["control"] = {"samples": len(policy), "latest": policy[-1] if policy else None}
print(json.dumps(out, indent=2))
