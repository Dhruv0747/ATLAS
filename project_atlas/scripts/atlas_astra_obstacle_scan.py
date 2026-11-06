#!/usr/bin/env python3
"""Track A (STAGED, inactive): /astra/depth/image_raw -> /astra/obstacle_scan (LaserScan, frame base_link).

Runs in the Astra private ROS domain (77). Read-only sensor node: no velocity, servo, map or driver control.
Startup refuses (exit 78, no restart loop) on an incomplete or implausible mount/scan config.
Intrinsics: FACTORY / driver-supplied calibration, read at runtime from /astra/depth/camera_info and validated
(core.validate_camera_info) before any scan is published; re-validated whenever it changes.
Publishes a scan only for fresh, sufficiently valid frames; otherwise publishes nothing (never an all-clear) and
reports why on /astra/obstacle_scan_status (JSON, 1 Hz):
OK | STALE | BLINDED | NO_FRAMES | BAD_FRAME | NO_CALIBRATION | BAD_CALIBRATION.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_astra_obstacle_core as core  # noqa: E402

REFUSE = 78   # systemd unit: RestartPreventExitStatus=78


def main():
    import yaml
    try:
        cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
        scanner = core.ObstacleScanner(cfg)
    except Exception as e:  # missing/implausible mount or scan config
        print('atlas_astra_obstacle_scan: REFUSING TO START - ' + str(e), file=sys.stderr, flush=True)
        sys.exit(REFUSE)
    if '--preflight' in sys.argv:   # systemd ExecCondition: config gate only, no ROS (calibration is runtime)
        print('atlas_astra_obstacle_scan: preflight OK', flush=True)
        return

    import numpy as np
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import CameraInfo, Image, LaserScan
    from std_msgs.msg import String

    class ScanNode(Node):
        def __init__(self):
            super().__init__('atlas_astra_obstacle_scan')
            qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
            self.pub = self.create_publisher(LaserScan, '/astra/obstacle_scan', 5)
            self.status_pub = self.create_publisher(String, '/astra/obstacle_scan_status', 5)
            self.create_subscription(Image, '/astra/depth/image_raw', self.on_depth, qos)
            self.create_subscription(CameraInfo, '/astra/depth/camera_info', self.on_info, qos)
            self.cal_state, self.cal_detail, self.last_info_key = 'NO_CALIBRATION', {}, None
            self.min_period = 1.0 / float(scanner.s['max_rate_hz'])
            self.last_processed = 0.0
            self.last_frame_mono = None
            self.state, self.detail = 'NO_FRAMES', {}
            self.published = 0
            self.create_timer(1.0, self.on_status)

        def on_info(self, msg):
            key = (msg.width, msg.height, msg.header.frame_id, tuple(msg.k), tuple(msg.d), msg.distortion_model)
            if key == self.last_info_key:
                return
            self.last_info_key = key
            try:
                cal = core.validate_camera_info(*key[:3], list(msg.k), list(msg.d), msg.distortion_model)
            except core.CalibrationError as e:
                scanner.clear_calibration()              # an invalid update stops publishing immediately
                self.cal_state, self.cal_detail = 'BAD_CALIBRATION', {'calibration_error': str(e)[:200]}
                self.get_logger().error('depth CameraInfo rejected: ' + str(e))
                return
            scanner.set_calibration(cal)
            self.cal_state = 'OK'
            self.cal_detail = {'calibration_source': cal['source'], 'calibration_nominal': cal['nominal'],
                               'fx': round(cal['k'][0], 3), 'fy': round(cal['k'][4], 3),
                               'cx': round(cal['k'][2], 3), 'cy': round(cal['k'][5], 3), 'd': cal['d']}
            self.get_logger().info('depth calibration loaded at runtime: ' + json.dumps(self.cal_detail))

        def on_depth(self, msg):
            now_mono = time.monotonic()
            self.last_frame_mono = now_mono
            if now_mono - self.last_processed < self.min_period:
                return                                   # rate cap: drop extra frames, never queue them
            self.last_processed = now_mono
            if self.cal_state != 'OK':
                self.state, self.detail = self.cal_state, {}
                return                                   # no validated intrinsics: publish nothing
            try:
                if (msg.width, msg.height) != (160, 120) or msg.header.frame_id != 'astra_depth_optical_frame':
                    raise ValueError('unexpected depth geometry/frame')
                dtype = {'16UC1': np.uint16, '32FC1': np.float32}.get(msg.encoding)
                if dtype is None:
                    raise ValueError('unsupported encoding ' + msg.encoding)
                row = msg.step // np.dtype(dtype).itemsize
                arr = np.frombuffer(bytes(msg.data), dtype=dtype)
                if msg.is_bigendian:
                    arr = arr.byteswap()
                depth = arr.reshape(120, row)[:, :160]
                ranges, stats = scanner.scan(depth, msg.encoding)
            except Exception as e:
                self.state, self.detail = 'BAD_FRAME', {'error': str(e)[:160]}
                return
            stamp_s = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            age = self.get_clock().now().nanoseconds * 1e-9 - stamp_s
            decision = scanner.decide(stats, age)
            self.state, self.detail = decision, dict(stats, age_s=round(age, 3))
            if decision != 'OK':
                return                                   # never publish a stale or blinded (all-clear) scan
            out = LaserScan()
            out.header.stamp = msg.header.stamp          # original sensor time: Nav2 transforms at capture time
            out.header.frame_id = 'base_link'
            out.angle_min, out.angle_increment = scanner.amin, scanner.inc
            out.angle_max = scanner.amin + scanner.inc * (scanner.nbins - 1)
            out.time_increment = 0.0
            out.scan_time = self.min_period
            out.range_min, out.range_max = float(scanner.s['range_min_m']), float(scanner.s['range_max_m'])
            out.ranges = ranges.tolist()
            self.pub.publish(out)
            self.published += 1

        def on_status(self):
            if self.last_frame_mono is None or time.monotonic() - self.last_frame_mono > scanner.s['stale_s']:
                self.state = 'NO_FRAMES' if self.last_frame_mono is None else 'STALE'   # camera gone or stalled
            msg = String()
            if self.cal_state != 'OK' and self.state not in ('NO_FRAMES', 'STALE'):
                self.state = self.cal_state
            msg.data = json.dumps({'state': self.state, 'published': self.published, **self.detail,
                                   'calibration': self.cal_state, **self.cal_detail})
            self.status_pub.publish(msg)
            if self.state != 'OK':
                self.get_logger().warning('obstacle scan not published: ' + self.state, throttle_duration_sec=30.0)

    rclpy.init()
    node = ScanNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
