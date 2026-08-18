#!/usr/bin/env python3
"""Inspect saved-map occupancy around a world-frame pose without moving ATLAS."""

import argparse
import json
from pathlib import Path

from PIL import Image
import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("x", type=float)
    parser.add_argument("y", type=float)
    parser.add_argument(
        "--map", default="/home/jetson/project_atlas/maps/atlas_latest.yaml"
    )
    parser.add_argument("--radius-cells", type=int, default=6)
    args = parser.parse_args()

    yaml_path = Path(args.map)
    metadata = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"])
    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path
    image = Image.open(image_path).convert("L")
    resolution = float(metadata["resolution"])
    origin_x, origin_y = map(float, metadata["origin"][:2])
    column = int((args.x - origin_x) / resolution)
    map_row = int((args.y - origin_y) / resolution)
    image_row = image.height - 1 - map_row

    radius = max(0, args.radius_cells)
    rows = []
    for row in range(image_row - radius, image_row + radius + 1):
        values = []
        for col in range(column - radius, column + radius + 1):
            values.append(image.getpixel((col, row)))
        rows.append(values)
    print(
        json.dumps(
            {
                "world": {"x": args.x, "y": args.y},
                "image_size": [image.width, image.height],
                "pixel": {"column": column, "row": image_row},
                "center_value": image.getpixel((column, image_row)),
                "window_values": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
