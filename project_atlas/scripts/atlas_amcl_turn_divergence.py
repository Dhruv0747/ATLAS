#!/usr/bin/env python3
"""Read-only wheel/gyro/AMCL timeline for a recorded manual route.

This does not replay a bag, create a ROS node, or command a rover. Reported
gyro integration and wheel yaw are estimates, not surveyed physical heading.
"""

import argparse
import collections
import json
import math
import statistics


def yaw(quaternion):
    return math.atan2(
        2 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1 - 2 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


def stamp(message):
    return message.header.stamp.sec + message.header.stamp.nanosec * 1e-9


def unwrap(series):
    """Unwrap (time, radians) without treating a +/-pi crossing as a turn."""
    result = []
    previous = None
    total = 0.0
    for time_s, angle in sorted(series):
        if previous is not None:
            total += math.atan2(math.sin(angle - previous),
                                math.cos(angle - previous))
        result.append((time_s, total))
        previous = angle
    return result


def interpolate(series, time_s):
    if not series or time_s < series[0][0] or time_s > series[-1][0]:
        return None
    for before, after in zip(series, series[1:]):
        if before[0] <= time_s <= after[0]:
            if after[0] == before[0]:
                return after[1]
            fraction = (time_s - before[0]) / (after[0] - before[0])
            return before[1] + fraction * (after[1] - before[1])
    return series[-1][1]


def integrated_gyro(series):
    """Cumulative gyro yaw; do not integrate across a missing >0.5 s gap."""
    result = []
    total = 0.0
    for (time_s, rate), (next_time, next_rate) in zip(series, series[1:]):
        if not result:
            result.append((time_s, total))
        interval = next_time - time_s
        if 0 < interval <= 0.5:
            total += (rate + next_rate) * interval / 2
        result.append((next_time, total))
    return result


def yaw_change(series, start, end):
    first, last = interpolate(series, start), interpolate(series, end)
    return None if first is None or last is None else math.degrees(last - first)


def summarize(wheel, fused, gyro, amcl, commands, health=(), steering=(), period_s=5.0):
    wheel_yaw = unwrap([(t, heading) for t, heading, _, _ in wheel])
    fused_yaw = unwrap([(t, heading) for t, heading, _, _ in fused])
    gyro_yaw = integrated_gyro(sorted(gyro))
    if not wheel_yaw or not fused_yaw or not gyro_yaw or not amcl:
        raise ValueError("wheel odom, fused odom, corrected gyro and AMCL required")
    start = max(wheel_yaw[0][0], fused_yaw[0][0], gyro_yaw[0][0])
    end = min(wheel_yaw[-1][0], fused_yaw[-1][0], gyro_yaw[-1][0])
    windows = []
    at = start
    while at + period_s <= end:
        stop = at + period_s
        changes = {name: yaw_change(series, at, stop) for name, series in
                   (("wheel_deg", wheel_yaw), ("ekf_deg", fused_yaw),
                    ("gyro_deg", gyro_yaw))}
        covariance = [std for t, _, _, std in amcl if at <= t < stop]
        health_in_window = [item for t, item in health if at <= t < stop]
        selections = collections.Counter(
            str(item.get("selected_encoders", "unknown")) for item in health_in_window)
        steering_ranges = {}
        for axle in ("front", "rear"):
            angles = [angle for t, name, angle in steering
                      if name == axle and at <= t < stop]
            steering_ranges[axle] = [round(min(angles), 1), round(max(angles), 1)] if angles else None
        windows.append({
            "offset_s": round(at - start, 2),
            **{name: round(value, 2) for name, value in changes.items()},
            "wheel_minus_gyro_deg": round(changes["wheel_deg"] - changes["gyro_deg"], 2),
            "amcl_xy_std_median_m": round(statistics.median(covariance), 3)
            if covariance else None,
            "encoder_fault_samples": sum(
                item.get("state") not in ("READY", "HEALTHY") or bool(item.get("faults"))
                for item in health_in_window),
            "encoder_health_samples": len(health_in_window),
            "encoder_selection_counts": dict(selections),
            "commanded_steering_ranges_deg": steering_ranges,
        })
        at = stop
    steps = []
    for before, after in zip(amcl, amcl[1:]):
        delta_t = after[0] - before[0]
        delta_xy = math.hypot(after[1] - before[1], after[2] - before[2])
        if 0 < delta_t <= 2 and delta_xy > 0.5:
            steps.append({"offset_s": round(after[0] - start, 2),
                          "step_m": round(delta_xy, 3),
                          "std_before_m": round(before[3], 3),
                          "std_after_m": round(after[3], 3)})
    last_command = max((t for t, linear, angular in commands
                        if abs(linear) > 0.005 or abs(angular) > 0.01),
                       default=None)
    return {
        "overlap_duration_s": round(end - start, 2),
        "last_nonzero_command_offset_s": round(last_command - start, 2)
        if last_command is not None else None,
        "first_amcl_xy_std_above_0_5_offset_s": next(
            (round(t - start, 2) for t, _, _, std in amcl if t >= start and std > 0.5), None),
        "first_amcl_xy_std_above_1_0_offset_s": next(
            (round(t - start, 2) for t, _, _, std in amcl if t >= start and std > 1.0), None),
        "large_amcl_steps": steps,
        "worst_turn_windows": sorted(windows, key=lambda row: abs(row["wheel_minus_gyro_deg"]),
                                     reverse=True)[:8],
        "window_count": len(windows),
        "caveat": "Commanded steering is not physical angle; odom/gyro estimates are not ground truth.",
    }


def read_bag(path):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    topics = {"/yahboom/odom", "/odom", "/im10a/imu/bias_corrected_candidate",
              "/amcl_pose", "/cmd_vel", "/atlas/encoder_health",
              "/steering/front_angle_deg", "/steering/rear_angle_deg"}
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {topic.name: get_message(topic.type)
             for topic in reader.get_all_topics_and_types() if topic.name in topics}
    wheel, fused, gyro, amcl, commands, health, steering = [], [], [], [], [], [], []
    while reader.has_next():
        topic, raw, received_ns = reader.read_next()
        if topic not in types:
            continue
        msg = deserialize_message(raw, types[topic])
        if topic == "/yahboom/odom" or topic == "/odom":
            position = msg.pose.pose.position
            row = (stamp(msg), yaw(msg.pose.pose.orientation), position.x, position.y)
            (wheel if topic == "/yahboom/odom" else fused).append(row)
        elif topic == "/im10a/imu/bias_corrected_candidate":
            gyro.append((stamp(msg), msg.angular_velocity.z))
        elif topic == "/amcl_pose":
            position = msg.pose.pose.position
            covariance = msg.pose.covariance
            amcl.append((stamp(msg), position.x, position.y,
                         math.sqrt(max(0, covariance[0] + covariance[7]))))
        elif topic == "/cmd_vel":
            commands.append((received_ns * 1e-9, msg.linear.x, msg.angular.z))
        elif topic == "/atlas/encoder_health":
            try:
                item = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            health.append((received_ns * 1e-9, item))
        elif topic in ("/steering/front_angle_deg", "/steering/rear_angle_deg"):
            steering.append((received_ns * 1e-9,
                             "front" if "front" in topic else "rear", msg.data))
    return wheel, fused, gyro, amcl, commands, health, steering


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    args = parser.parse_args()
    print(json.dumps(summarize(*read_bag(args.bag)), indent=2))


if __name__ == "__main__":
    main()
