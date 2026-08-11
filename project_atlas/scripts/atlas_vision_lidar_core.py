#!/usr/bin/env python3
"""Pure geometry helpers for ATLAS camera/LiDAR semantic fusion."""

import math
from typing import Iterable, Optional, Sequence, Tuple


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def pixel_to_bearing(pixel_x: float, image_width: int, horizontal_fov_rad: float) -> float:
    """Convert image x to base-frame bearing (left positive, right negative)."""
    if image_width <= 0:
        raise ValueError("image_width must be positive")
    return (0.5 - float(pixel_x) / float(image_width)) * horizontal_fov_rad


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def associate_detection(
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    range_min: float,
    range_max: float,
    left_bearing: float,
    right_bearing: float,
    laser_yaw_rad: float = math.pi,
    laser_x_m: float = -0.05,
    max_distance_m: float = 3.0,
) -> Optional[Tuple[float, float, float]]:
    """Return a robust LiDAR-confirmed point in base_link for a camera sector."""
    low = min(left_bearing, right_bearing)
    high = max(left_bearing, right_bearing)
    candidates = []
    for index, distance in enumerate(ranges):
        if not math.isfinite(distance):
            continue
        if distance < range_min or distance > min(range_max, max_distance_m):
            continue
        laser_angle = angle_min + index * angle_increment
        base_bearing = wrap_angle(laser_angle + laser_yaw_rad)
        if low <= base_bearing <= high:
            candidates.append((float(distance), laser_angle))
    if not candidates:
        return None
    # The 20th percentile rejects a single near speck while still selecting
    # the foreground object rather than the wall visible around its box.
    target_range = percentile([item[0] for item in candidates], 0.20)
    distance, laser_angle = min(candidates, key=lambda item: abs(item[0] - target_range))
    base_angle = laser_angle + laser_yaw_rad
    x = laser_x_m + distance * math.cos(base_angle)
    y = distance * math.sin(base_angle)
    return x, y, math.hypot(x, y)
