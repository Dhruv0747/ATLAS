#!/usr/bin/env python3
"""ATLAS LiDAR keyframe-ICP odometry (read-only sensor node; never commands motion).

Subscribes /scan, applies the base_link <- laser mount from TF (the ATLAS laser faces backwards),
and publishes /lidar/icp_odom (nav_msgs/Odometry, odom -> base_link): the ICP pose plus body-frame
vx/vy for EKF fusion. Rejected matches publish nothing, so the EKF falls back to the wheels.
Health JSON on /lidar/icp_odom/health at 1 Hz.
"""
import json
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener

from atlas_icp_odometry_core import IcpOdometry, body_velocity, scan_to_points


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class AtlasIcpOdometry(Node):
    def __init__(self):
        super().__init__('atlas_icp_odometry')
        self.base_frame = self.declare_parameter('base_frame', 'base_link').value
        self.vel_variance = float(self.declare_parameter('velocity_variance', 0.01).value)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.mount = None
        self.odom = IcpOdometry()
        self.prev = None          # (stamp_s, pose)
        self.proc_ms = 0.0
        self.scans = 0
        self.pub = self.create_publisher(Odometry, '/lidar/icp_odom', 10)
        self.health_pub = self.create_publisher(String, '/lidar/icp_odom/health', 10)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_timer(1.0, self.publish_health)

    def lookup_mount(self, frame):
        try:
            tr = self.tf_buffer.lookup_transform(self.base_frame, frame, rclpy.time.Time())
        except Exception:
            return None
        t = tr.transform
        return (t.translation.x, t.translation.y, yaw_of(t.rotation))

    def on_scan(self, msg: LaserScan):
        if self.mount is None:
            self.mount = self.lookup_mount(msg.header.frame_id)
            if self.mount is None:
                return
            self.get_logger().info(f'laser mount in {self.base_frame}: x={self.mount[0]:.3f} y={self.mount[1]:.3f} '
                                   f'yaw={math.degrees(self.mount[2]):.1f} deg')
        t0 = time.perf_counter()
        pts = scan_to_points(msg.ranges, msg.angle_min, msg.angle_increment, *self.mount, self.odom.cfg)
        pose, ok = self.odom.update(pts)
        self.proc_ms = 0.9 * self.proc_ms + 0.1 * (time.perf_counter() - t0) * 1000.0
        self.scans += 1
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if not ok:
            self.prev = None        # never difference across a rejected scan
            return
        if self.prev is None or not (0.02 < stamp - self.prev[0] < 0.5):
            self.prev = (stamp, pose)
            return
        vx, vy, wz = body_velocity(self.prev[1], pose, stamp - self.prev[0])
        self.prev = (stamp, pose)
        out = Odometry()
        out.header.stamp = msg.header.stamp
        out.header.frame_id = 'odom'
        out.child_frame_id = self.base_frame
        out.pose.pose.position.x, out.pose.pose.position.y = pose[0], pose[1]
        out.pose.pose.orientation.z, out.pose.pose.orientation.w = math.sin(pose[2] / 2), math.cos(pose[2] / 2)
        pc = [0.0] * 36; pc[0] = pc[7] = 0.05; pc[35] = 0.1; pc[14] = pc[21] = pc[28] = 1e6
        out.pose.covariance = pc
        out.twist.twist.linear.x, out.twist.twist.linear.y, out.twist.twist.angular.z = vx, vy, wz
        tc = [0.0] * 36; tc[0] = tc[7] = self.vel_variance; tc[35] = 0.05; tc[14] = tc[21] = tc[28] = 1e6
        out.twist.covariance = tc
        self.pub.publish(out)

    def publish_health(self):
        self.health_pub.publish(String(data=json.dumps({
            'mount_ok': self.mount is not None, 'scans': self.scans, 'accepted': self.odom.accepted,
            'rejected': self.odom.rejected, 'last_inliers': round(self.odom.last_inliers, 3),
            'proc_ms': round(self.proc_ms, 1)})))


def main():
    rclpy.init()
    node = AtlasIcpOdometry()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
