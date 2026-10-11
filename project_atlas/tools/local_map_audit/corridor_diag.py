import sys, json, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from PIL import Image
T = json.load(open(f'{W}/trajectories.json'))
old = core.load_map(f'{W}/atlas_latest.yaml')
def mapdict(raw, tag):
    p = f'{W}/tmp_{tag}.pgm'; Image.fromarray(raw[::-1]).save(p)
    open(f'{W}/tmp_{tag}.yaml', 'w').write(open(f'{W}/atlas_latest.yaml').read().replace('atlas_latest.pgm', f'tmp_{tag}.pgm'))
    return core.load_map(f'{W}/tmp_{tag}.yaml')
def run(m, d, idx, laser):
    meta = d['scan_meta']; rows = [list(r[~np.isnan(r)]) for r in d['scan_r'][idx]]
    allp, held = core.endpoints(float(meta[0]), float(meta[1]), core.median_ranges(rows), laser, POL)
    hyps = core.global_search(m, allp, held, POL); return core.decide(hyps, len(allp), None, POL), hyps, len(allp)
def cls(v, truth):
    if v.state != 'VERIFIED': return 'UNK'
    ok = math.hypot(v.pose[0] - truth[0], v.pose[1] - truth[1]) <= 0.3 and abs(math.degrees(math.atan2(math.sin(v.pose[2] - truth[2]), math.cos(v.pose[2] - truth[2])))) <= 10
    return 'OK' if ok else 'WRONG'
rows = []
for rec in ['hall_to_dhruv_20261009-20261009-122252', 'amcl_roundtrip_20261009_final', 'amcl_hall_outbound_20261009_retry2', 'amcl_hall_return_20261009_retry2']:
    loo = mapdict(np.load(f'{W}/loo_{rec[:20]}.npy'), rec[:10]); d = load(f'{rec}.npz'); laser = laser_tf(d); st = d['scan_t']
    for k, tr in T.items():
        if tr['name'] != rec: continue
        arr = np.array([(q['t'], *q['p']) for q in tr['keys']]); kt = arr[:, 0]
        for t in np.arange(kt[0] + 1, kt[-1] - 1, 2.0):
            idx = np.where((st >= t - 0.25) & (st <= t + 0.25))[0][:3]
            if len(idx) < 2: continue
            truth = interp_pose(arr, st[idx[1]])
            if not (1.0 <= truth[0] <= 5.0): continue
            vo, ho, n = run(old, d, idx, laser); vc, hc, _ = run(loo, d, idx, laser)
            fo = core.fit(old, core.endpoints(float(d['scan_meta'][0]), float(d['scan_meta'][1]), core.median_ranges([list(r[~np.isnan(r)]) for r in d['scan_r'][idx]]), laser, POL)[1], *truth, POL.tolerance_m)
            fc = core.fit(loo, core.endpoints(float(d['scan_meta'][0]), float(d['scan_meta'][1]), core.median_ranges([list(r[~np.isnan(r)]) for r in d['scan_r'][idx]]), laser, POL)[1], *truth, POL.tolerance_m)
            rows.append({'rec': rec[:12], 'key': k, 't': float(t), 'truth': [round(truth[0], 2), round(truth[1], 2), round(math.degrees(truth[2]))], 'n': n,
                         'old': [cls(vo, truth), vo.best_fit, vo.margin, round(fo, 3), vo.reason[:60]], 'cand': [cls(vc, truth), vc.best_fit, vc.margin, round(fc, 3), vc.reason[:60]],
                         'old_top': [[round(h['x'], 2), round(h['y'], 2), round(math.degrees(h['yaw'])), h['fit_heldout']] for h in ho[:2]],
                         'cand_top': [[round(h['x'], 2), round(h['y'], 2), round(math.degrees(h['yaw'])), h['fit_heldout']] for h in hc[:2]]})
json.dump(rows, open(f'{W}/corridor_diag.json', 'w'), indent=1)
from collections import Counter
print('corridor windows', len(rows), 'old', Counter(r['old'][0] for r in rows), 'cand', Counter(r['cand'][0] for r in rows))
print('fit at TRUE pose: old mean %.3f  cand mean %.3f' % (np.mean([r['old'][3] for r in rows]), np.mean([r['cand'][3] for r in rows])))
for r in rows:
    if r['old'][0] != r['cand'][0]:
        print(f"{r['key'][:22]:22s} t={r['t']-0:.0f} truth={r['truth']} n={r['n']}\n   old : {r['old']} top {r['old_top']}\n   cand: {r['cand']} top {r['cand_top']}")
