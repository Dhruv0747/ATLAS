"""Read-only recorded encoder/gyro/scan comparison; no ROS node or commands."""
import collections
import json
import math
import sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from atlas_turn_sensor_audit import icp, stamp


def main(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    updates, gyro, scans, commands = [], [], [], []
    counts = collections.Counter()
    while reader.has_next():
        topic, data, ns = reader.read_next()
        counts[topic] += 1
        if topic not in {'/atlas/encoder_update', '/im10a/imu/bias_corrected_candidate', '/scan', '/cmd_vel'}:
            continue
        msg = deserialize_message(data, types[topic])
        if topic == '/atlas/encoder_update':
            updates.append(json.loads(msg.data))
        elif topic == '/cmd_vel':
            commands.append((ns/1e9, msg.linear.x, msg.angular.z))
        elif topic == '/scan':
            r = np.asarray(msg.ranges)
            a = msg.angle_min + np.arange(len(r))*msg.angle_increment
            keep = np.isfinite(r) & (r > .3) & (r < 8)
            scans.append((stamp(msg), np.c_[r[keep]*np.cos(a[keep]), r[keep]*np.sin(a[keep])]))
        else:
            gyro.append((stamp(msg), msg.angular_velocity.z))
    gyro.sort()
    scans.sort(key=lambda v: v[0])
    updates.sort(key=lambda v: v['stamp_ns'])
    if not updates:
        raise SystemExit('No encoder snapshots recorded')
    origin = updates[0]['stamp_ns']/1e9
    active = [t for t, v, w in commands if abs(v) > .005 or abs(w) > .01]
    groups = []
    for t in active:
        if not groups or t-groups[-1][-1] > 1.0:
            groups.append([t])
        else:
            groups[-1].append(t)
    def integral(a, b):
        total = 0.
        for (t, z), (t2, z2) in zip(gyro, gyro[1:]):
            overlap = max(0., min(b, t2)-max(a, t))
            if 0 < t2-t < .5:
                total += overlap*(z+z2)/2
        return total
    windows = [('whole_motion', group[0]-.2, group[-1]+.5) for group in groups]
    # Separate by commanded curvature, not gyro outcome (which would bias
    # the comparison). Labels do not assert physical left/right calibration.
    for group in groups:
        rows = [u for u in updates if group[0] <= u['stamp_ns']/1e9 <= group[-1]+.5]
        runs = []
        for u in rows:
            k = u['applied_curvature_per_m']
            label = 'positive_curvature' if k > .15 else 'negative_curvature' if k < -.15 else 'near_straight'
            t = u['stamp_ns']/1e9
            if not runs or runs[-1][0] != label:
                if runs:
                    runs[-1][2] = t
                runs.append([label, t, t])
            else:
                runs[-1][2] = t
        windows.extend(tuple(run) for run in runs if run[2]-run[1] >= .25)
    results = []
    for label, a, b in windows:
        rows = [u for u in updates if a <= u['stamp_ns']/1e9 < b]
        ss = [s for s in scans if a <= s[0] <= b]
        fits, zero_fits = [], []
        for old, new in zip(ss, ss[1:]):
            if 0 < new[0]-old[0] < .5:
                fit = icp(old[1], new[1], integral(old[0], new[0]))
                if fit:
                    fits.append(fit)
                zero_fit = icp(old[1], new[1], 0.0)
                if zero_fit:
                    zero_fits.append(zero_fit)
        results.append(dict(label=label, start_s=a-origin, end_s=b-origin, snapshots=len(rows),
            integrated_distance_m=sum(u['accepted_delta_m'] for u in rows),
            wheel_yaw_deg=math.degrees(sum(u['accepted_delta_m']*u['applied_curvature_per_m'] for u in rows)),
            gyro_yaw_deg=math.degrees(integral(a,b)),
            scan_icp_yaw_deg=sum(f['yaw_deg'] for f in fits),
            zero_seed_icp_yaw_deg=sum(f['yaw_deg'] for f in zero_fits),
            scan_pairs=len(fits), scan_pairs_possible=max(0,len(ss)-1),
            median_icp_rmse_m=float(np.median([f['rmse_m'] for f in fits])) if fits else None,
            selection_counts=dict(collections.Counter(str(u['accepted_channels']) for u in rows)),
            raw_count_change=[rows[-1]['raw_counts'][i]-rows[0]['raw_counts'][i] for i in range(4)] if rows else [],
            steering_ranges=[[min(u['steering_command_deg'][i] for u in rows),max(u['steering_command_deg'][i] for u in rows)] for i in range(2)] if rows else []))
    print(json.dumps(dict(bag=path, topic_counts=counts, segments=results,
        stale_snapshots=sum(not u['packet_fresh'] for u in updates),
        sequence_gaps=sum(max(0,b['sequence']-a['sequence']-1) for a,b in zip(updates,updates[1:])),
        caveat='ICP is gyro-seeded, not independent ground truth; command windows use receipt times. No calibration changes justified by this alone.'), indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
