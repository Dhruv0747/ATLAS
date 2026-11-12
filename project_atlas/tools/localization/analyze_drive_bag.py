#!/usr/bin/env python3
"""Offline localization analysis of a recorded drive (read-only; never touches the running rover).

Usage: python3 analyze_drive_bag.py BAG_DIR [MAP_YAML]
Reports over time: AMCL pose + uncertainty, map->odom correction jumps, particle spread, scan-to-map fit at the
AMCL pose (fraction of LiDAR hits within 10 cm of an occupied map cell), and odometry source disagreement
(EKF /odom vs wheel /yahboom/odom vs /lidar/odom).
"""
import math
import sys
from pathlib import Path

import numpy as np
import yaml


def read_bag(path, topics):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(path), storage_id='sqlite3'),
           rosbag2_py.ConverterOptions('cdr', 'cdr'))
    types = {t.name: t.type for t in r.get_all_topics_and_types()}
    r.set_filter(rosbag2_py.StorageFilter(topics=[t for t in topics if t in types]))
    out = {t: [] for t in topics}
    while r.has_next():
        t, data, ts = r.read_next()
        out[t].append((ts * 1e-9, deserialize_message(data, get_message(types[t]))))
    return out


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def load_map(yaml_path):
    from PIL import Image
    y = yaml.safe_load(Path(yaml_path).read_text())
    img = np.array(Image.open(Path(yaml_path).parent / y['image']).convert('L'))
    occ = (255 - img) / 255.0 > float(y.get('occupied_thresh', 0.65))
    if y.get('negate', 0):
        occ = (img / 255.0) > float(y.get('occupied_thresh', 0.65))
    from scipy.ndimage import distance_transform_edt
    dist = distance_transform_edt(~occ) * float(y['resolution'])
    return {'res': float(y['resolution']), 'origin': y['origin'], 'h': img.shape[0], 'dist': dist}


def scan_fit(m, scan, pose):
    """Fraction of valid scan hits within 0.10 m of an occupied map cell, laser at pose (x, y, yaw) [laser ~ base]."""
    r = np.array(scan.ranges, dtype=float)
    a = scan.angle_min + np.arange(len(r)) * scan.angle_increment
    ok = np.isfinite(r) & (r > scan.range_min) & (r < min(scan.range_max, 8.0))
    if ok.sum() < 20:
        return None
    x, y, th = pose
    wx = x + r[ok] * np.cos(a[ok] + th); wy = y + r[ok] * np.sin(a[ok] + th)
    i = (m['h'] - 1 - ((wy - m['origin'][1]) / m['res']).astype(int)); j = ((wx - m['origin'][0]) / m['res']).astype(int)
    inside = (i >= 0) & (i < m['h']) & (j >= 0) & (j < m['dist'].shape[1])
    d = np.full(len(wx), 9.9); d[inside] = m['dist'][i[inside], j[inside]]
    return float((d < 0.10).mean())


def main():
    bag = Path(sys.argv[1]); map_yaml = sys.argv[2] if len(sys.argv) > 2 else str(Path.home() / 'project_atlas/maps/atlas_latest.yaml')
    d = read_bag(bag, ['/amcl_pose', '/odom', '/yahboom/odom', '/lidar/odom', '/scan', '/particle_cloud', '/cmd_vel'])
    t0 = min(v[0][0] for v in d.values() if v)
    amcl = [(t - t0, m.pose.pose.position.x, m.pose.pose.position.y, yaw_of(m.pose.pose.orientation),
             math.sqrt(max(m.pose.covariance[0], m.pose.covariance[7])), math.degrees(math.sqrt(max(m.pose.covariance[35], 0))))
            for t, m in d['/amcl_pose']]
    def odo(topic):
        return np.array([(t - t0, m.pose.pose.position.x, m.pose.pose.position.y, yaw_of(m.pose.pose.orientation),
                          m.twist.twist.linear.x, m.twist.twist.angular.z) for t, m in d[topic]]) if d[topic] else None
    ekf, wheel, lid = odo('/odom'), odo('/yahboom/odom'), odo('/lidar/odom')
    moving = ekf[np.abs(ekf[:, 4]) > 0.02] if ekf is not None else None
    print(f'bag {bag.name}: {ekf[-1,0]:.0f} s; moving {len(moving)/max(1,len(ekf))*100:.0f} % of samples; amcl_pose msgs {len(amcl)}')
    def pathlen(o): return float(np.linalg.norm(np.diff(o[:, 1:3], axis=0), axis=1).sum())
    def yawtot(o): return math.degrees(float(np.abs(np.diff(np.unwrap(o[:, 3]))).sum()))
    for name, o in (('EKF /odom', ekf), ('wheel /yahboom/odom', wheel), ('LiDAR /lidar/odom', lid)):
        if o is not None and len(o) > 2:
            print(f'  {name:22s} path {pathlen(o):5.2f} m, end ({o[-1,1]:+.2f},{o[-1,2]:+.2f}) yaw {math.degrees(o[-1,3]):+6.1f} deg, total turning {yawtot(o):6.1f} deg')
    # AMCL correction (map->odom) jumps: compare amcl pose with ekf pose at the same time
    a = np.array(amcl)
    if len(a) and ekf is not None:
        ei = np.searchsorted(ekf[:, 0], a[:, 0]).clip(0, len(ekf) - 1)
        corr = []
        for k, (t, x, y, th, sxy, syaw) in enumerate(amcl):
            ex, ey, eth = ekf[ei[k], 1], ekf[ei[k], 2], ekf[ei[k], 3]
            dth = (th - eth + math.pi) % (2 * math.pi) - math.pi
            cx = x - (math.cos(dth) * ex - math.sin(dth) * ey); cy = y - (math.sin(dth) * ex + math.cos(dth) * ey)
            corr.append((t, cx, cy, math.degrees(dth)))
        corr = np.array(corr)
        jumps = np.hypot(np.diff(corr[:, 1]), np.diff(corr[:, 2])); yj = np.abs((np.diff(corr[:, 3]) + 180) % 360 - 180)
        big = np.where((jumps > 0.25) | (yj > 10))[0]
        print(f'  AMCL: std_xy median {np.median(a[:,4]):.2f} m, max {a[:,4].max():.2f} m; std_yaw median {np.median(a[:,5]):.1f} deg, max {a[:,5].max():.1f} deg')
        print(f'  AMCL map->odom correction: total drift {np.hypot(corr[-1,1]-corr[0,1], corr[-1,2]-corr[0,2]):.2f} m / {((corr[-1,3]-corr[0,3]+180)%360-180):+.1f} deg; jumps >25 cm or >10 deg: {len(big)}')
        for k in big[:12]:
            print(f'     t={corr[k+1,0]:5.0f}s  jump {jumps[k]:.2f} m / {yj[k]:.1f} deg  -> amcl ({a[k+1,1]:+.2f},{a[k+1,2]:+.2f}) std {a[k+1,4]:.2f} m')
        # timeline every ~30 s
        print('  timeline (t, amcl x y yaw, std_xy, std_yaw, scan fit to map):')
        m = load_map(map_yaml); scans = d['/scan']; st = np.array([t - t0 for t, _ in scans])
        fits = []
        for t, x, y, th, sxy, syaw in amcl:
            k = int(np.searchsorted(st, t).clip(0, len(scans) - 1)); f = scan_fit(m, scans[k][1], (x, y, th))
            fits.append((t, f))
        nxt = -1
        for (t, x, y, th, sxy, syaw), (_, f) in zip(amcl, fits):
            if t >= nxt:
                print(f'     {t:5.0f}s  ({x:+.2f},{y:+.2f},{math.degrees(th):+6.1f})  std {sxy:.2f} m {syaw:5.1f} deg  fit {f if f is None else round(f,2)}')
                nxt = t + 30
        fv = np.array([f for _, f in fits if f is not None])
        print(f'  scan fit to saved map at AMCL pose: median {np.median(fv):.2f}, p10 {np.percentile(fv,10):.2f}, worst {fv.min():.2f} (1.0 = every LiDAR hit on a mapped wall)')
    pc = d['/particle_cloud']
    if pc:
        spreads = []
        for t, m in pc:
            xs = np.array([p.pose.position.x for p in m.particles]); ys = np.array([p.pose.position.y for p in m.particles])
            spreads.append((t - t0, len(xs), float(np.hypot(xs.std(), ys.std()))))
        sp = np.array(spreads)
        print(f'  particles: count {int(sp[:,1].min())}-{int(sp[:,1].max())}, spread median {np.median(sp[:,2]):.2f} m, max {sp[:,2].max():.2f} m at t={sp[sp[:,2].argmax(),0]:.0f}s')


if __name__ == '__main__':
    main()
