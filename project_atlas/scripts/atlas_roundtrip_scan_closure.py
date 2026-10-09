#!/usr/bin/env python3
"""Read-only first/last LiDAR scan registration for a manually driven loop.

Multiple yaw seeds expose geometric ambiguity. ICP alone is not a trustworthy
localization fix or a license to publish an initial pose.
"""

import argparse
import json
import math

import numpy as np
from scipy.spatial import cKDTree


def icp(reference, observed, initial_yaw):
    if len(reference) < 30 or len(observed) < 30:
        return None
    c, s = math.cos(initial_yaw), math.sin(initial_yaw)
    rotation = np.array(((c, -s), (s, c)))
    translation = np.zeros(2)
    tree = cKDTree(reference)
    for _ in range(50):
        moved = observed @ rotation.T + translation
        distance, index = tree.query(moved)
        keep = distance < min(0.45, np.quantile(distance, 0.8))
        if keep.sum() < 30:
            return None
        x, y = moved[keep], reference[index[keep]]
        xc, yc = x.mean(axis=0), y.mean(axis=0)
        u, _, vt = np.linalg.svd((x - xc).T @ (y - yc))
        update = vt.T @ u.T
        if np.linalg.det(update) < 0:
            vt[-1, :] *= -1
            update = vt.T @ u.T
        shift = yc - update @ xc
        rotation, translation = update @ rotation, update @ translation + shift
        if np.linalg.norm(shift) < 1e-5 and abs(math.atan2(update[1, 0], update[0, 0])) < 1e-5:
            break
    distance, _ = tree.query(observed @ rotation.T + translation)
    keep = distance < 0.25
    if keep.sum() < 30:
        return None
    return {"yaw_deg": round(math.degrees(math.atan2(rotation[1, 0], rotation[0, 0])), 2),
            "translation_m": [round(float(v), 3) for v in translation],
            "rmse_m": round(float(np.sqrt(np.mean(distance[keep] ** 2))), 3),
            "inliers": int(keep.sum()),
            "observed_points": int(len(observed)),
            "inlier_fraction": round(float(np.mean(keep)), 3)}


def scan_points(message):
    ranges = np.asarray(message.ranges, dtype=float)
    angles = message.angle_min + np.arange(len(ranges)) * message.angle_increment
    valid = np.isfinite(ranges) & (ranges > 0.3) & (ranges < 5.0)
    return np.column_stack((ranges[valid] * np.cos(angles[valid]),
                            ranges[valid] * np.sin(angles[valid])))


def read_scans(path):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import PoseWithCovarianceStamped

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    scans, poses = [], []
    while reader.has_next():
        topic, raw, _ = reader.read_next()
        if topic == "/scan":
            msg = deserialize_message(raw, LaserScan)
            scans.append((msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                          scan_points(msg)))
        elif topic == "/amcl_pose":
            msg = deserialize_message(raw, PoseWithCovarianceStamped)
            q = msg.pose.pose.orientation
            heading = math.atan2(2 * (q.w * q.z + q.x * q.y),
                                 1 - 2 * (q.y * q.y + q.z * q.z))
            poses.append((msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                          msg.pose.pose.position.x, msg.pose.pose.position.y, heading,
                          math.sqrt(max(0.0, msg.pose.covariance[0] + msg.pose.covariance[7]))))
    return scans, poses


def compare(scans, poses=()):
    if len(scans) < 100:
        raise ValueError("insufficient scans")
    start, end = scans[0][0], scans[-1][0]
    # Exclude bag start/stop transients; choose three independently acquired
    # scan pairs to check whether an apparent match is repeatable.
    offsets = (8.0, 12.0, 16.0)
    rows = []
    for offset in offsets:
        first = min(scans, key=lambda item: abs(item[0] - (start + offset)))
        last = min(scans, key=lambda item: abs(item[0] - (end - offset)))
        fits = [icp(first[1], last[1], math.radians(degrees))
                for degrees in range(-180, 180, 30)]
        ranked = sorted((fit for fit in fits if fit),
                        key=lambda fit: (-fit["inlier_fraction"], fit["rmse_m"]))
        rows.append({"start_offset_s": round(first[0] - start, 2),
                     "end_offset_s": round(end - last[0], 2),
                     "best_candidates": ranked[:3],
                     "all_seed_outcomes": ranked})
    first_poses = [pose for pose in poses if start <= pose[0] <= start + 20]
    last_poses = [pose for pose in poses if end - 20 <= pose[0] <= end]
    initial = min(first_poses, key=lambda item: abs(item[0] - (start + 12))) if first_poses else None
    final = min(last_poses, key=lambda item: abs(item[0] - (end - 12))) if last_poses else None
    estimated = None
    if initial and rows[1]["best_candidates"]:
        fit = rows[1]["best_candidates"][0]
        dx, dy = fit["translation_m"]
        c, s = math.cos(initial[3]), math.sin(initial[3])
        estimated = [round(initial[1] + c * dx - s * dy, 3),
                     round(initial[2] + s * dx + c * dy, 3),
                     round(math.atan2(math.sin(initial[3] + math.radians(fit["yaw_deg"])),
                                      math.cos(initial[3] + math.radians(fit["yaw_deg"]))), 3)]
    return {"duration_s": round(end - start, 2), "pairs": rows,
            "initial_amcl_near_12s": [round(v, 3) for v in initial[1:]] if initial else None,
            "final_amcl_near_end_minus_12s": [round(v, 3) for v in final[1:]] if final else None,
            "final_pose_estimate_from_scan_registration": estimated,
            "limitation": "Nearest-neighbour scan ICP can favor repeated walls, furniture and people; no ground-truth pose or AMCL posterior is inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    args = parser.parse_args()
    print(json.dumps(compare(*read_scans(args.bag)), indent=2))


if __name__ == "__main__":
    main()
