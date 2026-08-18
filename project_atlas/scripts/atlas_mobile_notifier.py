#!/usr/bin/env python3
"""Send deduplicated ATLAS boot and battery alerts to an ntfy mobile topic."""

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

from atlas_mobile_notifier_core import BatteryAlertState


class AtlasMobileNotifier(Node):
    def __init__(self) -> None:
        super().__init__("atlas_mobile_notifier")
        self.topic = os.environ.get("ATLAS_NTFY_TOPIC", "").strip()
        self.server = os.environ.get("ATLAS_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        self.dashboard_url = os.environ.get(
            "ATLAS_DASHBOARD_URL", "http://100.87.208.71:8088/"
        )
        self.state_path = Path(
            os.environ.get(
                "ATLAS_NOTIFY_STATE",
                str(Path.home() / ".local/state/project-atlas/mobile-notifier.json"),
            )
        )
        self.state = self._load_state()
        self.alerts = BatteryAlertState(
            low_threshold=float(os.environ.get("ATLAS_LOW_BATTERY_PERCENT", "20")),
            low_reset_threshold=float(os.environ.get("ATLAS_LOW_RESET_PERCENT", "25")),
            full_threshold=float(os.environ.get("ATLAS_FULL_BATTERY_PERCENT", "99")),
            full_reset_threshold=float(os.environ.get("ATLAS_FULL_RESET_PERCENT", "95")),
            low_alerted=bool(self.state.get("low_alerted", False)),
            full_alerted=bool(self.state.get("full_alerted", False)),
        )
        self.voltage: float | None = None
        self.current: float | None = None
        self.outbox: queue.Queue[dict] = queue.Queue()
        self.stop_worker = threading.Event()
        self.worker = threading.Thread(target=self._send_worker, daemon=True)
        self.worker.start()
        self.create_subscription(Float32, "/bms/percent", self.on_percent, 10)
        self.create_subscription(Float32, "/bms/voltage", self.on_voltage, 10)
        self.create_subscription(Float32, "/bms/current", self.on_current, 10)
        self.boot_id = self._boot_id()
        self.boot_queued = False
        self.get_logger().info(
            "Mobile notifier ready" if self.topic else
            "Mobile notifier disabled: ATLAS_NTFY_TOPIC is not configured"
        )

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        self.state.update(
            low_alerted=self.alerts.low_alerted,
            full_alerted=self.alerts.full_alerted,
        )
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.state_path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.state, separators=(",", ":")), encoding="utf-8")
            temp.replace(self.state_path)
        except OSError as exc:
            self.get_logger().warning(f"Cannot save notification state: {exc}")

    @staticmethod
    def _boot_id() -> str:
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        except OSError:
            return str(int(time.time()))

    def on_voltage(self, msg: Float32) -> None:
        self.voltage = float(msg.data)

    def on_current(self, msg: Float32) -> None:
        self.current = float(msg.data)

    def on_percent(self, msg: Float32) -> None:
        percent = float(msg.data)
        if not self.topic or not 0.0 <= percent <= 100.0:
            return
        if not self.boot_queued and self.state.get("boot_id") != self.boot_id:
            self.boot_queued = True
            self._queue(
                "atlas_online",
                "ATLAS is online",
                f"Hello Dhruv, ATLAS started successfully. Main battery: {percent:.0f}%.",
                priority=3,
                tags="robot,white_check_mark",
            )
        for alert in self.alerts.update(percent):
            if alert == "battery_low":
                self._queue(
                    alert,
                    "ATLAS battery low",
                    f"Dhruv, the main rover battery is {percent:.0f}%. Please return or charge ATLAS.",
                    priority=5,
                    tags="warning,battery",
                )
            elif alert == "battery_full":
                self._queue(
                    alert,
                    "ATLAS charging complete",
                    f"Dhruv, the main rover battery is fully charged ({percent:.0f}%).",
                    priority=4,
                    tags="battery,white_check_mark",
                )
        self._save_state()

    def _queue(self, kind: str, title: str, message: str, priority: int, tags: str) -> None:
        suffix = []
        if self.voltage is not None:
            suffix.append(f"{self.voltage:.2f} V")
        if self.current is not None:
            suffix.append(f"{self.current:+.2f} A")
        if suffix:
            message += " " + " / ".join(suffix)
        self.outbox.put({
            "kind": kind,
            "title": title,
            "message": message,
            "priority": str(priority),
            "tags": tags,
        })

    def _send_worker(self) -> None:
        while not self.stop_worker.is_set():
            try:
                item = self.outbox.get(timeout=1.0)
            except queue.Empty:
                continue
            while not self.stop_worker.is_set():
                try:
                    self._publish(item)
                    if item["kind"] == "atlas_online":
                        self.state["boot_id"] = self.boot_id
                        self._save_state()
                    self.get_logger().info(f"Mobile notification sent: {item['kind']}")
                    break
                except (OSError, urllib.error.URLError) as exc:
                    self.get_logger().warning(f"Notification send failed; retrying: {exc}")
                    self.stop_worker.wait(60.0)
            self.outbox.task_done()

    def _publish(self, item: dict) -> None:
        url = f"{self.server}/{urllib.parse.quote(self.topic, safe='')}"
        request = urllib.request.Request(
            url,
            data=item["message"].encode("utf-8"),
            method="POST",
            headers={
                "Title": item["title"],
                "Priority": item["priority"],
                "Tags": item["tags"],
                "Click": self.dashboard_url,
                "User-Agent": "Project-ATLAS/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status >= 300:
                raise OSError(f"ntfy returned HTTP {response.status}")

    def destroy_node(self) -> bool:
        self.stop_worker.set()
        self.worker.join(timeout=2.0)
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = AtlasMobileNotifier()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
