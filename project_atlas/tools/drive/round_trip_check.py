#!/usr/bin/env python3
"""ATLAS combined pre-autonomy round-trip check (read-only; publishes nothing, never commands motion). 2026-11-14.

The owner drives Dhruv Room -> hall -> Dhruv Room with the remote, stop-and-go. After every stop (standstill >= 1 s)
this prints ONE line covering the three remaining pre-autonomy tests:
  1. encoders (M3 excluded): wheel distance (/yahboom/odom, M1/M2/M4) vs LiDAR ICP distance (/lidar/icp_odom),
     and the worst /atlas/encoder_health state while moving (CRITICAL/INVALID/MISSING = fail);
  2. turning as navigation measures it: EKF yaw change (/odom, IM10A gyro) vs LiDAR ICP yaw change
     (wheel yaw is shown for information only; it is not used by the EKF);
  3. localization on the accepted map: the localization monitor verdict after the stop (VERIFIED needed);
plus whether the Astra obstacle bridge is active (needed so Nav2's astra_layer receives camera obstacles).
A running tally shows left/right turns covered and pass counts. Ctrl-C prints the final summary.
"""
import json, math, subprocess, time
from pathlib import Path

import rclpy
from nav_msgs.msg import Odometry
from std_msgs.msg import String

STILL_V, STILL_W, STILL_S, MIN_MOVE_M, MIN_TURN_DEG = 0.01, 0.02, 1.0, 0.05, 3.0
LOC_FILE = Path.home() / '.local/state/project_atlas/localization_check.json'
LOC_WAIT_S = 12.0
RANK = {'READY': 0, 'HEALTHY': 0, 'DEGRADED': 1, 'QUALIFYING': 2, 'CRITICAL': 3, 'INVALID': 3, 'MISSING': 3}


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap_deg(a):
    return math.degrees(math.atan2(math.sin(a), math.cos(a)))


def pose(m):
    p = m.pose.pose
    return (p.position.x, p.position.y, yaw(p.orientation))


def bridge_active():
    try:
        return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'atlas-astra-bridge.service'],
                              timeout=3).returncode == 0
    except Exception:
        return False


def loc_verdict(after_unix):
    try:
        d = json.loads(LOC_FILE.read_text())
    except Exception:
        return None, 'no localization check file'
    if float(d.get('written_unix', 0)) < after_unix:
        return None, 'waiting for a fresh check'
    return d.get('state'), str(d.get('reason', ''))[:60]


class RoundTrip:
    def __init__(self, node):
        self.node = node
        self.wheel = self.lidar = self.ekf = None
        self.v = self.w = 0.0
        self.moving = False
        self.still_since = time.monotonic()
        self.start = None
        self.worst, self.why = 'READY', ''
        self.pending = None                  # finished segment waiting for its localization verdict
        self.n = 0
        self.tally = {'pass': 0, 'fail': 0, 'left': 0, 'right': 0, 'verified': 0, 'not_verified': 0,
                      'wheel_m': 0.0, 'lidar_m': 0.0}
        node.create_subscription(Odometry, '/yahboom/odom', self.on_wheel, 20)
        node.create_subscription(Odometry, '/lidar/icp_odom', lambda m: setattr(self, 'lidar', pose(m)), 20)
        node.create_subscription(Odometry, '/odom', lambda m: setattr(self, 'ekf', pose(m)), 20)
        node.create_subscription(String, '/atlas/encoder_health', self.on_health, 10)
        node.create_timer(0.1, self.tick)
        print(f'round-trip check ready | Astra bridge {"ACTIVE" if bridge_active() else "OFF"} | '
              'drive stop-and-go; one line per stop', flush=True)

    def on_wheel(self, m):
        self.wheel = pose(m)
        self.v, self.w = m.twist.twist.linear.x, m.twist.twist.angular.z

    def on_health(self, m):
        d = json.loads(m.data)
        s = d.get('state', 'MISSING')
        if self.moving and RANK.get(s, 3) > RANK.get(self.worst, 3):
            self.worst = s
            self.why = f"{d.get('reason', '')} rejected={d.get('consensus_rejected_encoders')}"[:120]

    def snapshot(self):
        return (self.wheel, self.lidar, self.ekf)

    def tick(self):
        if None in self.snapshot():
            return
        now = time.monotonic()
        if self.pending is not None:
            self.finish_pending()
        still = abs(self.v) < STILL_V and abs(self.w) < STILL_W
        if not self.moving:
            if still:
                self.still_since = now
                self.start = self.snapshot()
            else:
                self.moving, self.worst, self.why = True, 'READY', ''
            return
        if not still:
            self.still_since = now
            return
        if now - self.still_since < STILL_S:
            return
        self.moving = False
        (w0, l0, e0), (w1, l1, e1) = self.start, self.snapshot()
        self.start = self.snapshot()

        def along(a, b):
            return (b[0] - a[0]) * math.cos(a[2]) + (b[1] - a[1]) * math.sin(a[2])
        dw, dl = along(w0, w1), along(l0, l1)
        ye, yl, yw = wrap_deg(e1[2] - e0[2]), wrap_deg(l1[2] - l0[2]), wrap_deg(w1[2] - w0[2])
        if abs(dl) < MIN_MOVE_M and abs(yl) < MIN_TURN_DEG:
            return
        self.pending = {'dw': dw, 'dl': dl, 'ye': ye, 'yl': yl, 'yw': yw, 'worst': self.worst, 'why': self.why,
                        'stopped_unix': time.time()}

    def finish_pending(self):
        p = self.pending
        state, reason = loc_verdict(p['stopped_unix'])
        if state in (None, 'VERIFYING') and time.time() - p['stopped_unix'] < LOC_WAIT_S:
            return
        self.pending = None
        self.n += 1
        d_ok = abs(p['dw'] - p['dl']) <= max(0.10, 0.05 * abs(p['dl']))
        y_ok = abs(p['yl']) < 5 or (math.copysign(1, p['ye']) == math.copysign(1, p['yl'])
                                    and abs(p['ye'] - p['yl']) <= max(5.0, 0.10 * abs(p['yl'])))
        h_ok = RANK.get(p['worst'], 3) < 3
        l_ok = state == 'VERIFIED'
        ok = d_ok and y_ok and h_ok and l_ok
        t = self.tally
        t['pass' if ok else 'fail'] += 1
        t['verified' if l_ok else 'not_verified'] += 1
        t['wheel_m'] += abs(p['dw']); t['lidar_m'] += abs(p['dl'])
        if p['yl'] >= 30:
            t['left'] += 1
        elif p['yl'] <= -30:
            t['right'] += 1
        bridge = 'ACTIVE' if bridge_active() else 'OFF'
        print(f"#{self.n} {'PASS' if ok else 'FAIL'} | dist wheel {p['dw']:+.2f} / LiDAR {p['dl']:+.2f} m "
              f"{'ok' if d_ok else 'BAD'} | turn IMU-EKF {p['ye']:+.0f} / LiDAR {p['yl']:+.0f} deg {'ok' if y_ok else 'BAD'}"
              f" (wheel {p['yw']:+.0f}) | enc {p['worst']}{'' if h_ok else ' [' + p['why'] + ']'}"
              f" | loc {state or 'NO VERDICT'}{'' if l_ok else ' (' + reason + ')'} | astra {bridge}"
              f" || so far {t['pass']}/{self.n} pass, turns L{t['left']} R{t['right']}, loc ok {t['verified']}/{self.n}",
              flush=True)

    def summary(self):
        t = self.tally
        print(f"SUMMARY: {self.n} stops, {t['pass']} pass / {t['fail']} fail; wheel {t['wheel_m']:.2f} m vs LiDAR "
              f"{t['lidar_m']:.2f} m; turns >= 30 deg: left {t['left']}, right {t['right']}; localization VERIFIED "
              f"{t['verified']}/{self.n}; Astra bridge {'ACTIVE' if bridge_active() else 'OFF'}", flush=True)


def main():
    rclpy.init()
    node = rclpy.create_node('atlas_round_trip_check')
    rt = RoundTrip(node)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rt.summary()


if __name__ == '__main__':
    main()
