#!/usr/bin/env python3
"""Continuous LiDAR check of the live AMCL pose (read-only by default).

Why: on 2026-10-10 a fast manual drive left AMCL 4 m wrong while the map page
still showed "START VERIFIED". A start check says nothing about later
tracking, and AMCL covariance collapses to ~0 whether right or wrong. The
same wrong place, about (3.8..4.1, -0.5..-0.8) facing ~157 deg, was found for
a rover actually in Dhruv Room in 4 separate recordings.

What it does:
  moving          state MOVING_UNVERIFIED (no claim is made while moving).
  stopped         PARKED_SETTLING, then VERIFYING (2026-10-10 state machine).
  stale inputs    INPUT_STALE (odometry, LiDAR or AMCL pose not fresh).
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
HISTORY_FILE = Path.home() / ".local/state/project_atlas/localization_check_history.jsonl"
HISTORY_MAX_BYTES = 2_000_000          # one rotated copy is kept (.1)
MODE_FILE = Path.home() / ".config/project_atlas/relocalize_mode"
DEFAULT_MAP = Path.home() / "project_atlas/maps/atlas_latest.yaml"
PARK_SETTLE_S = 2.0
PARKED_MPS = 0.01
PARKED_RADPS = 0.02
RECHECK_PARKED_S = 30.0                # measured from the START of the previous check
SCHEDULE_PERIOD_S = 0.25               # how often a due check is looked for
SCAN_MAX_AGE_S = 1.0                   # newest scan used must be this fresh
SCAN_WINDOW_S = PARK_SETTLE_S + 0.5    # scans older than this are never used
MIN_SCANS = 5
ODOM_MAX_AGE_S = 1.0                   # without fresh odometry "stopped" is unknown
AMCL_MAX_AGE_S = 2.5                   # AMCL publishes at 1 Hz while parked (nomotion)
POSE_CHANGE_M = 0.10                   # AMCL pose changed during the search:
POSE_CHANGE_DEG = 3.0                  #   the result describes an outdated pose
CHECK_TIMEOUT_S = 30.0                 # a search that has not returned is abandoned
CONFIRM_RECHECK_S = 5.0                # after an auto reseed: recheck soon, not back-to-back
NOT_VERIFIED_STATES = ("STARTING", "MOVING_UNVERIFIED", "PARKED_SETTLING", "VERIFYING", "INPUT_STALE")


def relocalize_mode(path=MODE_FILE):
    try:
        words = Path(path).read_text(encoding="utf-8").split()
    except OSError:
        return "suggest"
    mode = words[0].lower() if words else "suggest"
    return mode if mode in ("off", "suggest", "auto") else "suggest"


def _summary(result):
    if not result:
        return None
    return {k: result.get(k) for k in ("state", "checked_unix", "reason")}


class MonitorLogic:
    """Thread-safe state machine; the ROS node feeds it and acts on its decisions.

    MOVING_UNVERIFIED -> (odom stopped) PARKED_SETTLING -> (2 s) VERIFYING
      -> VERIFIED / DEGRADED / LOST, rechecked every 30 s while parked.
    INPUT_STALE when odometry, LiDAR or AMCL data stop arriving.
    Every motion/stop/staleness transition starts a new episode; a check result
    is applied only if its episode is still current, the rover is still parked
    and AMCL has not moved since the check started. Nothing here authorizes
    navigation.
    """

    def __init__(self, policy=core.VerifyPolicy(), wall=time.time):
        self.policy = policy
        self.wall = wall
        self.lock = threading.RLock()
        self.state = {"state": "STARTING", "reason": "waiting for data", "navigation_authorized": False}
        self.result = None             # last applied check result
        self.parked_since = None
        self.last_moving_at = None
        self.last_odom_at = None
        self.episode = 0
        self.checked_episode = None
        self.check_started_at = None
        self.in_flight = None          # episode token of the running check
        self.timing = {}
        self.lost_streak = []          # recovery poses of consecutive LOST checks
        self.awaiting_confirmation = False
        self.history = []              # records for the node to append to HISTORY_FILE

    # -- helpers ---------------------------------------------------------
    def _set(self, now, state, event, **extra):
        state = dict(state, navigation_authorized=False, episode=self.episode)
        self.state = state
        self.history.append(dict({"event": event, "state": state.get("state"), "reason": state.get("reason"),
                                  "episode": self.episode, "mono": round(now, 3),
                                  "unix": round(self.wall(), 3)}, **extra))

    def _not_verified(self, now, name, reason, event, **extra):
        self._set(now, {"state": name, "reason": reason, "last_check": _summary(self.result)}, event, **extra)

    def drain_history(self):
        with self.lock:
            out, self.history = self.history, []
            return out

    # -- inputs ------------------------------------------------------------
    def on_motion(self, now, moving):
        with self.lock:
            self.last_odom_at = now
            if moving:
                self.last_moving_at = now
                if self.parked_since is not None or self.state.get("state") != "MOVING_UNVERIFIED":
                    self.episode += 1                       # invalidates any running check
                    self.parked_since = None
                    self.lost_streak = []
                    self._not_verified(now, "MOVING_UNVERIFIED", "no LiDAR confirmation while moving", "moving")
            elif self.parked_since is None:
                self.episode += 1
                self.parked_since = now
                self.timing = {"stopped_mono": now, "last_moving_mono": self.last_moving_at}
                self._not_verified(now, "PARKED_SETTLING",
                                   f"stopped; LiDAR check after {PARK_SETTLE_S:.0f} s settle", "stopped")

    def on_inputs(self, now, scan_age, amcl_age):
        """Called on every scheduling tick. Ages are seconds (None = never)."""
        with self.lock:
            if self.last_odom_at is not None and now - self.last_odom_at > ODOM_MAX_AGE_S:
                if self.state.get("state") != "INPUT_STALE" or self.parked_since is not None:
                    self.episode += 1
                    self.parked_since = None
                    self._not_verified(now, "INPUT_STALE", "odometry stale: cannot tell if ATLAS is stopped",
                                       "odom_stale")
                return
            if self.in_flight is not None and now - self.check_started_at > CHECK_TIMEOUT_S:
                token, self.in_flight = self.in_flight, None
                self.episode += 1                           # a late result is discarded
                self.checked_episode = self.episode         # retry after RECHECK_PARKED_S, not instantly
                self.result = {"state": "DEGRADED", "reason": f"LiDAR check did not finish in {CHECK_TIMEOUT_S:.0f} s",
                               "checked_unix": self.wall()}
                self._set(now, self.result, "check_timeout", token=token)
                return
            if self.parked_since is None or now - self.parked_since < PARK_SETTLE_S:
                return
            stale = None
            if scan_age is None or scan_age > SCAN_MAX_AGE_S:
                stale = "LiDAR scan stale"
            elif amcl_age is None or (amcl_age > AMCL_MAX_AGE_S and now - self.parked_since > PARK_SETTLE_S + AMCL_MAX_AGE_S):
                stale = "AMCL pose stale"
            if stale and self.state.get("reason") != stale:
                self.episode += 1                           # invalidates any running check
                self.checked_episode = None
                self._not_verified(now, "INPUT_STALE", stale, "input_stale")
            elif not stale and self.state.get("state") == "INPUT_STALE":
                self.episode += 1                           # fresh data again: check promptly
                self.checked_episode = None
                self._not_verified(now, "PARKED_SETTLING", "data fresh again; LiDAR check pending", "input_ok")

    # -- checks ------------------------------------------------------------
    def check_due(self, now):
        with self.lock:
            if self.in_flight is not None or self.parked_since is None:
                return False
            if now - self.parked_since < PARK_SETTLE_S or self.state.get("state") == "INPUT_STALE":
                return False
            if self.checked_episode != self.episode:
                return True
            since = now - self.check_started_at
            return since >= RECHECK_PARKED_S or (self.awaiting_confirmation and since >= CONFIRM_RECHECK_S)

    def begin_check(self, now):
        """Returns the episode token the result must present."""
        with self.lock:
            first = self.checked_episode != self.episode
            self.checked_episode = self.episode
            self.check_started_at = now
            self.in_flight = self.episode
            if first:
                self.timing["check_started_mono"] = now
                self._not_verified(now, "VERIFYING", "stopped; comparing LiDAR scan with the map", "check_started")
            else:
                self.state = dict(self.state, rechecking=True)
            return self.episode

    def on_discard(self, now, token, why):
        with self.lock:
            if self.in_flight == token:
                self.in_flight = None
            self.history.append({"event": "result_discarded", "reason": why, "episode": token,
                                 "current_episode": self.episode, "mono": round(now, 3),
                                 "unix": round(self.wall(), 3)})

    def on_result(self, now, result, mode, token=None, amcl_start=None, amcl_now=None):
        """result: dict from core.assess_tracking. Returns a pose to reseed, or None."""
        with self.lock:
            if token is not None:
                if self.in_flight == token:
                    self.in_flight = None
                if token != self.episode or self.parked_since is None:
                    self.on_discard(now, token, "rover moved or data went stale during the check")
                    return None
                if amcl_start is not None and amcl_now is not None and (
                        math.hypot(amcl_now[0] - amcl_start[0], amcl_now[1] - amcl_start[1]) > POSE_CHANGE_M or
                        core.angle_deg(amcl_now[2], amcl_start[2]) > POSE_CHANGE_DEG):
                    self.checked_episode = None             # recheck the new pose promptly
                    self.on_discard(now, token, "AMCL pose changed during the check (outdated pose)")
                    return None
            result = dict(result, checked_unix=self.wall(), relocalize_mode=mode)
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
            timing = {}
            if "check_started_mono" in self.timing and "result_mono" not in self.timing:
                self.timing["result_mono"] = now
                t = self.timing
                timing = {"stop_to_check_start_s": round(t["check_started_mono"] - t["stopped_mono"], 2),
                          "search_s": round(now - t["check_started_mono"], 2),
                          "stop_to_result_s": round(now - t["stopped_mono"], 2)}
                if t.get("last_moving_mono") is not None:
                    timing["last_motion_to_result_s"] = round(now - t["last_moving_mono"], 2)
            elif self.check_started_at is not None:
                timing = {"search_s": round(now - self.check_started_at, 2)}
            result["timing"] = timing
            self.result = result
            self._set(now, result, "result", timing=timing, amcl_fit=result.get("amcl_fit"))
            return reseed

    def on_check_error(self, now, token, exc):
        with self.lock:
            if self.in_flight == token:
                self.in_flight = None
            if token != self.episode:
                self.on_discard(now, token, f"check failed after episode changed: {exc}")
                return
            self.result = {"state": "DEGRADED", "reason": f"check failed: {exc}", "checked_unix": self.wall()}
            self._set(now, self.result, "check_error")

    def snapshot(self):
        with self.lock:
            return dict(self.state)


def usable_scans(stamped, now, parked_since):
    """Scans a check may use: received within SCAN_WINDOW_S and after the stop."""
    return [m for t, m in stamped if now - t <= SCAN_WINDOW_S and parked_since is not None and t >= parked_since]


def append_history(records, path=HISTORY_FILE, max_bytes=HISTORY_MAX_BYTES):
    if not records:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except OSError:
        pass


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
            core._search_index(self.map, self.logic.policy)   # build the search index once, at start
            self.scans = []                 # (monotonic receive time, msg)
            self.amcl = None                # (x, y, yaw)
            self.amcl_at = None
            self.data_lock = threading.Lock()
            self.tf = Buffer()
            TransformListener(self.tf, self)
            self.pub = self.create_publisher(String, "/atlas/localization_check", 10)
            self.seed = self.create_client(SetInitialPose, "/set_initial_pose")
            self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
            self.create_subscription(Odometry, "/odom", self.on_odom, 10)
            self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.on_amcl, 10)
            self.create_timer(SCHEDULE_PERIOD_S, self.schedule)
            self.create_timer(1.0, self.publish)
            self.last_state = None

        def on_scan(self, msg):
            now = time.monotonic()
            with self.data_lock:
                self.scans.append((now, msg))
                self.scans = [s for s in self.scans if now - s[0] <= SCAN_WINDOW_S]

        def on_odom(self, msg):
            t = msg.twist.twist
            moving = abs(t.linear.x) > PARKED_MPS or abs(t.linear.y) > PARKED_MPS or abs(t.angular.z) > PARKED_RADPS
            self.logic.on_motion(time.monotonic(), moving)

        def on_amcl(self, msg):
            p = msg.pose.pose
            with self.data_lock:
                self.amcl = (p.position.x, p.position.y, yaw_of(p.orientation))
                self.amcl_at = time.monotonic()

        def publish(self):
            state = self.logic.snapshot()
            record = dict(state, written_unix=time.time())
            self.pub.publish(String(data=json.dumps(record)))
            try:
                CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = CHECK_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
                tmp.replace(CHECK_FILE)
            except OSError:
                pass
            append_history(self.logic.drain_history())
            self.last_state = (state.get("state"), state.get("checked_unix"), state.get("reason"))

        def schedule(self):
            now = time.monotonic()
            with self.data_lock:
                parked = self.logic.parked_since
                # Never use stale scans or scans from before the stop.
                scans = usable_scans(self.scans, now, parked)
                scan_age = now - self.scans[-1][0] if self.scans else None
                amcl, amcl_at = self.amcl, self.amcl_at
            amcl_age = None if amcl_at is None or (parked is not None and amcl_at < parked) else now - amcl_at
            self.logic.on_inputs(now, scan_age, amcl_age)
            if len(scans) >= MIN_SCANS and amcl_age is not None and amcl_age <= AMCL_MAX_AGE_S \
                    and self.logic.check_due(now):
                token = self.logic.begin_check(now)
                threading.Thread(target=self.check, args=(scans, amcl, token), daemon=True).start()
            state = self.logic.snapshot()
            if (state.get("state"), state.get("checked_unix"), state.get("reason")) != self.last_state:
                self.publish()          # transitions reach the dashboard without waiting for the 1 s tick

        def check(self, scans, amcl, token):
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
                with self.data_lock:
                    amcl_now = self.amcl
                reseed = self.logic.on_result(time.monotonic(), result, relocalize_mode(), token, amcl, amcl_now)
                if reseed is not None:
                    self.reseed(reseed)
            except Exception as exc:  # report, never act
                self.logic.on_check_error(time.monotonic(), token, exc)

        def reseed(self, pose):
            if not self.seed.service_is_ready():
                with self.logic.lock:
                    self.logic.state = dict(self.logic.state, action="reseed skipped: /set_initial_pose unavailable")
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
