#!/usr/bin/env python3
"""Continuous LiDAR check of the live AMCL pose (read-only by default).

Why: on 2026-10-10 a fast manual drive left AMCL 4 m wrong while the map page
still showed "START VERIFIED". A start check says nothing about later
tracking, and AMCL covariance collapses to ~0 whether right or wrong. The
same wrong place, about (3.8..4.1, -0.5..-0.8) facing ~157 deg, was found for
a rover actually in Dhruv Room in 4 separate recordings.

What it does:
  moving          state MOVING_UNVERIFIED (no claim is made while moving).
  parked >= 2 s   checks the AMCL pose against the LiDAR (held-out fit) and
                  runs the no-prior global search (atlas_localization_verify_core).
                  Result: VERIFIED / DEGRADED / LOST, published as JSON on
                  /atlas/localization_check and written to CHECK_FILE.
  recovery        ~/.config/project_atlas/relocalize_mode:
                    "suggest" (default) report the LiDAR pose, change nothing;
                    "auto"    reseed AMCL only after TWO consecutive parked
                              LOST results whose LiDAR answers agree, then
                              require a fresh VERIFIED check;
                    "off"     report state only.
It never publishes velocity, never grants navigation authority and never
touches encoders, EKF, AMCL parameters, the map or the network.
"""
import json
import math
from pathlib import Path
import threading
import time

import atlas_localization_verify_core as core

CHECK_FILE = Path.home() / ".local/state/project_atlas/localization_check.json"
MODE_FILE = Path.home() / ".config/project_atlas/relocalize_mode"
DEFAULT_MAP = Path.home() / "project_atlas/maps/atlas_latest.yaml"
PARK_SETTLE_S = 2.0
PARKED_MPS = 0.01
PARKED_RADPS = 0.02
RECHECK_PARKED_S = 30.0


def relocalize_mode(path=MODE_FILE):
    try:
        words = Path(path).read_text(encoding="utf-8").split()
    except OSError:
        return "suggest"
    mode = words[0].lower() if words else "suggest"
    return mode if mode in ("off", "suggest", "auto") else "suggest"


class MonitorLogic:
    """Pure state machine; the ROS node feeds it and acts on its decisions."""

    def __init__(self, policy=core.VerifyPolicy()):
        self.policy = policy
        self.state = {"state": "STARTING", "reason": "waiting for data"}
        self.parked_since = None
        self.last_check_at = None
        self.lost_streak = []          # recovery poses of consecutive LOST checks
        self.awaiting_confirmation = False

    def on_motion(self, now, moving):
        if moving:
            self.parked_since = None
            self.lost_streak = []
            last = self.state if self.state.get("state") not in ("MOVING_UNVERIFIED", "STARTING") else None
            self.state = {"state": "MOVING_UNVERIFIED", "reason": "no LiDAR confirmation while moving",
                          "last_check": None if last is None else {k: last.get(k) for k in ("state", "checked_unix")}}
        elif self.parked_since is None:
            self.parked_since = now

    def check_due(self, now):
        if self.parked_since is None or now - self.parked_since < PARK_SETTLE_S:
            return False
        return self.last_check_at is None or self.last_check_at < self.parked_since or \
            now - self.last_check_at >= RECHECK_PARKED_S or self.awaiting_confirmation

    def on_result(self, now, result, mode):
        """result: dict from core.assess_tracking. Returns a pose to reseed, or None."""
        self.last_check_at = now
        result = dict(result, checked_unix=time.time(), relocalize_mode=mode)
        reseed = None
        if result["state"] == "LOST" and result.get("recovery_pose"):
            self.lost_streak.append(result["recovery_pose"])
            self.lost_streak = self.lost_streak[-2:]
            agree = len(self.lost_streak) == 2 and math.hypot(
                self.lost_streak[0]["x"] - self.lost_streak[1]["x"],
                self.lost_streak[0]["y"] - self.lost_streak[1]["y"]) <= self.policy.track_agree_m and \
                core.angle_deg(math.radians(self.lost_streak[0]["yaw_deg"]),
                               math.radians(self.lost_streak[1]["yaw_deg"])) <= self.policy.track_agree_deg
            if mode == "auto" and agree:
                reseed = self.lost_streak[-1]
                self.lost_streak = []
                self.awaiting_confirmation = True
                result["action"] = "AMCL reseeded at the LiDAR pose; waiting for a fresh VERIFIED check"
            elif mode == "auto":
                result["action"] = "LiDAR pose found once; a second agreeing parked check is required"
            else:
                result["action"] = "suggest only: set the named place or enable auto relocalize"
        else:
            self.lost_streak = []
            if result["state"] == "VERIFIED":
                self.awaiting_confirmation = False
        result["navigation_authorized"] = False
        self.state = result
        return reseed


def main():
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from nav_msgs.msg import Odometry
    from nav2_msgs.srv import SetInitialPose
    from rclpy.duration import Duration
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String
    from tf2_ros import Buffer, TransformListener

    def yaw_of(q):
        return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))

    class Monitor(Node):
        def __init__(self):
            super().__init__("atlas_localization_monitor")
            self.logic = MonitorLogic()
            self.map = core.load_map(DEFAULT_MAP)
            self.scans = []
            self.amcl = None
            self.busy = False
            self.tf = Buffer()
            TransformListener(self.tf, self)
            self.pub = self.create_publisher(String, "/atlas/localization_check", 10)
            self.seed = self.create_client(SetInitialPose, "/set_initial_pose")
            self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
            self.create_subscription(Odometry, "/odom", self.on_odom, 10)
            self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.on_amcl, 10)
            self.create_timer(1.0, self.tick)

        def on_scan(self, msg):
            self.scans.append((time.monotonic(), msg))
            self.scans = [s for s in self.scans if time.monotonic() - s[0] <= PARK_SETTLE_S + 0.5]

        def on_odom(self, msg):
            t = msg.twist.twist
            moving = abs(t.linear.x) > PARKED_MPS or abs(t.linear.y) > PARKED_MPS or abs(t.angular.z) > PARKED_RADPS
            self.logic.on_motion(time.monotonic(), moving)

        def on_amcl(self, msg):
            p = msg.pose.pose
            self.amcl = (p.position.x, p.position.y, yaw_of(p.orientation))

        def publish(self):
            record = dict(self.logic.state, written_unix=time.time())
            self.pub.publish(String(data=json.dumps(record)))
            try:
                CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = CHECK_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
                tmp.replace(CHECK_FILE)
            except OSError:
                pass

        def tick(self):
            now = time.monotonic()
            if not self.busy and self.amcl is not None and len(self.scans) >= 5 and self.logic.check_due(now):
                self.busy = True
                scans = [m for _, m in self.scans]
                amcl = self.amcl
                threading.Thread(target=self.check, args=(scans, amcl), daemon=True).start()
            self.publish()

        def check(self, scans, amcl):
            try:
                t = self.tf.lookup_transform("base_link", scans[0].header.frame_id, Time(),
                                             timeout=Duration(seconds=0.5)).transform
                laser = (t.translation.x, t.translation.y, yaw_of(t.rotation))
                policy = self.logic.policy
                ranges = core.median_ranges([list(m.ranges) for m in scans])
                allp, held = core.endpoints(scans[0].angle_min, scans[0].angle_increment, ranges, laser, policy)
                amcl_fit = core.fit(self.map, held, *amcl, policy.tolerance_m)
                verdict = core.decide(core.global_search(self.map, allp, held, policy), len(allp), None, policy)
                result = core.assess_tracking(amcl, amcl_fit, verdict, policy)
                if self.logic.parked_since is None:      # moved during the check: discard
                    return
                reseed = self.logic.on_result(time.monotonic(), result, relocalize_mode())
                if reseed is not None:
                    self.reseed(reseed)
            except Exception as exc:  # report, never act
                self.logic.state = {"state": "DEGRADED", "reason": f"check failed: {exc}",
                                    "navigation_authorized": False}
            finally:
                self.busy = False

        def reseed(self, pose):
            if not self.seed.service_is_ready():
                self.logic.state["action"] = "reseed skipped: /set_initial_pose unavailable"
                return
            msg = PoseWithCovarianceStamped()
            msg.header.frame_id = "map"
            msg.header.stamp = self.get_clock().now().to_msg()
            yaw = math.radians(pose["yaw_deg"])
            msg.pose.pose.position.x, msg.pose.pose.position.y = pose["x"], pose["y"]
            msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            msg.pose.covariance[0] = msg.pose.covariance[7] = 0.10 ** 2
            msg.pose.covariance[35] = math.radians(8.0) ** 2
            req = SetInitialPose.Request()
            req.pose = msg
            self.seed.call_async(req)
            self.get_logger().warn(f"LOCALIZATION LOST: AMCL reseeded at LiDAR pose {pose}")

    rclpy.init()
    node = Monitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
