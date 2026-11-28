"""Read-only: compare active vs candidate map on fresh parked scans at one location."""
import sys, json, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
MAPS = {'active': f'{W}/atlas_latest.yaml', 'candidate': f'{W}/candidate/atlas_candidate_local_dhruv_hall_20261010.yaml'}
def through_wall(m, pose, laser, ranges, amin, inc):
    """Beams whose ray crosses a mapped wall >=0.15 m before the measured return (map wall where LiDAR sees through)."""
    lx, ly, lt = compose(pose, laser); r = np.asarray(ranges, float); a = lt + amin + inc * np.arange(len(r))
    ok = np.isfinite(r) & (r > 0.12) & (r < 8); n = 0; tot = int(ok.sum())
    for ang, rr in zip(a[ok], r[ok]):
        s = np.arange(0.10, rr - 0.15, 0.025)
        if len(s) == 0: continue
        x = lx + s * math.cos(ang); y = ly + s * math.sin(ang)
        ix = np.floor((x - m['origin'][0]) / m['res']).astype(int); iy = np.floor((y - m['origin'][1]) / m['res']).astype(int)
        v = (ix >= 0) & (ix < m['w']) & (iy >= 0) & (iy < m['h'])
        if m['occupied'][iy[v], ix[v]].any(): n += 1
    return n, tot
def residuals(m, pose, laser, ranges, amin, inc):
    pts = to_world(scan_points(ranges, amin, inc, laser), pose)
    ix = np.floor((pts[:, 0] - m['origin'][0]) / m['res']).astype(int); iy = np.floor((pts[:, 1] - m['origin'][1]) / m['res']).astype(int)
    v = (ix >= 0) & (ix < m['w']) & (iy >= 0) & (iy < m['h']); d = np.full(len(pts), 9.0); d[v] = m['dist'][iy[v], ix[v]]
    return d
def run(npz, label, ref_pose=None):
    L = load(npz); laser = tuple(L['laser']); amin, inc = float(L['scan_meta'][0]), float(L['scan_meta'][1]); R = L['scan_r']
    out = {'location': label, 'scans': int(len(R)), 'maps': {}}
    for name, path in MAPS.items():
        m = core.load_map(path); wins = []
        for w in range(6):
            rows = [list(r[~np.isnan(r)]) for r in R[w * (len(R) // 6):(w + 1) * (len(R) // 6)][:20]]
            med = core.median_ranges(rows); allp, held = core.endpoints(amin, inc, med, laser, POL)
            hyps = core.global_search(m, allp, held, POL); v = core.decide(hyps, len(allp), None, POL)
            wins.append((v, hyps, med))
        v0, h0, med0 = wins[0]
        pose = ref_pose or (v0.pose if v0.pose else (h0[0]['x'], h0[0]['y'], h0[0]['yaw']))
        d = residuals(m, pose, laser, med0, amin, inc); tw, tot = through_wall(m, pose, laser, med0, amin, inc)
        out['maps'][name] = {
            'verdicts': [w[0].state for w in wins], 'fit': [w[0].best_fit for w in wins], 'margin': [w[0].margin for w in wins],
            'pose': None if v0.pose is None else [round(v0.pose[0], 3), round(v0.pose[1], 3), round(math.degrees(v0.pose[2]), 1)],
            'competitors': [[round(h['x'], 2), round(h['y'], 2), round(math.degrees(h['yaw'])), h['fit_heldout']] for h in h0[:4]],
            'wall_residual_m': {'median': round(float(np.median(d)), 3), 'within_5cm': round(float(np.mean(d <= .05)), 3), 'within_10cm': round(float(np.mean(d <= .10)), 3), 'beyond_15cm': round(float(np.mean(d > .15)), 3)},
            'rays_through_mapped_wall': f'{tw}/{tot}'}
    return out
if __name__ == '__main__':
    r = run(sys.argv[1], sys.argv[2]); print(json.dumps(r, indent=1)); json.dump(r, open(f'{W}/validate_{sys.argv[2]}.json', 'w'), indent=1)
