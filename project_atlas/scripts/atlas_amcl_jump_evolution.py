#!/usr/bin/env python3
"""Read-only header-time scan/particle comparison at stationary AMCL jumps.

Endpoint proximity is a geometric diagnostic, not AMCL's internal likelihood.
"""

import argparse
import bisect
import json

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from atlas_amcl_stationary_jump_audit import (
    cloud_support, compose, map_model, pose, scan_points, score_scan,
    transform_pose,
)


TOPICS = {"/amcl_pose", "/particle_cloud", "/scan", "/map", "/tf_static"}


def stamp(message):
    return message.header.stamp.sec + message.header.stamp.nanosec * 1e-9


def nearest_before(series, times, at, max_age=0.5):
    index = bisect.bisect_right(times, at) - 1
    return series[index] if index >= 0 and at - times[index] <= max_age else None


def read(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()
             if t.name in TOPICS}
    poses, clouds, scans, grid, static = [], [], [], None, {}
    while reader.has_next():
        topic, raw, receipt_ns = reader.read_next()
        if topic not in types:
            continue
        msg = deserialize_message(raw, types[topic])
        if topic == "/amcl_pose":
            poses.append((stamp(msg), pose(msg.pose.pose), receipt_ns * 1e-9))
        elif topic == "/particle_cloud":
            # Cloud header stamps are not comparable to AMCL pose headers in
            # these bags. Match producer output by bag receipt time instead.
            clouds.append((receipt_ns * 1e-9,
                           np.asarray([pose(p.pose) for p in msg.particles]).reshape(-1, 3),
                           np.asarray([p.weight for p in msg.particles])))
        elif topic == "/scan":
            scans.append((stamp(msg), msg))
        elif topic == "/map":
            grid = msg
        elif topic == "/tf_static":
            for tf in msg.transforms:
                static[(tf.header.frame_id.strip("/"),
                        tf.child_frame_id.strip("/"))] = transform_pose(tf.transform)
    return sorted(poses, key=lambda x: x[0]), sorted(clouds, key=lambda x: x[0]), sorted(scans, key=lambda x: x[0]), grid, static


def summarize(path, stop_s, source_bag=None):
    poses, clouds, scans, grid, static = read(path)
    if ("base_footprint", "laser_frame") not in static and source_bag:
        static = read(source_bag)[-1]
    if grid is None or ("base_footprint", "laser_frame") not in static:
        raise ValueError("map or laser extrinsic missing")
    laser = compose(static.get(("base_link", "base_footprint"), np.zeros(3)),
                    static[("base_footprint", "laser_frame")])
    model = map_model(grid)
    cloud_times = [c[0] for c in clouds]
    events = []
    for before, after in zip(poses, poses[1:]):
        duration = after[0] - before[0]
        step = float(np.linalg.norm(after[1][:2] - before[1][:2]))
        if not (after[0] > stop_s and 0 < duration <= 2 and step > 0.5):
            continue
        window = [s for s in scans if after[0] - 1.0 <= s[0] <= after[0]]
        window = window[-8:]
        fits = []
        for _, scan in window:
            points = scan_points(scan)
            if not len(points):
                continue
            b = score_scan(points, before[1], laser, model, check_rays=False)
            a = score_scan(points, after[1], laser, model, check_rays=False)
            fits.append((b["within_15cm_wall_fraction"],
                         a["within_15cm_wall_fraction"]))
        pre_cloud = nearest_before(clouds, cloud_times, before[2])
        post_cloud = nearest_before(clouds, cloud_times, after[2])
        events.append({
            "after_stop_s": round(after[0] - stop_s, 3),
            "step_m": round(step, 3),
            "scans_in_preceding_second": len(fits),
            "scan_fit_before_mean": round(float(np.mean([x[0] for x in fits])), 3) if fits else None,
            "scan_fit_after_mean": round(float(np.mean([x[1] for x in fits])), 3) if fits else None,
            "scans_favor_after": sum(a > b for b, a in fits),
            "particle_before": cloud_support(pre_cloud[1], pre_cloud[2], before[1], after[1]) if pre_cloud else None,
            "particle_after": cloud_support(post_cloud[1], post_cloud[2], before[1], after[1]) if post_cloud else None,
            "particle_age_before_s": round(before[2] - pre_cloud[0], 3) if pre_cloud else None,
            "particle_age_after_s": round(after[2] - post_cloud[0], 3) if post_cloud else None,
        })
    return {"bag": path, "events": events,
            "limitation": "Endpoint distance is not AMCL's internal scan likelihood. Published particle weights may be resampled/uniform; support fractions are not calibrated hypothesis probabilities."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    parser.add_argument("--stop-ns", type=int, required=True)
    parser.add_argument("--source-bag")
    args = parser.parse_args()
    print(json.dumps(summarize(args.bag, args.stop_ns * 1e-9,
                               args.source_bag), indent=2))


if __name__ == "__main__":
    main()
