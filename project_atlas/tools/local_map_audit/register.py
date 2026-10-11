"""Map-independent trajectory per traversal: scan-to-submap ICP chain + two LiDAR-verified anchors."""
import sys, json; sys.path.insert(0, '.')
from common import *
from scipy.spatial import cKDTree
from scipy.optimize import least_squares

def rel(a, b):  # pose b expressed in frame a
    c, s = math.cos(a[2]), math.sin(a[2]); dx, dy = b[0] - a[0], b[1] - a[1]
    return np.array([c * dx + s * dy, -s * dx + c * dy, math.atan2(math.sin(b[2] - a[2]), math.cos(b[2] - a[2]))])

def icp(src, dst_tree, dst, init, iters=30, max_d=0.4):
    x = np.array(init, float)
    for k in range(iters):
        c, s = math.cos(x[2]), math.sin(x[2])
        p = np.c_[x[0] + c * src[:, 0] - s * src[:, 1], x[1] + s * src[:, 0] + c * src[:, 1]]
        d, j = dst_tree.query(p); md = max_d if k < 10 else max_d / 2
        ok = d < md
        if ok.sum() < 30: return x, 0.0, ok.sum()
        P, Q = p[ok], dst[j[ok]]; mp, mq = P.mean(0), Q.mean(0)
        H = (P - mp).T @ (Q - mq); th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
        cr, sr = math.cos(th), math.sin(th); t = mq - np.array([cr * mp[0] - sr * mp[1], sr * mp[0] + cr * mp[1]])
        nx = np.array([cr * x[0] - sr * x[1] + t[0], sr * x[0] + cr * x[1] + t[1], x[2] + th])
        if abs(th) < 1e-5 and np.hypot(*(nx[:2] - x[:2])) < 1e-5: x = nx; break
        x = nx
    c, s = math.cos(x[2]), math.sin(x[2])
    p = np.c_[x[0] + c * src[:, 0] - s * src[:, 1], x[1] + s * src[:, 0] + c * src[:, 1]]
    d, _ = dst_tree.query(p)
    return x, float(np.mean(d < 0.08)), int((d < 0.4).sum())

def traverse(d, t_start, t_end, a_pose, b_pose, laser):
    meta = d['scan_meta']; st = d['scan_t']; idx = np.where((st >= t_start) & (st <= t_end))[0]
    guide = d['lodom'] if len(d['lodom']) > 10 else d['odom']
    keys = []; sub = []; pose = np.array(a_pose, float); last_g = interp_pose(guide, st[idx[0]])
    for n, i in enumerate(idx):
        pts = scan_points(d['scan_r'][i][~np.isnan(d['scan_r'][i])], float(meta[0]), float(meta[1]), laser)
        if len(pts) < 60: continue
        g = interp_pose(guide, st[i]); dg = rel(last_g, g)
        init = np.array(compose(tuple(pose), tuple(dg)))
        if sub:
            dst = np.vstack(sub[-6:]); x, q, nm = icp(pts, cKDTree(dst), dst, init)
            if q < 0.35:  # weak match: keep odometry guess, mark
                x = init
        else:
            x, q = np.array(a_pose, float), 1.0
        if not keys or np.hypot(*(x[:2] - keys[-1]['p'][:2])) > 0.10 or abs(math.atan2(math.sin(x[2] - keys[-1]['p'][2]), math.cos(x[2] - keys[-1]['p'][2]))) > math.radians(6) or n == len(idx) - 1:
            keys.append({'t': st[i], 'p': x.copy(), 'i': int(i), 'q': q}); sub.append(to_world(pts, x))
        pose, last_g = x, g
    # pose graph: chain edges + anchors at both ends
    P0 = np.array([k['p'] for k in keys]); N = len(P0)
    meas = [rel(P0[k], P0[k + 1]) for k in range(N - 1)]
    def resid(v):
        P = v.reshape(N, 3); r = []
        for k in range(N - 1):
            e = rel(P[k], P[k + 1]) - meas[k]; e[2] = math.atan2(math.sin(e[2]), math.cos(e[2])); r.extend(e * [10, 10, 10 / math.radians(2) * 0.05])
        for k, A in ((0, a_pose), (N - 1, b_pose)):
            e = P[k] - np.array(A); e[2] = math.atan2(math.sin(e[2]), math.cos(e[2])); r.extend(e * [200, 200, 200 / math.radians(2) * 0.05])
        return np.array(r)
    end_err = rel(np.array(b_pose), P0[-1])
    sol = least_squares(resid, P0.ravel(), method='lm' if N * 3 <= 3 * N else 'trf').x.reshape(N, 3)
    for k in range(N): keys[k]['p'] = sol[k]
    length = float(np.sum(np.hypot(*np.diff(P0[:, :2], axis=0).T)))
    return keys, end_err, length, float(np.mean([k['q'] for k in keys]))

TRAV = [('M', 14.8, 43.2, 0, 1), ('M', 107.2, 168.4, 1, 2), ('hall_to_dhruv_20261009-20261009-122252', 158.5, 210.5, 0, 1),
        ('amcl_roundtrip_20261009_final', 125.5, 167.2, 1, 2), ('amcl_roundtrip_20261009_final', 276.6, 346.3, 2, 3),
        ('amcl_hall_outbound_20261009_retry2', 112.5, 152.8, 1, 2), ('amcl_hall_return_20261009_retry2', 93.9, 151.5, 0, 1)]
if __name__ == '__main__':
    A = json.load(open(f'{W}/anchors.json')); out = {}
    for name, t0, t1, ia, ib in TRAV:
        d = load(f'{name}.npz'); base = d['scan_t'][0]; laser = laser_tf(d)
        an = A[name]; pa = an[ia]['pose']; pb = an[ib]['pose']
        a = (pa[0], pa[1], math.radians(pa[2])); b = (pb[0], pb[1], math.radians(pb[2]))
        keys, err, L, q = traverse(d, base + t0, base + t1, a, b, laser)
        o = d['odom']; sel = (o[:, 0] >= base + t0) & (o[:, 0] <= base + t1)
        vmax, wmax = np.abs(o[sel, 4]).max(), np.abs(o[sel, 5]).max()
        key = f'{name[:24]}@{t0:.0f}'
        print(f'{key:34s} keys={len(keys):3d} path={L:5.2f}m dur={t1-t0:4.0f}s mean_v={L/(t1-t0):.2f} odom_vmax={vmax:.2f} wmax={math.degrees(wmax):5.1f}deg/s icp_q={q:.2f} chain_end_err=({err[0]:+.2f},{err[1]:+.2f},{math.degrees(err[2]):+.1f}deg)')
        out[key] = {'name': name, 'keys': [{'t': k['t'], 'p': list(map(float, k['p'])), 'i': k['i'], 'q': k['q']} for k in keys], 'end_err': list(map(float, err)), 'len': L}
    json.dump(out, open(f'{W}/trajectories.json', 'w'))
