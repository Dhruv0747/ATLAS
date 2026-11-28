#!/usr/bin/env python3
"""Pure geometry helpers for ATLAS camera/LiDAR semantic fusion."""

import math
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple


# Calibrated camera "forward" pose. It is the same file and keys that mission control
# (load_camera_home / center_camera_for_navigation) and semantic_advisory_check.camera_home()
# use. 2026-11-26: the fixed 2300 us constant that was here before was wrong (owner: 1801 is
# straight ahead).
CAMERA_HOME_FILE = (
    Path.home() / ".config/systemd/user/atlas-uno-r4-sensor-hub.service.d/camera-home.conf"
)
CAMERA_HOME_KEYS = ("ATLAS_CAMERA_PAN_HOME_US", "ATLAS_CAMERA_TILT_HOME_US")
PAN_TOLERANCE_US = 90
TILT_TOLERANCE_US = 180


def read_camera_home(path=None) -> Tuple[Optional[int], Optional[int]]:
    """(pan_us, tilt_us) from camera-home.conf, or None for each value that is missing."""
    values = {}
    try:
        for raw_line in Path(path or CAMERA_HOME_FILE).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            for key in CAMERA_HOME_KEYS:
                if line.startswith("Environment=" + key + "="):
                    values[key] = int(line.split("=", 2)[2])
    except (OSError, ValueError):
        return None, None
    return values.get(CAMERA_HOME_KEYS[0]), values.get(CAMERA_HOME_KEYS[1])


def camera_forward_state(pan_us, tilt_us, home) -> Tuple[bool, Optional[str]]:
    """(forward, suspend_reason). Forward is never assumed without a calibration and servo feedback."""
    home_pan, home_tilt = home
    if home_pan is None or home_tilt is None:
        return False, "SUSPENDED_CAMERA_HOME_UNKNOWN"
    if (
        pan_us is None
        or tilt_us is None
        or abs(pan_us - home_pan) > PAN_TOLERANCE_US
        or abs(tilt_us - home_tilt) > TILT_TOLERANCE_US
    ):
        return False, "SUSPENDED_CAMERA_NOT_FORWARD"
    return True, None


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
