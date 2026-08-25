#!/usr/bin/env python3
"""Clear only ATLAS's verified body envelope from a saved occupancy map."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image
import yaml


HALF_LENGTH_M = 0.25
HALF_WIDTH_M = 0.18
CLEAR_MARGIN_M = 0.01


def sanitize_saved_map(
    yaml_path: Path, image_path: Path, pose: dict,
    margin_m: float = CLEAR_MARGIN_M,
) -> int:
    """Mark cells inside the physical rover footprint free; return count."""
    metadata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    resolution = float(metadata["resolution"])
    origin_x, origin_y = map(float, metadata["origin"][:2])
    if resolution <= 0.0:
        raise ValueError("map resolution must be positive")

    image = Image.open(image_path).convert("L")
    pixels = image.load()
    tx, ty = float(pose["x"]), float(pose["y"])
    qz, qw = float(pose.get("qz", 0.0)), float(pose.get("qw", 1.0))
    yaw = 2.0 * math.atan2(qz, qw)
    cosine, sine = math.cos(yaw), math.sin(yaw)
    half_length = HALF_LENGTH_M + float(margin_m)
    half_width = HALF_WIDTH_M + float(margin_m)
    radius_cells = int(math.ceil(math.hypot(half_length, half_width) / resolution))
    center_col = int(math.floor((tx - origin_x) / resolution))
    center_map_row = int(math.floor((ty - origin_y) / resolution))
    center_image_row = image.height - 1 - center_map_row
    cleared = 0

    for image_row in range(
        center_image_row - radius_cells, center_image_row + radius_cells + 1
    ):
        if image_row < 0 or image_row >= image.height:
            continue
        map_row = image.height - 1 - image_row
        for col in range(center_col - radius_cells, center_col + radius_cells + 1):
            if col < 0 or col >= image.width:
                continue
            world_x = origin_x + (col + 0.5) * resolution
            world_y = origin_y + (map_row + 0.5) * resolution
            dx, dy = world_x - tx, world_y - ty
            local_x = cosine * dx + sine * dy
            local_y = -sine * dx + cosine * dy
            if abs(local_x) <= half_length and abs(local_y) <= half_width:
                if pixels[col, image_row] != 254:
                    pixels[col, image_row] = 254
                    cleared += 1

    if cleared:
        image.save(image_path, format="PPM")
    return cleared


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--pose-file", required=True, type=Path)
    parser.add_argument("--margin", type=float, default=CLEAR_MARGIN_M)
    args = parser.parse_args()
    pose = json.loads(args.pose_file.read_text(encoding="utf-8"))
    cleared = sanitize_saved_map(args.map, args.image, pose, args.margin)
    print(json.dumps({"ok": True, "cleared_cells": cleared}))


if __name__ == "__main__":
    main()
