#!/usr/bin/env python3
"""Read-only 3-encoder ground qualification helper (2026-11-14, M3 excluded). Publishes nothing, commands nothing.

For every drive segment (from standstill to standstill, owner driving with the remote) it prints one line comparing
wheel odometry (/yahboom/odom, selected encoders M1/M2/M4) with LiDAR ICP odometry (/lidar/icp_odom):
  distance (signed along the start heading), yaw change, and the worst encoder-health state seen.
PASS per segment: distance error <= max(0.10 m, 5 %), yaw sign agrees and error <= max(5 deg, 10 %),
encoder state never CRITICAL/INVALID/MISSING.
"""
import json, math, time
import rclpy
from nav_msgs.msg import Odometry
from std_msgs.msg import String

STILL_V, STILL_W, STILL_S, MIN_MOVE = 0.01, 0.02, 1.0, 0.05
RANK = {'READY': 0, 'HEALTHY': 0, 'DEGRADED': 1, 'QUALIFYING': 2, 'CRITICAL': 3, 'INVALID': 3, 'MISSING': 3}


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class Check:
    def __init__(self, node):
        self.wheel = self.lidar = None
        self.why = ''; self.moving = False; self.still_since = time.monotonic(); self.start = None; self.worst = 'READY'; self.n = 0
        node.create_subscription(Odometry, '/yahboom/odom', self.on_wheel, 20)
        node.create_subscription(Odometry, '/lidar/icp_odom', self.on_lidar, 20)
        node.create_subscription(String, '/atlas/encoder_health', self.on_health, 10)
        node.create_timer(0.1, self.tick)
        print('encoder segment check ready: drive a segment, stop for 1 s; one line per segment', flush=True)

    def on_wheel(self, m):
        p = m.pose.pose
        self.wheel = (p.position.x, p.position.y, yaw(p.orientation), m.twist.twist.linear.x, m.twist.twist.angular.z)

    def on_lidar(self, m):
        p = m.pose.pose
        self.lidar = (p.position.x, p.position.y, yaw(p.orientation))

    def on_health(self, m):
        d = json.loads(m.data); s = d.get('state', 'MISSING')
        if self.moving and RANK.get(s, 3) > RANK.get(self.worst, 3):
            self.worst = s
            self.why = f"{d.get('reason', '')} faults={d.get('faults')} selected={d.get('selected_encoders')} rejected={d.get('consensus_rejected_encoders')}"[:160]

    def tick(self):
        if self.wheel is None or self.lidar is None:
            return
        now = time.monotonic()
        still = abs(self.wheel[3]) < STILL_V and abs(self.wheel[4]) < STILL_W
        if not self.moving:
            if still:
                self.still_since = now
                self.start = (self.wheel, self.lidar)
            else:
                self.moving, self.worst, self.why = True, 'READY', ''
            return
        if not still:
            self.still_since = now
            return
        if now - self.still_since < STILL_S:
            return
        self.moving = False
        (w0, l0), w1, l1 = self.start, self.wheel, self.lidar
        def along(a, b):
            return (b[0] - a[0]) * math.cos(a[2]) + (b[1] - a[1]) * math.sin(a[2])
        dw, dl = along(w0, w1), along(l0, l1)
        yw, yl = math.degrees(wrap(w1[2] - w0[2])), math.degrees(wrap(l1[2] - l0[2]))
        if abs(dl) < MIN_MOVE and abs(yl) < 3:
            return
        self.n += 1
        d_ok = abs(dw - dl) <= max(0.10, 0.05 * abs(dl))
        y_ok = abs(yl) < 5 or (math.copysign(1, yw) == math.copysign(1, yl) and abs(yw - yl) <= max(5.0, 0.10 * abs(yl)))
        h_ok = RANK.get(self.worst, 3) < 3
        ok = d_ok and y_ok and h_ok
        print(f"#{self.n} {'PASS' if ok else 'FAIL'}  distance wheel {dw:+.2f} m / LiDAR {dl:+.2f} m ({'ok' if d_ok else 'BAD'})"
              f" | turn wheel {yw:+.0f} deg / LiDAR {yl:+.0f} deg ({'ok' if y_ok else 'BAD'}) | encoders worst {self.worst}"
              + (f" [{self.why}]" if self.why else ''), flush=True)
        self.start = (self.wheel, self.lidar)


def main():
    rclpy.init(); node = rclpy.create_node('atlas_encoder_segment_check'); Check(node)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
