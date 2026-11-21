#!/usr/bin/env python3
"""Reference-free comparison of parked-AMCL policies across several drives.

Read-only. For each parked window processed by atlas_amcl_diversity_experiment
(any reference arguments), score every policy without a ground-truth pose:

- held-out scan fit of each seed's final winner pose: the fraction of odd
  original-beam endpoints within 15 cm of a mapped wall, median over the
  recorded scans in the window's final 10 s (at least 0.9 s apart);
- AMCL jumps (>0.5 m winner steps), maximum jump and final-30 s pose span;
- outcome split: how many distinct final poses (0.5 m / 20 deg) the seeds
  reach, and the share of seeds in the largest group.

Then compare each policy with the recorded baseline in the same window. No ROS
node, publisher, service or actuator is created.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from atlas_amcl_diversity_summary import (check_invariants, endpoint_fit, last_span,
                                          load_scene, odd_beam_points, recovered)

HELD_OUT_S = 10.0
DEGRADE_MARGIN = 0.05


def held_out_points(scans, start_s, end_s):
    chosen, last = [], -math.inf
    for t, m in scans:
        if start_s <= t <= end_s and t - last >= .9:
            pts = odd_beam_points(m.angle_min, m.angle_increment, m.ranges, m.range_min, m.range_max)
            if len(pts) >= 30:
                chosen.append(pts)
                last = t
    return chosen


def outcome_groups(poses):
    """Greedy grouping of final poses within 0.5 m and 20 deg of a group seed."""
    groups = []
    for pose in poses:
        for group in groups:
            if recovered(pose, group[0]):
                group.append(pose)
                break
        else:
            groups.append([pose])
    return sorted((len(g) for g in groups), reverse=True)


def score_window(document, tree, laser, scans):
    end = document['window_offset_s'][1]
    held = held_out_points(scans, end - HELD_OUT_S, end)
    if not held:
        raise ValueError('no held-out scans in final window')

    def fit(pose):
        return float(np.median([endpoint_fit(p, np.array(pose), laser, tree)[0] for p in held]))

    by_mode = {}
    for row in document['results']:
        by_mode.setdefault(row['mode'], []).append(row)
    out = {'window_offset_s': document['window_offset_s'], 'held_out_scans': len(held),
           'initial_pose': document['results'][0]['initial']['pose'], 'policies': {}}
    for mode, rows in by_mode.items():
        rows = sorted(rows, key=lambda r: r['seed'])
        fits = [fit(r['final']['pose']) for r in rows]
        groups = outcome_groups([r['final']['pose'] for r in rows])
        out['policies'][mode] = {
            'runs': len(rows), 'seeds': [r['seed'] for r in rows], 'fits': fits,
            'fit_median': float(np.median(fits)), 'fit_min': float(min(fits)),
            'jumps_median': float(np.median([r['jumps_over_0_5m'] for r in rows])),
            'jumps_max': int(max(r['jumps_over_0_5m'] for r in rows)),
            'max_jump_m': float(max(r['max_step_m'] for r in rows)),
            'last_30s_span_m_max': float(max(last_span(r['trajectory']) for r in rows)),
            'outcome_groups': groups, 'largest_group_share': groups[0] / len(rows)}
    base = out['policies']['baseline']
    for mode, policy in out['policies'].items():
        if mode == 'baseline':
            continue
        paired = [(f, b) for s, f in zip(policy['seeds'], policy['fits'])
                  for t, b in zip(base['seeds'], base['fits']) if s == t]
        policy['vs_baseline'] = {
            'fit_median_change': policy['fit_median'] - base['fit_median'],
            'seeds_worse_by_margin': int(sum(f < b - DEGRADE_MARGIN for f, b in paired)),
            'seeds_better_by_margin': int(sum(f > b + DEGRADE_MARGIN for f, b in paired)),
            'paired_seeds': len(paired), 'margin': DEGRADE_MARGIN}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('pairs', nargs='+', help='bag_dir=results.json')
    args = parser.parse_args()
    summary = {'navigation_authorized': False, 'reference_free': True,
               'held_out_final_seconds': HELD_OUT_S, 'windows': {}}
    scenes = {}
    for pair in args.pairs:
        bag, path = pair.split('=', 1)
        document = json.loads(Path(path).read_text())
        check_invariants(document)
        if bag not in scenes:
            scenes[bag] = load_scene(bag)
        key = Path(bag).name + ':' + Path(path).stem
        summary['windows'][key] = score_window(document, *scenes[bag])
    Path(args.output).write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({'output': args.output, 'windows': len(summary['windows']),
                      'navigation_authorized': False}))


if __name__ == '__main__':
    main()
