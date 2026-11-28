#!/usr/bin/env python3
"""ATLAS camera visual odometry, SHADOW MODE (master-plan step 7, 2026-11-23). Read-only, publishes estimates only.

Runs in the Astra private ROS domain 77 (refuses any other domain) next to atlas-astra-obstacles:
  in   /astra/obstacle_scan   (LaserScan, base_link; published only for fresh, validated, non-blinded depth frames)
  out  /astra/vo/odom         (nav_msgs/Odometry, frame 'vo_odom' -> child 'vo_base_link'; NO TF is broadcast)
       /astra/vo/status       (std_msgs/String JSON, 2 Hz: state GOOD/DEGRADED/LOST, rate_hz, age_s, confidence, ...)
       ~/.local/state/project_atlas/vo_shadow_status.json   (same JSON, 2 Hz, atomic; read by the step-7 owner test
                                                            and by the turn check to compare against LiDAR-ICP)
Nothing in domain 77 consumes these, the Astra bridge relays only the obstacle scans to domain 0, and the EKF / Nav2
configs name no VO topic: the estimate cannot reach the EKF, Nav2 or any velocity path.
CPU: processing capped at 10 Hz (extra scans dropped, never queued); ~5 ms per scan on the Jetson (synthetic);
the systemd unit adds CPUQuota=20% and Nice=10. Its own CPU use is reported as cpu_pct.
Method and states: scripts/atlas_vo_core.py.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_vo_core as core  # noqa: E402

DOMAIN = '77'
STATUS_FILE = Path.home() / '.local/state/project_atlas/vo_shadow_status.json'
REFUSE = 78


def write_status(data, path=STATUS_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data), encoding='utf-8')
    tmp.replace(path)


def main():
    if os.environ.get('ROS_DOMAIN_ID') != DOMAIN:
        print('atlas_vo_shadow: REFUSING - must run in the Astra private domain ROS_DOMAIN_ID=77 (shadow mode)',
              file=sys.stderr, flush=True)
        sys.exit(REFUSE)
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String

    cfg = core.VoConfig()
    tracker = core.VoTracker(cfg)

    class VoShadow(Node):
        def __init__(self):
            super().__init__('atlas_vo_shadow')
            qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
            self.create_subscription(LaserScan, '/astra/obstacle_scan', self.on_scan, qos)
            self.odom_pub = self.create_publisher(Odometry, '/astra/vo/odom', 5)
            self.status_pub = self.create_publisher(String, '/astra/vo/status', 5)
            self.min_period = 1.0 / cfg.max_rate_hz
            self.last_t = 0.0
            self.cpu = (time.monotonic(), time.process_time())
            self.cpu_pct = None
            self.errors = 0
            self.create_timer(0.5, self.on_status)

        def now_s(self):
            return self.get_clock().now().nanoseconds * 1e-9

        def on_scan(self, m):
            mono = time.monotonic()
            if mono - self.last_t < self.min_period:
                return                                   # rate cap: drop, never queue
            self.last_t = mono
            try:
                pts = core.scan_points(m.ranges, m.angle_min, m.angle_increment, cfg)
                stamp = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
                pose, ok = tracker.update(pts, stamp, self.now_s())
            except Exception as e:                       # a bad scan never kills the shadow node
                self.errors += 1
                self.get_logger().warning('scan skipped: %s' % str(e)[:120], throttle_duration_sec=30.0)
                return
            if not ok:
                return
            o = Odometry()
            o.header.stamp = m.header.stamp
            o.header.frame_id = 'vo_odom'                # deliberately not 'odom' / 'base_link'
            o.child_frame_id = 'vo_base_link'
            o.pose.pose.position.x, o.pose.pose.position.y = float(pose[0]), float(pose[1])
            o.pose.pose.orientation.z, o.pose.pose.orientation.w = math.sin(pose[2] / 2), math.cos(pose[2] / 2)
            self.odom_pub.publish(o)

        def on_status(self):
            mono, cpu = time.monotonic(), time.process_time()
            if mono - self.cpu[0] >= 5.0:
                self.cpu_pct = round(100.0 * (cpu - self.cpu[1]) / (mono - self.cpu[0]), 1)
                self.cpu = (mono, cpu)
            st = tracker.status(self.now_s())
            st.update({'shadow': True, 'domain': int(DOMAIN), 'source': '/astra/obstacle_scan (Astra depth)',
                       'cpu_pct': self.cpu_pct, 'errors': self.errors, 'wall_time': round(time.time(), 2)})
            self.status_pub.publish(String(data=json.dumps(st)))
            try:
                write_status(st)
            except OSError as e:
                self.get_logger().warning('status file not written: %s' % e, throttle_duration_sec=60.0)

    rclpy.init()
    node = VoShadow()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():                                   # SIGTERM may already have shut the context down
            rclpy.shutdown()


if __name__ == '__main__':
    main()
