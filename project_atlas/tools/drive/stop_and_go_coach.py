#!/usr/bin/env python3
"""ATLAS stop-and-go drive coach (read-only; publishes nothing, never commands motion). 2026-11-14.

Owner strategy: drive a short distance, stop, wait until the LiDAR confirms the position, then drive again.
Once per second this prints one line:
  MOVING  wheels are turning
  WAIT    stopped, but not confirmed yet (settling time, pose still shifting, or LiDAR does not fit the map)
  GO      stopped >= SETTLE_S, map pose steady (< 2 cm / 1 deg over the last 2 s) and the LiDAR scan fits the live
          /map (the same scan-fit test mission control uses: >= 85 % of returns within 15 cm of a wall)
Works in localization mode (saved map) and mapping mode (the live SLAM map on /map).
Run on the Jetson:  python3 ~/project_atlas/tools/drive/stop_and_go_coach.py
"""
import json
import math
import sys
import time
import urllib.request
from collections import deque

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener

sys.path.insert(0, '/home/jetson/project_atlas/scripts')
from atlas_scan_fit_core import OccupiedIndex, ScanFitPolicy, evaluate, unused_beam_points  # noqa: E402

SETTLE_S = 1.5
STEADY_WINDOW_S = 2.0
STEADY_M, STEADY_DEG = 0.02, 1.0
MOVING_V, MOVING_W = 0.01, 0.02
COLOURS = {'MOVING': '\033[1;36m', 'WAIT': '\033[1;33m', 'GO': '\033[1;32m'}
MAPPING_MIN_FIT = 0.60
SESSION = '/home/jetson/.config/project_atlas/mapping_session.json'


def mapping_active():
    try:
        return json.load(open(SESSION)).get('state') == 'active'
    except Exception:
        return False


DASHBOARD = 'http://127.0.0.1:8088/api/map'   # read-only: the dashboard's strict LiDAR place check


def strict_check():
    """(state, reason, age_s) of the dashboard's unique-place LiDAR check (VERIFIED needs >= 93 %)."""
    try:
        with urllib.request.urlopen(DASHBOARD, timeout=2) as r:
            d = json.load(r).get('localization_check') or {}
        v = d.get('value') or {}
        return v.get('state'), str(v.get('reason') or ''), d.get('age')
    except Exception:
        return None, 'dashboard unreachable', None


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class Coach(Node):
    def __init__(self):
        super().__init__('atlas_drive_coach')
        self.tf = Buffer(); TransformListener(self.tf, self)
        self.scan = None; self.scan_at = None
        self.odom = None; self.stopped_since = None
        self.index = None; self.map_stamp = None
        self.poses = deque()
        self.policy = ScanFitPolicy()
        self.state = None
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/yahboom/odom', self.on_odom, 10)
        self.create_subscription(OccupancyGrid, '/map', self.on_map, QoSProfile(
            depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))
        self.create_timer(1.0, self.tick)
        print('ATLAS stop-and-go coach: drive a short bit, stop, wait for GO, repeat. Ctrl-C to quit.', flush=True)

    def on_scan(self, m):
        self.scan, self.scan_at = m, time.monotonic()

    def on_odom(self, m):
        moving = abs(m.twist.twist.linear.x) > MOVING_V or abs(m.twist.twist.angular.z) > MOVING_W
        now = time.monotonic()
        if moving:
            self.stopped_since = None
        elif self.stopped_since is None:
            self.stopped_since = now
        self.odom = (now, moving)

    def on_map(self, m):
        info = m.info; res = info.resolution; w = info.width
        c, s = math.cos(yaw_of(info.origin.orientation)), math.sin(yaw_of(info.origin.orientation))
        pts = []
        for i, v in enumerate(m.data):
            if v >= 65:
                gx, gy = (i % w + 0.5) * res, (i // w + 0.5) * res
                pts.append((info.origin.position.x + c * gx - s * gy, info.origin.position.y + s * gx + c * gy))
        if pts:
            self.index = OccupiedIndex(pts, res)
            self.map_stamp = time.monotonic()

    def pose(self, frame_from, frame_to):
        t = self.tf.lookup_transform(frame_from, frame_to, rclpy.time.Time())
        return (t.transform.translation.x, t.transform.translation.y, yaw_of(t.transform.rotation))

    def tick(self):
        now = time.monotonic()
        try:
            p = self.pose('map', 'base_link')
        except Exception:
            return self.show('WAIT', 'no map pose yet (localization/SLAM not ready)')
        self.poses.append((now, p))
        while self.poses and now - self.poses[0][0] > STEADY_WINDOW_S:
            self.poses.popleft()
        where = f'pose ({p[0]:+.2f}, {p[1]:+.2f}) {math.degrees(p[2]):+.0f} deg'
        if self.odom is None or now - self.odom[0] > 1.0:
            return self.show('WAIT', f'{where} | wheel odometry stale')
        if self.odom[1] or self.stopped_since is None:
            return self.show('MOVING', where)
        still = now - self.stopped_since
        if still < SETTLE_S:
            return self.show('WAIT', f'{where} | settling {still:.1f}/{SETTLE_S:.1f} s')
        xs = [q[1] for q in self.poses]
        spread = max(math.hypot(a[0] - p[0], a[1] - p[1]) for a in xs)
        dyaw = max(abs(math.degrees(math.atan2(math.sin(a[2] - p[2]), math.cos(a[2] - p[2])))) for a in xs)
        if spread > STEADY_M or dyaw > STEADY_DEG:
            return self.show('WAIT', f'{where} | position still settling ({spread*100:.0f} cm, {dyaw:.1f} deg)')
        if self.index is None or self.scan is None:
            return self.show('WAIT', f'{where} | waiting for map / LiDAR')
        try:
            laser = self.pose('base_link', self.scan.header.frame_id)
        except Exception:
            return self.show('WAIT', f'{where} | laser transform unavailable')
        s = self.scan
        pts = unused_beam_points(s.angle_min, s.angle_increment, s.ranges, s.range_min, s.range_max, self.policy)
        r = evaluate(pts, p, laser, self.index, now - self.scan_at, self.policy)
        fit = 'n/a' if r.fit_fraction is None else f'{r.fit_fraction:.0%}'
        if mapping_active():
            # 2026-11-14: while MAPPING, SLAM adds scans only after ~0.2 m of travel, so a new area in front stays
            # unmapped while stopped and the fit cannot reach 85 %. GO = stopped + settled + SLAM tracking (>= 60 %).
            if (r.fit_fraction or 0) >= MAPPING_MIN_FIT:
                return self.show('GO', f'{where} | MAPPING: settled, LiDAR fit {fit} on the growing map - drive the next short bit')
            return self.show('WAIT', f'{where} | MAPPING: LiDAR fit {fit} below {MAPPING_MIN_FIT:.0%} - stay stopped, tell Claude')
        if r.ok:
            st, why, age = strict_check()
            if st == 'VERIFIED':
                return self.show('GO', f'{where} | LiDAR fit {fit} ✔ LOCAL ✔ VERIFIED (unique place) - drive the next short bit')
            extra = 'strict check running' if st == 'VERIFYING' else f'strict: {st or "n/a"} {why[:55]}'
            return self.show('GO', f'{where} | LiDAR fit {fit} ✔ LOCAL only ({extra})')
        return self.show('WAIT', f'{where} | LiDAR fit {fit} - {r.reason[:60]}')

    def show(self, state, text):
        bell = '\a' if state == 'GO' and self.state != 'GO' else ''
        self.state = state
        print(f'{bell}{time.strftime("%H:%M:%S")} {COLOURS[state]}{state:6s}\033[0m {text}', flush=True)


def main():
    rclpy.init()
    node = Coach()
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
