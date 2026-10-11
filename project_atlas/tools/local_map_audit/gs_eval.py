import sys, json; sys.path.insert(0, '.')
from common import *
from PIL import Image
from anchors import parked_windows
A = json.load(open(f'{W}/anchors.json')); T = json.load(open(f'{W}/trajectories.json'))
def mapdict(raw, tag):
    p = f'{W}/tmp_{tag}.pgm'; Image.fromarray(raw[::-1]).save(p)
    open(f'{W}/tmp_{tag}.yaml', 'w').write(open(f'{W}/atlas_latest.yaml').read().replace('atlas_latest.pgm', f'tmp_{tag}.pgm'))
    return core.load_map(f'{W}/tmp_{tag}.yaml')
old = core.load_map(f'{W}/atlas_latest.yaml'); full = core.load_map(f'{W}/candidate/atlas_candidate_local_dhruv_hall_20261010.yaml')
def run(m, d, idx, laser):
    meta = d['scan_meta']; rows = [list(r[~np.isnan(r)]) for r in d['scan_r'][idx]]
    allp, held = core.endpoints(float(meta[0]), float(meta[1]), core.median_ranges(rows), laser, POL)
    hyps = core.global_search(m, allp, held, POL); return core.decide(hyps, len(allp), None, POL), hyps
def cls(v, truth):
    if v.state != 'VERIFIED': return 'UNKNOWN'
    ok = math.hypot(v.pose[0] - truth[0], v.pose[1] - truth[1]) <= 0.3 and abs(math.degrees(math.atan2(math.sin(v.pose[2] - truth[2]), math.cos(v.pose[2] - truth[2])))) <= 10
    return 'VERIFIED-correct' if ok else 'VERIFIED-WRONG'
# 1) parked windows + live on full candidate
print('PARKED (13 windows + live): old vs candidate  fit / margin / 2nd-best place fit')
recs = list(A)
L = load('live.npz'); lp = tuple(np.load(f'{W}/live_pose.npy'))
items = [(r, w) for r in recs for w in A[r]] + [('live', None)]
agg = {'old': [], 'cand': []}
for r, w in items:
    if r == 'live':
        d = {'scan_r': L['scan_r'], 'scan_meta': L['scan_meta']}; idx = np.arange(20); laser = tuple(L['laser']); truth = lp
    else:
        d = load(f'{r}.npz'); st = d['scan_t']; idx = np.where((st >= w['t0'] + .5) & (st <= w['t1'] - .2))[0][:20]; laser = laser_tf(d); p = w['pose']; truth = (p[0], p[1], math.radians(p[2]))
    out = []
    for tag, m in (('old', old), ('cand', full)):
        v, h = run(m, d, idx, laser); c = cls(v, truth); second = h[1]['fit_heldout'] if len(h) > 1 else None
        agg[tag].append((c, v.best_fit, v.margin, second)); out.append(f'{tag}: {c:16s} fit={v.best_fit} margin={v.margin} 2nd={second}')
    print(f'  {r[:22]:22s} | ' + ' | '.join(out))
for tag in agg:
    a = agg[tag]; print(f'  {tag}: correct {sum(x[0]=="VERIFIED-correct" for x in a)}/{len(a)}, wrong {sum(x[0]=="VERIFIED-WRONG" for x in a)}, mean margin {np.mean([x[2] for x in a if x[2] is not None]):.3f}, mean 2nd-best fit {np.mean([x[3] for x in a if x[3] is not None]):.3f}')
# 2) moving windows along traversals, leave-one-out candidate
print('MOVING-ROUTE windows (3-scan median every ~2 s along each Oct 9 traversal; LOO candidate)')
res = {'old': [], 'cand': []}
for rec in ['hall_to_dhruv_20261009-20261009-122252', 'amcl_roundtrip_20261009_final', 'amcl_hall_outbound_20261009_retry2', 'amcl_hall_return_20261009_retry2']:
    loo = mapdict(np.load(f'{W}/loo_{rec[:20]}.npy'), rec[:10]); d = load(f'{rec}.npz'); laser = laser_tf(d); st = d['scan_t']
    for k, tr in T.items():
        if tr['name'] != rec: continue
        keys = tr['keys']; kt = np.array([q['t'] for q in keys]); arr = np.array([(q['t'], *q['p']) for q in keys])
        for t in np.arange(kt[0] + 1, kt[-1] - 1, 2.0):
            idx = np.where((st >= t - 0.25) & (st <= t + 0.25))[0][:3]
            if len(idx) < 2: continue
            truth = interp_pose(arr, st[idx[1]])
            for tag, m in (('old', old), ('cand', loo)):
                v, h = run(m, d, idx, laser); res[tag].append((cls(v, truth), truth[0]))
for tag in res:
    r = res[tag]; n = len(r); c = sum(x[0] == 'VERIFIED-correct' for x in r); wr = sum(x[0] == 'VERIFIED-WRONG' for x in r)
    zone = [x for x in r if 1.0 <= x[1] <= 5.0]; zc = sum(x[0] == 'VERIFIED-correct' for x in zone)
    print(f'  {tag}: windows {n}  VERIFIED-correct {c} ({c/n*100:.0f}%)  VERIFIED-WRONG {wr}  UNKNOWN {n-c-wr}  | corridor x=1..5 m: correct {zc}/{len(zone)}')
