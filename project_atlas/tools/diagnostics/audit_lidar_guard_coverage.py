#!/usr/bin/env python3
"""Offline provenance audit of guard vetoes; never grants motion permission.

Consumes the existing lidar_provenance_probe format. Infinity is UNKNOWN,
not evidence that a beam reached range_max. No interpolation or scan edits.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_lidar_availability import LidarAvailability


def valid(value, scan):
    return math.isfinite(value) and scan['range_min'] <= value <= scan['range_max']


def classify(raw, filtered, scan):
    if valid(filtered, scan):
        return 'finite_observation'
    if valid(raw, scan):
        return 'finite_raw_removed_or_changed'
    if math.isnan(raw):
        return 'raw_nan_unknown'
    if math.isinf(raw):
        return 'raw_positive_inf_unknown' if raw > 0 else 'raw_negative_inf_invalid'
    return 'raw_below_minimum' if raw < scan['range_min'] else 'raw_above_maximum'


def audit(document):
    summaries = []
    causes = Counter()
    skipped = Counter()
    for row in document['samples']:
        if not row.get('raw_pair_found') or not row.get('raw_same_geometry'):
            skipped['unmatched_raw_geometry'] += 1
            continue
        raw, filtered = row.get('raw_scan'), row.get('filtered_scan')
        if raw is None or filtered is None:
            skipped['payload_missing'] += 1
            continue
        fields = ('angle_min', 'angle_increment', 'range_min', 'range_max')
        if any(raw[k] != filtered[k] for k in fields) or len(raw['ranges']) != len(filtered['ranges']):
            skipped['payload_geometry_mismatch'] += 1
            continue
        bins = {i: Counter() for i in range(72)}
        for i, (a, b) in enumerate(zip(raw['ranges'], filtered['ranges'])):
            category = classify(float(a), float(b), filtered)
            causes[category] += 1
            bearing = (math.degrees(filtered['angle_min'] + i * filtered['angle_increment']) + 180) % 360
            bins[int(bearing // 5) % 72][category] += 1
        stamp = float(row['stamp_s'])
        sec = int(stamp)
        scan = NS(**filtered)
        scan.ranges = [float(x) for x in filtered['ranges']]
        scan.header = NS(frame_id=row['frame'], stamp=NS(sec=sec, nanosec=int((stamp-sec)*1e9)))
        guard = LidarAvailability()
        guard.update(scan, 1.)
        # Freshness is synthetic here: ONLY the saved geometry is replayed.
        vetoes = {name: guard.reason(v, w, stamp + .2, 1.2)
                  for name, v, w in [('forward', .1, 0.), ('reverse', -.1, 0.),
                                     ('left', .1, .1), ('right', .1, -.1)]}
        summaries.append(dict(stamp=stamp, observed_bins=len(guard.bins), veto=vetoes,
                              missing_bins={str(i): dict(c) for i, c in bins.items()
                                            if not c['finite_observation']}))
    return dict(samples=len(summaries), skipped=dict(skipped), ray_classifications=dict(causes),
                geometry_only=True, movement_authorized=False,
                pass_counts={name: sum(r['veto'][name] is None for r in summaries)
                             for name in ('forward', 'reverse', 'left', 'right')},
                rows=summaries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.recording.read_text())), indent=2))
