#!/usr/bin/env python3
"""Read-only, same-scan AMCL hypothesis/particle audit of a recorded bag.

Never starts ROS nodes, publishers, Nav2, or actuators. Endpoint/map agreement
is diagnostic evidence, not an independent ground-truth pose measurement.
"""

import argparse
import bisect
import json
import math

import numpy as np
from scipy.spatial import cKDTree
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


TOPICS = {"/amcl_pose", "/particle_cloud", "/scan", "/map", "/odom", "/tf", "/tf_static"}


def yaw(quaternion):
    q = quaternion
    return math.atan2(2 * (q.w * q.z + q.x * q.y),
                      1 - 2 * (q.y * q.y + q.z * q.z))


def pose(item):
    return np.array((item.position.x, item.position.y, yaw(item.orientation)), dtype=float)


def transform_pose(transform):
    p = transform.translation
    return np.array((p.x, p.y, yaw(transform.rotation)), dtype=float)


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array((a[0] + c * b[0] - s * b[1],
                     a[1] + s * b[0] + c * b[1], a[2] + b[2]))


def wrap(value):
    return math.atan2(math.sin(value), math.cos(value))


def cloud_support(cloud, weights, first, second, radius=.5, yaw_radius_deg=35):
    """Weighted support near two pose hypotheses; regions may overlap."""
    if len(cloud) == 0:
        return None
    weights = np.asarray(weights, dtype=float)
    if len(weights) != len(cloud) or not np.all(np.isfinite(weights)) or np.any(weights < 0) or weights.sum() <= 0:
        return None
    weights = weights / weights.sum()
    result = {"particles": len(cloud),
              "effective_particle_count": round(float(1 / np.sum(weights ** 2)), 1)}
    for name, point in (("before", first), ("after", second)):
        distance = np.linalg.norm(cloud[:, :2] - point[:2], axis=1)
        heading = np.abs(np.arctan2(np.sin(cloud[:, 2] - point[2]),
                                    np.cos(cloud[:, 2] - point[2])))
        result[name + "_xy_weight"] = round(float(np.sum(weights[distance <= radius])), 3)
        result[name + "_xy_heading_weight"] = round(float(np.sum(weights[
            (distance <= radius) & (heading <= math.radians(yaw_radius_deg))])), 3)
    center = np.average(cloud[:, :2], axis=0, weights=weights)
    result["xy_std_m"] = round(float(math.sqrt(np.average(
        np.sum((cloud[:, :2] - center) ** 2, axis=1), weights=weights))), 3)
    return result


def map_model(message):
    info = message.info
    grid = np.asarray(message.data, dtype=np.int16).reshape(info.height, info.width)
    ys, xs = np.nonzero(grid >= 65)
    origin = pose(info.origin)
    local = np.column_stack(((xs + .5) * info.resolution,
                             (ys + .5) * info.resolution))
    c, s = math.cos(origin[2]), math.sin(origin[2])
    occupied = local @ np.array(((c, s), (-s, c))) + origin[:2]
    if not len(occupied):
        raise ValueError("map contains no occupied cells")
    return grid, info.resolution, origin, cKDTree(occupied)


def scan_points(scan):
    ranges = np.asarray(scan.ranges, dtype=float)
    angles = scan.angle_min + np.arange(len(ranges)) * scan.angle_increment
    valid = np.isfinite(ranges) & (ranges >= max(.3, scan.range_min)) & (
        ranges <= min(8., scan.range_max))
    return np.column_stack((ranges[valid] * np.cos(angles[valid]),
                            ranges[valid] * np.sin(angles[valid])))


def score_scan(points, robot_pose, laser_in_base, model, check_rays=True):
    grid, resolution, origin, tree = model
    laser_pose = compose(robot_pose, laser_in_base)
    c, s = math.cos(laser_pose[2]), math.sin(laser_pose[2])
    world = points @ np.array(((c, s), (-s, c))) + laser_pose[:2]
    distances, _ = tree.query(world)
    local = world - origin[:2]
    c, s = math.cos(origin[2]), math.sin(origin[2])
    local = local @ np.array(((c, -s), (s, c)))
    cells = np.floor(local / resolution).astype(int)
    inside = ((cells[:, 0] >= 0) & (cells[:, 0] < grid.shape[1]) &
              (cells[:, 1] >= 0) & (cells[:, 1] < grid.shape[0]))
    known = np.zeros(len(world), dtype=bool)
    known[inside] = grid[cells[inside, 1], cells[inside, 0]] >= 0
    premature, unknown_ray = [], []
    if check_rays:
        endpoint_guard = max(.2, .6 * resolution)
        for endpoint in world:
            ray = endpoint - laser_pose[:2]
            length = float(np.linalg.norm(ray))
            if length <= endpoint_guard:
                continue
            fractions = np.linspace(0, max(0, 1 - endpoint_guard / length),
                                    max(2, int((length - endpoint_guard) / max(resolution, .05))))
            sample = laser_pose[:2] + fractions[:, None] * ray
            relative = sample - origin[:2]
            local_sample = relative @ np.array(((c, -s), (s, c)))
            cell = np.floor(local_sample / resolution).astype(int)
            valid = ((cell[:, 0] >= 0) & (cell[:, 0] < grid.shape[1]) &
                     (cell[:, 1] >= 0) & (cell[:, 1] < grid.shape[0]))
            values = np.full(len(cell), -1, dtype=np.int16)
            values[valid] = grid[cell[valid, 1], cell[valid, 0]]
            premature.append(np.any(values >= 65))
            unknown_ray.append(np.any(values < 0))
    return {"endpoints": len(points),
            "within_15cm_wall_fraction": round(float(np.mean(distances <= .15)), 3),
            "median_wall_distance_m": round(float(np.median(distances)), 3),
            "known_endpoint_fraction": round(float(np.mean(known)), 3),
            "premature_mapped_obstacle_fraction": round(float(np.mean(premature)), 3)
            if premature else None,
            "unknown_ray_fraction": round(float(np.mean(unknown_ray)), 3)
            if unknown_ray else None}


def nearest_at_or_before(series, at, max_age):
    if not series:
        return None
    index = bisect.bisect_right([item[0] for item in series], at) - 1
    return series[index] if index >= 0 and at - series[index][0] <= max_age else None


def read_bag(path, with_clouds=True):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    types = {item.name: get_message(item.type)
             for item in reader.get_all_topics_and_types() if item.name in TOPICS}
    poses, clouds, scans, odom, transforms, map_message, static = [], [], [], [], [], None, {}
    while reader.has_next():
        topic, raw, receipt_ns = reader.read_next()
        if topic not in types or (topic == "/particle_cloud" and not with_clouds):
            continue
        msg = deserialize_message(raw, types[topic])
        t = receipt_ns * 1e-9
        if topic == "/amcl_pose":
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            poses.append((t, pose(msg.pose.pose), msg.pose.covariance, stamp))
        elif topic == "/particle_cloud":
            clouds.append((t, np.asarray([pose(p.pose) for p in msg.particles]).reshape(-1, 3),
                           np.asarray([p.weight for p in msg.particles])))
        elif topic == "/scan":
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            scans.append((stamp, t, msg))
        elif topic == "/odom":
            odom.append((t, pose(msg.pose.pose)))
        elif topic == "/map":
            map_message = msg
        elif topic in ("/tf", "/tf_static"):
            for tf in msg.transforms:
                key = (tf.header.frame_id.strip("/"), tf.child_frame_id.strip("/"))
                if topic == "/tf_static":
                    static[key] = transform_pose(tf.transform)
                elif key == ("map", "odom"):
                    stamp = tf.header.stamp.sec + tf.header.stamp.nanosec * 1e-9
                    transforms.append((t, transform_pose(tf.transform), stamp))
    return poses, clouds, scans, odom, transforms, map_message, static


def analyze(path):
    poses, clouds, scans, odom, transforms, map_message, static = read_bag(path)
    if map_message is None or ("base_footprint", "laser_frame") not in static:
        raise ValueError("recorded map or laser extrinsics missing")
    laser = compose(static.get(("base_link", "base_footprint"), np.zeros(3)),
                    static[("base_footprint", "laser_frame")])
    model = map_model(map_message)
    clouds.sort(key=lambda item: item[0])
    scans.sort(key=lambda item: item[1])
    scan_by_receipt = [(item[1], item) for item in scans]
    odom.sort(key=lambda item: item[0])
    transforms.sort(key=lambda item: item[0])
    events = []
    for previous, current in zip(poses, poses[1:]):
        start, end = previous[0], current[0]
        step = float(np.linalg.norm(current[1][:2] - previous[1][:2]))
        if not 0 < end - start <= 2 or step <= .5:
            continue
        # Use a scan that had actually arrived by the AMCL event. The laser
        # header denotes acquisition start and can predate a later receipt.
        selected_scan_item = nearest_at_or_before(scan_by_receipt, end, .5)
        selected_scan = selected_scan_item[1] if selected_scan_item else None
        before_cloud = nearest_at_or_before(clouds, start, 1.)
        after_cloud = nearest_at_or_before(clouds, end, 1.)
        before_odom = nearest_at_or_before(odom, start, .2)
        after_odom = nearest_at_or_before(odom, end, .2)
        before_tf = nearest_at_or_before(transforms, start, 1.)
        after_tf = nearest_at_or_before(transforms, end, 1.)
        result = {"record_time_s": end, "amcl_step_m": round(step, 3),
                  "amcl_heading_step_deg": round(math.degrees(wrap(current[1][2] - previous[1][2])), 2),
                  "amcl_before": previous[1].round(3).tolist(),
                  "amcl_after": current[1].round(3).tolist(),
                  "amcl_xy_std_before_after_m": [round(math.sqrt(max(0, item[2][0] + item[2][7])), 3)
                                                  for item in (previous, current)],
                  "particles_before": cloud_support(before_cloud[1], before_cloud[2], previous[1], current[1]) if before_cloud else None,
                  "particles_after": cloud_support(after_cloud[1], after_cloud[2], previous[1], current[1]) if after_cloud else None,
                  "particle_cloud_age_before_after_s": [round(start - before_cloud[0], 3) if before_cloud else None,
                                                        round(end - after_cloud[0], 3) if after_cloud else None],
                  "odom_xy_step_m": round(float(np.linalg.norm(after_odom[1][:2] - before_odom[1][:2])), 4)
                  if before_odom and after_odom else None,
                  "tf_same_odom_pose_step_m": round(float(np.linalg.norm(
                      compose(after_tf[1], after_odom[1])[:2] -
                      compose(before_tf[1], after_odom[1])[:2])), 3)
                  if before_tf and after_tf and after_odom else None,
                  "tf_receipt_age_before_after_s": [round(start - before_tf[0], 3) if before_tf else None,
                                                    round(end - after_tf[0], 3) if after_tf else None],
                  "tf_header_age_before_after_s": [round(start - before_tf[2], 3) if before_tf else None,
                                                   round(end - after_tf[2], 3) if after_tf else None]}
        if selected_scan:
            stamp, receipt, msg = selected_scan
            points = scan_points(msg)
            result["scan_age_s"] = round(end - stamp, 3)
            result["scan_receipt_age_s"] = round(end - receipt, 3)
            result["scan_frame"] = msg.header.frame_id
            if len(points):
                result["same_scan_map_fit"] = {
                    "before": score_scan(points, previous[1], laser, model),
                    "after": score_scan(points, current[1], laser, model)}
        events.append(result)
    return {"bag": path, "particle_cloud_messages": len(clouds),
            "map_resolution_m": model[1], "laser_in_base": laser.round(4).tolist(),
            "events": events,
            "limitations": "Particle weights are normalized per recorded cloud; nearby-weight regions can overlap and are not a unique-cluster decomposition. Diagnostic ray checks sample the frozen map and are not AMCL's internal likelihood, and ignore dynamic objects and scan deskew. AMCL and TF receipt timing is not a complete internal filter trace."}


def replay_summary(path, samples=31, source_bag=None):
    """Compare a bounded set of same-header-time scan/AMCL pairs in replay."""
    poses, _, scans, _, _, map_message, static = read_bag(path, with_clouds=False)
    if not poses or not scans or map_message is None:
        raise ValueError("AMCL, scan, or recorded map missing")
    if ("base_footprint", "laser_frame") not in static and source_bag:
        static = read_bag(source_bag, with_clouds=False)[-1]
    if ("base_footprint", "laser_frame") not in static:
        raise ValueError("recorded laser extrinsics missing")
    laser = compose(static.get(("base_link", "base_footprint"), np.zeros(3)),
                    static[("base_footprint", "laser_frame")])
    model = map_model(map_message)
    scans.sort(key=lambda item: item[0])
    scan_stamps = [item[0] for item in scans]
    indices = sorted(set(np.linspace(0, len(poses) - 1,
                                  min(samples, len(poses)), dtype=int)))
    fit = []
    paired = []
    for index in indices:
        amcl = poses[index]
        at = amcl[3]
        position = bisect.bisect_left(scan_stamps, at)
        candidates = scans[max(0, position - 1):position + 1]
        if not candidates:
            continue
        scan = min(candidates, key=lambda item: abs(item[0] - at))
        if abs(scan[0] - at) > .3:
            continue
        points = scan_points(scan[2])
        if len(points) < 30:
            continue
        result = score_scan(points, amcl[1], laser, model, check_rays=False)
        fit.append(result["within_15cm_wall_fraction"])
        paired.append(round(abs(scan[0] - at), 3))
    return {"bag": path, "amcl_poses": len(poses), "scan_pairs": len(fit),
            "max_pair_stamp_gap_s": max(paired) if paired else None,
            "median_endpoint_fit_15cm": round(float(np.median(fit)), 3) if fit else None,
            "last_pair_fit_15cm": fit[-1] if fit else None,
            "final_amcl_pose": poses[-1][1].round(3).tolist(),
            "limitation": "Evenly spaced pose samples matched to nearest scan header; endpoint fit is not AMCL likelihood or physical ground truth."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag")
    parser.add_argument("--summary", action="store_true",
                        help="Bounded replay scan/map-fit summary without particle processing")
    parser.add_argument("--source-bag", help="Original bag supplying static laser TF omitted by replay output")
    args = parser.parse_args()
    print(json.dumps(replay_summary(args.bag, source_bag=args.source_bag)
                     if args.summary else analyze(args.bag), indent=2))


if __name__ == "__main__":
    main()
