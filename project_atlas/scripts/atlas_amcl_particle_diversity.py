#!/usr/bin/env python3
"""Read-only rosbag particle-support audit; uniform weights do not prove diversity.

No ROS node, publisher, service client or actuator is created. Geometric
duplicates are counted independently of normalized-weight effective size.
"""
import argparse
import json
import math


def summarize_particles(points, weights):
    if not points or len(points) != len(weights):
        raise ValueError("nonempty, matched particles and weights required")
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("finite x/y/yaw particles required")
    total = sum(weights)
    if any(not math.isfinite(w) or w < 0 for w in weights) or not math.isfinite(total) or total <= 0:
        raise ValueError("finite nonnegative weights with positive sum required")
    normalized = [w / total for w in weights]
    # Wrap first so equivalent headings do not inflate exact support.
    wrapped = [(x, y, math.atan2(math.sin(a), math.cos(a))) for x, y, a in points]
    support = {tuple(round(v, 6) for v in p) for p in wrapped}
    return {
        "particles": len(points),
        "unique_exact": len(set(wrapped)),
        "unique_at_1e_minus_6_m_rad": len(support),
        "weight_ess": 1.0 / sum(w * w for w in normalized),
        "x_extent_m": max(p[0] for p in points) - min(p[0] for p in points),
        "y_extent_m": max(p[1] for p in points) - min(p[1] for p in points),
    }


def audit_bag(path):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from nav2_msgs.msg import ParticleCloud

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    reader.set_filter(rosbag2_py.StorageFilter(topics=["/particle_cloud"]))
    rows, start = [], None
    while reader.has_next():
        _, raw, timestamp = reader.read_next()
        message = deserialize_message(raw, ParticleCloud)
        if start is None:
            start = timestamp
        points = []
        for item in message.particles:
            p, q = item.pose.position, item.pose.orientation
            angle = math.atan2(2 * (q.w * q.z + q.x * q.y),
                               1 - 2 * (q.y * q.y + q.z * q.z))
            points.append((p.x, p.y, angle))
        row = summarize_particles(points, [p.weight for p in message.particles])
        row["offset_s"] = round((timestamp - start) / 1e9, 3)
        rows.append(row)
    return {
        "bag": path, "clouds": len(rows), "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
        "minimum_geometric_support": min((r["unique_at_1e_minus_6_m_rad"] for r in rows), default=None),
        "first_single_support": next((r for r in rows if r["unique_at_1e_minus_6_m_rad"] == 1), None),
        "limitation": "Published post-resampling clouds omit likelihood history. Duplicate support establishes impoverishment, not the original cause of a wrong pose or ground-truth accuracy.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bags", nargs="+")
    args = parser.parse_args()
    for bag in args.bags:
        print(json.dumps(audit_bag(bag), indent=2))
