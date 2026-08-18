#!/usr/bin/env python3
"""Persistent, bounded mission and recovery memory for Project ATLAS."""

import json
from pathlib import Path
import sqlite3
import time
import uuid

import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    finished_at REAL,
    mission TEXT NOT NULL,
    mode TEXT NOT NULL,
    outcome TEXT,
    final_reason TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY(episode_id) REFERENCES episodes(id)
);
CREATE INDEX IF NOT EXISTS events_episode_time
ON events(episode_id, created_at);
CREATE TABLE IF NOT EXISTS recovery_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    failure_class TEXT NOT NULL,
    strategy TEXT NOT NULL,
    outcome TEXT NOT NULL,
    context TEXT NOT NULL,
    validation_state TEXT NOT NULL DEFAULT 'candidate',
    controlled_successes INTEGER NOT NULL DEFAULT 0,
    collision_count INTEGER NOT NULL DEFAULT 0,
    approved INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(episode_id) REFERENCES episodes(id)
);
"""


class AtlasExperienceStore(Node):
    FINAL_SUCCESS = ("FINISHED STATUS=4", "MAP SAVED", "COMPLETE")
    FINAL_FAILURE = ("ERROR", "FAILED", "BLOCKED", "REJECTED")

    def __init__(self):
        super().__init__("atlas_experience_store")
        self.declare_parameter(
            "database",
            "/home/jetson/project_atlas/data/experience/atlas_experience.sqlite3",
        )
        self.declare_parameter("max_events", 100000)
        self.database = Path(str(self.get_parameter("database").value))
        self.max_events = int(self.get_parameter("max_events").value)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database, timeout=10.0)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

        self.episode_id = ""
        self.last_values = {}
        self.last_recorded_at = {}
        self.last_pose = {}
        self.latest_context = {}
        self.status_pub = self.create_publisher(
            String, "/atlas/experience/status", 10
        )
        self.create_subscription(
            String, "/atlas/experience/record", self.on_external_event, 10
        )
        for topic, source in (
            ("/atlas/mission_status", "mission"),
            ("/atlas/safety_status", "safety"),
            ("/atlas/recovery_status", "recovery"),
            ("/atlas/tight_recovery_status", "tight_recovery"),
            ("/atlas/mode", "mode"),
            ("/atlas/agent/decision", "agent_decision"),
            ("/atlas/agent/response", "agent_response"),
            ("/atlas/autonomy_state", "autonomy"),
        ):
            self.create_subscription(
                String,
                topic,
                lambda msg, name=source: self.on_status(name, msg.data),
                10,
            )
        self.create_subscription(Odometry, "/odom", self.on_odom, 10)
        self.create_service(Trigger, "/atlas/experience/start", self.start_service)
        self.create_service(Trigger, "/atlas/experience/stop", self.stop_service)
        self.create_service(Trigger, "/atlas/experience/status", self.status_service)
        self.create_timer(10.0, self.publish_status)
        self.start_episode("system commissioning", "OBSERVE")
        self.prune()

    def execute(self, sql, values=()):
        self.connection.execute(sql, values)
        self.connection.commit()

    def start_episode(self, mission, mode):
        if self.episode_id:
            self.finish_episode("superseded", "new episode started")
        self.episode_id = uuid.uuid4().hex
        self.execute(
            "INSERT INTO episodes(id, started_at, mission, mode) VALUES(?,?,?,?)",
            (self.episode_id, time.time(), mission[:240], mode[:40]),
        )
        self.record("recorder", "episode_started", {"mission": mission, "mode": mode})

    def finish_episode(self, outcome, reason):
        if not self.episode_id:
            return
        self.execute(
            "UPDATE episodes SET finished_at=?, outcome=?, final_reason=? WHERE id=?",
            (time.time(), outcome[:40], reason[:500], self.episode_id),
        )
        self.episode_id = ""

    def record(self, source, event_type, payload):
        if not self.episode_id:
            self.start_episode("automatic observation", "OBSERVE")
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        self.execute(
            "INSERT INTO events(episode_id, created_at, source, event_type, payload) "
            "VALUES(?,?,?,?,?)",
            (self.episode_id, time.time(), source[:80], event_type[:80], encoded[:8000]),
        )

    def on_odom(self, msg):
        self.last_pose = {
            "frame": msg.header.frame_id,
            "x": round(msg.pose.pose.position.x, 4),
            "y": round(msg.pose.pose.position.y, 4),
            "linear_x": round(msg.twist.twist.linear.x, 4),
            "angular_z": round(msg.twist.twist.angular.z, 4),
        }

    def on_status(self, source, value):
        value = str(value)[:4000]
        previous = self.last_values.get(source, "")
        if previous == value:
            return
        self.last_values[source] = value
        if source in {"safety", "autonomy", "mode"}:
            self.latest_context[source] = value
        now = time.monotonic()
        urgent_words = ("ERROR", "FAILED", "BLOCKED", "RECOVERED", "COLLISION", "EMERGENCY")
        upper = value.upper()
        previous_upper = previous.upper()
        newly_urgent = any(word in upper and word not in previous_upper for word in urgent_words)
        # Safety and autonomy payloads contain continuously changing ranges and
        # pose values.  Preserve periodic context and every new fault transition
        # without filling the NVMe with near-identical samples.
        if (
            source in {"safety", "autonomy"}
            and not newly_urgent
            and now - self.last_recorded_at.get(source, 0.0) < 5.0
        ):
            return
        self.last_recorded_at[source] = now
        self.record(source, "status_changed", {"value": value, "pose": self.last_pose})
        if source in {"recovery", "tight_recovery"} and (
            "RECOVERED" in upper or "BLOCKED" in upper or "FAILED" in upper
        ):
            outcome = "success" if "RECOVERED" in upper else "failure"
            self.execute(
                "INSERT INTO recovery_cases(episode_id, created_at, failure_class, "
                "strategy, outcome, context) VALUES(?,?,?,?,?,?)",
                (
                    self.episode_id,
                    time.time(),
                    source,
                    value[:500],
                    outcome,
                    json.dumps(
                        {"pose": self.last_pose, **self.latest_context},
                        separators=(",", ":"),
                    )[:8000],
                ),
            )

    def on_external_event(self, msg):
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                payload = {"value": payload}
        except Exception:
            payload = {"value": msg.data}
        source = str(payload.pop("source", "external"))
        event_type = str(payload.pop("event_type", "event"))
        self.record(source, event_type, payload)

    def start_service(self, _request, response):
        self.start_episode("operator requested mission", self.last_values.get("mode", "UNKNOWN"))
        response.success = True
        response.message = f"experience episode started: {self.episode_id}"
        return response

    def stop_service(self, _request, response):
        current = self.episode_id
        self.finish_episode("stopped", "operator requested stop")
        response.success = True
        response.message = f"experience episode stopped: {current}"
        return response

    def counts(self):
        episodes = self.connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        events = self.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        cases = self.connection.execute("SELECT COUNT(*) FROM recovery_cases").fetchone()[0]
        return episodes, events, cases

    def publish_status(self):
        episodes, events, cases = self.counts()
        payload = {
            "database": str(self.database),
            "episode": self.episode_id,
            "episodes": episodes,
            "events": events,
            "recovery_cases": cases,
        }
        self.status_pub.publish(
            String(data=json.dumps(payload, separators=(",", ":")))
        )

    def status_service(self, _request, response):
        episodes, events, cases = self.counts()
        response.success = True
        response.message = (
            f"episode={self.episode_id} episodes={episodes} events={events} "
            f"recovery_cases={cases} database={self.database}"
        )
        return response

    def prune(self):
        count = self.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        excess = count - self.max_events
        if excess > 0:
            self.execute(
                "DELETE FROM events WHERE id IN "
                "(SELECT id FROM events ORDER BY id ASC LIMIT ?)",
                (excess,),
            )

    def destroy_node(self):
        if self.episode_id:
            self.finish_episode("service_stopped", "recorder shutdown")
        self.connection.close()
        return super().destroy_node()


def main():
    rclpy.init()
    node = AtlasExperienceStore()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
