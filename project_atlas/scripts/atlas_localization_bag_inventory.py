#!/usr/bin/env python3
"""Read-only inventory of recorded localization inputs and AMCL outputs."""

import argparse
import json
from pathlib import Path

import yaml

TOPICS = (
    "/scan", "/yahboom/odom", "/im10a/imu/bias_corrected_candidate",
    "/odom", "/amcl_pose", "/tf", "/atlas/encoder_health",
    "/steering/front_angle_deg", "/steering/rear_angle_deg", "/cmd_vel_joy",
)


def inventory(root):
    result = []
    for path in sorted(Path(root).rglob("metadata.yaml")):
        if "diagnostics" in path.parts:
            continue
        info = yaml.safe_load(path.read_text())["rosbag2_bagfile_information"]
        counts = {
            item["topic_metadata"]["name"]: item["message_count"]
            for item in info["topics_with_message_count"]
        }
        if not counts.get("/scan") or not counts.get("/yahboom/odom"):
            continue
        result.append({
            "bag": str(path.parent),
            "duration_s": round(info["duration"]["nanoseconds"] / 1e9, 2),
            "counts": {name: counts.get(name, 0) for name in TOPICS},
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    print(json.dumps(inventory(args.root), indent=2))


if __name__ == "__main__":
    main()
