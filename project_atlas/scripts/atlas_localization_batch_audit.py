#!/usr/bin/env python3
"""Read-only, common-time localization summary across recorded ROS 2 bags.

No ROS nodes, publishers, services, command topics or motor interfaces are used.
Absence of AMCL in a bag is reported as unavailable, never as zero jumps.
"""

import argparse
import bisect
import collections
import json
import math
from pathlib import Path
import statistics

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import yaml

GYRO = "/im10a/imu/bias_corrected_candidate"
WHEEL = "/yahboom/odom"
TOPICS = {GYRO, WHEEL, "/odom", "/amcl_pose", "/scan",
          "/atlas/encoder_update", "/cmd_vel_joy"}


def angle(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def integrated(series, start, end):
    """Trapezoidal yaw integral with linearly interpolated common endpoints."""
    if len(series) < 2 or start < series[0][0] or end > series[-1][0] or end <= start:
        return None
    def value(t):
        for (a, va), (b, vb) in zip(series, series[1:]):
            if a <= t <= b:
                return va + (vb - va) * (t - a) / (b - a) if b > a else va
        return series[-1][1]
    points = [(start, value(start))] + [(t, v) for t, v in series if start < t < end]
    points.append((end, value(end)))
    return math.degrees(sum((b - a) * (va + vb) / 2
                            for (a, va), (b, vb) in zip(points, points[1:])))


def jumps(samples, threshold=0.5, max_interval_s=2.0):
    result = []
    for previous, current in zip(samples, samples[1:]):
        step = math.hypot(current[1] - previous[1], current[2] - previous[2])
        if 0 < current[0] - previous[0] <= max_interval_s and step > threshold:
            result.append((current[0], step))
    return result


def jump_context(amcl, wheel, gyro, scans, stop, threshold=0.5):
    """Describe recorded AMCL steps without treating sparse sensor data as zero motion."""
    wheel_times = [sample[0] for sample in wheel]
    scan_times = sorted(scans)
    events = []
    for previous, current in zip(amcl, amcl[1:]):
        start, end = previous[0], current[0]
        distance = math.hypot(current[1] - previous[1], current[2] - previous[2])
        if not 0 < end - start <= 2.0 or distance <= threshold:
            continue
        before = bisect.bisect_left(wheel_times, start)
        after = bisect.bisect_left(wheel_times, end)
        wheel_pair = (wheel[before], wheel[after]) if before < len(wheel) and after < len(wheel) else None
        if wheel_pair and (abs(wheel_pair[0][0] - start) > .2 or
                           abs(wheel_pair[1][0] - end) > .2):
            wheel_pair = None
        wheel_translation = (round(math.hypot(wheel_pair[1][1] - wheel_pair[0][1],
                                               wheel_pair[1][2] - wheel_pair[0][2]), 4)
                             if wheel_pair else None)
        gyro_turn = integrated(gyro, start, end)
        events.append({
            "time_after_last_remote_command_s": round(end - stop, 3) if stop is not None else None,
            "amcl_step_m": round(distance, 3),
            "amcl_heading_step_deg": round(math.degrees(math.remainder(current[3] - previous[3], 2 * math.pi)), 2),
            "amcl_xy_std_before_m": round(math.sqrt(max(0, previous[4])), 3),
            "amcl_xy_std_after_m": round(math.sqrt(max(0, current[4])), 3),
            "wheel_translation_m": wheel_translation,
            "gyro_turn_deg": round(gyro_turn, 3) if gyro_turn is not None else None,
            "scans_between_poses": bisect.bisect_right(scan_times, end) - bisect.bisect_left(scan_times, start),
        })
    return events


def pose_stability(samples, window_s=20.0):
    """Consecutive translation and final-window span; caller must check coverage."""
    if len(samples) < 2:
        return None
    adjacent = [(b[0] - a[0], math.hypot(b[1] - a[1], b[2] - a[2]))
                for a, b in zip(samples, samples[1:])]
    valid = [step for gap, step in adjacent if 0 < gap <= 2.0]
    recent = [point for point in samples if point[0] >= samples[-1][0] - window_s]
    recent_steps = [math.hypot(b[1] - a[1], b[2] - a[2])
                    for a, b in zip(recent, recent[1:])
                    if 0 < b[0] - a[0] <= 2.0]
    recent_headings = [sample[3] for sample in recent if len(sample) > 3]
    recent_yaw_steps = [abs(math.degrees(math.remainder(b[3] - a[3], 2 * math.pi)))
                        for a, b in zip(recent, recent[1:])
                        if len(a) > 3 and len(b) > 3 and 0 < b[0] - a[0] <= 2.0]
    return {
        "max_consecutive_step_m": round(max(valid), 3) if valid else None,
        "last_window_coverage_s": round(recent[-1][0] - recent[0][0], 2),
        "last_window_span_m": round(math.hypot(recent[-1][1] - recent[0][1],
                                               recent[-1][2] - recent[0][2]), 3),
        "last_window_max_step_m": round(max(recent_steps, default=0), 3),
        "last_window_heading_net_deg": round(math.degrees(math.remainder(
            recent_headings[-1] - recent_headings[0], 2 * math.pi)), 3)
        if len(recent_headings) >= 2 else None,
        "last_window_heading_max_step_deg": round(max(recent_yaw_steps), 3)
        if recent_yaw_steps else None,
    }


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[int(fraction * (len(ordered) - 1))], 4)


def audit(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {item.name: get_message(item.type)
             for item in reader.get_all_topics_and_types() if item.name in TOPICS}
    series = {"wheel": [], "gyro": [], "ekf": []}
    ages = {"wheel": [], "gyro": [], "ekf": [], "scan": []}
    poses = {"wheel": [], "ekf": []}
    amcl, active_commands, accepted, source_counts = [], [], collections.Counter(), collections.Counter()
    scan_stamps = []
    first_receipt = None
    while reader.has_next():
        topic, raw, receipt_ns = reader.read_next()
        if first_receipt is None:
            first_receipt = receipt_ns * 1e-9
        if topic not in types:
            continue
        msg = deserialize_message(raw, types[topic])
        t = receipt_ns * 1e-9
        if topic in (WHEEL, GYRO, "/odom", "/scan"):
            key = ("wheel" if topic == WHEEL else "gyro" if topic == GYRO
                   else "ekf" if topic == "/odom" else "scan")
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            ages[key].append(t - stamp)
            if topic == GYRO:
                series[key].append((stamp, float(msg.angular_velocity.z)))
            elif topic == "/scan":
                scan_stamps.append(stamp)
            else:
                series[key].append((stamp, float(msg.twist.twist.angular.z)))
                p = msg.pose.pose
                poses[key].append((stamp, p.position.x, p.position.y, angle(p.orientation)))
        elif topic == "/amcl_pose":
            p = msg.pose.pose
            amcl.append((t, p.position.x, p.position.y, angle(p.orientation),
                         msg.pose.covariance[0] + msg.pose.covariance[7]))
        elif topic == "/cmd_vel_joy":
            if abs(msg.linear.x) > 0.005 or abs(msg.angular.z) > 0.01:
                active_commands.append(t)
        elif topic == "/atlas/encoder_update":
            try:
                update = json.loads(msg.data)
                selected = tuple(update.get("accepted_channels", []))
                accepted[selected] += 1
                source_counts["M3_accepted"] += int(3 in selected)
                source_counts["updates"] += 1
            except (ValueError, TypeError):
                source_counts["invalid_json"] += 1
    common_start = max((v[0][0] for v in series.values() if v), default=None)
    common_end = min((v[-1][0] for v in series.values() if v), default=None)
    yaw = {key: integrated(values, common_start, common_end)
           if common_start is not None and common_end is not None else None
           for key, values in series.items()}
    corrections = jumps(amcl)
    stop = max(active_commands) if active_commands else None
    after_stop = [step for t, step in corrections if stop is not None and stop < t <= stop + 30]
    covariance = [math.sqrt(max(0.0, sample[4])) for sample in amcl]
    return {
        "bag": str(path), "counts": {"wheel": len(series["wheel"]),
                                    "gyro": len(series["gyro"]),
                                    "scan": len(ages["scan"]), "amcl": len(amcl)},
        "common_yaw_deg": {key: round(value, 2) if value is not None else None
                           for key, value in yaw.items()},
        "wheel_minus_gyro_deg": round(yaw["wheel"] - yaw["gyro"], 2)
            if yaw["wheel"] is not None and yaw["gyro"] is not None else None,
        "amcl_jumps_gt_0_5m_within_2s": len(corrections) if len(amcl) > 1 else None,
        "amcl_max_jump_m": round(max((step for _, step in corrections), default=0), 3)
            if len(amcl) > 1 else None,
        "amcl_jumps_within_30s_after_last_command": len(after_stop)
            if len(amcl) > 1 and stop is not None else None,
        "amcl_xy_std_median": round(statistics.median(covariance), 3) if covariance else None,
        "amcl_pose_stability": pose_stability(amcl),
        "amcl_jump_context": jump_context(amcl, poses["wheel"], series["gyro"],
                                            scan_stamps, stop),
        "encoder_updates": dict(source_counts),
        "encoder_selected_sets": {str(k): v for k, v in accepted.items()},
        "age_p95_s": {key: percentile(value, .95) for key, value in ages.items()},
        "limitations": "Commanded steering is not measured wheel angle. No AMCL samples means jump metrics are unavailable, not zero. Common-time yaw covers the overlapping recording interval, including stationary periods; map frames and hardware configuration can differ between dates."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", help="Recorded-drive tree to inventory")
    parser.add_argument("--bag", action="append", default=[],
                        help="Audit an explicit bag (including offline replay outputs)")
    args = parser.parse_args()
    if not args.root and not args.bag:
        parser.error("provide a root or at least one --bag")
    results = []
    paths = ([Path(path) / "metadata.yaml" for path in args.bag]
             if args.bag else sorted(Path(args.root).rglob("metadata.yaml")))
    for metadata in paths:
        if not args.bag and "diagnostics" in metadata.parts:
            continue
        info = yaml.safe_load(metadata.read_text())["rosbag2_bagfile_information"]
        counts = {item["topic_metadata"]["name"]: item["message_count"]
                  for item in info["topics_with_message_count"]}
        if args.bag or all(counts.get(topic, 0) for topic in (WHEEL, GYRO, "/scan")):
            results.append(audit(metadata.parent))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
