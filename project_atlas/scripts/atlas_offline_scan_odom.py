#!/usr/bin/env python3
"""Read-only adjacent-scan odometry for a recorded ATLAS bag.

This is a diagnostic comparison, not a replacement odometry publisher. ICP
can drift or match moving objects, and the scan origin is not the robot base.
"""

import argparse
import json
import math

import numpy as np
from scipy.spatial import cKDTree


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def register(previous, current):
    """Estimate current scan-frame pose in the previous scan frame."""
    if len(previous) < 40 or len(current) < 40:
        return None
    tree = cKDTree(previous)
    rotation = np.eye(2)
    translation = np.zeros(2)
    for _ in range(25):
        moved = current @ rotation.T + translation
        distances, indexes = tree.query(moved)
        keep = distances < min(0.35, float(np.quantile(distances, 0.8)))
        if keep.sum() < 40:
            return None
        source, target = moved[keep], previous[indexes[keep]]
        source_mean, target_mean = source.mean(axis=0), target.mean(axis=0)
        u, _, vt = np.linalg.svd((source - source_mean).T @ (target - target_mean))
        correction = vt.T @ u.T
        if np.linalg.det(correction) < 0:
            vt[-1, :] *= -1
            correction = vt.T @ u.T
        shift = target_mean - correction @ source_mean
        rotation, translation = correction @ rotation, correction @ translation + shift
        if np.linalg.norm(shift) < 1e-5 and abs(math.atan2(correction[1, 0], correction[0, 0])) < 1e-5:
            break
    distances, _ = tree.query(current @ rotation.T + translation)
    inliers = distances < 0.25
    if inliers.sum() < 40:
        return None
    return (translation, math.atan2(rotation[1, 0], rotation[0, 0]),
            float(np.sqrt(np.mean(distances[inliers] ** 2))), float(np.mean(inliers)))


def integrate(pose, translation, turn):
    x, y, heading = pose
    c, s = math.cos(heading), math.sin(heading)
    return (x + c * translation[0] - s * translation[1],
            y + s * translation[0] + c * translation[1], wrap(heading + turn))


def read_scans(path):
    """Read only /scan from a rosbag2 SQLite recording."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import LaserScan

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    scans = []
    while reader.has_next():
        topic, raw, _ = reader.read_next()
        if topic != "/scan":
            continue
        message = deserialize_message(raw, LaserScan)
        ranges = np.asarray(message.ranges, dtype=float)
        angles = message.angle_min + np.arange(len(ranges)) * message.angle_increment
        valid = np.isfinite(ranges) & (ranges > 0.3) & (ranges < 5.0)
        points = np.column_stack((ranges[valid] * np.cos(angles[valid]),
                                  ranges[valid] * np.sin(angles[valid])))
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        scans.append((stamp, points))
    return scans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="minimum seconds between accepted scan samples")
    args = parser.parse_args()
    if not 0.1 <= args.interval <= 2:
        parser.error("interval must be 0.1-2 seconds")

    scans = read_scans(args.bag)
    if len(scans) < 2:
        parser.error("at least two /scan messages required")
    sampled = []
    for stamp, points in scans:
        if not sampled or stamp - sampled[-1][0] >= args.interval:
            sampled.append((stamp, points))
    pose = (0.0, 0.0, 0.0)
    positions = [pose]
    failures = []
    rmse_values = []
    inlier_values = []
    for index, ((old_time, old), (new_time, new)) in enumerate(zip(sampled, sampled[1:])):
        fit = register(old, new)
        if fit is None:
            failures.append([index, round(new_time - old_time, 3), "no fit"])
            positions.append(pose)
            continue
        translation, turn, rmse, inliers = fit
        # Reject obviously implausible increments, but report them instead of
        # concealing their effect on path closure.
        if (np.linalg.norm(translation) > 0.35 or abs(turn) > math.radians(25)
                or rmse > 0.12 or inliers < 0.65):
            failures.append([index, round(new_time - old_time, 3),
                             round(float(np.linalg.norm(translation)), 3),
                             round(math.degrees(turn), 2), round(rmse, 3), round(inliers, 3)])
            positions.append(pose)
            continue
        pose = integrate(pose, translation, turn)
        positions.append(pose)
        rmse_values.append(rmse)
        inlier_values.append(inliers)
    final_window = [p for (stamp, _), p in zip(sampled, positions)
                    if stamp >= sampled[-1][0] - 20.0]
    stop_reference = final_window[0]
    final_window_translation = max(math.hypot(p[0] - stop_reference[0],
                                               p[1] - stop_reference[1])
                                   for p in final_window)
    final_window_turn = max(abs(wrap(p[2] - stop_reference[2]))
                            for p in final_window)
    print(json.dumps({
        "scan_count": len(scans), "sampled_count": len(sampled),
        "duration_s": round(sampled[-1][0] - sampled[0][0], 2),
        "final_pose_in_initial_scan_frame": [round(float(v), 3) for v in pose],
        "closure_translation_m": round(math.hypot(pose[0], pose[1]), 3),
        "last_20s_spread_m": round(final_window_translation, 3),
        "last_20s_spread_deg": round(math.degrees(final_window_turn), 2),
        "median_step_rmse_m": round(float(np.median(rmse_values)), 3) if rmse_values else None,
        "median_step_inlier_fraction": round(float(np.median(inlier_values)), 3) if inlier_values else None,
        "rejected_steps": len(failures), "first_rejections": failures[:12],
        "limitation": "Local scan ICP drifts; rejected increments were held at zero. No ground-truth or production pose is inferred."
    }, indent=2))


if __name__ == "__main__":
    main()
