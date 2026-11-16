#!/usr/bin/env python3
"""Offline replay of the LiDAR-availability guard with and without map-known gaps (read-only; no ROS graph).

For every recorded /scan while Nav2 commanded motion (/cmd_vel_nav), rebuild the guard decision with
atlas_lidar_availability (travel cone + swept bins) and report how many scans stay vetoed when missing bins may be
explained by the accepted map (map_known_bins) at several minimum wall distances. AMCL confidence gates as in the mux.
Usage: replay_map_known_gaps.py MAP_YAML BAG [BAG ...]
"""
import bisect, math, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import atlas_lidar_availability as ala  # noqa: E402
if os.environ.get('TIGHT_ARC_SWEPT') == '1':
    ala.TIGHT_ARC_FULL_RING = False


def load_map(yaml_path):
    import yaml
    meta = yaml.safe_load(open(yaml_path))
    data = open(os.path.join(os.path.dirname(yaml_path), meta['image']), 'rb').read()
    toks, i = [], 0
    while len(toks) < 4:
        while data[i:i + 1].isspace(): i += 1
        if data[i:i + 1] == b'#':
            while data[i:i + 1] != b'\n': i += 1
            continue
        j = i
        while not data[j:j + 1].isspace(): j += 1
        toks.append(data[i:j]); i = j
    i += 1
    w, h = int(toks[1]), int(toks[2]); px = data[i:i + w * h]
    neg = int(meta.get('negate', 0)); occ_th = meta.get('occupied_thresh', 0.65); free_th = meta.get('free_thresh', 0.25)
    grid = [0] * (w * h)
    for row in range(h):                       # pgm row 0 = top; OccupancyGrid row 0 = bottom
        for col in range(w):
            v = px[row * w + col]; p = (v / 255.0) if neg else ((255 - v) / 255.0)
            grid[(h - 1 - row) * w + col] = 100 if p > occ_th else (0 if p < free_th else -1)
    return ala.OccGrid(w, h, meta['resolution'], meta['origin'][0], meta['origin'][1], grid)


def main():
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
    grid = load_map(sys.argv[1])
    for bag in sys.argv[2:]:
        r = rosbag2_py.SequentialReader()
        r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
        r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/cmd_vel_nav', '/amcl_pose', '/astra/obstacle_coverage']))
        scans, nav, am, cov = [], [], [], []
        while r.has_next():
            t, b, ts = r.read_next(); s = ts / 1e9
            if t == '/scan': scans.append((s, deserialize_message(b, LaserScan)))
            elif t == '/astra/obstacle_coverage': cov.append((s, deserialize_message(b, LaserScan)))
            elif t == '/cmd_vel_nav':
                m = deserialize_message(b, Twist); nav.append((s, m.linear.x, m.angular.z))
            else:
                m = deserialize_message(b, PoseWithCovarianceStamped); p = m.pose.pose; c = m.pose.covariance
                am.append((s, p.position.x, p.position.y, 2 * math.atan2(p.orientation.z, p.orientation.w),
                           math.sqrt(max(0, c[0]) + max(0, c[7])), math.degrees(math.sqrt(max(0, c[35])))))
        nt = [n[0] for n in nav]; at = [a[0] for a in am]; ct = [c[0] for c in cov]
        thresholds = (None, 0.4, 'sweep')
        blocked = {k: 0 for k in thresholds}; total = 0; gated = 0
        for s, sc in scans:
            i = bisect.bisect_right(nt, s) - 1
            if i < 0 or s - nav[i][0] > 0.5 or abs(nav[i][1]) < 0.02:
                continue
            v, w = nav[i][1], nav[i][2]
            g = ala.LidarAvailability(); g.update(sc, 0.0)
            k_ = bisect.bisect_right(ct, s) - 1
            if k_ >= 0 and s - cov[k_][0] <= ala.COVER_TIMEOUT_S:
                g.update_coverage(cov[k_][1], 0.0)
            req = (ala.travel_cone(v) | ala.swept_bins(v, w)) if abs(w) > 1e-4 else ala.travel_cone(v)
            missing = req - g.bins - g.covered(0.0)
            total += 1
            j = bisect.bisect_right(at, s) - 1
            conf = (j >= 0 and s - am[j][0] <= ala.MAP_POSE_MAX_AGE_S and am[j][4] <= ala.MAP_POSE_MAX_XY_STD_M
                    and am[j][5] <= ala.MAP_POSE_MAX_YAW_STD_DEG)
            if missing and not conf:
                gated += 1
            for k in thresholds:
                left = missing
                if k is not None and missing and conf and len(missing) <= ala.MAP_GAP_MAX_BINS:
                    ext = ala.sweep_extent(v, w) if k == 'sweep' else None
                    left = missing - ala.map_known_bins(missing, grid, am[j][1:4],
                                                        min_dist=0.4 if k == 'sweep' else k,
                                                        obstacles=g.obstacles(0.0), extent=ext)
                if left:
                    blocked[k] += 1
        print(os.path.basename(bag.rstrip('/')), 'coverage msgs', len(cov), 'moving scans', total,
              '| missing but AMCL not confident:', gated)
        for k in thresholds:
            print('   %-22s blocked %5d  (%.0f%%)' % ('no map rule' if k is None else ('sweep-aware' if k == 'sweep' else 'fixed >= %.2f m' % k),
                                                    blocked[k], 100.0 * blocked[k] / max(1, total)))


if __name__ == '__main__':
    main()
