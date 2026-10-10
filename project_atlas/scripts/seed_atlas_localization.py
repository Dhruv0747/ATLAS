#!/usr/bin/env python3
"""Seed AMCL from a saved map-frame pose without moving the rover.

Seed modes (--mode, else ATLAS_SEED_MODE, else the first word of
~/.config/project_atlas/seed_mode, else "saved"; one switch covers both the
boot-time ExecStartPost and the mode manager's LOCALIZATION transition):

  saved   (default, unchanged behaviour) seed from the saved seed/home pose.
  verify  (2026-10-10 Hall cold-start fix) first match a parked LiDAR scan
          against the saved map with no prior pose. Seed only at a unique,
          well-fitting match; otherwise do NOT seed and record
          LOCALIZATION UNKNOWN. Never seeds the saved pose blindly.

Every run records its outcome in VERDICT_FILE for the dashboard. The file is
diagnostic only; it grants no navigation authority.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from nav2_msgs.srv import SetInitialPose
from rclpy.node import Node
from std_srvs.srv import Empty


POSE_FILES = (
    Path.home() / ".config/project_atlas/localization_seed_pose.json",
    Path.home() / ".config/project_atlas/home_pose.json",
)
PLACES_FILE = Path.home() / ".config/project_atlas/named_places.json"
VERDICT_FILE = Path.home() / ".local/state/project_atlas/localization_verdict.json"
DEFAULT_MAP = Path.home() / "project_atlas/maps/atlas_latest.yaml"
SEED_MODE_FILE = Path.home() / ".config/project_atlas/seed_mode"


def configured_seed_mode():
    mode = os.environ.get("ATLAS_SEED_MODE", "").strip().lower()
    if not mode:
        try:
            words = SEED_MODE_FILE.read_text(encoding="utf-8").split()
            mode = words[0].lower() if words else ""
        except OSError:
            mode = ""
    return mode if mode in ("saved", "verify") else "saved"
PARKED_SCAN_S = 3.0
PARKED_MPS = 0.01
PARKED_RADPS = 0.02


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def write_verdict(record):
    """Atomic, best-effort; failure to record never changes what was seeded."""
    try:
        record = dict(record, written_unix=time.time(), boot_id=boot_id(),
                      navigation_authorized=False)
        VERDICT_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = VERDICT_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        temporary.replace(VERDICT_FILE)
    except OSError:
        pass


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def collect_parked_scans(node, duration_s=PARKED_SCAN_S, timeout_s=20.0):
    """Ranges from /scan while /odom reports the rover still; None if it moved."""
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from nav_msgs.msg import Odometry
    scans, moving = [], {"seen": False, "odom": False}

    def on_scan(msg):
        scans.append(msg)

    def on_odom(msg):
        moving["odom"] = True
        t = msg.twist.twist
        if abs(t.linear.x) > PARKED_MPS or abs(t.linear.y) > PARKED_MPS or abs(t.angular.z) > PARKED_RADPS:
            moving["seen"] = True
    subs = [node.create_subscription(LaserScan, "/scan", on_scan, qos_profile_sensor_data),
            node.create_subscription(Odometry, "/odom", on_odom, 10)]
    start = time.monotonic()
    first_scan = None
    while time.monotonic() - start < timeout_s:
        rclpy.spin_once(node, timeout_sec=0.1)
        if scans and first_scan is None:
            first_scan = time.monotonic()
        if first_scan is not None and time.monotonic() - first_scan >= duration_s:
            break
    for sub in subs:
        node.destroy_subscription(sub)
    if moving["seen"]:
        return None, "rover moved while the startup scan was collected"
    if not moving["odom"]:
        return None, "no odometry while the startup scan was collected"
    if len(scans) < 5:
        return None, f"too few LiDAR scans ({len(scans)}) for startup verification"
    return scans, None


def laser_in_base(node, frame):
    import rclpy
    from rclpy.duration import Duration
    from rclpy.time import Time
    from tf2_ros import Buffer, TransformListener
    buffer = Buffer()
    TransformListener(buffer, node)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        try:
            t = buffer.lookup_transform("base_link", frame, Time(), timeout=Duration(seconds=0.1)).transform
            return (t.translation.x, t.translation.y, yaw_of(t.rotation))
        except Exception:
            continue
    raise RuntimeError(f"no base_link -> {frame} transform")


VERIFY_ATTEMPTS = 3
VERIFY_BUDGET_S = 60.0


def verify_start_pose(node, map_yaml, attempts=VERIFY_ATTEMPTS, budget_s=VERIFY_BUDGET_S):
    """Return (pose dict or None, verdict record). Uses no saved pose.

    Up to ``attempts`` independent parked-scan checks (people walking past
    lower the fit). VERIFIED needs one attempt to pass AND every attempt's
    best place to agree with it; any disagreement is UNKNOWN.
    """
    import atlas_localization_verify_core as core
    record = {"mode": "verify", "map_yaml": str(map_yaml), "attempts": []}
    policy = core.VerifyPolicy()
    started = time.monotonic()
    try:
        record["map_sha256"] = hashlib.sha256(Path(map_yaml).read_bytes()).hexdigest()
        grid = core.load_map(map_yaml)
        laser = None
        verdict = None
        for _ in range(max(1, attempts)):
            scans, problem = collect_parked_scans(node)
            if problem:
                record.update(state="UNKNOWN", reason=problem)
                return None, record
            if laser is None:
                laser = laser_in_base(node, scans[0].header.frame_id)
            ranges = core.median_ranges([list(m.ranges) for m in scans])
            all_pts, held = core.endpoints(scans[0].angle_min, scans[0].angle_increment, ranges, laser, policy)
            verdict = core.decide(core.global_search(grid, all_pts, held, policy), len(all_pts), None, policy)
            record["attempts"].append({"state": verdict.state, "best": (verdict.hypotheses or [None])[0],
                                       "best_fit": verdict.best_fit, "margin": verdict.margin,
                                       "scans_used": len(scans)})
            if verdict.state == "VERIFIED" or time.monotonic() - started > budget_s:
                break
    except Exception as exc:  # fail closed: unknown, never a blind seed
        record.update(state="UNKNOWN", reason=f"verification failed: {exc}")
        return None, record
    record.update(verdict.as_dict())
    if verdict.state != "VERIFIED":
        return None, record
    x, y, yaw = verdict.pose
    for attempt in record["attempts"]:
        best = attempt["best"]
        if best is None:
            continue
        dyaw = abs(math.degrees(math.atan2(math.sin(math.radians(best["yaw_deg"]) - yaw),
                                           math.cos(math.radians(best["yaw_deg"]) - yaw))))
        if math.hypot(best["x"] - x, best["y"] - y) > policy.agree_m or dyaw > policy.agree_deg:
            record.update(state="UNKNOWN", pose=None,
                          reason="parked checks disagree about where ATLAS is")
            return None, record
    return {"frame_id": "map", "x": x, "y": y, "z": 0.0, "qx": 0.0, "qy": 0.0,
            "qz": math.sin(yaw / 2.0), "qw": math.cos(yaw / 2.0)}, record


def load_pose(place=None):
    if place is not None:
        places = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
        key = place.strip().lower().replace("_", " ")
        if key not in places:
            raise RuntimeError(f"unknown named place: {place!r}")
        pose = places[key]
        POSE_FILES[0].parent.mkdir(parents=True, exist_ok=True)
        temporary = POSE_FILES[0].with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(POSE_FILES[0])
        return pose
    pose_file = next((path for path in POSE_FILES if path.exists()), None)
    if pose_file is None:
        raise RuntimeError("no localization seed or home pose is saved")
    pose = json.loads(pose_file.read_text(encoding="utf-8"))
    if pose.get("frame_id") != "map":
        raise RuntimeError(f"saved pose is not in map frame: {pose.get('frame_id')!r}")
    for field in ("x", "y", "qx", "qy", "qz", "qw"):
        if field not in pose:
            raise RuntimeError(f"saved pose is missing {field}")
    return pose


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", help="named map place to seed and persist")
    parser.add_argument("--mode", choices=("saved", "verify"),
                        default=configured_seed_mode())
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--dry-run", action="store_true",
                        help="verify only: print the verdict; seed nothing, write nothing")
    args = parser.parse_args()
    verify = args.mode == "verify" and args.place is None
    pose = None if (verify or args.dry_run) else load_pose(args.place)
    rclpy.init()
    node = Node("atlas_localization_seeder")
    if args.dry_run:
        pose, record = verify_start_pose(node, args.map)
        print(json.dumps(dict(record, dry_run=True, seeded=False, navigation_authorized=False), indent=2))
        node.destroy_node()
        rclpy.shutdown()
        return
    if verify:
        pose, record = verify_start_pose(node, args.map)
        if pose is None:
            write_verdict(record)
            node.get_logger().warn(
                "LOCALIZATION UNKNOWN: AMCL not seeded; " + record.get("reason", "")
                + ". Set the current named place after checking where ATLAS is.")
            node.destroy_node()
            rclpy.shutdown()
            return  # exit 0: an unverified start is a reported state, not a crash loop
    publisher = node.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
    pose_client = node.create_client(SetInitialPose, "/set_initial_pose")
    update_client = node.create_client(Empty, "/request_nomotion_update")
    latest_odom_stamp = {"value": None}

    def receive_odom(msg: Odometry):
        latest_odom_stamp["value"] = msg.header.stamp

    odom_subscription = node.create_subscription(
        Odometry, "/odom", receive_odom, 10
    )
    message = PoseWithCovarianceStamped()
    message.header.frame_id = "map"
    message.pose.pose.position.x = float(pose["x"])
    message.pose.pose.position.y = float(pose["y"])
    message.pose.pose.position.z = float(pose.get("z", 0.0))
    message.pose.pose.orientation.x = float(pose["qx"])
    message.pose.pose.orientation.y = float(pose["qy"])
    message.pose.pose.orientation.z = float(pose["qz"])
    message.pose.pose.orientation.w = float(pose["qw"])
    message.pose.covariance[0] = 0.25
    message.pose.covariance[7] = 0.25
    message.pose.covariance[35] = 0.068
    if verify:
        # LiDAR-matched pose: start AMCL near it, but not as a single point.
        message.pose.covariance[0] = 0.10 ** 2
        message.pose.covariance[7] = 0.10 ** 2
        message.pose.covariance[35] = math.radians(8.0) ** 2

    deadline = time.monotonic() + 20.0
    while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if publisher.get_subscription_count() == 0:
        raise RuntimeError("AMCL is not subscribed to /initialpose")

    odom_deadline = time.monotonic() + 8.0
    while latest_odom_stamp["value"] is None and time.monotonic() < odom_deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if latest_odom_stamp["value"] is None:
        raise RuntimeError("no odometry timestamp is available for AMCL seeding")
    # Freeze this known-good timestamp. The subscription continues receiving
    # newer odometry while we publish; following that moving edge would put
    # every new initial pose just ahead of the TF buffer again.
    seed_stamp = latest_odom_stamp["value"]

    # Use AMCL's direct service when available. Topic publication can report a
    # subscriber yet still be discarded during lifecycle/timestamp races.
    message.header.stamp.sec = seed_stamp.sec
    message.header.stamp.nanosec = seed_stamp.nanosec
    service_applied = False
    if pose_client.wait_for_service(timeout_sec=5.0):
        request = SetInitialPose.Request()
        request.pose = message
        future = pose_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        service_applied = future.done() and future.exception() is None
    if not service_applied:
        # Compatibility fallback for older AMCL builds without the service.
        for _ in range(20):
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.5)
    if update_client.wait_for_service(timeout_sec=2.0):
        future = update_client.call_async(Empty.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
    if verify:
        write_verdict(dict(record, seeded=True,
                           seeded_via="service" if service_applied else "topic fallback"))
    else:
        write_verdict({"mode": "saved", "state": "UNVERIFIED",
                       "reason": "seeded from a saved pose without checking the LiDAR",
                       "pose": {"x": round(float(pose["x"]), 3), "y": round(float(pose["y"]), 3)},
                       "seeded": True})
    node.get_logger().info(
        f"Seeded AMCL from {'LiDAR-verified' if verify else 'saved'} pose x={pose['x']:.3f} y={pose['y']:.3f} "
        f"via {'service' if service_applied else 'topic fallback'}"
    )
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
