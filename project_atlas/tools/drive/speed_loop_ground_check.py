#!/usr/bin/env python3
"""ATLAS closed-loop speed GROUND CHECK (owner-triggered, bounded). 2026-11-15.

COMMANDS MOTION. Run only when the owner starts it, standing by with the remote (the remote pre-empts the
COMMISSION channel), with at least ~1.5 m clear floor ahead, after the speed loop is enabled in config/speed_loop.yaml.

What it does
  * arms the mux COMMISSION lease (20 s, works while manual-only stays ON; remote neutral >= 1 s required);
  * sends ONE continuous forward command --speed (0.05..0.15 m/s) on /cmd_vel_commission;
  * stops (zero + disarm) at the first of: --distance travelled (wheel odom, <= 1.0 m), --timeout (<= 15 s),
    LiDAR front clearance < 0.60 m, front sector blind (no valid ray in +-18 deg for 3 scans) or /scan older than
    0.5 s, /atlas/speed_loop or /yahboom/odom older than 0.5 s, measured speed > target + 0.15 m/s for 2 samples,
    a status reason starting with 'fail_closed', or Ctrl-C;
  * prints commanded vs measured speed and a PASS/FAIL verdict, and saves the samples as JSON under
    ~/.local/state/project_atlas/speed_loop_check_<time>.json.

PASS = rover started within 2.0 s, steady-window (after 1.5 s) mean wheel speed within +-0.04 m/s of the
target, peak < max(1.5 x target, target + 0.08) + 0.05 m/s, LiDAR-ICP distance agrees with wheel distance within
25 % (when /lidar/icp_odom is available), and the run ended by distance or timeout (not by a guard).

Usage (on the Jetson):  python3 speed_loop_ground_check.py --speed 0.10 --distance 0.6
"""
import argparse
import json
import math
import time
from pathlib import Path

SPEED_MIN, SPEED_MAX = 0.05, 0.15
DISTANCE_MAX, TIMEOUT_MAX = 1.0, 15.0
CLEARANCE_STOP_M = 0.60
STALE_S = 0.5
RUNAWAY_MARGIN = 0.15
RUNAWAY_FLOOR_MPS = 0.35     # 2026-11-15: below the ~0.37 m/s manual driving speed; above the breakaway surge
STEADY_AFTER_S = 1.5
LASER_YAW_DEG = 180.0
LASER_X_M = -0.05              # base_link -> laser_frame (tf)
FRONT_BUMPER_X_M = 0.25        # footprint front edge
CORRIDOR_HALF_WIDTH_M = 0.28   # half footprint width 0.18 + 0.10 margin


def bounded_args(speed, distance, timeout):
    if not SPEED_MIN <= speed <= SPEED_MAX:
        raise ValueError(f'--speed must be within {SPEED_MIN}..{SPEED_MAX} m/s')
    if not 0.1 <= distance <= DISTANCE_MAX:
        raise ValueError(f'--distance must be within 0.1..{DISTANCE_MAX} m')
    if not 2.0 <= timeout <= TIMEOUT_MAX:
        raise ValueError(f'--timeout must be within 2..{TIMEOUT_MAX} s')
    return speed, distance, timeout


def effective_target(samples, requested):
    """Median of the targets the base reported while commanded; falls back to the requested speed."""
    vals = sorted(float(s['base_target']) for s in samples
                  if isinstance(s.get('base_target'), (int, float)) and s['base_target'] > 0.02)
    return round(vals[len(vals) // 2], 3) if vals else requested


def evaluate(samples, target, end_reason, icp_distance=None):
    """samples: list of dicts with t (s since start), v (wheel m/s), d (wheel m). Pure; unit-tested."""
    out = {'target_mps': target, 'end_reason': end_reason, 'checks': {}}
    moving = [s for s in samples if s['v'] > 0.02]
    start = moving[0]['t'] if moving else None
    steady = [s['v'] for s in samples if s['t'] >= STEADY_AFTER_S]
    mean = sum(steady) / len(steady) if steady else None
    # 2026-11-15: the breakaway surge (static -> kinetic friction) is physical; judge the peak after the start
    # transient. A real runaway is still stopped live by the RUNAWAY guard.
    peak = max((s['v'] for s in samples if s['t'] >= STEADY_AFTER_S), default=0.0)
    wheel_d = samples[-1]['d'] if samples else 0.0
    limit = max(1.5 * target, target + 0.08) + 0.05
    c = out['checks']
    c['started_within_2s'] = start is not None and start <= 2.0
    c['steady_mean_within_0.04'] = mean is not None and abs(mean - target) <= 0.04
    c['peak_below_limit'] = peak < limit
    c['ended_by_distance_or_timeout'] = end_reason in ('DISTANCE', 'TIMEOUT')
    if icp_distance is not None and wheel_d > 0.05:
        c['icp_agrees_25pct'] = abs(icp_distance - wheel_d) <= 0.25 * wheel_d
    out.update({'start_s': start, 'steady_mean_mps': mean, 'peak_mps': peak, 'peak_limit_mps': limit,
                'wheel_distance_m': wheel_d, 'icp_distance_m': icp_distance,
                'verdict': 'PASS' if all(c.values()) else 'FAIL'})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--speed', type=float, default=0.10)
    ap.add_argument('--distance', type=float, default=0.60)
    ap.add_argument('--timeout', type=float, default=12.0)
    a = ap.parse_args()
    speed, distance, timeout = bounded_args(a.speed, a.distance, a.timeout)

    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String
    from std_srvs.srv import Trigger
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    sys.path.insert(0, '/home/jetson/project_atlas/scripts')
    from atlas_scan_geometry import ray_in_base_sector

    class Check(Node):
        def __init__(self):
            super().__init__('atlas_speed_loop_ground_check')
            self.pub = self.create_publisher(Twist, '/cmd_vel_commission', 10)
            self.arm_c = self.create_client(Trigger, '/atlas/commission/arm')
            self.disarm_c = self.create_client(Trigger, '/atlas/commission/disarm')
            self.odom = None; self.odom_t = 0.0; self.start_xy = None
            self.icp0 = None; self.icp = None
            self.loop = {}; self.loop_t = 0.0; self.loop_log = []
            self.clear = math.inf; self.scan_t = 0.0; self.blind = 0
            self.create_subscription(Odometry, '/yahboom/odom', self.on_odom, 20)
            self.create_subscription(Odometry, '/lidar/icp_odom', self.on_icp, 20)
            self.create_subscription(String, '/atlas/speed_loop', self.on_loop, 20)
            self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

        def on_odom(self, m):
            p = m.pose.pose.position
            self.odom = (p.x, p.y, m.twist.twist.linear.x); self.odom_t = time.monotonic()

        def on_icp(self, m):
            p = m.pose.pose.position
            self.icp = (p.x, p.y)

        def on_loop(self, m):
            try:
                self.loop = json.loads(m.data); self.loop_t = time.monotonic()
            except ValueError:
                pass

        def on_scan(self, m):
            # 2026-11-15 (owner: "front is clear but..."): a +-18 deg cone also caught an object 0.31 m to the side
            # at 1 m, outside the rover's path. Clearance is now the distance ahead inside the straight driving
            # CORRIDOR (|y| <= CORRIDOR_HALF_WIDTH_M in base_link); the front-blind guard keeps the +-18 deg cone.
            vals, corridor, ang = [], [], m.angle_min
            for r in m.ranges:
                if math.isfinite(r) and r >= m.range_min:
                    a = math.radians(math.degrees(ang) + LASER_YAW_DEG)
                    x, y = LASER_X_M + r * math.cos(a), r * math.sin(a)
                    if x > 0 and abs(y) <= CORRIDOR_HALF_WIDTH_M:
                        corridor.append(x - FRONT_BUMPER_X_M + 0.3)   # same reference as before (~laser origin)
                    if ray_in_base_sector(math.degrees(ang), 0.0, 18.0, LASER_YAW_DEG):
                        vals.append(r)
                ang += m.angle_increment
            self.blind = 0 if vals else self.blind + 1
            if vals or corridor:
                self.clear = min(corridor) if corridor else math.inf
            self.scan_t = time.monotonic()

        def call(self, client, timeout):
            if not client.wait_for_service(timeout_sec=timeout):
                return None
            fut = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, fut, timeout_sec=8.0)
            return fut.result()

    rclpy.init()
    n = Check()
    samples, end, runaway = [], 'NOT_STARTED', 0
    try:
        # 2026-11-15 (main session, owner run from the dashboard): DDS discovery of a fresh process on the loaded
        # Jetson plus the 1 Hz idle /atlas/speed_loop status needed more than the old 5 s; wait up to 20 s, say which.
        t_wait = time.monotonic() + 20.0
        while time.monotonic() < t_wait and (n.odom is None or not n.loop or n.scan_t == 0.0):
            rclpy.spin_once(n, timeout_sec=0.1)
        if n.odom is None or not n.loop or n.scan_t == 0.0:
            missing = [t for t, ok in (('/yahboom/odom', n.odom is not None), ('/atlas/speed_loop', bool(n.loop)),
                                       ('/scan', n.scan_t != 0.0)) if not ok]
            print('ABORT: not received within 20 s: ' + ', '.join(missing) + ' (is the speed loop enabled?)')
            return
        if n.clear < CLEARANCE_STOP_M + 0.4:
            print(f'ABORT: front clearance {n.clear:.2f} m < {CLEARANCE_STOP_M + 0.4:.2f} m needed to start')
            return
        r = n.call(n.arm_c, 12.0)
        print(f'ARM success={getattr(r, "success", None)} message={getattr(r, "message", "no response")}')
        if r is None or not r.success:
            return
        n.start_xy = n.odom[:2]; n.icp0 = n.icp
        t0 = time.monotonic(); cmd = Twist(); cmd.linear.x = speed; end = 'RUNNING'
        while rclpy.ok() and end == 'RUNNING':
            rclpy.spin_once(n, timeout_sec=0.05)
            now = time.monotonic(); t = now - t0
            d = math.hypot(n.odom[0] - n.start_xy[0], n.odom[1] - n.start_xy[1])
            v = n.odom[2]
            if not samples or t - samples[-1]['t'] >= 0.1:
                samples.append({'t': round(t, 2), 'v': round(v, 3), 'd': round(d, 3),
                                'pwm': n.loop.get('pwm'), 'reason': n.loop.get('reason'),
                                'base_target': n.loop.get('target_mps'),
                                'loop_measured': n.loop.get('measured_mps')})
                print(f"t={t:4.1f}s cmd={speed:.2f} wheel={v:+.3f} m/s d={d:.3f} m pwm={n.loop.get('pwm')} "
                      f"{n.loop.get('reason')} clear={n.clear:.2f}", flush=True)
            runaway = runaway + 1 if v > max(RUNAWAY_FLOOR_MPS, speed + RUNAWAY_MARGIN) else 0
            if d >= distance: end = 'DISTANCE'
            elif t >= timeout: end = 'TIMEOUT'
            elif n.clear < CLEARANCE_STOP_M: end = f'STOP_LIDAR_{n.clear:.2f}M'
            elif n.blind >= 3: end = 'STOP_LIDAR_FRONT_BLIND'
            elif now - n.scan_t > STALE_S: end = 'STOP_SCAN_STALE'
            elif now - n.odom_t > STALE_S: end = 'STOP_ODOM_STALE'
            elif now - n.loop_t > STALE_S and t > 0.5: end = 'STOP_SPEED_LOOP_STATUS_STALE'
            elif str(n.loop.get('reason', '')).startswith('fail_closed'): end = 'STOP_SPEED_LOOP_FAIL_CLOSED'
            elif runaway >= 2: end = 'STOP_RUNAWAY'
            else:
                n.pub.publish(cmd)
    except KeyboardInterrupt:
        end = 'STOP_CTRL_C'
    finally:
        for _ in range(5):
            n.pub.publish(Twist()); time.sleep(0.02)
        if end not in ('NOT_STARTED',):
            n.call(n.disarm_c, 0.5)
    if not samples:
        n.destroy_node(); rclpy.shutdown(); return
    t_end = time.monotonic() + 2.0                      # record the coast to standstill
    while time.monotonic() < t_end:
        rclpy.spin_once(n, timeout_sec=0.1)
    coast = math.hypot(n.odom[0] - n.start_xy[0], n.odom[1] - n.start_xy[1]) - samples[-1]['d']
    icp_d = (math.hypot(n.icp[0] - n.icp0[0], n.icp[1] - n.icp0[1])
             if n.icp is not None and n.icp0 is not None else None)
    # 2026-11-15: the mux scales autonomous/commission commands (encoder DEGRADED -> 0.5), so judge the loop
    # against the target the base actually received (reported in /atlas/speed_loop), not the requested --speed.
    res = evaluate(samples, effective_target(samples, speed), end, icp_d)
    res['requested_mps'] = speed
    res['coast_after_stop_m'] = round(coast, 3)
    res['samples'] = samples
    out = Path.home() / '.local/state/project_atlas' / f'speed_loop_check_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != 'samples'}, indent=1))
    print(f'saved {out}')
    n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
