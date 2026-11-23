#!/usr/bin/env python3
"""ATLAS Stage-2 GENTLE TURN check (owner-triggered, bounded). 2026-11-23.

Master-plan entry gate stage 2: "a bounded gentle left/right turn sequence".

COMMANDS MOTION. Run only when the owner starts it (dashboard Stage 2 page), standing by with the remote (the
remote pre-empts the COMMISSION channel), with about 1.5 m clear floor ahead and 0.6 m to each side.

What it does, twice (arc 1 = LEFT, arc 2 = RIGHT):
  * arms the mux COMMISSION lease (20 s; the mux itself clamps COMMISSION to |vx| <= 0.12 m/s, |wz| <= 0.15 rad/s);
  * sends ONE gentle forward arc: vx 0.10 m/s, wz +-0.15 rad/s (radius ~0.67 m, ~15 deg wheel angle);
  * stops (zero + disarm) at the first of: IM10A heading change >= --yaw deg (default 25, max 35) = normal end,
    wheel distance 0.6 m without that turn, 12 s, a LiDAR point on the curved path ATLAS will sweep (footprint
    + 0.10 m) closer than 0.30 m along that path, front sector blind for 3 scans, /scan, /yahboom/odom, IM10A or /atlas/speed_loop older than 0.5 s,
    speed > 0.30 m/s for 2 samples, a speed-loop 'fail_closed' reason, or Ctrl-C;
  * waits for ATLAS to stand still between the arcs.
Saves ~/.local/state/project_atlas/turn_check_<time>.json and records the result on the master-plan board.

An arc PASSES when it started within 2 s, ended by the heading target, the IM10A turn has the commanded sign and
>= 10 deg, the LiDAR-ICP heading change (when available) agrees within max(8 deg, 35 %), the peak speed stayed
< 0.25 m/s and ATLAS was still (< 0.02 m/s) within 1.5 s of the stop. The sequence PASSES when both arcs pass and
the net heading after left + right is within 15 deg.

--workload (2026-11-23, master-plan step 4 part B "controlled turns + full workload timing"): the same two arcs,
refused unless the full autonomy stack is running (WORKLOAD_SERVICES), and additionally recording while each arc runs:
IM10A, EKF /odom and TF odom->base_link / map->odom arrival rate, largest gap and REAL message age (now - stamp +
the configured future-dating: EKF transform_time_offset, AMCL transform_tolerance), and the EKF heading change of
each arc against LiDAR-ICP. Writes imu_workload_check_<time>.json and records step 4 part B (not stage 2).

Usage (on the Jetson):  python3 turn_ground_check.py [--yaw 25] [--workload]
"""
import argparse
import json
import math
import time
from pathlib import Path

VX = 0.10
WZ = 0.15                    # == the mux COMMISSION angular clamp
YAW_MIN_DEG, YAW_MAX_DEG = 15.0, 35.0
DISTANCE_GUARD_M = 0.60
TIMEOUT_S = 12.0
STALE_S = 0.5
RUNAWAY_MPS = 0.30
PEAK_LIMIT_MPS = 0.25
STOP_CLEAR_M = 0.30
STILL_MPS = 0.02
STOP_SETTLE_S = 1.5
MIN_TURN_DEG = 10.0
NET_HEADING_MAX_DEG = 15.0
LASER_YAW_DEG = 180.0
LASER_X_M = -0.05
FRONT_BUMPER_X_M = 0.25
HALF_WIDTH_M = 0.18
SIDE_MARGIN_M = 0.10
RADIUS_M = VX / WZ            # turning radius of the commanded arc (~0.67 m)


def bounded_yaw(yaw_deg):
    if not YAW_MIN_DEG <= yaw_deg <= YAW_MAX_DEG:
        raise ValueError(f'--yaw must be within {YAW_MIN_DEG:.0f}..{YAW_MAX_DEG:.0f} deg')
    return yaw_deg


def swept_clearance(points, direction, remaining_deg):
    """Distance ALONG THE ARC from the front bumper to the nearest LiDAR point inside the band the footprint sweeps
    (inner edge - margin .. outer front corner + margin) between now and the heading target + STOP_CLEAR_M.
    points: (x, y) in base_link; direction +1 = left, -1 = right. inf = path clear. Pure; unit-tested.
    2026-11-23 run 1: the former straight box (|y| <= 0.58 on the turning side, 1 m ahead) took a side wall ~0.6 m
    away for an obstacle as soon as ATLAS yawed 1-2 deg (0.69 -> 0.20 m in 0.3 s) although the arc stays ~0.27 m
    from it; this band follows the real circle instead."""
    r_in = RADIUS_M - HALF_WIDTH_M - SIDE_MARGIN_M
    r_out = math.hypot(RADIUS_M + HALF_WIDTH_M, FRONT_BUMPER_X_M) + SIDE_MARGIN_M
    phi_max = math.radians(max(0.0, remaining_deg)) + (FRONT_BUMPER_X_M + STOP_CLEAR_M) / RADIUS_M
    cy = direction * RADIUS_M                       # turning centre (0, +-R) in base_link
    best = math.inf
    for x, y in points:
        r = math.hypot(x, y - cy)
        if not r_in <= r <= r_out:
            continue
        # angle travelled from the rover's position to the point, positive in the direction of motion
        phi = direction * (math.atan2(y - cy, x) + direction * math.pi / 2)
        phi = (phi + math.pi) % (2 * math.pi) - math.pi
        if 0.0 < phi <= phi_max:
            best = min(best, max(0.0, RADIUS_M * phi - FRONT_BUMPER_X_M))
    return best


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def evaluate_arc(samples, direction, end_reason, icp_yaw_deg=None, settle_s=None):
    """samples: dicts with t, v (wheel m/s), d (wheel m), yaw (IM10A integrated deg). Pure; unit-tested."""
    moving = [s for s in samples if s['v'] > 0.02]
    start = moving[0]['t'] if moving else None
    imu_yaw = samples[-1]['yaw'] if samples else 0.0
    peak = max((s['v'] for s in samples), default=0.0)
    c = {
        'started_within_2s': start is not None and start <= 2.0,
        'ended_by_heading_target': end_reason == 'YAW',
        'turn_sign_and_size': imu_yaw * direction >= MIN_TURN_DEG,
        'peak_below_0.25': peak < PEAK_LIMIT_MPS,
        'still_within_1.5s': settle_s is not None and settle_s <= STOP_SETTLE_S,
    }
    if icp_yaw_deg is not None:
        c['lidar_heading_agrees'] = abs(icp_yaw_deg - imu_yaw) <= max(8.0, 0.35 * abs(imu_yaw))
    return {'direction': 'LEFT' if direction > 0 else 'RIGHT', 'end_reason': end_reason, 'checks': c,
            'start_s': start, 'imu_yaw_deg': round(imu_yaw, 1),
            'icp_yaw_deg': None if icp_yaw_deg is None else round(icp_yaw_deg, 1),
            'wheel_distance_m': samples[-1]['d'] if samples else 0.0, 'peak_mps': peak, 'settle_s': settle_s,
            'verdict': 'PASS' if all(c.values()) else 'FAIL'}


def evaluate(arcs):
    """arcs: list of evaluate_arc results (LEFT then RIGHT)."""
    net = sum(a.get('imu_yaw_deg') or 0.0 for a in arcs)
    checks = {'left_arc': len(arcs) > 0 and arcs[0]['verdict'] == 'PASS' and arcs[0]['direction'] == 'LEFT',
              'right_arc': len(arcs) > 1 and arcs[1]['verdict'] == 'PASS' and arcs[1]['direction'] == 'RIGHT',
              'net_heading_within_15deg': len(arcs) == 2 and abs(net) <= NET_HEADING_MAX_DEG}
    failed = [k for k, v in checks.items() if not v]
    for a in arcs:
        failed += ['%s:%s' % (a['direction'].lower(), k) for k, v in a['checks'].items() if not v]
    detail = ' · '.join('%s %+.0f deg (%s)' % (a['direction'].lower(), a['imu_yaw_deg'], a['end_reason']) for a in arcs)
    return {'verdict': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks, 'arcs': arcs,
            'net_heading_deg': round(net, 1), 'failed': failed,
            'detail': (detail + ' · net %+.0f deg' % net) if arcs else 'no arc ran'}


# ---- step 4 part B: timing under full workload -------------------------------------------------------------------
WORKLOAD_SERVICES = ('atlas-localization', 'atlas-ekf', 'atlas-im10a', 'atlas-lidar', 'atlas-icp-odometry',
                     'atlas-astra-bridge', 'atlas-camera', 'atlas-mission-control', 'atlas-cmd-vel-mux',
                     'rover-base-telemetry')
# 2026-11-23: map->odom 0.50 s. The owner briefly allowed 0.80 s after runs 1-2 showed 0.725-0.755 s, but those were
# inflated by the since-fixed backlog bug; the PASS run 3 measured 0.256 s, so the owner restored 0.50 s ("Yes, back
# to 0.5 s").
AGE_P95_MAX_S = {'imu': 0.10, 'ekf': 0.15, 'tf_odom_base': 0.15, 'tf_map_odom': 0.50}
RATE_MIN_HZ = {'imu': 8.0, 'ekf': 8.0, 'tf_odom_base': 8.0, 'tf_map_odom': 1.0}
GAP_MAX_S = {'imu': 0.30, 'ekf': 0.30, 'tf_odom_base': 0.30, 'tf_map_odom': 2.0}
FUTURE_SLACK_S = 0.05        # a real age below -0.05 s means an unexplained future stamp
TIMING_WARMUP_S = 0.5        # 2026-11-23 part B runs 1-2: messages queued while the arm service call blocked arrived
                             # up to ~1 s old right after it; judge timing from 0.5 s into each arc


def percentile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None


def evaluate_workload(streams, active_s, offsets, ekf_turns, missing_services, load_avg=None):
    """streams: {name: [(t_arrival, raw_age_s, arc_index)]} recorded while arcs ran (active_s seconds in total); gaps
    are measured WITHIN each arc (2026-11-23 runs 1-2 counted the ~1.2 s pause between the two arcs as a gap);
    offsets: {name: configured future-dating s}; ekf_turns: [(ekf_deg, icp_deg)] per arc. Pure; unit-tested."""
    c, m = {'full_workload_running': not missing_services}, {'missing_services': list(missing_services),
                                                              'load_avg_1m': load_avg, 'active_s': round(active_s, 1)}
    for name in ('imu', 'ekf', 'tf_odom_base', 'tf_map_odom'):
        rows = streams.get(name, [])
        ages = [r[1] + offsets.get(name, 0.0) for r in rows]
        gap = -math.inf
        for seg in sorted({(r[2] if len(r) > 2 else 0) for r in rows}):
            ts = sorted(r[0] for r in rows if (r[2] if len(r) > 2 else 0) == seg)
            gap = max([gap] + [b - a for a, b in zip(ts, ts[1:])])
        gap = math.inf if gap == -math.inf else gap
        hz = len(rows) / active_s if active_s > 0 else 0.0
        p95 = percentile(ages, 0.95)
        m[name] = {'hz': round(hz, 1), 'max_gap_s': None if math.isinf(gap) else round(gap, 3),
                   'age_p95_s': None if p95 is None else round(p95, 3),
                   'age_min_s': None if not ages else round(min(ages), 3), 'offset_s': offsets.get(name, 0.0)}
        c[name + '_rate'] = len(rows) > 1 and hz >= RATE_MIN_HZ[name] and gap <= GAP_MAX_S[name]
        c[name + '_age'] = p95 is not None and p95 <= AGE_P95_MAX_S[name] and min(ages) >= -FUTURE_SLACK_S
    c['ekf_heading_agrees'] = bool(ekf_turns) and all(
        e is not None and i is not None and abs(e - i) <= max(8.0, 0.35 * abs(i)) for e, i in ekf_turns)
    m['ekf_turns'] = [(None if e is None else round(e, 1), None if i is None else round(i, 1)) for e, i in ekf_turns]
    return {'checks': c, 'measured': m, 'failed': [k for k, v in c.items() if not v]}


def combine_part_b(turns, workload):
    """Step 4 part B = the turn sequence PASS + every workload timing check."""
    failed = list(turns['failed']) + ['timing:' + k for k in workload['failed']]
    t = workload['measured']
    detail = '%s · under workload: IMU %s Hz / p95 %s s, EKF %s Hz / p95 %s s, TF %s / %s Hz, EKF turns %s' % (
        turns['detail'], t['imu']['hz'], t['imu']['age_p95_s'], t['ekf']['hz'], t['ekf']['age_p95_s'],
        t['tf_odom_base']['hz'], t['tf_map_odom']['hz'], t['ekf_turns'])
    return dict(turns, verdict='PASS' if not failed else 'FAIL', failed=failed, workload=workload, detail=detail)


def configured_offsets(root):
    """Future-dating configured on the rover (EKF transform_time_offset, AMCL transform_tolerance)."""
    import re
    out = {'imu': 0.0, 'ekf': 0.0, 'tf_odom_base': 0.0, 'tf_map_odom': 0.0}
    try:
        txt = (Path(root) / 'config' / 'atlas_ekf.yaml').read_text()
        mm = re.search(r'transform_time_offset:\s*([0-9.]+)', txt)
        out['tf_odom_base'] = float(mm.group(1)) if mm else 0.0
    except OSError:
        pass
    try:
        txt = (Path(root) / 'config' / 'nav2_params.yaml').read_text()
        amcl = txt.split('amcl:', 1)[1] if 'amcl:' in txt else ''
        mm = re.search(r'transform_tolerance:\s*([0-9.]+)', amcl)
        out['tf_map_odom'] = float(mm.group(1)) if mm else 0.0
    except (OSError, IndexError):
        pass
    return out


VO_STATUS_FILE = Path.home() / '.local/state/project_atlas/vo_shadow_status.json'


def vo_shadow_pose(path=None, now=None):
    """2026-11-23 master-plan step 7: the shadow VO pose from its status file (never a ROS topic, never a
    command), or None when the file is missing or older than 2 s. Read only at arc start and after the settle."""
    try:
        s = json.loads(Path(path or VO_STATUS_FILE).read_text(encoding='utf-8'))
        if abs((now or time.time()) - float(s.get('wall_time') or 0)) > 2.0 or not s.get('pose'):
            return None
        return {'pose': s['pose'], 'state': s.get('state')}
    except (OSError, ValueError, TypeError):
        return None


def vo_arc(vo0, icp0, icp1, path=None):
    """Per-arc VO vs LiDAR-ICP record for step 7 (information only: never changes the arc verdict)."""
    vo1 = vo_shadow_pose(path)
    if not (vo0 and vo1 and icp0[0] and icp1[0] and icp0[1] is not None and icp1[1] is not None):
        return None
    try:
        import atlas_vo_core
    except ImportError:
        return None
    cmp = atlas_vo_core.arc_compare(vo0['pose'], vo1['pose'], (*icp0[0], icp0[1]), (*icp1[0], icp1[1]))
    return dict(cmp, state=vo1['state'], state_start=vo0['state']) if cmp else None


def _yaw(q):
    return math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--yaw', type=float, default=25.0)
    ap.add_argument('--workload', action='store_true')
    a = ap.parse_args()
    yaw_target = bounded_yaw(a.yaw)
    missing_services = []
    if a.workload:
        import subprocess
        for unit in WORKLOAD_SERVICES:
            r = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit + '.service'])
            if r.returncode != 0:
                missing_services.append(unit)
        if missing_services:
            print('ABORT: not the full workload, inactive: ' + ', '.join(missing_services))
            return

    import sys
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu, LaserScan
    from std_msgs.msg import String
    from std_srvs.srv import Trigger
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    sys.path.insert(0, '/home/jetson/project_atlas/scripts')
    from atlas_scan_geometry import ray_in_base_sector

    class Check(Node):
        def __init__(self):
            super().__init__('atlas_turn_ground_check')
            self.pub = self.create_publisher(Twist, '/cmd_vel_commission', 10)
            self.arm_c = self.create_client(Trigger, '/atlas/commission/arm')
            self.disarm_c = self.create_client(Trigger, '/atlas/commission/disarm')
            self.odom = None; self.odom_t = 0.0
            self.icp_yaw = None
            self.icp_xy = None
            self.gz = None; self.imu_t = 0.0; self.imu_yaw = 0.0
            self.loop = {}; self.loop_t = 0.0
            self.points = []; self.scan_t = 0.0; self.blind = 0
            self.timing_on = False; self.streams = {k: [] for k in ('imu', 'ekf', 'tf_odom_base', 'tf_map_odom')}
            self.ekf_yaw = None; self.active_s = 0.0; self.ekf_turns = []; self.arc_index = 0
            self.create_subscription(Odometry, '/yahboom/odom', self.on_odom, 20)
            if a.workload:
                from tf2_msgs.msg import TFMessage
                self.create_subscription(Odometry, '/odom', self.on_ekf, 20)
                self.create_subscription(TFMessage, '/tf', self.on_tf, 50)
            self.create_subscription(Odometry, '/lidar/icp_odom', self.on_icp, 20)
            self.create_subscription(Imu, '/im10a/imu/bias_corrected_candidate', self.on_imu, qos_profile_sensor_data)
            self.create_subscription(String, '/atlas/speed_loop', self.on_loop, 20)
            self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

        def on_odom(self, m):
            p = m.pose.pose.position
            self.odom = (p.x, p.y, m.twist.twist.linear.x); self.odom_t = time.monotonic()

        def age(self, stamp):
            return (self.get_clock().now().nanoseconds - (stamp.sec * 10 ** 9 + stamp.nanosec)) / 1e9

        def on_ekf(self, m):
            self.ekf_yaw = _yaw(m.pose.pose.orientation)
            if self.timing_on:
                self.streams['ekf'].append((time.monotonic(), self.age(m.header.stamp), self.arc_index))

        def on_tf(self, m):
            if not self.timing_on:
                return
            for tr in m.transforms:
                k = tr.header.frame_id.lstrip('/') + '->' + tr.child_frame_id.lstrip('/')
                name = {'odom->base_link': 'tf_odom_base', 'map->odom': 'tf_map_odom'}.get(k)
                if name:
                    self.streams[name].append((time.monotonic(), self.age(tr.header.stamp), self.arc_index))

        def on_icp(self, m):
            self.icp_yaw = _yaw(m.pose.pose.orientation)
            self.icp_xy = (m.pose.pose.position.x, m.pose.pose.position.y)

        def on_imu(self, m):
            now = time.monotonic()
            gz = float(m.angular_velocity.z)
            if self.gz is not None and now - self.imu_t < 0.5:
                self.imu_yaw += math.degrees(0.5 * (gz + self.gz) * (now - self.imu_t))
            self.gz = gz; self.imu_t = now
            if self.timing_on:
                self.streams['imu'].append((now, self.age(m.header.stamp), self.arc_index))

        def on_loop(self, m):
            try:
                self.loop = json.loads(m.data); self.loop_t = time.monotonic()
            except ValueError:
                pass

        def on_scan(self, m):
            pts, front, ang = [], 0, m.angle_min
            for r in m.ranges:
                if math.isfinite(r) and r >= m.range_min:
                    b = math.radians(math.degrees(ang) + LASER_YAW_DEG)
                    pts.append((LASER_X_M + r * math.cos(b), r * math.sin(b)))
                    if ray_in_base_sector(math.degrees(ang), 0.0, 18.0, LASER_YAW_DEG):
                        front += 1
                ang += m.angle_increment
            self.blind = 0 if front else self.blind + 1
            self.points = pts; self.scan_t = time.monotonic()

        def call(self, client, timeout):
            if not client.wait_for_service(timeout_sec=timeout):
                return None
            fut = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, fut, timeout_sec=8.0)
            return fut.result()

        def spin_for(self, seconds):
            t_end = time.monotonic() + seconds
            while time.monotonic() < t_end:
                rclpy.spin_once(self, timeout_sec=0.05)

    def run_arc(n, direction):
        clear = swept_clearance(n.points, direction, yaw_target)
        if clear < math.inf:
            print(f'ABORT: something is on the {"left" if direction > 0 else "right"} arc path, {clear:.2f} m ahead '
                  f'along the curve; clear the floor and start again')
            return None
        r = n.call(n.arm_c, 12.0)
        print(f'ARM success={getattr(r, "success", None)} message={getattr(r, "message", "no response")}', flush=True)
        if r is None or not r.success:
            return None
        x0, y0 = n.odom[:2]; yaw0 = n.imu_yaw; icp0 = n.icp_yaw; ekf0 = n.ekf_yaw
        vo0, icpp0 = vo_shadow_pose(), (n.icp_xy, n.icp_yaw)      # step 7: shadow VO, read-only (file)
        n.arc_index += 1; t_on = None
        cmd = Twist(); cmd.linear.x = VX; cmd.angular.z = WZ * direction
        samples, end, runaway, t0 = [], 'RUNNING', 0, time.monotonic()
        try:
            while rclpy.ok() and end == 'RUNNING':
                rclpy.spin_once(n, timeout_sec=0.05)
                now = time.monotonic(); t = now - t0
                if t_on is None and t >= TIMING_WARMUP_S:
                    n.timing_on = True; t_on = now
                d = math.hypot(n.odom[0] - x0, n.odom[1] - y0); v = n.odom[2]; yaw = n.imu_yaw - yaw0
                clear = swept_clearance(n.points, direction, yaw_target - yaw * direction)
                if not samples or t - samples[-1]['t'] >= 0.1:
                    samples.append({'t': round(t, 2), 'v': round(v, 3), 'd': round(d, 3), 'yaw': round(yaw, 2),
                                    'clear': None if math.isinf(clear) else round(clear, 2),
                                    'reason': n.loop.get('reason')})
                    print(f't={t:4.1f}s wheel={v:+.3f} m/s d={d:.3f} m turn={yaw:+5.1f} deg clear={clear:.2f}', flush=True)
                runaway = runaway + 1 if v > RUNAWAY_MPS else 0
                if yaw * direction >= yaw_target: end = 'YAW'
                elif d >= DISTANCE_GUARD_M: end = 'STOP_DISTANCE_WITHOUT_TURN'
                elif t >= TIMEOUT_S: end = 'TIMEOUT'
                elif clear < STOP_CLEAR_M: end = f'STOP_LIDAR_{clear:.2f}M'
                elif n.blind >= 3: end = 'STOP_LIDAR_FRONT_BLIND'
                elif now - n.scan_t > STALE_S: end = 'STOP_SCAN_STALE'
                elif now - n.odom_t > STALE_S: end = 'STOP_ODOM_STALE'
                elif now - n.imu_t > STALE_S: end = 'STOP_IMU_STALE'
                elif now - n.loop_t > STALE_S and t > 0.5: end = 'STOP_SPEED_LOOP_STATUS_STALE'
                elif str(n.loop.get('reason', '')).startswith('fail_closed'): end = 'STOP_SPEED_LOOP_FAIL_CLOSED'
                elif runaway >= 2: end = 'STOP_RUNAWAY'
                else:
                    n.pub.publish(cmd)
        except KeyboardInterrupt:
            end = 'STOP_CTRL_C'
        finally:
            if t_on is not None:                           # timing covers the driven arc only
                n.timing_on = False; n.active_s += time.monotonic() - t_on
            for _ in range(5):
                n.pub.publish(Twist()); time.sleep(0.02)
            n.call(n.disarm_c, 0.5)
        t_stop, settle = time.monotonic(), None
        while time.monotonic() - t_stop < 3.0:          # wait for standstill, record the coast
            rclpy.spin_once(n, timeout_sec=0.05)
            if abs(n.odom[2]) < STILL_MPS:
                settle = round(time.monotonic() - t_stop, 2); break
        n.spin_for(1.0)
        icp_turn = wrap_deg(n.icp_yaw - icp0) if (n.icp_yaw is not None and icp0 is not None) else None
        if a.workload:
            n.ekf_turns.append((wrap_deg(n.ekf_yaw - ekf0) if (n.ekf_yaw is not None and ekf0 is not None) else None,
                                icp_turn))
        res = evaluate_arc(samples, direction, end, icp_turn, settle)
        res['vo'] = vo_arc(vo0, icpp0, (n.icp_xy, n.icp_yaw))
        res['samples'] = samples
        print(json.dumps({k: v for k, v in res.items() if k != 'samples'}), flush=True)
        return res if end != 'STOP_CTRL_C' else dict(res, aborted=True)

    rclpy.init()
    n = Check()
    arcs = []
    try:
        t_wait = time.monotonic() + 20.0
        while time.monotonic() < t_wait and (n.odom is None or not n.loop or n.scan_t == 0.0 or n.gz is None):
            rclpy.spin_once(n, timeout_sec=0.1)
        missing = [t for t, ok in (('/yahboom/odom', n.odom is not None), ('/atlas/speed_loop', bool(n.loop)),
                                   ('/scan', n.scan_t != 0.0), ('IM10A imu', n.gz is not None)) if not ok]
        if missing:
            print('ABORT: not received within 20 s: ' + ', '.join(missing))
            return
        for direction in (+1, -1):
            print(f'=== {"LEFT" if direction > 0 else "RIGHT"} arc ===', flush=True)
            arc = run_arc(n, direction)
            if arc is None:
                break
            arcs.append(arc)
            if arc.get('aborted') or arc['end_reason'] != 'YAW':
                break                                     # a guard stopped it: do not start the next arc
            n.spin_for(1.0)
    finally:
        n.pub.publish(Twist())
    if not arcs:
        n.destroy_node(); rclpy.shutdown(); return
    res = evaluate(arcs)
    label, prefix = 'STAGE 2', 'turn_check_'
    if a.workload:
        try:
            load = round(__import__('os').getloadavg()[0], 2)
        except OSError:
            load = None
        wl = evaluate_workload(n.streams, n.active_s, configured_offsets('/home/jetson/project_atlas'),
                               n.ekf_turns, missing_services, load)
        res = combine_part_b(res, wl)
        label, prefix = 'STAGE 4 PART B', 'imu_workload_check_'
    res['yaw_target_deg'] = yaw_target
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = Path.home() / '.local/state/project_atlas' / f'{prefix}{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import atlas_master_plan
        if a.workload:
            atlas_master_plan.record_stage4b(res, out.name)
        else:
            atlas_master_plan.record_stage2(res, out.name)
    except Exception as exc:                              # the board must never break the test result
        print(f'note: master plan not updated ({exc})')
    print(json.dumps({k: v for k, v in res.items() if k != 'arcs'}, indent=1))
    print(f'{label}: {res["verdict"]}')
    print(f'saved {out}')
    n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
