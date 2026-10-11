#!/usr/bin/env python3
"""ROS-independent helpers for ATLAS Visual Cloud."""

import math
import time


FAILURE_CLASSES = (
    "LOCALIZATION", "ODOMETRY", "TF", "PLANNER", "CONTROLLER", "COSTMAP",
    "SENSOR", "MOTOR", "RECOVERY", "COMPUTE", "UNKNOWN",
)

ACTIVE_STATUS_WORDS = (
    "MAPPING", "NAVIGATING", "RETURNING", "RECOVERING", "EXPLORING",
    "EXPLORATION ACTIVE", "EXECUTING", "MISSION_ACTIVE",
    "NAVIGATION_ACTIVE", "GOAL DISPATCHED", "GOAL ACCEPTED",
    "TAUGHT ROUTE DISPATCHED", "RETURN HOME",
)
INACTIVE_STATUS_WORDS = (
    "IDLE", "INACTIVE", "STOPPED", "COMPLETE", "COMPLETED", "SUCCEEDED",
    "FAILED", "ABORT", "CANCELLED", "CANCELED", "READY", "WAITING",
    "FINISHED", "VERIFIED", "REJECTED", "INACCURATE", "NOT ACTIVE",
)


def link_health(age_s, expected_hz=0.0, observed_hz=0.0):
    """Return a stable traffic state without inventing missing samples."""
    if age_s is None or not math.isfinite(float(age_s)):
        return "STOPPED"
    expected_period = 1.0 / max(0.01, float(expected_hz or 0.0))
    stopped_after = max(5.0, expected_period * 8.0)
    delayed_after = max(1.0, expected_period * 3.0)
    if age_s > stopped_after:
        return "STOPPED"
    if age_s > delayed_after:
        return "DELAYED"
    if expected_hz and observed_hz < expected_hz * 0.35:
        return "DELAYED"
    return "HEALTHY"


def classify_failure(text):
    """Classify terminal navigation evidence into the requested taxonomy."""
    value = str(text or "").upper()
    rules = (
        ("LOCALIZATION", ("AMCL", "LOCALIZATION", "POSE JUMP", "LOST POSE")),
        ("ODOMETRY", ("ODOM", "ENCODER", "WHEEL SLIP")),
        ("TF", ("TRANSFORM", "EXTRAPOLATION", " TF ", "TF_")),
        ("PLANNER", ("NO VALID PATH", "NO PATH", "PLANNER", "COMPUTE_PATH")),
        ("CONTROLLER", ("CONTROLLER", "PROGRESS CHECKER", "FOLLOW_PATH")),
        ("COSTMAP", ("COSTMAP", "LETHAL SPACE", "STALE OBSTACLE")),
        ("SENSOR", ("LIDAR", "SCAN STALE", "SENSOR", "ULTRASONIC")),
        ("MOTOR", ("MOTOR", "TRACTION", "DRIVER BOARD")),
        ("RECOVERY", ("RECOVERY", "BACKUP FAILED", "BEHAVIOR SERVER")),
        ("COMPUTE", ("CPU", "OOM", "MEMORY", "DEADLINE", "UPDATE RATE")),
    )
    for label, terms in rules:
        if any(term in value for term in terms):
            return label
    return "UNKNOWN"


def topic_stat(samples, now=None, expected_hz=0.0, retained=False):
    """Summarize monotonic receive timestamps into Hz, age and health."""
    now = time.monotonic() if now is None else float(now)
    samples = list(samples)
    age = None if not samples else max(0.0, now - samples[-1])
    hz = 0.0
    if len(samples) > 1 and samples[-1] > samples[0]:
        hz = (len(samples) - 1) / (samples[-1] - samples[0])
    return {
        "hz": round(hz, 2),
        "age_s": None if age is None else round(age, 3),
        # Retained map/static-TF data is event-driven, not a live heartbeat.
        # Keep the real receipt age and explicitly label cached data.
        "health": "CACHED" if retained and samples else link_health(age, expected_hz, hz),
    }


def is_robot_activity(topic, value, epsilon=1e-4):
    """Recognize signals that require the agent's full real-time cadence.

    This deliberately looks only at already-observed telemetry. It grants no
    control authority and never treats a stale value as activity.
    """
    if topic in ("/cmd_vel", "/cmd_vel_nav") and isinstance(value, dict):
        try:
            return (
                abs(float(value.get("linear_x", 0.0))) > float(epsilon)
                or abs(float(value.get("angular_z", 0.0))) > float(epsilon)
            )
        except (TypeError, ValueError):
            return False
    if topic not in ("/atlas/mission_status", "/atlas/recovery_status"):
        return False
    status = str(value or "").upper()
    if any(word in status for word in INACTIVE_STATUS_WORDS):
        return False
    return any(word in status for word in ACTIVE_STATUS_WORDS)


def interval_due(last_at, now, active, active_interval_s, idle_interval_s):
    """Return whether an adaptive periodic task is due at ``now``."""
    interval = active_interval_s if active else idle_interval_s
    try:
        interval = max(0.01, float(interval))
        return not last_at or float(now) - float(last_at) >= interval
    except (TypeError, ValueError):
        return True


# ---- 2026-10-11: local-only, viewer-activated observability ----------------------------------

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def upload_mode(config):
    """'off' | 'local' | 'remote'. An explicit ``upload_mode`` wins; otherwise infer from the URL.

    A placeholder (``*.example``) or empty URL means 'off': no snapshot is built and no DNS lookup
    or connection is attempted. Loopback means 'local' (the Jetson preview server).
    """
    from urllib.parse import urlsplit
    explicit = str(config.get("upload_mode", "")).strip().lower()
    if explicit in ("off", "local", "remote"):
        return explicit
    host = (urlsplit(str(config.get("cloud_url", ""))).hostname or "").lower()
    if not host or host.endswith(".example") or host.endswith(".invalid"):
        return "off"
    return "local" if host in LOCAL_HOSTS else "remote"


class ViewerGate:
    """Decides whether snapshots are wanted. 'remote' always, 'off' never, 'local' only while the
    preview server reports a viewer seen within ``hold_s``. ``fetch`` returns the server's
    viewer age in seconds (or None); it is called at most every ``check_s`` and any error counts as
    'no viewer', so a stopped preview server makes the agent idle rather than busy."""

    def __init__(self, mode, fetch, check_s=5.0, hold_s=30.0):
        self.mode, self.fetch = mode, fetch
        self.check_s, self.hold_s = float(check_s), float(hold_s)
        self.last_check = None
        self.viewer_until = float("-inf")

    def poll(self, now):
        """Call from a non-executor thread. Returns True when a check was made."""
        if self.mode != "local" or (self.last_check is not None and now - self.last_check < self.check_s):
            return False
        self.last_check = now
        try:
            age = self.fetch()
        except Exception:
            age = None
        if age is not None and math.isfinite(float(age)) and float(age) <= self.hold_s:
            self.viewer_until = now + self.check_s + 1.0
        return True

    def wanted(self, now):
        if self.mode == "remote":
            return True
        if self.mode == "off":
            return False
        return now < self.viewer_until


def history_row(value):
    """Bounded copy of a snapshot for persistent history: rates, ages and health per topic,
    graph sizes and system figures. Large per-topic values (scan, costmaps, paths, TF) and the
    full graph are not stored; the live view still shows them from memory."""
    traffic = value.get("traffic", {}) if isinstance(value, dict) else {}
    graph = value.get("graph", {}) if isinstance(value, dict) else {}
    slim = {
        name: {k: v for k, v in (item or {}).items() if k in ("hz", "age_s", "health", "expected_hz", "data_mode")}
        for name, item in (traffic.items() if isinstance(traffic, dict) else ())
    }
    mission = (traffic.get("/atlas/mission_status") or {}).get("value") if isinstance(traffic, dict) else None
    return {
        "schema": 2, "robot_id": value.get("robot_id"), "observed_at": value.get("observed_at"),
        "git_version": value.get("git_version"), "system": value.get("system"),
        "failure_class": value.get("failure_class"), "collection_mode": value.get("collection_mode"),
        "mission_status": str(mission)[:500] if mission is not None else None,
        "traffic": slim,
        "graph_counts": {k: len(graph.get(k) or []) for k in ("nodes", "topics", "services", "actions")}
        if isinstance(graph, dict) else {},
        "authority": value.get("authority"),
    }


def persist_due(last_at, last_failure_at, now, failure_class, interval_s=60.0, failure_interval_s=10.0):
    """One bounded row per ``interval_s``; failures are kept more densely but still rate-limited."""
    if failure_class not in (None, "", "NONE"):
        return last_failure_at is None or now - last_failure_at >= failure_interval_s
    return last_at is None or now - last_at >= interval_s
