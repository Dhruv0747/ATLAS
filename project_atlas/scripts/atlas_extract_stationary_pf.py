#!/usr/bin/env python3
"""Export recorded stationary windows for the non-ROS AMCL core experiment.

Generated bundles contain raw recorded data; keep them outside source control.
The filter state is initialized from a published cloud, not an internal RNG
checkpoint. This experiment tests stationary update policy, not exact replay.
"""
import argparse
import glob
import json
import math
from pathlib import Path
import sqlite3


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def main():
    import yaml
    from rclpy.serialization import deserialize_message as decode
    from nav_msgs.msg import Odometry, OccupancyGrid
    from nav2_msgs.msg import ParticleCloud
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    parser.add_argument("nav_config")
    parser.add_argument("output")
    args = parser.parse_args()
    databases = glob.glob(str(Path(args.bag) / "*.db3"))
    if len(databases) != 1:
        raise ValueError("experiment requires one SQLite bag segment")
    db = sqlite3.connect("file:" + databases[0] + "?mode=ro", uri=True)
    topics = dict(db.execute("SELECT name,id FROM topics"))
    start = db.execute("SELECT MIN(timestamp) FROM messages").fetchone()[0]

    def rows(topic):
        return db.execute("SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp",
                          (topics[topic],))

    odom = []
    for t, raw in rows("/odom"):
        p = decode(raw, Odometry).pose.pose
        odom.append((t, p.position.x, p.position.y, yaw(p.orientation)))
    windows, anchor, last = [], None, None
    for point in odom:
        if anchor is None:
            anchor = point
        elif (math.hypot(point[1] - anchor[1], point[2] - anchor[2]) > .002 or
              abs(math.atan2(math.sin(point[3] - anchor[3]), math.cos(point[3] - anchor[3]))) > math.radians(.2) or
              point[0] - last[0] > 1e9):
            if last[0] - anchor[0] > 30e9:
                windows.append((anchor[0], last[0]))
            anchor = point
        last = point
    if last and last[0] - anchor[0] > 30e9:
        windows.append((anchor[0], last[0]))
    if not windows:
        raise ValueError("no stationary window of at least 30 seconds")

    grid = decode(next(iter(rows("/map")))[1], OccupancyGrid)
    if abs(yaw(grid.info.origin.orientation)) > 1e-8:
        raise ValueError("rotated occupancy map unsupported")
    static = {}
    for _, raw in rows("/tf_static"):
        for tf in decode(raw, TFMessage).transforms:
            static[(tf.header.frame_id.strip("/"), tf.child_frame_id.strip("/"))] = tf.transform
    tf = static[("base_footprint", "laser_frame")]
    if abs(tf.rotation.x) + abs(tf.rotation.y) > 1e-8:
        raise ValueError("nonplanar laser rotation needs explicit bearing transformation")
    base = static.get(("base_link", "base_footprint"))
    if base and (abs(base.translation.x) + abs(base.translation.y) + abs(yaw(base.rotation))) > 1e-8:
        raise ValueError("nonidentity base_link/base_footprint needs explicit composition")
    laser = [tf.translation.x, tf.translation.y, yaw(tf.rotation)]
    params = yaml.safe_load(Path(args.nav_config).read_text())["amcl"]["ros__parameters"]
    if params["laser_model_type"] != "likelihood_field":
        raise ValueError("experiment only supports installed likelihood_field model")
    if params["recovery_alpha_fast"] != 0 or params["recovery_alpha_slow"] != 0:
        raise ValueError("experiment assumes the current disabled random recovery")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    files = []
    for index, (begin, end) in enumerate(windows):
        # Start from the first published cloud inside the verified still window.
        record = db.execute("SELECT timestamp,data FROM messages WHERE topic_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp LIMIT 1",
                            (topics["/particle_cloud"], begin, end)).fetchone()
        if not record:
            continue
        seed_time, raw = record
        cloud = decode(raw, ParticleCloud)
        particles = [[p.pose.position.x, p.pose.position.y, yaw(p.pose.orientation), p.weight]
                     for p in cloud.particles]
        scans, target = [], seed_time + int(1e9)
        for t, raw in db.execute("SELECT timestamp,data FROM messages WHERE topic_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp",
                                 (topics["/scan"], seed_time, end)):
            if t < target:
                continue
            msg = decode(raw, LaserScan)
            stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            if stamp < begin:
                continue
            target = t + int(1e9)
            maximum = min(msg.range_max, params["laser_max_range"]) if params["laser_max_range"] > 0 else msg.range_max
            minimum = max(msg.range_min, params["laser_min_range"]) if params["laser_min_range"] > 0 else msg.range_min
            ranges = [float(v) if math.isfinite(v) and v > minimum and v < maximum else maximum
                      for v in msg.ranges]
            scans.append({"time_s": (t - seed_time) / 1e9, "range_max": maximum,
                          "angle_min": msg.angle_min + laser[2], "angle_increment": msg.angle_increment,
                          "ranges": ranges})
        bundle = {"source_bag": args.bag, "window_offset_s": [(begin-start)/1e9, (end-start)/1e9],
                  "zero_motion_assumption": "recorded EKF pose within 2 mm / 0.2 deg of window anchor; no motion model applied",
                  "ground_truth": None, "particle_checkpoint": "published cloud only; fresh controlled RNG",
                  "map": {"width": grid.info.width, "height": grid.info.height, "resolution": grid.info.resolution,
                          "origin": [grid.info.origin.position.x, grid.info.origin.position.y], "cells": list(grid.data)},
                  "laser": laser, "parameters": params, "particles": particles, "scans": scans}
        filename = output / f"window_{index}.json"
        filename.write_text(json.dumps(bundle, allow_nan=False))
        files.append({"file": str(filename), "offset_s": bundle["window_offset_s"],
                      "particles": len(particles), "scans": len(scans)})
    print(json.dumps(files, indent=2))


if __name__ == "__main__":
    main()
