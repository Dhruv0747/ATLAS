#!/usr/bin/env python3
"""Offline projection regression and scan-density summary; no ROS required."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from atlas_lidar_view import project


def summarize(document):
    rows = [r for r in document['samples'] if 'minima' in r]
    replayed = 0
    max_error = 0.0
    for row in rows:
        if 'filtered_scan' not in row:
            continue
        scan = NS(**row['filtered_scan'])
        scan.ranges = [float(v) for v in scan.ranges]
        t = row['transform']
        tf = NS(translation=NS(**dict(zip('xyz',t['translation']))),
                rotation=NS(**dict(zip('xyzw',t['rotation']))))
        result = project(scan, tf)
        assert result['points'] == row['points'], 'point projection regression'
        for key, old in row['closest'].items():
            new = result['closest'][key]
            assert (old is None) == (new is None), 'missing-return regression'
            if old is None:
                continue
            max_error = max(max_error, abs(new-old))
            assert math.isclose(new,old,abs_tol=1e-12,rel_tol=1e-12), 'nearest distance regression'
            for field, value in row['minima'][key].items():
                assert math.isclose(result['minima'][key][field],value,abs_tol=1e-12,rel_tol=1e-12), 'provenance regression'
        replayed += 1
    out = dict(projected=len(rows), replayed=replayed,
               max_replay_distance_error_m=max_error,
               tf_errors=sum('error' in r for r in document['samples']),
               raw_pairs=sum(r.get('raw_pair_found', False) for r in rows),
               valid_count_range=[min(r['valid'] for r in rows),max(r['valid'] for r in rows)] if rows else None,
               changed_finite_ranges=sum(r.get('changed_finite_ranges',0) for r in rows),
               raw_minimum_mismatches=sum(not v for r in rows for v in r.get('minima_raw_matches',{}).values()),
               age_s_range=[min(r['stamp_age_s'] for r in rows),max(r['stamp_age_s'] for r in rows)] if rows else None,
               directions={})
    for direction in ('front','left','rear','right'):
        values = [r['minima'][direction] for r in rows if r['minima'][direction]]
        # Sampled temporal evidence only: no identity association or rejection.
        out['directions'][direction] = dict(observed_samples=len(values),
            distance_range_m=[min(v['distance_m'] for v in values),max(v['distance_m'] for v in values)] if values else None,
            under_075m_samples=sum(v['distance_m'] < .75 for v in values),
            median_bearing_deg=math.degrees(statistics.median(v['bearing_rad'] for v in values)) if values else None)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('recording', type=Path)
    args = ap.parse_args()
    print(json.dumps(summarize(json.loads(args.recording.read_text())), indent=2))
