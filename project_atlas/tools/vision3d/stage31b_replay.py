#!/usr/bin/env python3
"""Replay captured Stage 31 CPU traces against the deployed guard and the >=1 s-window candidate.
Inputs are 1-second whole-machine samples, so the candidate's windows are those bins; the deployed guard's real
sub-second samples are taken from the session records where they exist. Threshold 75% (unchanged) for both."""
import json, sys
from pathlib import Path
EV = Path(sys.argv[1] if len(sys.argv) > 1 else 'evidence')
LIMIT = 75.0

def jp(name):
    raw = (EV / 'stage31_astra' / name).read_text(); return [s['busy'] for s in json.loads(raw[raw.find('{'):])['series']]

out = {}
rows = [json.loads(l) for l in (EV / 'stage31_live_b' / 's31b_trace.jsonl').read_text().splitlines()][1:]
b = [r['busy'] for r in rows]
guard = [r['guard'] for r in rows if r['guard'] and r['guard'].get('state') in ('CHECKING', 'ACTIVE', 'RESOURCE BLOCKED')]
out['second_depth_test_14_44'] = {
    'one_second_bins': len(b), 'max_1s': max(b), 'bins_over_75': [x for x in b if x > LIMIT],
    'deployed_guard_actual': 'BLOCKED at 76.0% on a 0.68 s window (3.38->4.06 s); recorder bin for that second 73.75%',
    'candidate_verdict': 'PASS' if max(b) <= LIMIT else 'BLOCK'}
for name, label in (('jp_main.json', 'production_domain_join_ros2_cli'), ('jp_iso.json', 'private_domain77_join_ros2_cli'), ('jp_none.json', 'parked_no_join')):
    s = jp(name)
    out[label] = {'max_1s': max(s), 'bins_over_75': [x for x in s if x > LIMIT], 'candidate_verdict': 'BLOCK' if max(s) > LIMIT else 'PASS'}
t1 = json.loads((EV / 'stage31_live' / 'depth_test.json').read_text())
out['first_depth_test_14_32'] = {'deployed_guard_samples_seen_by_page': [r['cpu'] for r in t1['timeline']],
    'note': 'no per-second recorder survived; the final 77.8% sample window length is unknown, so this session cannot be replayed'}
# What a single window can absorb: a burst of d seconds at 100% on a baseline b stays under 75% when b + d*(100-b) <= 75
for base in (62.6, 65.0, 69.8):
    out.setdefault('max_full_machine_burst_absorbed_s', {})['baseline_%.1f' % base] = {
        'deployed_0.5s_window': round(0.5 * (LIMIT - base) / (100 - base), 3), 'candidate_1.0s_window': round(1.0 * (LIMIT - base) / (100 - base), 3)}
print(json.dumps(out, indent=1))
