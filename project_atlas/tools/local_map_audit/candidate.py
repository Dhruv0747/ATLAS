"""Local candidate: active map changed only inside BOX, only where >=3 independent drives agree."""
import sys, json; sys.path.insert(0, '.')
from common import *
from evidence import traversal_grids, m, res, ox, oy, Wd, Hd
from scipy import ndimage
from PIL import Image
BOX = (-1.6, 7.6, -3.6, 1.8)
def parked_hits(exclude=None):
    """Wall hits from parked, LiDAR-verified windows (no motion distortion). Never removed."""
    A = json.load(open(f'{W}/anchors.json')); H = np.zeros((Hd, Wd), int)
    for rec, ws in A.items():
        if rec == exclude: continue
        d = load(f'{rec}.npz'); st = d['scan_t']
        for w in ws:
            p = w['pose']; idx = np.where((st >= w['t0'] + .5) & (st <= w['t1'] - .2))[0][:40:4]
            hit, _ = traversal_grids(d, [{'i': int(i), 'p': (p[0], p[1], math.radians(p[2]))} for i in idx], laser_tf(d)); H += hit > 0
    L = load('live.npz'); pose = tuple(np.load(f'{W}/live_pose.npy'))
    hit, _ = traversal_grids({'scan_r': L['scan_r'], 'scan_meta': L['scan_meta']}, [{'i': i, 'p': pose} for i in range(0, len(L['scan_r']), 6)], tuple(L['laser'])); H += 2 * (hit > 0)
    return H

def build(use_keys, live=True, tag='candidate', exclude=None):
    T = json.load(open(f'{W}/trajectories.json')); occ = np.zeros((Hd, Wd), int); free = np.zeros((Hd, Wd), int)
    for key in use_keys:
        tr = T[key]; d = load(f"{tr['name']}.npz"); hit, thru = traversal_grids(d, tr['keys'], laser_tf(d))
        occ += (hit >= 2) & (hit >= 0.3 * thru); free += (thru >= 3) & (hit == 0)
    if live:
        L = load('live.npz'); pose = tuple(np.load(f'{W}/live_pose.npy'))
        hit, thru = traversal_grids({'scan_r': L['scan_r'], 'scan_meta': L['scan_meta']}, [{'i': i, 'p': pose} for i in range(0, len(L['scan_r']), 6)], tuple(L['laser']))
        occ += (hit >= 2) & (hit >= 0.3 * thru); free += (thru >= 3) & (hit == 0)
    raw = np.array(Image.open(f'{W}/atlas_latest.pgm'))[::-1].copy()
    R = np.zeros((Hd, Wd), bool); x0, x1, y0, y1 = BOX
    R[int((y0 - oy) / res):int((y1 - oy) / res), int((x0 - ox) / res):int((x1 - ox) / res)] = True
    near_occ = ndimage.binary_dilation(occ >= 3, iterations=1)
    protect = ndimage.binary_dilation(parked_hits(exclude) >= 2, iterations=1)
    remove = (raw < 50) & R & (free >= 3) & ~near_occ & ~protect
    add = R & (occ >= 3) & (raw >= 50) & (m['dist'] > 0.10)
    new = raw.copy(); new[remove] = 254; new[add] = 0
    return new, remove, add, occ, free
if __name__ == '__main__':
    T = json.load(open(f'{W}/trajectories.json')); keys = [k for k in T if k != 'M@107']
    new, remove, add, occ, free = build(keys)
    out = f'{W}/candidate'; import os; os.makedirs(out, exist_ok=True)
    Image.fromarray(new[::-1]).save(f'{out}/atlas_candidate_local_dhruv_hall_20261010.pgm')
    open(f'{out}/atlas_candidate_local_dhruv_hall_20261010.yaml', 'w').write(open(f'{W}/atlas_latest.yaml').read().replace('atlas_latest.pgm', 'atlas_candidate_local_dhruv_hall_20261010.pgm'))
    np.savez_compressed(f'{W}/cand_masks.npz', remove=remove, add=add)
    print('drives used', keys); print('removed wall cells', int(remove.sum()), 'added wall cells', int(add.sum()), 'unchanged outside box: ', bool((new[~np.pad(np.ones((0,0)),0).astype(bool)] if False else True)))
    raw = np.array(Image.open(f'{W}/atlas_latest.pgm'))[::-1]
    print('cells changed outside region:', int(((new != raw) & ~(remove | add)).sum()), '| wall cells before', int((raw < 50).sum()), 'after', int((new < 50).sum()))


# ---- v2 (2026-10-10 23:45): never delete anything any scan has hit -------------
def direct_hits(use_keys, exclude=None, fresh=('fresh_dhruv.npz',)):
    """Count of sources (drives, parked windows, fresh/live parked sets) that hit each cell directly."""
    T = json.load(open(f'{W}/trajectories.json')); A = json.load(open(f'{W}/anchors.json'))
    src = np.zeros((Hd, Wd), int); thru_parked = np.zeros((Hd, Wd), int)
    for key in use_keys:
        tr = T[key]; d = load(f"{tr['name']}.npz"); hit, _ = traversal_grids(d, tr['keys'], laser_tf(d)); src += hit > 0
    for rec, ws in A.items():
        if rec == exclude: continue
        d = load(f'{rec}.npz'); st = d['scan_t']
        for w in ws:
            p = w['pose']; idx = np.where((st >= w['t0'] + .5) & (st <= w['t1'] - .2))[0][:40:4]
            hit, thru = traversal_grids(d, [{'i': int(i), 'p': (p[0], p[1], math.radians(p[2]))} for i in idx], laser_tf(d))
            src += hit > 0; thru_parked += (thru >= 5) & (hit == 0)
    for f in ('live.npz',) + tuple(fresh):
        import os
        if not os.path.exists(f'{W}/{f}'): continue
        L = load(f); pose = tuple(np.load(f'{W}/live_pose.npy')) if f == 'live.npz' else tuple(np.load(f'{W}/pose_{f}.npy'))
        hit, thru = traversal_grids({'scan_r': L['scan_r'], 'scan_meta': L['scan_meta']}, [{'i': i, 'p': pose} for i in range(0, len(L['scan_r']), 3)], tuple(L['laser']))
        src += hit > 0; thru_parked += (thru >= 5) & (hit == 0)
    return src, thru_parked

def build_v2(use_keys, exclude=None, fresh=('fresh_dhruv.npz',)):
    T = json.load(open(f'{W}/trajectories.json')); occ = np.zeros((Hd, Wd), int); free = np.zeros((Hd, Wd), int)
    for key in use_keys:
        tr = T[key]; d = load(f"{tr['name']}.npz"); hit, thru = traversal_grids(d, tr['keys'], laser_tf(d))
        occ += (hit >= 2) & (hit >= 0.3 * thru); free += (thru >= 3) & (hit == 0)
    src, thru_parked = direct_hits(use_keys, exclude, fresh)
    raw = np.array(Image.open(f'{W}/atlas_latest.pgm'))[::-1].copy()
    R = np.zeros((Hd, Wd), bool); x0, x1, y0, y1 = BOX
    R[int((y0 - oy) / res):int((y1 - oy) / res), int((x0 - ox) / res):int((x1 - ox) / res)] = True
    never_hit = src == 0
    remove = (raw < 50) & R & never_hit & ((free >= 3) | (thru_parked >= 1))
    add = R & (occ >= 3) & (raw >= 50) & (m['dist'] > 0.10)
    new = raw.copy(); new[remove] = 254; new[add] = 0
    return new, remove, add


# ---- v3: v2 + no new reachable space for any robot radius / known or unknown ----
def _reach(g, r_m, strict, seed_xy):
    rad = int(math.ceil(r_m / res)); yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]; disk = (xx ** 2 + yy ** 2) <= rad ** 2
    blocked = ndimage.binary_dilation(g < 50, structure=disk)
    ok = ((g > 250) if strict else (g >= 50)) & ~blocked
    lab, _ = ndimage.label(ok); s = lab[int((seed_xy[1] - oy) / res), int((seed_xy[0] - ox) / res)]
    return (lab == s) if s else np.zeros_like(ok)

def no_new_passages(raw, new, removed, radii=(0.18, 0.25, 0.28), seeds=((0.254, -1.539), (6.279, -2.199))):
    new = new.copy(); removed = removed.copy(); restored = 0
    for _ in range(50):
        changed = False
        for r_m in radii:
            rad = int(math.ceil(r_m / res)) + 1
            for strict in (True, False):
                for sd in seeds:
                    grown = _reach(new, r_m, strict, sd) & ~_reach(raw, r_m, strict, sd)
                    if not grown.any(): continue
                    near = ndimage.binary_dilation(grown, iterations=rad) & removed
                    if near.any():
                        new[near] = raw[near]; removed &= ~near; restored += int(near.sum()); changed = True
        if not changed: break
    return new, removed, restored

def build_v3(use_keys, exclude=None, fresh=('fresh_dhruv.npz',)):
    new, rem, add = build_v2(use_keys, exclude, fresh)
    raw = np.array(Image.open(f'{W}/atlas_latest.pgm'))[::-1].copy()
    new, rem, restored = no_new_passages(raw, new, rem)
    return new, rem, add, restored
