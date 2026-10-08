"""Offline sensitivity experiment, NOT validated LiDAR deskew.

Tests forward/reverse uniform ray-time hypotheses using recorded gyro Z.
Driver read duration is not a verified acquisition clock. Translation omitted.
No ROS node or modified bag is created.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from atlas_turn_sensor_audit import icp
from atlas_scan_tf_timing_audit import stats


def rotate(points, angles):
    c, s = np.cos(angles), np.sin(angles)
    return np.c_[c*points[:, 0]-s*points[:, 1], s*points[:, 0]+c*points[:, 1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('--event', type=float, required=True)
    parser.add_argument('--output', help='New diagnostic JSON file (never overwritten)')
    args = parser.parse_args()
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    scans, gyro = [], []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic not in {'/scan', '/im10a/imu/bias_corrected_candidate'}:
            continue
        m = deserialize_message(data, types[topic])
        t = m.header.stamp.sec+m.header.stamp.nanosec*1e-9
        if abs(t-args.event) > 7:
            continue
        if topic == '/scan':
            scans.append((t, m))
        else:
            gyro.append((t, m.angular_velocity.z))
    if len(gyro) < 2 or len(scans) < 2:
        raise SystemExit('Insufficient recorded input')
    g = np.asarray(sorted(gyro))
    # Cumulative trapezoidal integration, with shared reference for all variants.
    heading = np.r_[0, np.cumsum(np.diff(g[:,0])*(g[:-1,1]+g[1:,1])*0.5)]
    prepared = []
    for t, m in sorted(scans, key=lambda item: item[0]):
        n = len(m.ranges)
        duration = (n-1)*m.time_increment
        if n < 30 or t < g[0,0] or t+duration > g[-1,0]:
            continue
        r = np.asarray(m.ranges)
        keep = np.isfinite(r)&(r>0.3)&(r<8.0)
        angles = m.angle_min+np.arange(n)*m.angle_increment
        points = np.c_[r[keep]*np.cos(angles[keep]), r[keep]*np.sin(angles[keep])]
        h0 = np.interp(t, g[:,0], heading)
        fits = {'unchanged': points}
        for name, indexes in [('forward_time', np.arange(n)), ('reverse_time', np.arange(n)[::-1])]:
            beam_times = t+indexes[keep]*m.time_increment
            change = np.interp(beam_times, g[:,0], heading)-h0
            fits[name] = rotate(points, change)
        rotation = abs(math.degrees(np.interp(t+duration,g[:,0],heading)-h0))
        prepared.append((t, h0, rotation, fits))
    rows = []
    for a,b in zip(prepared, prepared[1:]):
        if abs(a[0]-args.event) > 5 or b[0]-a[0] > 0.4:
            continue
        row = {'offset_s': a[0]-args.event, 'reported_window_rotation_deg': max(a[2],b[2]), 'fits': {}}
        for name in a[3]:
            row['fits'][name] = icp(a[3][name], b[3][name], b[1]-a[1])
        rows.append(row)
    summary = {}
    for group, selected in [('all', rows), ('rotation_over_2deg', [r for r in rows if r['reported_window_rotation_deg']>2])]:
        result = {'pairs': len(selected)}
        for name in ('unchanged', 'forward_time', 'reverse_time'):
            result[name+'_rmse_m'] = stats([r['fits'][name]['rmse_m'] for r in selected if r['fits'][name]])
            if name != 'unchanged':
                comparable = [r for r in selected if r['fits'][name] and r['fits']['unchanged']]
                result[name+'_improved_pairs'] = sum(r['fits'][name]['rmse_m']<r['fits']['unchanged']['rmse_m'] for r in comparable)
        summary[group] = result
    report = {'summary': summary, 'rows': rows,
              'limitations': 'Uniform ray-time hypotheses only. ICP residual is not map accuracy. Rotation-only; unknown SDK phase, driver reordering, translation, dynamics and nearest-neighbour ambiguities remain.'}
    if args.output:
        with Path(args.output).open('x') as destination:
            json.dump(report, destination, indent=2)
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
