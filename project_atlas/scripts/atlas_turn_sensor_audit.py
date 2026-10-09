"""Offline yaw comparison near the largest recorded map correction.

ICP is a diagnostic estimate, not ground truth or a navigation input.
"""
import argparse
import json
import math
import numpy as np
from scipy.spatial import cKDTree
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def stamp(m):
    return m.header.stamp.sec + m.header.stamp.nanosec*1e-9


def icp(old, new, initial):
    if len(old) < 30 or len(new) < 30:
        return None
    a = initial
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    t = np.zeros(2)
    tree = cKDTree(old)
    for _ in range(40):
        moved = new @ R.T + t
        dist, idx = tree.query(moved)
        keep = dist < min(0.45, np.quantile(dist, 0.8))
        if keep.sum() < 30:
            return None
        x, y = moved[keep], old[idx[keep]]
        xc, yc = x.mean(0), y.mean(0)
        u, _, vt = np.linalg.svd((x-xc).T @ (y-yc))
        delta = vt.T @ u.T
        if np.linalg.det(delta) < 0:
            vt[-1] *= -1
            delta = vt.T @ u.T
        shift = yc-delta@xc
        R, t = delta@R, delta@t+shift
        if np.linalg.norm(shift) < 1e-5 and abs(math.atan2(delta[1, 0], delta[0, 0])) < 1e-5:
            break
    dist, _ = tree.query(new@R.T+t)
    keep = dist < min(0.45, np.quantile(dist, 0.8))
    return {'yaw_deg': math.degrees(math.atan2(R[1, 0], R[0, 0])),
            'rmse_m': float(np.sqrt(np.mean(dist[keep]**2))),
            'inliers': int(keep.sum())}


def event_time(corrections, scans, center_offset_s=None):
    if center_offset_s is not None:
        return scans[0][0] + center_offset_s
    return max(zip(corrections, corrections[1:]),
               key=lambda p: math.hypot(p[1][1]-p[0][1],
                                        p[1][2]-p[0][2]))[1][0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('--center-offset-s', type=float,
                        help='compare scans near this offset from the first scan; '
                             'default is the largest map correction')
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    scans, corrections = [], []
    odom = {'/odom': [], '/yahboom/odom': []}
    gyro = []
    while reader.has_next():
        topic, data, record = reader.read_next()
        if topic not in {'/scan', '/tf', '/odom', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate'}:
            continue
        m = deserialize_message(data, types[topic])
        if topic == '/scan':
            r = np.asarray(m.ranges)
            a = m.angle_min+np.arange(len(r))*m.angle_increment
            keep = np.isfinite(r)&(r>0.3)&(r<8.0)
            scans.append((stamp(m), np.c_[r[keep]*np.cos(a[keep]), r[keep]*np.sin(a[keep])]))
        elif topic in odom:
            odom[topic].append((stamp(m), yaw(m.pose.pose.orientation)))
        elif topic.endswith('bias_corrected_candidate'):
            gyro.append((stamp(m), m.angular_velocity.z))
        else:
            for tr in m.transforms:
                if tr.header.frame_id.strip('/') == 'map' and tr.child_frame_id.strip('/') == 'odom':
                    corrections.append((record*1e-9, tr.transform.translation.x, tr.transform.translation.y))
    if len(corrections) < 2 or not scans or not gyro or any(not s for s in odom.values()):
        raise SystemExit('Required scans, map corrections, odometry or candidate IMU data missing')
    scans.sort(key=lambda s: s[0])
    gyro.sort()
    for series in odom.values():
        series.sort()
    event = event_time(corrections, scans, args.center_offset_s)
    def heading(series, t):
        values = np.asarray(series)
        return float(np.interp(t, values[:, 0], np.unwrap(values[:, 1])))
    rows = []
    for offset in [-5, -3, -1, 1, 3]:
        first = min(scans, key=lambda s: abs(s[0]-(event+offset)))
        last = min(scans, key=lambda s: abs(s[0]-(first[0]+1)))
        if last[0] <= first[0] or any(
            first[0] < series[0][0] or last[0] > series[-1][0]
            for series in [gyro, *odom.values()]
        ):
            rows.append({'offset_s': offset, 'unavailable': 'Insufficient time coverage'})
            continue
        angles = {key: math.degrees(heading(series,last[0])-heading(series,first[0])) for key,series in odom.items()}
        g = np.asarray(gyro)
        times = np.r_[first[0], g[(g[:,0]>first[0])&(g[:,0]<last[0]),0], last[0]]
        integrated = float(np.trapz(np.interp(times,g[:,0],g[:,1]),times))
        seeds = [0.0, math.radians(angles['/odom']), integrated]
        fits = [icp(first[1],last[1],seed) for seed in seeds]
        rows.append({'offset_s':offset,'dt_s':last[0]-first[0], 'odom_yaw_deg':angles,
                     'imu_integrated_yaw_deg': math.degrees(integrated),'scan_icp_seeds':fits})
    print(json.dumps({'event_unix':event,'rows':rows,
                      'limitations':'ICP is un-deskewed, locally optimized and can match ambiguous walls. Pose interpolation uses message stamps; verify clock offsets before tuning.'},indent=2))


if __name__ == '__main__':
    main()
