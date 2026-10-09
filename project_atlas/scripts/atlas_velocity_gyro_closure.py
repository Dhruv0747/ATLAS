#!/usr/bin/env python3
"""Read-only round-trip closure comparison using recorded wheel speed and IMU gyro.

This is a kinematic diagnostic, not a replacement for robot_localization EKF or
physical ground truth. It does not publish ROS messages or change settings.
"""

import argparse
import bisect
import json
import math


TOPICS = {"/yahboom/odom", "/odom", "/im10a/imu/bias_corrected_candidate"}


def stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def yaw(quaternion):
    return math.atan2(2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
                      1 - 2 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z))


def integrate_velocity_gyro(wheel, gyro):
    """Integrate body-forward wheel velocity with corrected gyro Z on common time."""
    if len(wheel) < 2 or len(gyro) < 2:
        raise ValueError("wheel and gyro samples are required")
    gyro_t = [row[0] for row in gyro]
    x = y = heading = 0.0
    used = skipped = 0
    for (t0, vx0), (t1, vx1) in zip(wheel, wheel[1:]):
        dt = t1 - t0
        if not 0 < dt <= 0.5:
            skipped += 1
            continue
        mid = (t0 + t1) / 2
        index = bisect.bisect_left(gyro_t, mid)
        if index == 0 or index == len(gyro):
            skipped += 1
            continue
        left, right = gyro[index - 1], gyro[index]
        if mid - left[0] > 0.25 or right[0] - mid > 0.25:
            skipped += 1
            continue
        rate = left[1] + (right[1] - left[1]) * (mid - left[0]) / (right[0] - left[0])
        dtheta = rate * dt
        distance = (vx0 + vx1) * 0.5 * dt
        x += distance * math.cos(heading + dtheta / 2)
        y += distance * math.sin(heading + dtheta / 2)
        heading += dtheta
        used += 1
    return {"closure_m": round(math.hypot(x, y), 3),
            "yaw_change_deg": round(math.degrees(heading), 2),
            "signed_distance_m": round(sum((b[0] - a[0]) * (a[1] + b[1]) / 2
                                           for a, b in zip(wheel, wheel[1:])
                                           if 0 < b[0] - a[0] <= 0.5), 3),
            "intervals_used": used, "intervals_skipped": skipped}


def pose_closure(series):
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    return {"closure_m": round(math.hypot(last[1] - first[1], last[2] - first[2]), 3),
            "yaw_change_deg": round(math.degrees(math.remainder(last[3] - first[3], 2 * math.pi)), 2),
            "samples": len(series)}


def read_bag(path):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {item.name: get_message(item.type)
             for item in reader.get_all_topics_and_types() if item.name in TOPICS}
    wheel, gyro, wheel_pose, ekf_pose = [], [], [], []
    while reader.has_next():
        topic, raw, _ = reader.read_next()
        if topic not in types:
            continue
        msg = deserialize_message(raw, types[topic])
        t = stamp(msg)
        if topic == "/im10a/imu/bias_corrected_candidate":
            gyro.append((t, float(msg.angular_velocity.z)))
        else:
            pose = msg.pose.pose
            record = (t, pose.position.x, pose.position.y, yaw(pose.orientation))
            (wheel_pose if topic == "/yahboom/odom" else ekf_pose).append(record)
            if topic == "/yahboom/odom":
                wheel.append((t, float(msg.twist.twist.linear.x)))
    wheel.sort()
    gyro.sort()
    wheel_pose.sort()
    ekf_pose.sort()
    return wheel, gyro, wheel_pose, ekf_pose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    args = parser.parse_args()
    wheel, gyro, wheel_pose, ekf_pose = read_bag(args.bag)
    print(json.dumps({"bag": args.bag,
                      "velocity_plus_corrected_gyro": integrate_velocity_gyro(wheel, gyro),
                      "recorded_wheel_pose": pose_closure(wheel_pose),
                      "recorded_ekf_pose": pose_closure(ekf_pose),
                      "caveat": "An approximate return to the same room is not exact pose ground truth; this is not a robot_localization EKF replay."}, indent=2))


if __name__ == "__main__":
    main()
