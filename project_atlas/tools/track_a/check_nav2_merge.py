#!/usr/bin/env python3
"""Track A: merge the Astra LIVE snippet into a nav2_params.yaml IN MEMORY and prove LiDAR independence.

Usage: check_nav2_merge.py NAV2_PARAMS [--write OUT]   (--write only at gate G5, with owner approval)
Exit 0 = every check PASS. Never modifies the input file.
"""
import copy
import sys
from pathlib import Path

import yaml

SNIPPET = Path(__file__).resolve().parents[2] / 'config/nav2_astra_obstacles_LIVE_SNIPPET.yaml'


def merge(params, snippet):
    out = copy.deepcopy(params)
    lc = out['local_costmap']['local_costmap']['ros__parameters']
    sp = snippet['local_costmap']['local_costmap']['ros__parameters']
    lc['plugins'] = list(sp['plugins'])
    lc['astra_layer'] = copy.deepcopy(sp['astra_layer'])
    return out


def checks(before, after):
    res = []
    def ok(name, cond): res.append((name, bool(cond)))
    lb = before['local_costmap']['local_costmap']['ros__parameters']
    la = after['local_costmap']['local_costmap']['ros__parameters']
    ok('LiDAR obstacle_layer byte-identical after merge', lb.get('obstacle_layer') == la.get('obstacle_layer'))
    ok('LiDAR source still /scan', la['obstacle_layer']['scan']['topic'] == '/scan'
       and la['obstacle_layer']['observation_sources'] == lb['obstacle_layer']['observation_sources'])
    ok('Astra is a separate layer (not inside obstacle_layer)',
       'astra' not in str(la['obstacle_layer'].get('observation_sources', '')).split() and 'astra_layer' in la)
    ok('all previous plugins kept', all(p in la['plugins'] for p in lb['plugins']))
    ok('inflation_layer is last', la['plugins'][-1] == 'inflation_layer')
    ok('astra_layer before inflation', la['plugins'].index('astra_layer') < la['plugins'].index('inflation_layer'))
    a = la['astra_layer']['astra']
    ok('astra inf_is_valid false (no clearing from no-return rays)', a.get('inf_is_valid') is False)
    ok('astra topic /astra/obstacle_scan LaserScan',
       a.get('topic') == '/astra/obstacle_scan' and a.get('data_type') == 'LaserScan')
    ok('astra ranges inside local costmap reach', a['obstacle_max_range'] <= a['raytrace_max_range'] <= 3.0)
    ok('astra min range 0.35 matches node', a['obstacle_min_range'] == 0.35 and a['raytrace_min_range'] == 0.35)
    ok('astra layer frame base_link-compatible (robot_base_frame base_link)',
       la.get('robot_base_frame') == 'base_link')
    ok('global costmap unchanged', before['global_costmap'] == after['global_costmap'])
    ok('everything outside local_costmap unchanged',
       {k: v for k, v in before.items() if k != 'local_costmap'} == {k: v for k, v in after.items() if k != 'local_costmap'})
    return res


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    params = yaml.safe_load(Path(argv[1]).read_text())
    merged = merge(params, yaml.safe_load(SNIPPET.read_text()))
    res = checks(params, merged)
    for name, good in res:
        print(('PASS ' if good else 'FAIL ') + name)
    if '--write' in argv:
        out = Path(argv[argv.index('--write') + 1])
        if out.resolve() == Path(argv[1]).resolve():
            print('refusing to overwrite the input; write to a new file and swap after review'); return 2
        out.write_text(yaml.safe_dump(merged, sort_keys=False))
        print('merged params written to', out)
    return 0 if all(g for _, g in res) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
