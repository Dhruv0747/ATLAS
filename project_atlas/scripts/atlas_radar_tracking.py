#!/usr/bin/env python3
"""Local radar observer. No actuator publishers; calibration-gated mux advice."""
import json
import math
import os
import struct
import time
from pathlib import Path
import yaml
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, LaserScan, PointCloud2, PointField
from geometry_msgs.msg import Twist
from std_msgs.msg import String, Int32, Header
from tf2_ros import Buffer, TransformListener
from atlas_radar_core import Tracker, risk


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


class RadarTracking(Node):
    def __init__(self):
        super().__init__('atlas_radar_tracking')
        path = os.environ.get('ATLAS_RADAR_TRACKING_CONFIG', '/home/jetson/project_atlas/config/radar_tracking.yaml')
        self.cfg = yaml.safe_load(Path(path).read_text())
        self.tracker = Tracker(self.cfg)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.pose = (0., 0., 0.)
        self.velocity = (0., 0., 0.)
        self.odom_at = self.imu_at = self.radar_at = self.scan_at = self.camera_at = -1e9
        self.pan_at = self.tilt_at = -1e9
        self.pan, self.tilt, self.imu_rate = 0, 0, 0.
        self.scan_points, self.people = [], []
        self.command, self.command_at = (0., 0.), -1e9
        self.last_sequence = -1
        self.fault = 'WAITING_FOR_DATA'
        self.frames = self.invalid = 0
        self.pub = self.create_publisher(String, '/radar/tracks', 10)
        self.diagnostic = self.create_publisher(String, '/radar/tracking_status', 10)
        self.guard = self.create_publisher(String, '/radar/speed_guard', 10)
        self.cloud = self.create_publisher(PointCloud2, '/radar/validated_obstacles', 10)
        self.create_subscription(String, '/radar/frames', self.on_frame, 10)
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        self.create_subscription(Imu, '/imu/data', self.on_imu, qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_subscription(String, '/camera/detections/json', self.on_camera, 10)
        self.create_subscription(Int32, '/camera/bottom_servo_us', self.on_pan, 10)
        self.create_subscription(Int32, '/camera/second_servo_us', self.on_tilt, 10)
        self.create_subscription(Twist, '/cmd_vel_nav', self.on_command, 10)
        self.create_timer(0.1, self.tick)

    def stamp_fresh(self, stamp, limit):
        age = (self.get_clock().now().nanoseconds-Time.from_msg(stamp).nanoseconds)/1e9
        return -0.05 <= age <= limit

    def on_odom(self, msg):
        if msg.header.frame_id != 'odom' or msg.child_frame_id != 'base_link':
            self.fault = 'ODOM_FRAME_MISMATCH'
            return
        if not self.stamp_fresh(msg.header.stamp, self.cfg['ego_timeout_s']):
            return
        p, v = msg.pose.pose, msg.twist.twist
        values = (p.position.x, p.position.y, yaw(p.orientation), v.linear.x, v.linear.y, v.angular.z)
        if all(math.isfinite(x) for x in values):
            self.pose, self.velocity = values[:3], values[3:]
            self.odom_at = time.monotonic()

    def on_imu(self, msg):
        if (msg.header.frame_id == 'base_link' and
                self.stamp_fresh(msg.header.stamp, self.cfg['ego_timeout_s']) and
                math.isfinite(msg.angular_velocity.z)):
            self.imu_rate, self.imu_at = msg.angular_velocity.z, time.monotonic()

    def on_pan(self, msg):
        self.pan, self.pan_at = msg.data, time.monotonic()

    def on_tilt(self, msg):
        self.tilt, self.tilt_at = msg.data, time.monotonic()

    def transform(self, frame, stamp):
        if frame == 'base_link':
            return 0., 0., 0.
        t = self.tf.lookup_transform('base_link', frame, stamp).transform
        return t.translation.x, t.translation.y, yaw(t.rotation)

    def on_scan(self, msg):
        if not self.stamp_fresh(msg.header.stamp, self.cfg['fusion_timeout_s']):
            return
        try:
            x, y, angle = self.transform(msg.header.frame_id, Time.from_msg(msg.header.stamp))
            points = []
            for i, distance in enumerate(msg.ranges):
                if math.isfinite(distance) and msg.range_min <= distance <= min(8.5, msg.range_max):
                    a = msg.angle_min+i*msg.angle_increment+angle
                    points.append((x+distance*math.cos(a), y+distance*math.sin(a)))
            self.scan_points, self.scan_at = points, time.monotonic()
        except Exception as exc:
            self.scan_points = []
            self.fault = 'LIDAR_TF_UNAVAILABLE: '+type(exc).__name__

    def on_camera(self, msg):
        self.people = []
        now = time.monotonic()
        if not self.cfg['camera_alignment_verified']:
            return
        # Fixed camera extrinsics only apply at the calibrated pan/tilt pose.
        if (now-self.pan_at > 1. or now-self.tilt_at > 1. or
                abs(self.pan-self.cfg['camera_pan_center_us']) > 40 or
                abs(self.tilt-self.cfg['camera_tilt_center_us']) > 40):
            return
        try:
            data = json.loads(msg.data)
            width = float(data['width'])
            if not math.isfinite(width) or width <= 0:
                return
            x, y, a = self.transform(self.cfg['camera_frame'], Time())
            for d in data.get('detections', [])[:100]:
                if d.get('label') != 'person' or float(d['confidence']) < 0.6:
                    continue
                center = (float(d['x1'])+float(d['x2']))/2
                bearing = a+math.atan((0.5-center/width)*2*math.tan(self.cfg['camera_hfov_rad']/2))
                if math.isfinite(bearing):
                    self.people.append((x, y, bearing))
            self.camera_at = now
        except (ValueError, KeyError, TypeError):
            self.invalid += 1
        except Exception as exc:
            self.fault = 'CAMERA_TF_UNAVAILABLE: '+type(exc).__name__

    def on_command(self, msg):
        if math.isfinite(msg.linear.x) and math.isfinite(msg.angular.z):
            self.command, self.command_at = (msg.linear.x, msg.angular.z), time.monotonic()

    def on_frame(self, msg):
        now = time.monotonic()
        try:
            data = json.loads(msg.data)
            age = self.get_clock().now().nanoseconds/1e9-float(data['stamp_s'])
            if not -0.05 <= age <= self.cfg['radar_timeout_s']:
                raise ValueError('old timestamp')
            seq = int(data['sequence'])
            if seq <= self.last_sequence:
                self.tracker.clear()
                if seq == self.last_sequence:
                    return
            self.last_sequence = seq
            targets = data['targets']
            if not isinstance(targets, list) or len(targets) > 3:
                raise ValueError('invalid target count')
            for t in targets:
                if not all(math.isfinite(float(t[k])) for k in ('slot', 'x_mm', 'y_mm', 'speed_cm_s')):
                    raise ValueError('nonfinite target')
                if not (1 <= t['slot'] <= 3 and t['y_mm'] > 0 and
                        50 <= math.hypot(t['x_mm'], t['y_mm']) <= 8500 and abs(t['speed_cm_s']) <= 1000):
                    raise ValueError('out of range target')
            self.radar_at = now
            self.frames += 1
            if now-self.odom_at > self.cfg['ego_timeout_s']:
                self.tracker.clear()
                self.fault = 'ODOMETRY_STALE'
                return
            self.tracker.update(targets, now, self.pose, self.velocity)
            self.fault = ''
        except (ValueError, KeyError, TypeError):
            self.invalid += 1
            self.fault = 'INVALID_RADAR_FRAME'

    def tick(self):
        now = time.monotonic()
        missing = [k for k in ('protocol_verified', 'alignment_verified',
                              'speed_sign_verified', 'braking_verified') if not self.cfg[k]]
        reason = 'UNCALIBRATED' if missing else ''
        if now-self.radar_at > self.cfg['radar_timeout_s']:
            reason = 'RADAR_STALE'
            self.tracker.clear()
        if now-self.odom_at > self.cfg['ego_timeout_s']:
            reason = 'ODOMETRY_STALE'
            self.tracker.clear()
        turning = abs(self.velocity[2]) > .05 or (now-self.command_at < .5 and abs(self.command[1]) > .05)
        if turning and (not self.cfg['imu_yaw_verified'] or now-self.imu_at > .35 or
                        abs(self.imu_rate-self.velocity[2]) > .3):
            reason = 'TURN_EGO_MOTION_UNVERIFIED'
        if now-self.scan_at > self.cfg['fusion_timeout_s']:
            reason = 'LIDAR_OR_TF_STALE'
        tracks = self.tracker.snapshot(now, self.pose)
        candidates = []
        for t in tracks:
            obj = next(v for v in self.tracker.tracks if v.id == t['track_id'])
            if t['age_s'] > .2:
                continue
            lidar_match = now-self.scan_at <= self.cfg['fusion_timeout_s'] and any(
                math.hypot(x-t['x_m'], y-t['y_m']) < self.cfg['camera_lidar_gate_m'] for x, y in self.scan_points)
            if lidar_match:
                obj.lidar_at = self.scan_at
                if now-self.camera_at <= .25 and not t['ambiguous']:
                    for index, (cx, cy, bearing) in enumerate(self.people):
                        delta = math.atan2(t['y_m']-cy, t['x_m']-cx)-bearing
                        error = abs(math.atan2(math.sin(delta), math.cos(delta)))
                        if error < self.cfg['camera_bearing_gate_rad']:
                            candidates.append((error, t['track_id'], index))
        used_tracks, used_people = set(), set()
        for _, ident, index in sorted(candidates):
            if ident not in used_tracks and index not in used_people:
                next(t for t in self.tracker.tracks if t.id == ident).camera_at = self.camera_at
                used_tracks.add(ident)
                used_people.add(index)
        tracks = self.tracker.snapshot(now, self.pose)
        speed, omega = self.velocity[0], self.velocity[2]
        if now-self.command_at < .5:
            if abs(self.command[0]) > abs(speed):
                speed = self.command[0]
            omega = self.command[1]
        advice = risk(tracks, speed, omega, self.cfg)
        if reason or self.fault:
            advice.update(scale=0., reason=reason or self.fault)
        advice.update(qualified=not (reason or self.fault), stamp_s=self.get_clock().now().nanoseconds/1e9,
                      scope='NAV2_FORWARD_ONLY', calibration_missing=missing)
        payload = dict(advice, tracks=tracks, frame_id='base_link',
                       radar_age_s=min(999., now-self.radar_at), frames=self.frames,
                       invalid_frames=self.invalid, firmware=self.cfg['installed_firmware'],
                       mode='OBSERVATION_UNLESS_MUX_GATE_ENABLED')
        self.pub.publish(String(data=json.dumps(payload, allow_nan=False)))
        self.diagnostic.publish(String(data=json.dumps(payload, allow_nan=False)))
        self.guard.publish(String(data=json.dumps(advice, allow_nan=False)))
        # Empty clouds do not erase old Nav2 marks. Integration into a decaying
        # layer must be tested before enabling this candidate source in Nav2.
        points = [t for t in tracks if advice['qualified'] and t['lidar_confirmed'] and
                  t['confidence'] >= .6 and t['age_s'] <= .2]
        cloud = PointCloud2(header=Header(stamp=self.get_clock().now().to_msg(), frame_id='base_link'),
                            height=1, width=len(points), is_bigendian=False, point_step=12,
                            row_step=12*len(points), is_dense=True)
        cloud.fields = [PointField(name=n, offset=i*4, datatype=PointField.FLOAT32, count=1)
                        for i, n in enumerate(('x', 'y', 'z'))]
        cloud.data = b''.join(struct.pack('<fff', t['x_m'], t['y_m'], .2) for t in points)
        self.cloud.publish(cloud)


def main():
    rclpy.init()
    node = RadarTracking()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
