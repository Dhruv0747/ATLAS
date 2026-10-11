import sys, json; sys.path.insert(0, '.')
from common import *
from scipy import ndimage
m = core.load_map(f'{W}/atlas_latest.yaml'); res, ox, oy, Wd, Hd = m['res'], m['origin'][0], m['origin'][1], m['w'], m['h']
def cells(x, y): return np.floor((y - oy) / res).astype(int), np.floor((x - ox) / res).astype(int)
def traversal_grids(d, keys, laser):
    hit = np.zeros((Hd, Wd), np.int32); thru = np.zeros((Hd, Wd), np.int32); meta = d['scan_meta']
    for k in keys:
        r = d['scan_r'][k['i']]; r = r[~np.isnan(r)]; pose = k['p']
        a = float(meta[0]) + float(meta[1]) * np.arange(len(r)); ok = np.isfinite(r) & (r > 0.12) & (r < 8)
        lx, ly, lt = compose(tuple(pose), laser)
        ang = lt + a[ok]; rr = r[ok]
        ex, ey = lx + rr * np.cos(ang), ly + rr * np.sin(ang)
        iy, ix = cells(ex, ey); v = (iy >= 0) & (iy < Hd) & (ix >= 0) & (ix < Wd); np.add.at(hit, (iy[v], ix[v]), 1)
        steps = np.arange(0.05, 8, res / 2)
        S = steps[None, :] < (rr[:, None] - 0.10)
        px = lx + steps[None, :] * np.cos(ang)[:, None]; py = ly + steps[None, :] * np.sin(ang)[:, None]
        iy, ix = cells(px[S], py[S]); v = (iy >= 0) & (iy < Hd) & (ix >= 0) & (ix < Wd)
        u = np.unique(iy[v] * Wd + ix[v]); np.add.at(thru.ravel(), u, 1)
    return hit, thru
if __name__ == '__main__':
    T = json.load(open(f'{W}/trajectories.json')); occ_votes = np.zeros((Hd, Wd), int); free_votes = np.zeros((Hd, Wd), int)
    per = {}
    for key, tr in T.items():
        d = load(f"{tr['name']}.npz"); hit, thru = traversal_grids(d, tr['keys'], laser_tf(d))
        o = (hit >= 2) & (hit >= 0.3 * thru); f = (thru >= 3) & (hit == 0)
        occ_votes += o; free_votes += f; per[key] = o
    # live parked scans (pose = LiDAR-verified)
    L = load('live.npz'); pose = tuple(np.load(f'{W}/live_pose.npy'))
    lk = [{'i': i, 'p': pose} for i in range(0, len(L['scan_r']), 6)]
    class Dd(dict): pass
    dl = {'scan_r': L['scan_r'], 'scan_meta': L['scan_meta']}; hit, thru = traversal_grids(dl, lk, tuple(L['laser']))
    np.savez_compressed(f'{W}/evidence.npz', occ_votes=occ_votes, free_votes=free_votes, live_hit=hit, live_thru=thru, n=len(T), **{f'per_{i}': v for i, v in enumerate(per.values())})
    near_occ = ndimage.binary_dilation(occ_votes >= 3, iterations=1)
    mo = m['occupied']; x0, x1, y0, y1 = -1.6, 7.6, -3.6, 1.8
    r0, r1 = int((y0 - oy) / res), int((y1 - oy) / res); c0, c1 = int((x0 - ox) / res), int((x1 - ox) / res)
    R = np.zeros_like(mo); R[r0:r1, c0:c1] = True
    seen = (occ_votes + free_votes) > 0
    confirmed = mo & R & near_occ
    contradicted = mo & R & (free_votes >= 3) & ~near_occ
    unobs = mo & R & ~seen
    missing = R & (occ_votes >= 3) & (m['dist'] > 0.10)
    print('traversals', len(T), '| map wall cells in region', int((mo & R).sum()))
    print('  confirmed by >=3 drives (within 5 cm):', int(confirmed.sum()))
    print('  contradicted (>=3 drives see through, none see wall):', int(contradicted.sum()))
    print('  not observed by drives:', int(unobs.sum()), '| other/weak:', int((mo & R).sum() - confirmed.sum() - contradicted.sum() - unobs.sum()))
    print('wall cells seen by >=3 drives but >10 cm from any map wall (missing/misplaced):', int(missing.sum()))
    np.savez_compressed(f'{W}/classes.npz', confirmed=confirmed, contradicted=contradicted, missing=missing, R=R)
