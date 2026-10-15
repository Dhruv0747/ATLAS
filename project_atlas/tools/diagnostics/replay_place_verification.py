#!/usr/bin/env python3
"""Offline: replay archived Stage 16 startup evidence through the startup verifier, whole map and
restricted to an operator-confirmed place (config/place_regions.json). Read-only.
  replay_place_verification.py <map.yaml> <localization_verdict_history.jsonl> <place>
"""
import hashlib, json, math, sys, time
sys.path.insert(0, __file__.rsplit('/tools/', 1)[0] + '/scripts')
import atlas_localization_verify_core as core

map_yaml, history, place = sys.argv[1:4]
regions = json.load(open(__file__.rsplit('/tools/', 1)[0] + '/config/place_regions.json'))
box = regions['places'][place]
same_map = hashlib.sha256(open(map_yaml, 'rb').read()).hexdigest() == regions['map_yaml_sha256']
m = core.load_map(map_yaml); pol = core.VerifyPolicy()
print(f'map matches region binding: {same_map}; thresholds fit>={pol.min_fit} margin>={pol.min_margin}')
fmt = lambda v: (v.state, None if v.pose is None else (round(v.pose[0], 3), round(v.pose[1], 3), round(math.degrees(v.pose[2]), 1)),
                 v.best_fit, v.margin)
for line in open(history):
    r = json.loads(line)
    ev = next((a.get('evidence') for a in (r.get('attempts') or []) if 'median_ranges_mm' in (a.get('evidence') or {})), None)
    if not ev:
        continue
    rng = [None if v is None else v / 1000 for v in ev['median_ranges_mm']]
    allp, held = core.endpoints(ev['angle_min'], ev['angle_increment'], rng, tuple(ev['laser_in_base']), pol)
    g = core.decide(core.global_search(m, allp, held, pol), len(allp), None, pol)
    p = core.decide(core.global_search(m, allp, held, pol, None, box), len(allp), None, pol)
    t = time.strftime('%m-%d %H:%M', time.gmtime(r['written_unix'] + 19800))
    print(f"{t} IST recorded={r['state']:9s} replay={g.state:9s} {'OK ' if g.state == r['state'] else 'MISMATCH'} | in '{place}': {fmt(p)}")
