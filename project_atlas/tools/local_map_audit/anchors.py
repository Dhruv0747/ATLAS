import sys, json; sys.path.insert(0, '.')
from common import *
m = core.load_map(f'{W}/atlas_latest.yaml')
RECS = ['M', 'hall_to_dhruv_20261009-20261009-122252', 'amcl_roundtrip_20261009_final', 'amcl_hall_outbound_20261009_retry2', 'amcl_hall_return_20261009_retry2']
def parked_windows(d, min_s=3.0):
    o = d['odom']; mv = (np.abs(o[:, 4]) > 0.01) | (np.abs(o[:, 5]) > 0.02)
    out, start = [], None
    for i in range(len(o)):
        if not mv[i] and start is None: start = o[i, 0]
        if (mv[i] or i == len(o) - 1) and start is not None:
            if o[i, 0] - start >= min_s: out.append((start, o[i, 0]))
            start = None
    return out
def verify(d, t0, t1, laser):
    st = d['scan_t']; idx = np.where((st >= t0 + 0.5) & (st <= t1 - 0.2))[0][:20]
    if len(idx) < 5: return None
    meta = d['scan_meta']; rows = [list(r[~np.isnan(r)]) for r in d['scan_r'][idx]]
    allp, held = core.endpoints(float(meta[0]), float(meta[1]), core.median_ranges(rows), laser, POL)
    v = core.decide(core.global_search(m, allp, held, POL), len(allp), None, POL)
    return v
res = {}
for name in RECS:
    d = load(f'{name}.npz'); laser = laser_tf(d); w = parked_windows(d)
    t0 = d['scan_t'][0]; print(f'== {name} laser={laser} dur={d["scan_t"][-1]-t0:.0f}s parked windows={len(w)}')
    res[name] = []
    for a, b in w:
        v = verify(d, a, b, laser)
        if v is None: continue
        p = None if v.pose is None else [round(v.pose[0], 3), round(v.pose[1], 3), round(math.degrees(v.pose[2]), 1)]
        print(f'  {a-t0:6.1f}-{b-t0:6.1f}s {v.state:8s} {p} fit={v.best_fit} margin={v.margin}')
        res[name].append({'t0': a, 't1': b, 'state': v.state, 'pose': p, 'fit': v.best_fit, 'margin': v.margin})
json.dump(res, open(f'{W}/anchors.json', 'w'), indent=1)
