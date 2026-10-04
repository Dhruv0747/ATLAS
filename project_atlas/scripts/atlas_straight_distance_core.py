#!/usr/bin/env python3
"""Pure helpers for bounded straight-distance commissioning tests."""

from __future__ import annotations

import math
import statistics


def robust_corridor_range(ranges_m: list[float]) -> float:
    """Return a stable corridor range without trusting a single nearest ray."""
    valid = [value for value in ranges_m if math.isfinite(value) and value > 0.0]
    if not valid:
        return math.inf
    return float(statistics.median(valid))


def conservative_corridor_range(ranges_m: list[float]) -> float:
    """Return a lower-quartile range for a noise-resistant stop guard."""
    valid = sorted(
        value for value in ranges_m if math.isfinite(value) and value > 0.0
    )
    if not valid:
        return math.inf
    index = int(0.25 * (len(valid) - 1))
    return float(valid[index])


def corridor_clearance_progress(start_m: float, current_m: float) -> float:
    """Infer travel toward the selected front or rear LiDAR corridor."""
    if not math.isfinite(start_m) or not math.isfinite(current_m):
        return 0.0
    return max(0.0, start_m - current_m)


# Compatibility name used by recorded commissioning analysis.
forward_clearance_progress = corridor_clearance_progress


def conservative_progress(lidar_odom_m: float, clearance_progress_m: float) -> float:
    """Stop on whichever independent LiDAR measurement advances farther."""
    return max(0.0, lidar_odom_m, clearance_progress_m)


class IncrementalPlanarDistance:
    """Accumulate accepted planar pose increments without trusting heading."""

    def __init__(self, max_step_m: float = 0.20) -> None:
        self.max_step_m = max_step_m
        self.previous: tuple[float, float] | None = None
        self.distance_m = 0.0
        self.rejected_updates = 0

    def update(self, x_m: float, y_m: float) -> bool:
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            self.rejected_updates += 1
            return False
        current = (x_m, y_m)
        if self.previous is None:
            self.previous = current
            return True
        step_m = math.hypot(
            current[0] - self.previous[0], current[1] - self.previous[1]
        )
        if step_m > self.max_step_m:
            self.rejected_updates += 1
            return False
        self.previous = current
        self.distance_m += step_m
        return True
