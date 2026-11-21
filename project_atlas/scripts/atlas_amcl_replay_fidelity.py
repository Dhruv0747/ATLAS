#!/usr/bin/env python3
"""Read-only audit of whether an AMCL replay preserves its recorded inputs.

No ROS nodes are started and no messages or commands are published. The bag
reader intentionally inspects only topics required to explain replay fidelity.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import yaml


TOPICS = {"/amcl_pose", "/particle_cloud", "/scan", "/odom", "/map",
          "/tf", "/tf_static", "/yahboom/odom",
          "/im10a/imu/bias_corrected_candidate"}


def stamp_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def map_overlap(occupancy, map_yaml):
    """Compare trinary saved-map cells with the map latched in the bag."""
    settings = yaml.safe_load(Path(map_yaml).read_text())
    image = Path(settings["image"])
    if not image.is_absolute():
        image = Path(map_yaml).parent / image
    pixels = np.flipud(np.asarray(Image.open(image).convert("L"), dtype=np.float64))
    recorded = np.asarray(occupancy.data, dtype=np.int16).reshape(
        occupancy.info.height, occupancy.info.width)
    if pixels.shape != recorded.shape:
        return {"same_dimensions": False, "recorded_shape": recorded.shape,
                "saved_shape": pixels.shape}
    occupancy_fraction = (255 - pixels) / 255 if not settings.get("negate") else pixels / 255
    saved = np.full(pixels.shape, -1, dtype=np.int16)
    saved[occupancy_fraction < settings["free_thresh"]] = 0
    saved[occupancy_fraction > settings["occupied_thresh"]] = 100
    recorded_class = np.where(recorded < 0, -1, np.where(recorded >= 65, 100, 0))
    return {"same_dimensions": True,
            "same_trinary_cell_fraction": round(float(np.mean(saved == recorded_class)), 5),
            "different_cells": int(np.count_nonzero(saved != recorded_class)),
            "cells": int(saved.size),
            "recorded_origin": [round(float(v), 4) for v in
                                (occupancy.info.origin.position.x,
                                 occupancy.info.origin.position.y,
                                 yaw(occupancy.info.origin.orientation))],
            "saved_origin": settings["origin"]}


def inspect_bag(path, start_ns=None, end_ns=None):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()
             if t.name in TOPICS}
    counts, window_counts = {}, {}
    first, last, seed, cloud, tf_before = {}, {}, None, None, {}
    first_pose, last_pose, first_cloud = None, None, None
    pose_std_window, cloud_spread_window = [], []
    headers, window_headers = {}, {}
    map_message = None
    while reader.has_next():
        topic, raw, receipt = reader.read_next()
        if topic not in types:
            continue
        counts[topic] = counts.get(topic, 0) + 1
        if start_ns is not None and start_ns <= receipt <= end_ns:
            window_counts[topic] = window_counts.get(topic, 0) + 1
        if topic in ("/scan", "/odom", "/yahboom/odom",
                     "/im10a/imu/bias_corrected_candidate"):
            msg = deserialize_message(raw, types[topic])
            headers.setdefault(topic, set()).add(stamp_ns(msg.header.stamp))
            if start_ns is not None and start_ns <= receipt <= end_ns:
                window_headers.setdefault(topic, set()).add(stamp_ns(msg.header.stamp))
            delta_ms = round((receipt - stamp_ns(msg.header.stamp)) / 1e6, 1)
            first.setdefault(topic, {"receipt_ns": receipt, "header_ns": stamp_ns(msg.header.stamp),
                                     "header_to_receipt_ms": delta_ms})
            last[topic] = {"receipt_ns": receipt, "header_ns": stamp_ns(msg.header.stamp),
                           "header_to_receipt_ms": delta_ms}
        elif topic == "/map":
            map_message = deserialize_message(raw, types[topic])
        elif start_ns is not None and receipt <= start_ns:
            if topic == "/amcl_pose":
                msg = deserialize_message(raw, types[topic])
                p = msg.pose.pose
                seed = {"age_s": round((start_ns - receipt) / 1e9, 3),
                        "pose": [round(p.position.x, 3), round(p.position.y, 3),
                                 round(yaw(p.orientation), 3)],
                        "xy_std_m": round(math.sqrt(max(0, msg.pose.covariance[0] +
                                                       msg.pose.covariance[7])), 3),
                        "yaw_std_deg": round(math.degrees(math.sqrt(max(0,
                                                        msg.pose.covariance[35]))), 2)}
            elif topic == "/particle_cloud":
                msg = deserialize_message(raw, types[topic])
                positions = np.asarray([(p.pose.position.x, p.pose.position.y)
                                        for p in msg.particles])
                cloud = {"age_s": round((start_ns - receipt) / 1e9, 3),
                         "particles": len(positions),
                         "xy_spread_m": round(float(np.sqrt(np.sum(np.var(positions, axis=0)))), 3)}
            elif topic in ("/tf", "/tf_static"):
                msg = deserialize_message(raw, types[topic])
                for tf in msg.transforms:
                    pair = (tf.header.frame_id.strip("/"), tf.child_frame_id.strip("/"))
                    if pair in (("map", "odom"), ("odom", "base_link"),
                                ("base_footprint", "laser_frame")):
                        tf_before["->".join(pair)] = {
                            "receipt_age_s": round((start_ns - receipt) / 1e9, 3),
                            "header_age_s": round((start_ns - stamp_ns(tf.header.stamp)) / 1e9, 3)}
        if topic == "/amcl_pose":
            msg = deserialize_message(raw, types[topic])
            latest = {"receipt_ns": receipt,
                      "header_ns": stamp_ns(msg.header.stamp),
                      "xy_std_m": round(math.sqrt(max(0, msg.pose.covariance[0] +
                                                       msg.pose.covariance[7])), 3)}
            if first_pose is None:
                first_pose = latest
            last_pose = latest
        elif topic == "/particle_cloud" and first_cloud is None:
            msg = deserialize_message(raw, types[topic])
            positions = np.asarray([(p.pose.position.x, p.pose.position.y)
                                    for p in msg.particles])
            first_cloud = {"receipt_ns": receipt, "particles": len(positions),
                           "xy_spread_m": round(float(np.sqrt(np.sum(np.var(positions, axis=0)))), 3)}
        if start_ns is None or start_ns <= receipt <= end_ns:
            if topic == "/amcl_pose":
                msg = deserialize_message(raw, types[topic])
                pose_std_window.append(math.sqrt(max(0, msg.pose.covariance[0] +
                                                    msg.pose.covariance[7])))
            elif topic == "/particle_cloud":
                msg = deserialize_message(raw, types[topic])
                positions = np.asarray([(p.pose.position.x, p.pose.position.y)
                                        for p in msg.particles])
                cloud_spread_window.append(float(np.sqrt(np.sum(np.var(positions, axis=0)))))
    if cloud is not None and seed is not None:
        # The serialized cloud is not retained: dispersion is enough to show
        # that one mean pose is not a particle-filter checkpoint.
        cloud["mean_pose_is_full_particle_state"] = False
    return {"counts": counts, "clip_window_counts": window_counts,
            "headers": headers, "window_headers": window_headers,
            "first_pose": first_pose, "last_pose": last_pose, "first_cloud": first_cloud,
            "pose_xy_std_median_m": round(float(np.median(pose_std_window)), 3) if pose_std_window else None,
            "pose_xy_std_max_m": round(float(max(pose_std_window)), 3) if pose_std_window else None,
            "cloud_spread_median_m": round(float(np.median(cloud_spread_window)), 3) if cloud_spread_window else None,
            "cloud_spread_max_m": round(float(max(cloud_spread_window)), 3) if cloud_spread_window else None,
            "first": first, "last": last, "seed": seed, "cloud": cloud,
            "tf_at_clip_start": tf_before, "map": map_message}


def audit(original, clip, replay_input, map_yaml):
    meta = yaml.safe_load((Path(clip) / "metadata.yaml").read_text())[
        "rosbag2_bagfile_information"]
    start = meta["starting_time"]["nanoseconds_since_epoch"]
    end = start + meta["duration"]["nanoseconds"]
    recorded = inspect_bag(original, start, end)
    filtered = inspect_bag(replay_input)
    missing_headers = {}
    for topic in ("/scan", "/yahboom/odom", "/im10a/imu/bias_corrected_candidate"):
        missing = sorted(recorded["window_headers"].get(topic, set()) -
                         filtered["headers"].get(topic, set()))
        missing_headers[topic] = {"count": len(missing),
                                  "first_ns": missing[0] if missing else None,
                                  "last_ns": missing[-1] if missing else None}
    result = {"clip_start_ns": start, "clip_end_ns": end,
              "original_counts": recorded["counts"],
              "original_clip_window_counts": recorded["clip_window_counts"],
              "replay_input_counts": filtered["counts"],
              "missing_original_header_stamps_in_replay": missing_headers,
              "original_seed": recorded["seed"],
              "original_particle_cloud_at_clip_start": recorded["cloud"],
              "original_window_particle_spread_median_max": [recorded["cloud_spread_median_m"],
                                                               recorded["cloud_spread_max_m"]],
              "original_tf_at_clip_start": recorded["tf_at_clip_start"],
              "first_last_original": {"first": recorded["first"], "last": recorded["last"]},
              "first_last_replay_input": {"first": filtered["first"], "last": filtered["last"]},
              "replay_particle_spread_median_max": [filtered["cloud_spread_median_m"],
                                                    filtered["cloud_spread_max_m"]],
              "recorded_vs_saved_map": map_overlap(recorded["map"], map_yaml)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("clip", nargs="?")
    parser.add_argument("replay_input", nargs="?")
    parser.add_argument("map_yaml", nargs="?")
    parser.add_argument("--first-only", action="store_true",
                        help="Summarize initial AMCL particle spread of one bag")
    args = parser.parse_args()
    if args.first_only:
        bag = inspect_bag(args.original)
        result = {"first_pose": bag["first_pose"], "last_pose": bag["last_pose"],
                  "first_cloud": bag["first_cloud"],
                  "counts": bag["counts"]}
    else:
        if not all((args.clip, args.replay_input, args.map_yaml)):
            parser.error("clip, replay_input and map_yaml required unless --first-only")
        result = audit(args.original, args.clip, args.replay_input, args.map_yaml)
    print(json.dumps(result, indent=2))
