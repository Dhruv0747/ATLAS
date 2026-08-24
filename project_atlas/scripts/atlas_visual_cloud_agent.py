#!/usr/bin/env python3
"""Read-only, low-overhead ROS graph telemetry agent for ATLAS.

This node creates subscriptions only. It intentionally exposes no ROS
publishers, services, actions, or cloud-to-robot command path.
"""

import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
import sqlite3

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.utilities import get_message

from atlas_visual_cloud_core import classify_failure, topic_stat


DEFAULT_CONFIG = Path("/home/jetson/project_atlas/config/atlas_visual_cloud.json")


def git_version():
    try:
        return subprocess.check_output(
            ["git", "-C", "/home/jetson/project_atlas", "rev-parse", "HEAD"],
            text=True, timeout=2, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        paths = (Path("/home/jetson/project_atlas/config/nav2_params.yaml"),)
        digest = hashlib.sha256()
        for path in paths:
            if path.exists():
                digest.update(path.read_bytes())
        return "config-" + digest.hexdigest()[:12]


def compact_message(topic, msg):
    """Extract bounded visualization data; never serialize full sensor frames."""
    if hasattr(msg, "pose") and hasattr(msg.pose, "pose"):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        return {"x": round(p.x, 4), "y": round(p.y, 4), "qz": round(q.z, 5), "qw": round(q.w, 5)}
    if hasattr(msg, "pose") and hasattr(msg.pose, "position"):
        p, q = msg.pose.position, msg.pose.orientation
        return {"x": round(p.x, 4), "y": round(p.y, 4), "qz": round(q.z, 5), "qw": round(q.w, 5)}
    if hasattr(msg, "poses"):
        return {"points": [[round(x.pose.position.x, 3), round(x.pose.position.y, 3)] for x in msg.poses[::max(1, len(msg.poses)//150 or 1)]]}
    if hasattr(msg, "ranges"):
        step = max(1, len(msg.ranges) // 180)
        return {"ranges": [round(float(x), 3) if float(x) < 100 else None for x in msg.ranges[::step]], "angle_min": msg.angle_min, "angle_increment": msg.angle_increment * step}
    if hasattr(msg, "info") and hasattr(msg, "data") and hasattr(msg.info, "width"):
        stride = max(1, int(max(msg.info.width, msg.info.height) / 120))
        cells = []
        for y in range(0, msg.info.height, stride):
            row = y * msg.info.width
            cells.append(list(msg.data[row:row + msg.info.width:stride]))
        return {"width": msg.info.width, "height": msg.info.height, "resolution": msg.info.resolution, "origin_x": msg.info.origin.position.x, "origin_y": msg.info.origin.position.y, "stride": stride, "cells": cells}
    if hasattr(msg, "linear") and hasattr(msg, "angular"):
        return {"linear_x": round(msg.linear.x, 4), "angular_z": round(msg.angular.z, 4)}
    if hasattr(msg, "data"):
        value = msg.data
        return value[:2000] if isinstance(value, str) else value
    if hasattr(msg, "transforms"):
        return {"transforms": [{"parent": t.header.frame_id, "child": t.child_frame_id} for t in msg.transforms[:100]]}
    return {"type": type(msg).__name__}


class VisualCloudAgent(Node):
    def __init__(self, config):
        super().__init__("atlas_visual_cloud_agent")
        self.config = config
        self.lock = threading.Lock()
        self.samples = {name: collections.deque(maxlen=100) for name in config["topics"]}
        self.values = {}
        self.subscriptions_live = []
        self.subscribed_topics = set()
        self.graph = {}
        self.last_graph = 0.0
        self.last_mission_read = 0.0
        self.mission_evidence = {"missions": [], "bags": []}
        self.token = Path(config["token_file"]).read_text(encoding="utf-8").strip()
        if not self.token:
            raise RuntimeError("visual cloud token is empty")
        self.discover_subscriptions()
        self.create_timer(10.0, self.discover_subscriptions)
        self.create_timer(float(config.get("publish_interval_s", 1.0)), self.queue_snapshot)
        self.pending = None
        self.sender = threading.Thread(target=self.send_loop, daemon=True)
        self.sender.start()

    def discover_subscriptions(self):
        types = dict(self.get_topic_names_and_types())
        for topic in self.config["topics"]:
            if topic in self.subscribed_topics:
                continue
            names = types.get(topic, [])
            if not names:
                continue
            try:
                cls = get_message(names[0])
                sub = self.create_subscription(cls, topic, lambda m, t=topic: self.on_message(t, m), qos_profile_sensor_data)
                self.subscriptions_live.append(sub)
                self.subscribed_topics.add(topic)
            except Exception as exc:
                self.get_logger().warning(f"cannot monitor {topic}: {exc}")

    def on_message(self, topic, msg):
        now = time.monotonic()
        with self.lock:
            self.samples[topic].append(now)
            self.values[topic] = compact_message(topic, msg)

    def graph_snapshot(self):
        nodes = []
        for name, namespace in self.get_node_names_and_namespaces():
            full = (namespace.rstrip("/") + "/" + name).replace("//", "/")
            nodes.append(full)
        topics = []
        for topic, type_names in self.get_topic_names_and_types():
            pubs = self.get_publishers_info_by_topic(topic)
            subs = self.get_subscriptions_info_by_topic(topic)
            topics.append({
                "name": topic, "types": type_names,
                "publishers": sorted({x.node_namespace.rstrip("/") + "/" + x.node_name for x in pubs}),
                "subscribers": sorted({x.node_namespace.rstrip("/") + "/" + x.node_name for x in subs}),
            })
        services = [{"name": n, "types": t} for n, t in self.get_service_names_and_types()]
        actions = sorted({s["name"].split("/_action/")[0] for s in services if "/_action/" in s["name"]})
        return {"nodes": sorted(nodes), "topics": topics, "services": services, "actions": actions}

    def system_metrics(self):
        def text(path):
            try: return Path(path).read_text().strip()
            except OSError: return ""
        mem = {}
        for line in text("/proc/meminfo").splitlines():
            if ":" in line: mem[line.split(":", 1)[0]] = int(line.split()[1])
        return {
            "load": [round(x, 2) for x in os.getloadavg()],
            "ram_used_pct": round(100 * (1 - mem.get("MemAvailable", 0) / max(1, mem.get("MemTotal", 1))), 1),
            "temperature_c": round(float(text("/sys/devices/virtual/thermal/thermal_zone0/temp") or 0) / 1000, 1),
        }

    def read_mission_evidence(self):
        """Read bounded existing evidence; never write or start a recorder."""
        db_path = Path("/home/jetson/project_atlas/data/experience/atlas_experience.sqlite3")
        missions = []
        if db_path.exists():
            try:
                db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
                rows = db.execute("SELECT created_at,outcome,failure_class,status,final_pose FROM mission_results ORDER BY created_at DESC LIMIT 20").fetchall()
                db.close()
                missions = [{"at": r[0], "outcome": r[1], "failure_class": r[2], "status": r[3], "final_pose": r[4]} for r in rows]
            except Exception as exc:
                missions = [{"error": str(exc)[:200]}]
        bag_root = Path("/home/jetson/project_atlas/data/demonstrations")
        bags = []
        try:
            for path in sorted(bag_root.glob("*/metadata.yaml"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                bags.append({"name": path.parent.name, "path": str(path.parent), "modified_at": path.stat().st_mtime})
        except OSError:
            pass
        return {"missions": missions, "bags": bags}

    def build_snapshot(self):
        now_mono = time.monotonic()
        if now_mono - self.last_graph >= float(self.config.get("graph_interval_s", 5)):
            self.graph = self.graph_snapshot()
            self.last_graph = now_mono
        if now_mono - self.last_mission_read >= 10.0:
            self.mission_evidence = self.read_mission_evidence()
            self.last_mission_read = now_mono
        with self.lock:
            traffic = {name: {**topic_stat(self.samples[name], now_mono, hz), "expected_hz": hz, "value": self.values.get(name)} for name, hz in self.config["topics"].items()}
        mission = str((traffic.get("/atlas/mission_status") or {}).get("value") or "")
        return {
            "schema": 1, "robot_id": self.config["robot_id"], "observed_at": time.time(),
            "git_version": git_version(), "system": self.system_metrics(),
            "traffic": traffic, "graph": self.graph,
            "mission_evidence": self.mission_evidence,
            "failure_class": classify_failure(mission) if any(x in mission.upper() for x in ("FAIL", "ABORT", "ERROR")) else "NONE",
            "authority": "OBSERVABILITY_ONLY",
        }

    def queue_snapshot(self):
        self.pending = self.build_snapshot()

    def send_loop(self):
        while rclpy.ok():
            snapshot, self.pending = self.pending, None
            if not snapshot:
                time.sleep(0.1); continue
            payload = gzip.compress(json.dumps(snapshot, separators=(",", ":")).encode())
            request = urllib.request.Request(self.config["cloud_url"], data=payload, method="POST", headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json", "Content-Encoding": "gzip"})
            try:
                urllib.request.urlopen(request, timeout=4).read()
            except Exception as exc:
                self.get_logger().warning(f"cloud unavailable; local control unaffected: {exc}")
            time.sleep(0.05)


def main():
    config_path = Path(os.environ.get("ATLAS_VISUAL_CLOUD_CONFIG", DEFAULT_CONFIG))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rclpy.init()
    node = VisualCloudAgent(config)
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()


if __name__ == "__main__": main()
