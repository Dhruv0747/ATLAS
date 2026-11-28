#!/usr/bin/env python3
"""ATLAS Stage-4 part A: PARKED IM10A / EKF / TF check (read-only, no motion). 2026-11-23.

Master-plan step 4 "Revalidate IM10A/EKF/TF using stationary bias, controlled turns and full workload timing.
Promote no IMU field without covariance and drift evidence." This tool covers the STATIONARY part only. It publishes
nothing and never commands motion. ATLAS must stay parked for the whole --duration (default 60 s).

It records /im10a/imu/bias_corrected_candidate, /odom (EKF), /yahboom/odom and /tf, then checks:
  parked             wheel speed stayed below 0.01 m/s (otherwise the result is MOVED: repeat it)
  imu_rate           IM10A >= 8 Hz and no gap > 0.30 s
  imu_covariance     the fused gyro-Z field carries a positive covariance (no field without covariance)
  imu_bias           |mean gyro-Z| <= 0.002 rad/s
  imu_drift          integrated gyro-Z heading change <= 1.0 deg over the run
  ekf_rate           /odom >= 8 Hz and no gap > 0.30 s
  ekf_drift          EKF heading change <= 1.0 deg and position change <= 0.02 m
  tf_odom_base       odom -> base_link >= 8 Hz
  tf_map_odom        map -> odom present (>= 1 Hz)
Note: the IM10A reports gyro in steps of 0.061 deg/s and reads exactly 0 below one step, so a parked bias of 0 is
expected; very slow rotation below that step is invisible to it (documented 2026-10-02).

Usage (on the Jetson):  python3 imu_ekf_tf_parked_check.py [--duration 60]
"""
import argparse
import json
import math
import time
from pathlib import Path

DURATION_MIN, DURATION_MAX = 20.0, 120.0
PARKED_MPS = 0.01
RATE_MIN_HZ = 8.0
GAP_MAX_S = 0.30
BIAS_MAX_RAD_S = 0.002
DRIFT_MAX_DEG = 1.0
EKF_POS_MAX_M = 0.02
MAP_ODOM_MIN_HZ = 1.0


def bounded_duration(d):
    if not DURATION_MIN <= d <= DURATION_MAX:
        raise ValueError(f'--duration must be within {DURATION_MIN:.0f}..{DURATION_MAX:.0f} s')
    return d


def _rate(ts, duration):
    return len(ts) / duration if duration > 0 else 0.0


def _max_gap(ts):
    return max((b - a for a, b in zip(ts, ts[1:])), default=math.inf)


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def evaluate(imu, ekf, wheel_v, tf_counts, duration):
    """imu: [(t, gz, gz_cov)], ekf: [(t, x, y, yaw_deg)], wheel_v: [v], tf_counts: {'odom->base_link': n, ...}.
    Pure; unit-tested."""
    c, m = {}, {'duration_s': round(duration, 1)}
    moved = max((abs(v) for v in wheel_v), default=0.0)
    m['wheel_max_mps'] = round(moved, 4)
    c['parked'] = bool(wheel_v) and moved < PARKED_MPS
    its = [s[0] for s in imu]
    m['imu_hz'], m['imu_max_gap_s'] = round(_rate(its, duration), 1), round(_max_gap(its), 3) if len(its) > 1 else None
    c['imu_rate'] = len(its) > 1 and m['imu_hz'] >= RATE_MIN_HZ and _max_gap(its) <= GAP_MAX_S
    c['imu_covariance'] = bool(imu) and all(s[2] > 0 for s in imu)
    gz = [s[1] for s in imu]
    mean = sum(gz) / len(gz) if gz else math.inf
    drift = math.degrees(sum(0.5 * (imu[i][1] + imu[i + 1][1]) * (imu[i + 1][0] - imu[i][0])
                             for i in range(len(imu) - 1) if imu[i + 1][0] - imu[i][0] < 0.5)) if len(imu) > 1 else math.inf
    m['imu_mean_gz_rad_s'], m['imu_drift_deg'] = (round(mean, 5) if gz else None), (round(drift, 3) if len(imu) > 1 else None)
    c['imu_bias'] = bool(gz) and abs(mean) <= BIAS_MAX_RAD_S
    c['imu_drift'] = len(imu) > 1 and abs(drift) <= DRIFT_MAX_DEG
    ets = [s[0] for s in ekf]
    m['ekf_hz'] = round(_rate(ets, duration), 1)
    c['ekf_rate'] = len(ets) > 1 and m['ekf_hz'] >= RATE_MIN_HZ and _max_gap(ets) <= GAP_MAX_S
    if len(ekf) > 1:
        m['ekf_yaw_change_deg'] = round(wrap_deg(ekf[-1][3] - ekf[0][3]), 3)
        m['ekf_pos_change_m'] = round(math.hypot(ekf[-1][1] - ekf[0][1], ekf[-1][2] - ekf[0][2]), 4)
        c['ekf_drift'] = abs(m['ekf_yaw_change_deg']) <= DRIFT_MAX_DEG and m['ekf_pos_change_m'] <= EKF_POS_MAX_M
    else:
        c['ekf_drift'] = False
    m['tf_odom_base_hz'] = round(tf_counts.get('odom->base_link', 0) / duration, 1) if duration > 0 else 0.0
    m['tf_map_odom_hz'] = round(tf_counts.get('map->odom', 0) / duration, 1) if duration > 0 else 0.0
    c['tf_odom_base'] = m['tf_odom_base_hz'] >= RATE_MIN_HZ
    c['tf_map_odom'] = m['tf_map_odom_hz'] >= MAP_ODOM_MIN_HZ
    failed = [k for k, v in c.items() if not v]
    verdict = 'MOVED' if not c['parked'] and wheel_v else ('PASS' if not failed else 'FAIL')
    detail = 'parked %.0f s: IM10A %.1f Hz, drift %s deg; EKF %.1f Hz, yaw %s deg, pos %s m; TF %.1f / %.1f Hz' % (
        duration, m['imu_hz'], m['imu_drift_deg'], m['ekf_hz'], m.get('ekf_yaw_change_deg'), m.get('ekf_pos_change_m'),
        m['tf_odom_base_hz'], m['tf_map_odom_hz'])
    return {'verdict': verdict, 'checks': c, 'measured': m, 'failed': failed, 'detail': detail}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--duration', type=float, default=60.0)
    duration = bounded_duration(ap.parse_args().duration)

    import sys
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Imu
    from tf2_msgs.msg import TFMessage
    sys.path.insert(0, '/home/jetson/project_atlas/scripts')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

    def yaw(q):
        return math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))

    rclpy.init()
    n = rclpy.create_node('atlas_imu_ekf_tf_parked_check')
    imu, ekf, wheel, tf = [], [], [], {}
    rec = {'on': False}

    def on_imu(m):
        if rec['on']:
            imu.append((time.monotonic(), float(m.angular_velocity.z), float(m.angular_velocity_covariance[8])))

    def on_ekf(m):
        if rec['on']:
            p = m.pose.pose.position
            ekf.append((time.monotonic(), p.x, p.y, yaw(m.pose.pose.orientation)))

    def on_wheel(m):
        if rec['on']:
            wheel.append(float(m.twist.twist.linear.x))

    def on_tf(m):
        if rec['on']:
            for t in m.transforms:
                k = t.header.frame_id.lstrip('/') + '->' + t.child_frame_id.lstrip('/')
                tf[k] = tf.get(k, 0) + 1

    n.create_subscription(Imu, '/im10a/imu/bias_corrected_candidate', on_imu, qos_profile_sensor_data)
    n.create_subscription(Odometry, '/odom', on_ekf, 20)
    n.create_subscription(Odometry, '/yahboom/odom', on_wheel, 20)
    n.create_subscription(TFMessage, '/tf', on_tf, 50)
    t_warm = time.monotonic() + 3.0                      # DDS discovery before recording starts
    while time.monotonic() < t_warm:
        rclpy.spin_once(n, timeout_sec=0.1)
    print(f'RECORDING {duration:.0f} s — keep ATLAS parked, do not touch it or the remote', flush=True)
    rec['on'] = True
    t0 = time.monotonic(); last = t0
    try:
        while time.monotonic() - t0 < duration:
            rclpy.spin_once(n, timeout_sec=0.05)
            if time.monotonic() - last >= 10:
                last = time.monotonic()
                print(f'  {last - t0:4.0f} s  imu {len(imu)}  ekf {len(ekf)}  wheel {len(wheel)}', flush=True)
                if any(abs(v) >= PARKED_MPS for v in wheel):
                    print('ATLAS MOVED: stopping early; repeat with ATLAS parked', flush=True)
                    break
    except KeyboardInterrupt:
        pass
    rec['on'] = False
    res = evaluate(imu, ekf, wheel, tf, time.monotonic() - t0)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = Path.home() / '.local/state/project_atlas' / f'imu_check_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import atlas_master_plan
        atlas_master_plan.record_stage4a(res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STAGE 4 PART A: {res["verdict"]}')
    print(f'saved {out}')
    n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
