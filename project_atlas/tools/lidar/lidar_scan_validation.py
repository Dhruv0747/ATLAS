#!/usr/bin/env python3
"""Offline LiDAR scan validation from a recorded bag (read-only). 2026-11-13.

For /scan_raw (driver output) and /scan (self-filtered, thinned to ~360 beams in Boost mode) reports:
  * timing: header-stamp period (mean / p95 / max gap), bag-receipt minus header stamp (latency),
    time_increment * beams vs scan_time (the per-point timing a deskew/SLAM would rely on)
  * geometry: beams per scan, angle_increment, valid-return fraction
  * accuracy proxy: per-beam range noise (std over consecutive scans) while the rover is stationary
    (|wheel vx| < 0.003 m/s and |wz| < 0.01 rad/s), median over beams with returns at 0.3-6 m.
Usage: python3 lidar_scan_validation.py BAG [--max-seconds 900] [--json out.json]
"""
import argparse, json, math, sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bag'); ap.add_argument('--max-seconds', type=float, default=900.0); ap.add_argument('--json')
    a = ap.parse_args()
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=a.bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    types = {t.name: t.type for t in r.get_all_topics_and_types()}
    topics = [t for t in ('/scan_raw', '/scan', '/yahboom/odom') if t in types]
    r.set_filter(rosbag2_py.StorageFilter(topics=topics))
    msgt = {t: get_message(types[t]) for t in topics}
    data = {t: {'stamp': [], 'recv': [], 'n': [], 'valid': [], 'inc': [], 'tinc': [], 'scan_time': [], 'ranges': []}
            for t in ('/scan_raw', '/scan') if t in topics}
    still = []           # (recv, still?)
    t0 = None
    while r.has_next():
        name, raw, t = r.read_next()
        t0 = t0 or t
        if (t - t0) * 1e-9 > a.max_seconds:
            break
        m = deserialize_message(raw, msgt[name])
        if name == '/yahboom/odom':
            still.append((t * 1e-9, abs(m.twist.twist.linear.x) < 0.003 and abs(m.twist.twist.angular.z) < 0.01))
            continue
        d = data[name]
        rr = np.asarray(m.ranges, dtype=np.float32)
        ok = np.isfinite(rr) & (rr > m.range_min) & (rr < m.range_max)
        d['stamp'].append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9); d['recv'].append(t * 1e-9)
        d['n'].append(len(rr)); d['valid'].append(ok.mean() if len(rr) else 0.0)
        d['inc'].append(m.angle_increment); d['tinc'].append(m.time_increment); d['scan_time'].append(m.scan_time)
        d['ranges'].append(rr)
    st = np.array(still) if still else np.zeros((0, 2))
    out = {'bag': a.bag, 'seconds_read': a.max_seconds}
    for name, d in data.items():
        if len(d['stamp']) < 10:
            continue
        s = np.array(d['stamp']); rc = np.array(d['recv']); dt = np.diff(s)
        n = np.array(d['n']); tinc = np.array(d['tinc']); sct = np.array(d['scan_time'])
        res = {
            'scans': len(s), 'rate_hz': round(1 / np.median(dt), 2), 'period_mean_s': round(dt.mean(), 4),
            'period_p95_s': round(np.percentile(dt, 95), 4), 'max_gap_s': round(dt.max(), 3),
            'gaps_over_0.3s': int((dt > 0.3).sum()), 'nonmonotonic_stamps': int((dt <= 0).sum()),
            'latency_median_s': round(float(np.median(rc - s)), 3), 'latency_p95_s': round(float(np.percentile(rc - s, 95)), 3),
            'beams_median': int(np.median(n)), 'beams_min': int(n.min()), 'beams_max': int(n.max()),
            'angle_increment_deg': round(math.degrees(float(np.median(d['inc']))), 4),
            'valid_fraction_mean': round(float(np.mean(d['valid'])), 4),
            'time_increment_x_beams_over_scan_time': round(float(np.median(tinc * n / np.where(sct > 0, sct, np.nan))), 3)
            if np.any(sct > 0) else None,
            'scan_time_median_s': round(float(np.median(sct)), 4),
        }
        # stationary range noise: consecutive scans with identical beam count, both inside a still window
        if len(st):
            idx = np.searchsorted(st[:, 0], rc)
            is_still = np.array([bool(st[min(i, len(st) - 1), 1]) for i in idx])
            diffs = []
            for k in range(1, len(s)):
                if is_still[k] and is_still[k - 1] and n[k] == n[k - 1]:
                    a1, a2 = d['ranges'][k - 1], d['ranges'][k]
                    ok = np.isfinite(a1) & np.isfinite(a2) & (a1 > 0.3) & (a1 < 6) & (a2 > 0.3) & (a2 < 6)
                    dd = (a2 - a1)[ok]
                    dd = dd[np.abs(dd) < 0.2]          # ignore edge flips between foreground/background
                    if len(dd) > 50:
                        diffs.append(np.median(np.abs(dd)))
            if diffs:
                # median |r2-r1| of a Gaussian = 0.954 sigma*sqrt(2) -> sigma ~ value / 0.954 / 1.414
                res['stationary_pairs'] = len(diffs)
                res['range_noise_sigma_mm'] = round(float(np.median(diffs)) / 0.954 / math.sqrt(2) * 1000, 1)
        out[name] = res
    print(json.dumps(out, indent=1))
    if a.json:
        open(a.json, 'w').write(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
