#!/usr/bin/env python3
"""Deterministic, watchdog-protected velocity multiplexer for Project ATLAS."""

from dataclasses import dataclass, field
import math
import time
from typing import Dict, Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32, String


@dataclass
class Channel:
    name: str
    topic: str
    priority: int
    timeout: float
    last_rx: float = 0.0
    command: Twist = field(default_factory=Twist)
    engaged: bool = False


class AtlasCmdVelMux(Node):
    """Select the highest-priority live command and stop on stale ownership."""

    def __init__(self):
        super().__init__("atlas_cmd_vel_mux")
        self.declare_parameter("watchdog_period", 0.05)
        self.declare_parameter("manual_timeout", 0.35)
        self.declare_parameter("nav_timeout", 0.50)
        self.declare_parameter("foxglove_max_linear", 0.20)
        self.declare_parameter("foxglove_max_angular", 0.45)
        self.declare_parameter("foxglove_steering_expo", 2.0)
        self.declare_parameter("auto_front_stop_m", 0.30)
        self.declare_parameter("auto_side_stop_m", 0.18)
        self.declare_parameter("auto_reaction_time_s", 1.0)
        self.declare_parameter("auto_stop_margin_m", 0.15)
        self.declare_parameter("ultrasonic_timeout", 1.0)

        manual_timeout = float(self.get_parameter("manual_timeout").value)
        nav_timeout = float(self.get_parameter("nav_timeout").value)
        self.foxglove_max_linear = float(
            self.get_parameter("foxglove_max_linear").value
        )
        self.foxglove_max_angular = float(
            self.get_parameter("foxglove_max_angular").value
        )
        self.foxglove_steering_expo = float(
            self.get_parameter("foxglove_steering_expo").value
        )
        self.auto_front_stop_m = float(
            self.get_parameter("auto_front_stop_m").value
        )
        self.auto_side_stop_m = float(
            self.get_parameter("auto_side_stop_m").value
        )
        self.auto_reaction_time_s = float(
            self.get_parameter("auto_reaction_time_s").value
        )
        self.auto_stop_margin_m = float(
            self.get_parameter("auto_stop_margin_m").value
        )
        self.ultrasonic_timeout = float(
            self.get_parameter("ultrasonic_timeout").value
        )
        self.ultrasonic = {"front": float("inf"), "left": float("inf"), "right": float("inf")}
        self.ultrasonic_rx = {"front": 0.0, "left": 0.0, "right": 0.0}
        self.channels: Dict[str, Channel] = {
            "REMOTE": Channel("REMOTE", "/cmd_vel_joy", 1, manual_timeout),
            "WEB": Channel("WEB", "/cmd_vel_web", 2, manual_timeout),
            "FOXGLOVE": Channel(
                "FOXGLOVE", "/cmd_vel_teleop", 3, manual_timeout
            ),
            "NAV2": Channel("NAV2", "/cmd_vel_nav", 4, nav_timeout),
        }

        self.output = self.create_publisher(Twist, "/cmd_vel", 10)
        self.mode_output = self.create_publisher(String, "/atlas/drive_mode", 10)
        self.safety_output = self.create_publisher(
            String, "/atlas/motion_safety", 10
        )
        self.active_name: Optional[str] = None
        self.last_sent = Twist()

        for channel in self.channels.values():
            self.create_subscription(
                Twist,
                channel.topic,
                lambda msg, name=channel.name: self.on_command(name, msg),
                10,
            )
        for side in ("front", "left", "right"):
            self.create_subscription(
                Float32,
                f"/ultrasonic/{side}_mm",
                lambda msg, sensor=side: self.on_ultrasonic(sensor, msg),
                10,
            )

        period = float(self.get_parameter("watchdog_period").value)
        self.create_timer(period, self.watchdog)
        self.create_timer(0.5, self.publish_mode)
        hierarchy = " > ".join(
            c.name for c in sorted(self.channels.values(), key=lambda c: c.priority)
        )
        self.get_logger().info(f"ATLAS cmd_vel priority: {hierarchy}")

    @staticmethod
    def moving(msg: Twist) -> bool:
        return any(
            abs(value) > 1.0e-4
            for value in (
                msg.linear.x, msg.linear.y, msg.linear.z,
                msg.angular.x, msg.angular.y, msg.angular.z,
            )
        )

    @staticmethod
    def copy_twist(msg: Twist) -> Twist:
        out = Twist()
        out.linear.x, out.linear.y, out.linear.z = (
            msg.linear.x, msg.linear.y, msg.linear.z
        )
        out.angular.x, out.angular.y, out.angular.z = (
            msg.angular.x, msg.angular.y, msg.angular.z
        )
        return out

    def on_command(self, name: str, msg: Twist) -> None:
        channel = self.channels[name]
        channel.last_rx = time.monotonic()
        command = self.copy_twist(msg)
        if name == "FOXGLOVE":
            command.linear.x = max(
                -self.foxglove_max_linear,
                min(self.foxglove_max_linear, command.linear.x),
            )
            command.angular.z = max(
                -self.foxglove_max_angular,
                min(self.foxglove_max_angular, command.angular.z),
            )
            # Exponential steering gives fine centre-stick control while
            # preserving the full steering range at the edge of the joystick.
            if self.foxglove_max_angular > 0.0:
                normalized = command.angular.z / self.foxglove_max_angular
                command.angular.z = (
                    math.copysign(
                        abs(normalized) ** self.foxglove_steering_expo,
                        normalized,
                    )
                    * self.foxglove_max_angular
                )
            command.linear.y = 0.0
            command.linear.z = 0.0
            command.angular.x = 0.0
            command.angular.y = 0.0
        channel.command = command

        if self.moving(command):
            channel.engaged = True
            return

        # A zero from the current owner is an explicit release/stop. Idle zero
        # heartbeats from an unengaged panel never steal control.
        if channel.engaged or self.active_name == name:
            channel.engaged = False
            if self.active_name == name:
                self.publish_stop(f"{name} released")

    def on_ultrasonic(self, sensor: str, msg: Float32) -> None:
        value_m = float(msg.data) / 1000.0
        if value_m > 0.0:
            self.ultrasonic[sensor] = value_m
            self.ultrasonic_rx[sensor] = time.monotonic()

    def autonomous_guard(self, command: Twist, now: float) -> Optional[str]:
        # Ultrasonics supplement the LiDAR/Nav2 costmaps. A disconnected side
        # sensor must not deadlock all autonomy; only a fresh positive reading
        # may veto motion. Sensor health is still published below as DEGRADED.
        fresh = {
            name: stamp > 0.0 and now - stamp <= self.ultrasonic_timeout
            for name, stamp in self.ultrasonic_rx.items()
        }
        # Account for the distance travelled while ROS, the motor controller,
        # and the drivetrain react. The fixed floor protects low-speed motion;
        # the dynamic term grows automatically if autonomy is later made faster.
        front_stop_m = max(
            self.auto_front_stop_m,
            abs(command.linear.x) * self.auto_reaction_time_s
            + self.auto_stop_margin_m,
        )
        if (
            command.linear.x > 0.0
            and fresh["front"]
            and self.ultrasonic["front"] < front_stop_m
        ):
            return (
                "AUTONOMY BLOCKED: FRONT "
                f"{self.ultrasonic['front']:.2f} m "
                f"(stop {front_stop_m:.2f} m)"
            )
        if (
            command.angular.z > 0.05
            and fresh["left"]
            and self.ultrasonic["left"] < self.auto_side_stop_m
        ):
            return (
                "AUTONOMY BLOCKED: LEFT "
                f"{self.ultrasonic['left']:.2f} m"
            )
        if (
            command.angular.z < -0.05
            and fresh["right"]
            and self.ultrasonic["right"] < self.auto_side_stop_m
        ):
            return (
                "AUTONOMY BLOCKED: RIGHT "
                f"{self.ultrasonic['right']:.2f} m"
            )
        return None

    def live_channel(self, now: float) -> Optional[Channel]:
        live = [
            c for c in self.channels.values()
            if c.engaged and (now - c.last_rx) <= c.timeout
        ]
        return min(live, key=lambda c: c.priority) if live else None

    def publish(self, msg: Twist) -> None:
        self.last_sent = self.copy_twist(msg)
        self.output.publish(msg)

    def publish_stop(self, reason: str) -> None:
        self.output.publish(Twist())
        self.last_sent = Twist()
        self.active_name = None
        self.safety_output.publish(String(data="AUTONOMY IDLE"))
        self.get_logger().warn(f"Safety stop: {reason}")
        self.publish_mode()

    def watchdog(self) -> None:
        now = time.monotonic()

        if self.active_name:
            active = self.channels[self.active_name]
            if active.engaged and (now - active.last_rx) > active.timeout:
                active.engaged = False
                # Stop in this cycle. A lower-priority source can take control
                # only on the next watchdog cycle.
                self.publish_stop(
                    f"{active.name} stale for {now - active.last_rx:.3f}s"
                )
                return

        selected = self.live_channel(now)
        if selected is None:
            if self.moving(self.last_sent):
                self.publish_stop("no live command source")
            elif self.active_name is not None:
                self.active_name = None
                self.safety_output.publish(String(data="AUTONOMY IDLE"))
                self.publish_mode()
            return

        self.active_name = selected.name
        if selected.name == "NAV2":
            blocked_reason = self.autonomous_guard(selected.command, now)
            if blocked_reason:
                self.output.publish(Twist())
                self.last_sent = Twist()
                self.safety_output.publish(String(data=blocked_reason))
                return
            stale = [
                name for name, stamp in self.ultrasonic_rx.items()
                if stamp <= 0.0 or now - stamp > self.ultrasonic_timeout
            ]
            health = (
                "AUTONOMY DEGRADED: ULTRASONIC STALE " + ",".join(stale)
                if stale
                else "AUTONOMY CLEAR:"
            )
            self.safety_output.publish(
                String(
                    data=(
                        f"{health} "
                        f"F {self.ultrasonic['front']:.2f} m "
                        f"L {self.ultrasonic['left']:.2f} m "
                        f"R {self.ultrasonic['right']:.2f} m"
                    )
                )
            )
        self.publish(selected.command)

    def publish_mode(self) -> None:
        mode = self.active_name or "STOPPED"
        self.mode_output.publish(String(data=mode))

    def shutdown_stop(self) -> None:
        if not rclpy.ok():
            return
        for _ in range(3):
            self.output.publish(Twist())
            time.sleep(0.02)


def main(args=None):
    rclpy.init(args=args)
    node = AtlasCmdVelMux()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.shutdown_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
