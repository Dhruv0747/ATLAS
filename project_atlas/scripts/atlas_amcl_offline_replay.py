#!/usr/bin/env python3
"""Isolated, command-free EKF + saved-map AMCL replay; never launches Nav2 control.

This is a diagnostic experiment, not a production configuration change.
The source clip must contain wheel odometry, corrected IMU, scan and static TF.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import rosbag2_py
from rclpy.serialization import deserialize_message
from geometry_msgs.msg import PoseWithCovarianceStamped
import yaml

from atlas_fusion_replay import ALLOWED, configurations, prepare, stop


def recorded_seed(original, clip_start_ns):
    """Use the same recorded AMCL hypothesis at clip start in both variants."""
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(original), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    before = after = None
    while reader.has_next():
        topic, raw, stamp = reader.read_next()
        if topic != "/amcl_pose":
            continue
        item = (stamp, deserialize_message(raw, PoseWithCovarianceStamped))
        if stamp <= clip_start_ns:
            before = item
        elif after is None:
            after = item
            break
    selected = before or after
    if selected is None:
        raise ValueError("Original bag has no AMCL seed")
    stamp, message = selected
    q = message.pose.pose.orientation
    yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                     1 - 2 * (q.y * q.y + q.z * q.z))
    pose = message.pose.pose.position
    return {"x": float(pose.x), "y": float(pose.y), "z": 0.0, "yaw": yaw,
            "seed_record_ns": stamp, "clip_start_ns": clip_start_ns,
            "seed_age_s": round((clip_start_ns - stamp) / 1e9, 3)}


def localization_params(raw, map_file, seed):
    data = yaml.safe_load(raw)
    amcl = data["amcl"]["ros__parameters"]
    amcl["use_sim_time"] = True
    amcl["set_initial_pose"] = True
    amcl["initial_pose"] = {key: seed[key] for key in ("x", "y", "z", "yaw")}
    data["map_server"]["ros__parameters"]["use_sim_time"] = True
    data["map_server"]["ros__parameters"]["yaml_filename"] = str(map_file)
    return data


def count_amcl(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    count = 0
    while reader.has_next():
        topic, _, _ = reader.read_next()
        count += topic == "/amcl_pose"
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip")
    parser.add_argument("original")
    parser.add_argument("ekf_config")
    parser.add_argument("nav_config")
    parser.add_argument("map_yaml")
    parser.add_argument("output")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=False, exist_ok=False)
    ekf_raw = Path(args.ekf_config).read_text()
    nav_raw = Path(args.nav_config).read_text()
    meta = yaml.safe_load((Path(args.clip) / "metadata.yaml").read_text())
    clip_start_ns = meta["rosbag2_bagfile_information"]["starting_time"]["nanoseconds_since_epoch"]
    seed = recorded_seed(args.original, clip_start_ns)
    filtered = prepare(args.clip, out / "input")
    (out / "manifest.json").write_text(json.dumps({
        "clip": args.clip, "original": args.original, "map": args.map_yaml,
        "seed": seed, "input": filtered, "domain": 179,
        "ekf_sha256": hashlib.sha256(ekf_raw.encode()).hexdigest(),
        "nav_sha256": hashlib.sha256(nav_raw.encode()).hexdigest(),
        "only_variant_change": "wheel odom X/Y pose fusion disabled",
        "actuator_topics_allowed": sorted(ALLOWED & {"/cmd_vel", "/cmd_vel_joy", "/cmd_vel_nav"}),
    }, indent=2))
    nav_path = out / "localization.yaml"
    nav_path.write_text(yaml.safe_dump(localization_params(nav_raw, args.map_yaml, seed)))
    env = dict(os.environ, ROS_DOMAIN_ID="179", ROS_LOCALHOST_ONLY="1",
               FASTDDS_BUILTIN_TRANSPORTS="UDPv4", PYTHONUNBUFFERED="1")
    for variant, config in configurations(ekf_raw).items():
        config_path = out / (variant + ".yaml")
        config_path.write_text(yaml.safe_dump(config))
        processes, logs = [], []

        def launch(name, command):
            log = (out / (variant + "_" + name + ".log")).open("w")
            logs.append(log)
            process = subprocess.Popen(command, env=env, stdout=log,
                                       stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        print("START", variant, flush=True)
        try:
            ekf = launch("ekf", ["/opt/ros/humble/lib/robot_localization/ekf_node",
                                  "--ros-args", "-r", "__node:=atlas_ekf",
                                  "--params-file", str(config_path),
                                  "-r", "odometry/filtered:=/odom"])
            localization = launch("amcl", [
                "ros2", "launch", "nav2_bringup", "localization_launch.py",
                "map:=" + args.map_yaml, "use_sim_time:=true",
                "params_file:=" + str(nav_path), "autostart:=true",
            ])
            recorder = launch("record", ["ros2", "bag", "record", "-o",
                                         str(out / variant), "/amcl_pose", "/odom",
                                         "/tf", "/scan", "/map", "/diagnostics"])
            time.sleep(8)
            if any(p.poll() is not None for p in (ekf, localization, recorder)):
                raise RuntimeError("Offline process exited before playback")
            player = launch("play", ["ros2", "bag", "play", str(out / "input"),
                                     "--clock", "50", "--rate", "1.0", "--topics",
                                     *sorted(ALLOWED)])
            if player.wait(timeout=600) != 0:
                raise RuntimeError("Offline playback failed")
            time.sleep(3)
        finally:
            for process in reversed(processes):
                stop(process)
            for log in logs:
                log.close()
        count = count_amcl(out / variant)
        print("COMPLETE", variant, "AMCL", count, flush=True)
        if count < 20:
            raise RuntimeError("Too few AMCL poses for comparison; inspect offline logs")
    print("ALL COMPLETE", flush=True)


if __name__ == "__main__":
    main()
