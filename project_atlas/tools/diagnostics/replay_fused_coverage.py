#!/usr/bin/env python3
"""Offline (read-only) replay: LiDAR-only availability vs LiDAR + Astra floor-coverage fusion. 2026-11-15.

Inputs: a colour-remap session folder with base/ (/scan) and astra/ (/astra/depth/image_raw, camera_info) bags
recorded at the same time. Depth frames are turned into the coverage scan with the live ObstacleScanner and the
config/astra_obstacles.yaml mount; each /scan is paired with the nearest depth frame within 0.2 s.
Usage: replay_fused_coverage.py <session_dir> [...]
"""
import bisect, math, os, sys
from types import SimpleNamespace as NS
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts'))
import numpy as np
import rosbag2_py, yaml
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import CameraInfo, Image, LaserScan
import atlas_astra_obstacle_core as core
import atlas_lidar_availability as la

CFG = yaml.safe_load(open(os.path.join(HERE, '..', '..', 'config', 'astra_obstacles.yaml')))
CMDS = [(0.15, 0.0), (0.15, 0.1), (0.15, -0.1), (0.15, 0.2), (0.15, -0.2), (-0.15, 0.0)]


def reader(uri, topics):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=uri, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    r.set_filter(rosbag2_py.StorageFilter(topics=topics))
    return r


def coverage_frames(astra, every=2):
    scanner, out, n = None, [], 0
    r = reader(astra, ['/astra/depth/camera_info', '/astra/depth/image_raw'])
    while r.has_next():
        topic, raw, t = r.read_next()
        if topic.endswith('camera_info'):
            if scanner is None:
                m = deserialize_message(raw, CameraInfo)
                cal = core.validate_camera_info(m.width, m.height, m.header.frame_id, list(m.k), list(m.d),
                                                m.distortion_model)
                scanner = core.ObstacleScanner(CFG, cal)
            continue
        n += 1
        if scanner is None or n % every:
            continue
        m = deserialize_message(raw, Image)
        depth = np.frombuffer(m.data, dtype=np.uint16 if m.encoding == '16UC1' else np.float32).reshape(m.height, m.width)
        if depth.shape != (120, 160):
            continue
        ranges, stats = scanner.scan(depth, m.encoding)
        if stats['valid_fraction'] < scanner.s['min_valid_fraction']:
            continue
        cov = scanner.last_coverage
        out.append((t, NS(header=NS(frame_id='base_link'), angle_min=scanner.amin, angle_increment=scanner.inc,
                          ranges=[float(x) for x in cov],
                          intensities=[1.0 if math.isfinite(x) else 0.0 for x in ranges])))
    return out


def main(sessions):
    for sdir in sessions:
        cov = coverage_frames(os.path.join(sdir, 'astra'))
        ct = [c[0] for c in cov]
        r = reader(os.path.join(sdir, 'base'), ['/scan'])
        stats = {c: [0, 0] for c in CMDS}; paired = 0; total = 0; bins_rescued = 0; gaps = 0
        k = 0
        while r.has_next():
            _, raw, t = r.read_next(); total += 1
            if total % 2:
                continue
            i = bisect.bisect_left(ct, t)
            best = min((j for j in (i - 1, i) if 0 <= j < len(ct)), key=lambda j: abs(ct[j] - t), default=None)
            if best is None or abs(ct[best] - t) > 2e8:
                continue
            paired += 1
            s = deserialize_message(raw, LaserScan)
            g = la.LidarAvailability(); g.update(s, 10.0)
            st = s.header.stamp.sec + s.header.stamp.nanosec * 1e-9
            base_missing = la.travel_cone(0.15) - g.bins
            gaps += len(base_missing)
            g.update_coverage(cov[best][1], 10.0)
            bins_rescued += len(base_missing & g.cover_bins)
            for c in CMDS:
                lid = la.LidarAvailability(); lid.update(s, 10.0)
                stats[c][0] += lid.reason(c[0], c[1], st, 10.1) is not None
                stats[c][1] += g.reason(c[0], c[1], st, 10.1) is not None
        print(f'session {os.path.basename(sdir)}: {len(cov)} coverage frames, {paired} paired scans')
        print(f'  forward-cone LiDAR gap bins: {gaps}, filled by Astra coverage: {bins_rescued} '
              f'({100 * bins_rescued / max(gaps, 1):.0f} %)')
        for c, (a, b) in stats.items():
            print(f'  v {c[0]:+.2f} w {c[1]:+.2f}: veto LiDAR-only {100 * a / max(paired, 1):.0f} % -> fused '
                  f'{100 * b / max(paired, 1):.0f} %')


if __name__ == '__main__':
    main(sys.argv[1:])
