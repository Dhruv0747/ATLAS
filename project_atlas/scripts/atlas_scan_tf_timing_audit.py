"""Read-only recorded LiDAR/TF timing audit; creates no ROS node."""
import argparse
import json
import math

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def stamp(header):
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


def stats(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {'n': 0}
    return dict(n=len(a), min=float(a.min()), median=float(np.median(a)),
                p95=float(np.percentile(a, 95)), max=float(a.max()))


def interpolate(series, times):
    a = np.asarray(sorted(series))
    # Caller checks coverage; never silently extrapolate.
    if min(times) < a[0, 0] or max(times) > a[-1, 0]:
        return None
    return np.interp(times, a[:, 0], np.unwrap(a[:, 1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    scans = {'/scan': [], '/scan_raw': []}
    odom, tf, gyro, corrections = [], [], [], []
    for_read = set(scans) | {'/odom', '/tf', '/im10a/imu/bias_corrected_candidate'}
    while reader.has_next():
        topic, data, record = reader.read_next()
        if topic not in for_read:
            continue
        m = deserialize_message(data, types[topic])
        receipt = record * 1e-9
        if topic in scans:
            scans[topic].append((stamp(m.header), receipt, m.scan_time,
                                m.time_increment, len(m.ranges)))
        elif topic == '/odom':
            odom.append((stamp(m.header), yaw(m.pose.pose.orientation)))
        elif topic.endswith('bias_corrected_candidate'):
            gyro.append((stamp(m.header), m.angular_velocity.z))
        else:
            for t in m.transforms:
                pair = (t.header.frame_id.strip('/'), t.child_frame_id.strip('/'))
                if pair == ('odom', 'base_link'):
                    tf.append((stamp(t.header), yaw(t.transform.rotation)))
                elif pair == ('map', 'odom'):
                    corrections.append((receipt, t.transform.translation.x, t.transform.translation.y))
    if len(corrections) < 2 or not odom or not tf or not gyro:
        raise SystemExit('Required recorded TF, odometry or IMU missing')
    event = max(zip(corrections, corrections[1:]),
                key=lambda p: math.hypot(p[1][1]-p[0][1], p[1][2]-p[0][2]))[1][0]
    raw = {round(s[0]*1e9): s for s in scans['/scan_raw']}
    report = {'event_unix': event, 'window_seconds': 5, 'scans': {}}
    for topic, series in scans.items():
        window = [s for s in series if abs(s[0]-event) <= 5]
        report['scans'][topic] = {
            'count_total': len(series),
            'nonincreasing_stamps': sum(b[0] <= a[0] for a, b in zip(series, series[1:])),
            'window_header_interval_ms': stats([(b[0]-a[0])*1000 for a,b in zip(window,window[1:])]),
            'window_receipt_age_ms': stats([(s[1]-s[0])*1000 for s in window]),
            'window_receipt_age_minus_scan_time_ms': stats([(s[1]-s[0]-s[2])*1000 for s in window]),
            'window_scan_time_ms': stats([s[2]*1000 for s in window]),
            'window_ray_span_ms': stats([s[3]*(s[4]-1)*1000 for s in window])}
    paired = [(s, raw[round(s[0]*1e9)]) for s in scans['/scan'] if round(s[0]*1e9) in raw]
    report['raw_filtered_stamp_matches'] = len(paired)
    report['filter_receipt_delay_ms'] = stats([(a[1]-b[1])*1000 for a,b in paired])
    window = [s for s in scans['/scan'] if abs(s[0]-event) <= 5]
    times = [s[0] for s in window]
    if not times:
        raise SystemExit('No scans in correction window')
    reference = interpolate(odom, times)
    report['tf_vs_odom_yaw_error_deg_by_tf_stamp_shift'] = {}
    for shift in [0.0, -0.1, -0.2, -0.3]:
        estimate = interpolate([(t+shift, y) for t,y in tf], times)
        if reference is not None and estimate is not None:
            error = np.arctan2(np.sin(estimate-reference), np.cos(estimate-reference))
            report['tf_vs_odom_yaw_error_deg_by_tf_stamp_shift'][str(shift)] = stats(np.abs(np.degrees(error)))
    g = np.asarray(sorted(gyro))
    rotations = []
    details = []
    for s in window:
        start, end = s[0], s[0]+s[3]*(s[4]-1)
        if end <= start or start < g[0,0] or end > g[-1,0]:
            continue
        t = np.r_[start, g[(g[:,0]>start)&(g[:,0]<end),0], end]
        rotations.append(abs(math.degrees(float(np.trapz(np.interp(t,g[:,0],g[:,1]),t)))))
        details.append({'seconds_from_correction': start-event,
                        'ray_span_ms': (end-start)*1000, 'rotation_deg': rotations[-1]})
    report['imu_rotation_during_one_scan_deg'] = stats(rotations)
    report['largest_scan_rotations'] = sorted(details, key=lambda d: d['rotation_deg'], reverse=True)[:3]
    report['caveat'] = ('Receipt age includes acquisition/transport. TF shift comparison measures consistency with the same EKF output, not physical ground truth. Scan rotation indicates possible distortion, not a proven mapping cause.')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
