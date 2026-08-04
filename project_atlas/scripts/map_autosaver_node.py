#!/usr/bin/env python3
import os
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from nav_msgs.srv import GetMap
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


class MapAutosaver(Node):
    def __init__(self):
        super().__init__("map_autosaver")
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("output_prefix", "/home/jetson/project_atlas/maps/autosave")
        self.declare_parameter("save_interval_sec", 120.0)
        self.declare_parameter("occupied_thresh", 0.65)
        self.declare_parameter("free_thresh", 0.25)

        self.map_topic = self.get_parameter("map_topic").value
        self.map_service = "/slam_toolbox/dynamic_map"
        self.output_prefix = self.get_parameter("output_prefix").value
        self.save_interval_sec = float(self.get_parameter("save_interval_sec").value)
        self.occupied_thresh = float(self.get_parameter("occupied_thresh").value)
        self.free_thresh = float(self.get_parameter("free_thresh").value)
        self.last_save_time = 0.0
        self.last_signature = None

        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(OccupancyGrid, self.map_topic, self.map_callback, qos)
        self.map_client = self.create_client(GetMap, self.map_service)
        self.map_request_in_flight = False
        self.map_request_start_time = 0.0
        self.create_timer(self.save_interval_sec, self.request_dynamic_map)
        self.initial_timer = self.create_timer(10.0, self.request_initial_dynamic_map)
        self.get_logger().info(
            f"Autosaving {self.map_topic} to {self.output_prefix}.yaml every "
            f"{self.save_interval_sec:.0f}s when map data is available"
        )

    def request_initial_dynamic_map(self):
        self.initial_timer.cancel()
        self.request_dynamic_map()

    def request_dynamic_map(self):
        if self.map_request_in_flight:
            if time.monotonic() - self.map_request_start_time < 45.0:
                return
            self.get_logger().warning("Dynamic map request timed out; will retry")
            self.map_request_in_flight = False
        if not self.map_client.service_is_ready():
            self.get_logger().warning(f"{self.map_service} is not ready yet")
            return

        self.map_request_in_flight = True
        self.map_request_start_time = time.monotonic()
        future = self.map_client.call_async(GetMap.Request())
        future.add_done_callback(self.dynamic_map_response)

    def dynamic_map_response(self, future):
        self.map_request_in_flight = False
        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().warning(f"Dynamic map request failed: {exc}")
            return

        self.save_map(response.map)
        self.last_save_time = time.monotonic()

    def map_callback(self, msg):
        now = time.monotonic()
        signature = (
            msg.info.width,
            msg.info.height,
            msg.info.resolution,
            msg.info.origin.position.x,
            msg.info.origin.position.y,
            len(msg.data),
            hash(bytes((value + 1) & 0xFF for value in msg.data[:4096])),
        )
        if (
            self.last_signature == signature
            and now - self.last_save_time < self.save_interval_sec
        ):
            return
        if now - self.last_save_time < self.save_interval_sec:
            return

        self.save_map(msg)
        self.last_save_time = now
        self.last_signature = signature

    def save_map(self, msg):
        width = msg.info.width
        height = msg.info.height
        if width == 0 or height == 0 or len(msg.data) != width * height:
            self.get_logger().warning("Skipping invalid map message")
            return

        directory = os.path.dirname(self.output_prefix)
        os.makedirs(directory, exist_ok=True)
        pgm_path = self.output_prefix + ".pgm"
        yaml_path = self.output_prefix + ".yaml"
        tmp_pgm = pgm_path + ".tmp"
        tmp_yaml = yaml_path + ".tmp"

        with open(tmp_pgm, "wb") as pgm:
            pgm.write(f"P5\n# ROS 2 map autosave\n{width} {height}\n255\n".encode("ascii"))
            for y in range(height):
                map_y = height - y - 1
                row_start = map_y * width
                row = bytearray()
                for x in range(width):
                    value = msg.data[row_start + x]
                    if value < 0:
                        pixel = 205
                    elif value >= int(self.occupied_thresh * 100):
                        pixel = 0
                    elif value <= int(self.free_thresh * 100):
                        pixel = 254
                    else:
                        pixel = 205
                    row.append(pixel)
                pgm.write(row)

        origin = msg.info.origin
        yaw = self.quaternion_to_yaw(
            origin.orientation.x,
            origin.orientation.y,
            origin.orientation.z,
            origin.orientation.w,
        )
        with open(tmp_yaml, "w", encoding="ascii") as yaml:
            yaml.write("image: autosave.pgm\n")
            yaml.write(f"mode: trinary\n")
            yaml.write(f"resolution: {msg.info.resolution:.12g}\n")
            yaml.write(
                "origin: "
                f"[{origin.position.x:.12g}, {origin.position.y:.12g}, {yaw:.12g}]\n"
            )
            yaml.write("negate: 0\n")
            yaml.write(f"occupied_thresh: {self.occupied_thresh:.12g}\n")
            yaml.write(f"free_thresh: {self.free_thresh:.12g}\n")

        os.replace(tmp_pgm, pgm_path)
        os.replace(tmp_yaml, yaml_path)
        self.get_logger().info(f"Saved map to {yaml_path}")

    @staticmethod
    def quaternion_to_yaw(x, y, z, w):
        import math

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)


def main():
    rclpy.init()
    node = MapAutosaver()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
