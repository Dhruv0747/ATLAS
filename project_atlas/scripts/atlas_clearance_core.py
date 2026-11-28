"""Pure helpers for explicit LiDAR/ultrasonic clearance reporting."""

import math


def clearance_channel(lidar_m: float, ultrasonic_m: float) -> dict:
    """Return raw channels and the conservative fused safety guard."""
    lidar = float(lidar_m) if math.isfinite(lidar_m) and lidar_m >= 0.0 else None
    ultrasonic = (
        float(ultrasonic_m)
        if math.isfinite(ultrasonic_m) and ultrasonic_m >= 0.0
        else None
    )
    available = [("LIDAR", lidar), ("ULTRASONIC", ultrasonic)]
    available = [(name, value) for name, value in available if value is not None]
    if not available:
        return {"lidar_m": None, "ultrasonic_m": None, "fused_m": None,
                "fused_source": "NONE"}
    source, fused = min(available, key=lambda item: item[1])
    return {
        "lidar_m": None if lidar is None else round(lidar, 3),
        "ultrasonic_m": None if ultrasonic is None else round(ultrasonic, 3),
        "fused_m": round(fused, 3),
        "fused_source": source,
    }
