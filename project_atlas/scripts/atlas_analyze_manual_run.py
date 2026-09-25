#!/usr/bin/env python3
"""Summarize a manually measured ATLAS ground-drive rosbag."""

import argparse
import bisect
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import rosbag2_py
import yaml
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from atlas_encoder_selection import EncoderDeltaEstimator


ENCODER_TOPICS = tuple(f"/yahboom/encoder/m{index}" for index in range(1, 5))


def yaw_of(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def value_at(samples, timestamp_ns):
    if not samples:
        return None
    index = bisect.bisect_right([sample[0] for sample in samples], timestamp_ns) - 1
    return samples[max(0, index)][1]


def motion_segments(samples, gap_s=0.75):
    moving = [sample for sample in samples if abs(sample[1]) > 1.0e-4]
    if not moving:
        return []
    segments = []
    current = [moving[0]]
    for sample in moving[1:]:
        previous = current[-1]
        same_direction = (sample[1] > 0) == (previous[1] > 0)
        close = (sample[0] - previous[0]) / 1e9 <= gap_s
        if same_direction and close:
            current.append(sample)
        else:
            segments.append(current)
            current = [sample]
    segments.append(current)
    return segments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    parser.add_argument("--measured-distance-m", type=float)
    parser.add_argument("--encoder-calibration")
    parser.add_argument("--laser-yaw-deg", type=float, default=180.0)
    args = parser.parse_args()

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=args.bag, storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    topic_types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    wanted = set(ENCODER_TOPICS) | {"/cmd_vel", "/cmd_vel_joy", "/odom", "/yahboom/odom", "/imu/data", "/scan"}
    messages = {name: get_message(topic_types[name]) for name in wanted if name in topic_types}
    encoders = defaultdict(list)
    commands = defaultdict(list)
    odometry = defaultdict(list)
    imu_yaw = []
    lidar_sectors = []
    replay_raw = {}
    replay_seen = set()
    replay_estimator = EncoderDeltaEstimator()
    replay_distance = 0.0
    replay_rejections = defaultdict(int)
    calibration = None
    if args.encoder_calibration:
        calibration = yaml.safe_load(
            Path(args.encoder_calibration).read_text(encoding="utf-8")
        )["encoder_calibration"]
        circumference = float(calibration["wheel_circumference_m"])

    while reader.has_next():
        topic, raw, recorded_ns = reader.read_next()
        if topic not in messages:
            continue
        msg = deserialize_message(raw, messages[topic])
        if topic in ENCODER_TOPICS:
            encoders[topic].append((recorded_ns, int(msg.data)))
            if calibration is not None:
                replay_raw[topic] = int(msg.data)
                replay_seen.add(topic)
                if replay_seen == set(ENCODER_TOPICS):
                    distances = []
                    for motor_index, encoder_topic in enumerate(ENCODER_TOPICS, start=1):
                        motor = calibration["motors"][f"m{motor_index}"]
                        distances.append(
                            replay_raw[encoder_topic]
                            * float(motor["encoder_sign"])
                            * circumference
                            / float(motor["counts_per_revolution"])
                        )
                    replay_distance += replay_estimator.update(distances, range(4))
                    for rejected in replay_estimator.last_rejected:
                        replay_rejections[rejected] += 1
                    replay_seen.clear()
        elif topic in ("/cmd_vel", "/cmd_vel_joy"):
            commands[topic].append((recorded_ns, float(msg.linear.x), float(msg.angular.z)))
        elif topic in ("/odom", "/yahboom/odom"):
            pose = msg.pose.pose
            odometry[topic].append((recorded_ns, float(pose.position.x), float(pose.position.y)))
        elif topic == "/imu/data":
            imu_yaw.append((recorded_ns, yaw_of(msg.orientation)))
        elif topic == "/scan":
            nearest = {"front": math.inf, "rear": math.inf}
            for scan_index, value in enumerate(msg.ranges):
                if not math.isfinite(value) or value < msg.range_min or value > msg.range_max:
                    continue
                raw_degrees = math.degrees(msg.angle_min + scan_index * msg.angle_increment)
                base_degrees = raw_degrees + args.laser_yaw_deg
                front_error = abs((base_degrees + 180.0) % 360.0 - 180.0)
                rear_error = abs((base_degrees - 180.0 + 180.0) % 360.0 - 180.0)
                if front_error <= 17.5:
                    nearest["front"] = min(nearest["front"], value)
                if rear_error <= 17.5:
                    nearest["rear"] = min(nearest["rear"], value)
            lidar_sectors.append((recorded_ns, nearest["front"], nearest["rear"]))

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

    command_source = commands.get("/cmd_vel_joy") or commands.get("/cmd_vel") or []
    result["motion_segments"] = []
    for index, segment in enumerate(motion_segments(command_source), start=1):
        start_ns, end_ns = segment[0][0], segment[-1][0]
        item = {
            "index": index,
            "direction": "forward" if segment[0][1] > 0 else "reverse",
            "duration_s": round((end_ns - start_ns) / 1e9, 3),
            "command_samples": len(segment),
            "encoder_delta": {},
        }
        for topic in ENCODER_TOPICS:
            start_value = value_at(encoders.get(topic, []), start_ns)
            end_value = value_at(encoders.get(topic, []), end_ns)
            item["encoder_delta"][topic] = (
                end_value - start_value if start_value is not None and end_value is not None else None
            )
        for topic, values in odometry.items():
            xs = [(stamp, x) for stamp, x, _ in values]
            ys = [(stamp, y) for stamp, _, y in values]
            start_x, end_x = value_at(xs, start_ns), value_at(xs, end_ns)
            start_y, end_y = value_at(ys, start_ns), value_at(ys, end_ns)
            if None not in (start_x, end_x, start_y, end_y):
                item[topic] = {
                    "delta_x_m": round(end_x - start_x, 4),
                    "delta_y_m": round(end_y - start_y, 4),
                    "distance_m": round(math.hypot(end_x - start_x, end_y - start_y), 4),
                }
        result["motion_segments"].append(item)

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
    if lidar_sectors:
        window = min(20, max(1, len(lidar_sectors) // 4))
        first_window = lidar_sectors[:window]
        last_window = lidar_sectors[-window:]
        def sector_median(samples, index):
            values = [sample[index] for sample in samples if math.isfinite(sample[index])]
            return statistics.median(values) if values else None
        front_start = sector_median(first_window, 1)
        front_end = sector_median(last_window, 1)
        rear_start = sector_median(first_window, 2)
        rear_end = sector_median(last_window, 2)
        front_change = front_start - front_end if None not in (front_start, front_end) else None
        rear_change = rear_end - rear_start if None not in (rear_start, rear_end) else None
        estimates = [value for value in (front_change, rear_change) if value is not None and value > 0]
        result["lidar_scene_check"] = {
            "laser_yaw_deg": args.laser_yaw_deg,
            "front_start_m": round(front_start, 3) if front_start is not None else None,
            "front_end_m": round(front_end, 3) if front_end is not None else None,
            "front_forward_change_m": round(front_change, 3) if front_change is not None else None,
            "rear_start_m": round(rear_start, 3) if rear_start is not None else None,
            "rear_end_m": round(rear_end, 3) if rear_end is not None else None,
            "rear_forward_change_m": round(rear_change, 3) if rear_change is not None else None,
            "scene_displacement_estimate_m": round(statistics.median(estimates), 3) if estimates else None,
            "warning": "Scene-sector change is a cross-check, not LiDAR scan-matching odometry.",
        }
    if calibration is not None:
        result["consensus_replay"] = {
            "integrated_distance_m": round(replay_distance, 4),
            "last_accepted_encoders": [i + 1 for i in replay_estimator.last_accepted],
            "rejected_intervals_by_encoder": {
                f"M{index + 1}": replay_rejections[index] for index in range(4)
            },
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
