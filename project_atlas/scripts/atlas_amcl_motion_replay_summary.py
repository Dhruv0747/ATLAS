#!/usr/bin/env python3
"""Summarise offline AMCL motion replays against the recorded AMCL stream.

For the recorded /amcl_pose stream and each replay trajectory, report:
- fraction of updates while moving that the dashboard rule calls UNCERTAIN
  (XY std > 0.25 m or yaw std > 20 deg) and the median XY std while moving;
- after each stop of at least 3 s: seconds until the rule turns CONFIDENT;
- published pose steps larger than 0.5 m (all, and while stopped);
- held-out scan fit: fraction of LiDAR endpoints from beams AMCL does NOT
  use that land within 0.15 m of an occupied map cell, at each published
  pose (same metric as atlas_scan_fit_core, nearest-cell via a KD-tree).
  This is the independent accuracy proxy; there is no surveyed ground truth.

Read-only analysis of files; no ROS graph.
"""
import argparse
import glob
import json
import math
import statistics
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

UNCERTAIN_XY, UNCERTAIN_YAW = 0.25, 20.0
JUMP_M = 0.5
TOL_M = 0.15
AMCL_BEAMS = 60


def uncertain(p):
    return p['xy_std'] > UNCERTAIN_XY or p['yaw_std_deg'] > UNCERTAIN_YAW


class Fitter:
    def __init__(self, bundle):
        g = bundle['map']
        cells = np.asarray(g['cells']).reshape(g['height'], g['width'])
        rows, cols = np.nonzero(cells == 100)
        res = g['resolution']
        pts = np.c_[g['origin'][0] + (cols + 0.5) * res, g['origin'][1] + (rows + 0.5) * res]
        self.tree = cKDTree(pts)
        self.laser = bundle['laser']
        self.scans = bundle['scans']
        self.cache = {}

    def endpoints(self, k):
        if k not in self.cache:
            s = self.scans[k]
            r = np.array([np.nan if v is None else v for v in s['ranges']], float)
            idx = np.arange(len(r))
            step = max(1, (len(r) - 1) // (AMCL_BEAMS - 1))
            ok = (idx % step != 0) & np.isfinite(r) & (r >= max(0.3, s['range_min'])) & (r <= min(8.0, s['range_max']))
            b = s['angle_min'] + idx[ok] * s['angle_increment']
            self.cache[k] = (r[ok], b)
        return self.cache[k]

    def fit(self, k, x, y, yaw):
        r, b = self.endpoints(k)
        if len(r) < 60:
            return None
        c, s = math.cos(yaw), math.sin(yaw)
        lx = x + c * self.laser[0] - s * self.laser[1]
        ly = y + s * self.laser[0] + c * self.laser[1]
        px, py = lx + r * np.cos(yaw + b), ly + r * np.sin(yaw + b)
        d, _ = self.tree.query(np.c_[px, py])
        return float(np.mean(d <= TOL_M))


def nearest_scan(times, t):
    i = int(np.searchsorted(times, t))
    if i == 0:
        return 0
    if i >= len(times):
        return len(times) - 1
    return i if abs(times[i] - t) < abs(times[i - 1] - t) else i - 1


def summarize(traj, scans, fitter, scan_times):
    moving_flags = [s['moving'] for s in scans]
    # stop segments from per-scan motion flags (>= 3 s)
    stops, start = [], None
    for k, m in enumerate(moving_flags):
        if not m and start is None:
            start = k
        if m and start is not None:
            if scan_times[k - 1] - scan_times[start] >= 3.0:
                stops.append((scan_times[start], scan_times[k - 1]))
            start = None
    if start is not None and scan_times[-1] - scan_times[start] >= 3.0:
        stops.append((scan_times[start], scan_times[-1]))
    moving = [p for p in traj if p['moving']]
    stopped = [p for p in traj if not p['moving']]
    conv = []
    for a, b in stops:
        inside = [p for p in traj if a <= p['time_s'] <= b]
        first = next((p for p in inside if not uncertain(p)), None)
        conv.append(None if first is None else round(first['time_s'] - a, 2))
    jumps = jumps_stopped = 0
    for p, q in zip(traj, traj[1:]):
        if math.hypot(q['x'] - p['x'], q['y'] - p['y']) > JUMP_M:
            jumps += 1
            jumps_stopped += 0 if q['moving'] else 1
    fits_moving = [f for f in (fitter.fit(p['scan_index'], p['x'], p['y'], p['yaw']) for p in moving) if f is not None]
    fits_all = [f for f in (fitter.fit(p['scan_index'], p['x'], p['y'], p['yaw']) for p in traj) if f is not None]
    return {
        'updates': len(traj), 'moving_updates': len(moving),
        'uncertain_fraction_moving': None if not moving else round(sum(map(uncertain, moving)) / len(moving), 3),
        'uncertain_fraction_stopped': None if not stopped else round(sum(map(uncertain, stopped)) / len(stopped), 3),
        'xy_std_median_moving': None if not moving else round(statistics.median(p['xy_std'] for p in moving), 3),
        'stops': len(stops), 'seconds_to_confident_after_stop': conv,
        'stops_never_confident': sum(c is None for c in conv),
        'jumps_over_0_5m': jumps, 'jumps_while_stopped': jumps_stopped,
        'heldout_fit_median_moving': None if not fits_moving else round(statistics.median(fits_moving), 3),
        'heldout_fit_ge_0_85_moving': None if not fits_moving else round(sum(f >= 0.85 for f in fits_moving) / len(fits_moving), 3),
        'heldout_fit_final': None if not fits_all else round(fits_all[-1], 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bundle')
    ap.add_argument('runs', nargs='+', help='replay outputs for this bundle')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    bundle = json.loads(Path(a.bundle).read_text())
    scans = bundle['scans']
    scan_times = np.array([s['time_s'] for s in scans])
    fitter = Fitter(bundle)
    recorded = []
    for p in bundle['recorded_amcl']:
        if p['time_s'] < scan_times[0]:
            continue
        k = nearest_scan(scan_times, p['time_s'])
        recorded.append({**p, 'scan_index': k, 'moving': scans[k]['moving']})
    result = {'source_bag': bundle['source_bag'], 'navigation_authorized': False,
              'recorded': summarize(recorded, scans, fitter, scan_times), 'replays': {}}
    groups = {}
    for path in sorted(a.runs):
        run = json.loads(Path(path).read_text())
        key = f"odom={run['odom']} forced={run['forced_period_s']} alpha={','.join(str(v) for v in run['alpha'])}"
        groups.setdefault(key, []).append(summarize(run['trajectory'], scans, fitter, scan_times) | {'seed': run['seed']})
    for key, runs in groups.items():
        agg = {'runs': len(runs)}
        for field in ('uncertain_fraction_moving', 'xy_std_median_moving', 'jumps_over_0_5m', 'jumps_while_stopped',
                      'stops_never_confident', 'heldout_fit_median_moving', 'heldout_fit_ge_0_85_moving', 'heldout_fit_final'):
            vals = [r[field] for r in runs if r[field] is not None]
            agg[field] = None if not vals else {'median': round(statistics.median(vals), 3),
                                                 'min': round(min(vals), 3), 'max': round(max(vals), 3)}
        conv = [c for r in runs for c in r['seconds_to_confident_after_stop'] if c is not None]
        agg['seconds_to_confident_after_stop_median'] = None if not conv else round(statistics.median(conv), 2)
        agg['per_seed'] = runs
        result['replays'][key] = agg
    Path(a.output).write_text(json.dumps(result, indent=1))
    brief = {'recorded': {k: v for k, v in result['recorded'].items() if k != 'seconds_to_confident_after_stop'}}
    for key, agg in result['replays'].items():
        brief[key] = {k: v for k, v in agg.items() if k != 'per_seed'}
    print(json.dumps(brief, indent=1))


if __name__ == '__main__':
    main()
