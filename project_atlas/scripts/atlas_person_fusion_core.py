#!/usr/bin/env python3
"""Pure parsing and association helpers for ATLAS person sensor fusion."""

import math
import re


TARGET_RE = re.compile(
    r"T(?P<id>\d+):x=(?P<x>-?\d+)mm,y=(?P<y>-?\d+)mm,spd=(?P<speed>-?\d+)cm/s"
)


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def parse_radar_targets(text):
    targets = []
    for match in TARGET_RE.finditer(str(text)):
        x_m = int(match.group("x")) / 1000.0
        y_m = int(match.group("y")) / 1000.0
        if y_m <= 0:
            continue
        targets.append({
            "id": f"T{match.group('id')}",
            "x_m": x_m,
            "y_m": y_m,
            "distance_m": math.hypot(x_m, y_m),
            "bearing_rad": math.atan2(x_m, y_m),
            "speed_mps": int(match.group("speed")) / 100.0,
        })
    return targets


def camera_person(detections, pan_us, center_us=1300, pan_span_us=700,
                  pan_span_rad=math.radians(45), hfov_rad=math.radians(66)):
    width = float(detections.get("width", 0))
    height = float(detections.get("height", 0))
    people = [item for item in detections.get("detections", [])
              if item.get("label") == "person" and float(item.get("confidence", 0)) >= 0.50]
    if width <= 0 or height <= 0 or not people:
        return None
    person = max(people, key=lambda item: (item["x2"] - item["x1"]) * (item["y2"] - item["y1"]))
    center_x = 0.5 * (float(person["x1"]) + float(person["x2"]))
    optical_bearing = (0.5 - center_x / width) * hfov_rad
    servo_bearing = (float(pan_us) - center_us) / pan_span_us * pan_span_rad
    return {
        "confidence": float(person.get("confidence", 0)),
        "bearing_rad": wrap_angle(servo_bearing + optical_bearing),
        "left_bearing": wrap_angle(servo_bearing + (0.5 - float(person["x1"]) / width) * hfov_rad),
        "right_bearing": wrap_angle(servo_bearing + (0.5 - float(person["x2"]) / width) * hfov_rad),
        "height_ratio": (float(person["y2"]) - float(person["y1"])) / height,
    }


def associate_radar(person_bearing, targets, max_angle_rad=math.radians(35),
                    lidar_distance=None, max_distance_delta_m=1.0):
    candidates = []
    for target in targets:
        angle_error = abs(wrap_angle(target["bearing_rad"] - person_bearing))
        if angle_error > max_angle_rad:
            continue
        distance_error = 0.0
        if lidar_distance is not None and math.isfinite(lidar_distance):
            distance_error = abs(target["distance_m"] - lidar_distance)
            if distance_error > max_distance_delta_m:
                continue
        candidates.append((angle_error + 0.25 * distance_error, target))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None
