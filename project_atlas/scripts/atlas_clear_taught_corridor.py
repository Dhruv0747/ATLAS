#!/usr/bin/env python3
"""Clear only ATLAS's physically traversed footprint from a taught map."""

import argparse
import json
import math
from pathlib import Path

from PIL import Image
import yaml


def angle_delta(first: float, second: float) -> float:
    return math.atan2(math.sin(second - first), math.cos(second - first))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("map_yaml")
    parser.add_argument("route_json")
    parser.add_argument("output_prefix")
    parser.add_argument("--half-length", type=float, default=0.25)
    parser.add_argument("--half-width", type=float, default=0.18)
    parser.add_argument("--margin", type=float, default=0.02)
    args = parser.parse_args()

    yaml_path = Path(args.map_yaml)
    metadata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"])
    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path
    image = Image.open(image_path).convert("L")
    pixels = image.load()
    route = json.loads(Path(args.route_json).read_text(encoding="utf-8"))["points"]
    resolution = float(metadata["resolution"])
    origin_x, origin_y = map(float, metadata["origin"][:2])
    half_length = args.half_length + args.margin
    half_width = args.half_width + args.margin
    radius_cells = int(math.ceil(math.hypot(half_length, half_width) / resolution))
    cleared = set()

    interpolated = []
    for first, second in zip(route, route[1:]):
        distance = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
        steps = max(1, int(math.ceil(distance / (resolution * 0.4))))
        yaw_change = angle_delta(first["yaw"], second["yaw"])
        for index in range(steps):
            ratio = index / steps
            interpolated.append(
                (
                    first["x"] + ratio * (second["x"] - first["x"]),
                    first["y"] + ratio * (second["y"] - first["y"]),
                    first["yaw"] + ratio * yaw_change,
                )
            )
    final = route[-1]
    interpolated.append((final["x"], final["y"], final["yaw"]))

    for x, y, yaw in interpolated:
        center_col = int((x - origin_x) / resolution)
        center_map_row = int((y - origin_y) / resolution)
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        for map_row in range(center_map_row - radius_cells, center_map_row + radius_cells + 1):
            image_row = image.height - 1 - map_row
            if not 0 <= image_row < image.height:
                continue
            for col in range(center_col - radius_cells, center_col + radius_cells + 1):
                if not 0 <= col < image.width:
                    continue
                world_x = origin_x + (col + 0.5) * resolution
                world_y = origin_y + (map_row + 0.5) * resolution
                dx = world_x - x
                dy = world_y - y
                local_x = cos_yaw * dx + sin_yaw * dy
                local_y = -sin_yaw * dx + cos_yaw * dy
                if abs(local_x) <= half_length and abs(local_y) <= half_width:
                    pixels[col, image_row] = 254
                    cleared.add((col, image_row))

    prefix = Path(args.output_prefix)
    output_pgm = prefix.with_suffix(".pgm")
    output_yaml = prefix.with_suffix(".yaml")
    image.save(output_pgm)
    output_metadata = dict(metadata)
    output_metadata["image"] = output_pgm.name
    output_yaml.write_text(yaml.safe_dump(output_metadata, sort_keys=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "route_points": len(route),
                "interpolated_poses": len(interpolated),
                "cleared_cells": len(cleared),
                "output_yaml": str(output_yaml),
                "output_pgm": str(output_pgm),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
