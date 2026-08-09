#!/usr/bin/env python3
"""Small frame-angle helpers shared by ATLAS LiDAR safety consumers."""


def wrap_degrees(angle_deg: float) -> float:
    """Return an angle in the half-open range [-180, 180)."""
    return (float(angle_deg) + 180.0) % 360.0 - 180.0


def sensor_ray_in_base_degrees(sensor_angle_deg: float, sensor_yaw_deg: float) -> float:
    """Rotate a scan ray from the sensor frame into the rover base frame."""
    return wrap_degrees(float(sensor_angle_deg) + float(sensor_yaw_deg))


def ray_in_base_sector(
    sensor_angle_deg: float,
    sector_center_deg: float,
    half_width_deg: float,
    sensor_yaw_deg: float,
) -> bool:
    base_angle = sensor_ray_in_base_degrees(sensor_angle_deg, sensor_yaw_deg)
    return abs(wrap_degrees(base_angle - float(sector_center_deg))) <= float(
        half_width_deg
    )
