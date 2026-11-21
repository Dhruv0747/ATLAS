"""Diagnostic-only AMCL quality for the map display; never controls motion."""

import math


def summarize_amcl_pose(x, y, yaw, covariance, previous=None):
    """Return display metrics from one AMCL pose and an optional prior pose.

    The uncertainty limits mirror the currently configured mux defaults, but
    this module does not grant or revoke navigation authority. The map page
    must not call a fresh yet uncertain estimate a precise live position.
    """
    values = (x, y, yaw, covariance[0], covariance[7], covariance[35])
    valid = all(math.isfinite(value) for value in values) and all(
        variance >= 0.0 for variance in (covariance[0], covariance[7], covariance[35])
    )
    if not valid:
        return {
            "xy_std_m": None,
            "yaw_std_deg": None,
            "last_step_m": None,
            "last_step_deg": None,
            "uncertain": True,
            "large_step": False,
            "source": "Invalid AMCL pose/covariance; diagnostic only",
        }
    xy_std = math.sqrt(covariance[0] + covariance[7])
    yaw_std_deg = math.degrees(math.sqrt(covariance[35]))
    jump_m = 0.0
    jump_deg = 0.0
    if previous is not None:
        if not all(math.isfinite(value) for value in previous):
            previous = None
    if previous is not None:
        jump_m = math.hypot(x - previous[0], y - previous[1])
        delta = yaw - previous[2]
        jump_deg = abs(math.degrees(math.atan2(math.sin(delta), math.cos(delta))))
    return {
        "xy_std_m": round(xy_std, 3),
        "yaw_std_deg": round(yaw_std_deg, 1),
        "last_step_m": round(jump_m, 3),
        "last_step_deg": round(jump_deg, 1),
        "uncertain": xy_std > 0.25 or yaw_std_deg > 20.0,
        "large_step": previous is not None and (jump_m > 0.5 or jump_deg > 45.0),
        "source": "AMCL covariance; diagnostic only",
    }
