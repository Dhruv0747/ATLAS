#!/usr/bin/env python3
"""AMCL-only offline replay with original scan, EKF odom TF and timestamps.

No motor/control/steering topics are written or played. This is a diagnostic
experiment, not an AMCL particle-state checkpoint or a production change.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import rosbag2_py
from rclpy.serialization import deserialize_message, serialize_message
from tf2_msgs.msg import TFMessage
import yaml

from atlas_amcl_offline_replay import count_amcl, localization_params, recorded_seed
from atlas_fusion_replay import stop


ALLOWED = {"/scan", "/tf", "/tf_static", "/odom"}


def replay_localization_params(raw, map_yaml, seed, stationary_updates=False):
    data = localization_params(raw, map_yaml, seed)
    if stationary_updates:
        # Diagnostic stress case only. This is not evidence that the recorded
        # live AMCL used zero thresholds, and must never be deployed from here.
        params = data["amcl"]["ros__parameters"]
        params["update_min_d"] = 0.0
        params["update_min_a"] = 0.0
    return data


def keep_tf(msg):
    """Leave original odom/base and static geometry; AMCL owns map->odom."""
    msg.transforms = [tf for tf in msg.transforms
                      if (tf.header.frame_id.strip("/"), tf.child_frame_id.strip("/"))
                      != ("map", "odom")]
    return msg


def prepare(original, destination, start_ns, end_ns):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(original), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(destination), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    for topic in reader.get_all_topics_and_types():
        if topic.name in ALLOWED:
            writer.create_topic(topic)
    counts = {}
    static = []
    while reader.has_next():
        topic, raw, receipt = reader.read_next()
        if topic not in ALLOWED:
            continue
        if topic == "/tf_static" and receipt < start_ns:
            static.append(raw)
            continue
        if receipt < start_ns or receipt > end_ns:
            continue
        if topic == "/tf":
            msg = keep_tf(deserialize_message(raw, TFMessage))
            if not msg.transforms:
                continue
            raw = serialize_message(msg)
        writer.write(topic, raw, receipt)
        counts[topic] = counts.get(topic, 0) + 1
    # Original static transforms were published long before the clip. Put the
    # same payloads immediately before the first selected dynamic message.
    for raw in static:
        writer.write("/tf_static", raw, start_ns - 1)
        counts["/tf_static"] = counts.get("/tf_static", 0) + 1
    del writer
    if not all(counts.get(t) for t in ALLOWED):
        raise RuntimeError("Missing recorded AMCL replay input: " + str(counts))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("clip")
    parser.add_argument("nav_config")
    parser.add_argument("map_yaml")
    parser.add_argument("output")
    parser.add_argument("--stationary-updates", action="store_true",
                        help="Replay-only zero AMCL motion thresholds for causal diagnosis")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=False, exist_ok=False)
    meta = yaml.safe_load((Path(args.clip) / "metadata.yaml").read_text())[
        "rosbag2_bagfile_information"]
    start_ns = meta["starting_time"]["nanoseconds_since_epoch"]
    end_ns = start_ns + meta["duration"]["nanoseconds"]
    counts = prepare(args.original, out / "input", start_ns, end_ns)
    seed = recorded_seed(args.original, start_ns)
    nav_path = out / "localization.yaml"
    nav_path.write_text(yaml.safe_dump(replay_localization_params(
        Path(args.nav_config).read_text(), args.map_yaml, seed,
        args.stationary_updates)))
    (out / "manifest.json").write_text(json.dumps({
        "original": args.original, "input_counts": counts, "seed": seed,
        "recorded_odom_tf": True, "original_particle_state_restored": False,
        "stationary_updates_replay_only": args.stationary_updates,
        "actuator_topics_allowed": sorted(ALLOWED & {"/cmd_vel", "/cmd_vel_joy"}),
    }, indent=2))
    env = dict(os.environ, ROS_DOMAIN_ID="179", ROS_LOCALHOST_ONLY="1",
               FASTDDS_BUILTIN_TRANSPORTS="UDPv4", PYTHONUNBUFFERED="1")
    processes, logs = [], []

    def launch(name, command):
        log = (out / (name + ".log")).open("w")
        logs.append(log)
        process = subprocess.Popen(command, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    try:
        amcl = launch("amcl", ["ros2", "launch", "nav2_bringup",
                 "localization_launch.py", "map:=" + args.map_yaml,
                 "use_sim_time:=true", "params_file:=" + str(nav_path),
                 "autostart:=true"])
        recorder = launch("record", ["ros2", "bag", "record", "-o",
                          str(out / "result"), "/amcl_pose", "/particle_cloud",
                          "/scan", "/map", "/tf", "/odom"])
        time.sleep(8)
        if amcl.poll() is not None or recorder.poll() is not None:
            raise RuntimeError("Offline AMCL or recorder exited before playback")
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
    count = count_amcl(out / "result")
    print(json.dumps({"amcl_poses": count, "input_counts": counts}))
    if count < 20:
        raise RuntimeError("Too few AMCL poses; inspect offline logs")


if __name__ == "__main__":
    main()
