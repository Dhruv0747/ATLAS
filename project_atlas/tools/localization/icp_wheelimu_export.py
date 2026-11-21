import math, sys, numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, '/tmp'); import analyze_drive_bag as A
B = open('/tmp/remap3_base').read().strip(); D = open('/tmp/lidar_replay_last').read().strip()
d = A.read_bag(B, ['/scan', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate'])
def pts(s):
    r = np.array(s.ranges, float); a = s.angle_min + np.arange(len(r)) * s.angle_increment
    ok = np.isfinite(r) & (r > 0.15) & (r < 6.0); return np.c_[r[ok]*np.cos(a[ok]), r[ok]*np.sin(a[ok])]
def icp(P, Q, th=0.0, tx=0.0, ty=0.0, it=40):
    tree = cKDTree(Q)
    for k in range(it):
        c, s = math.cos(th), math.sin(th); Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt); m = dist < (0.5 if k < 10 else 0.15)
        if m.sum() < 40: return None
        Aa, Bb = P[m], Q[idx[m]]; ca, cb = Aa.mean(0), Bb.mean(0); H = (Aa-ca).T @ (Bb-cb)
        th = math.atan2(H[0,1]-H[1,0], H[0,0]+H[1,1]); c, s = math.cos(th), math.sin(th)
        tx, ty = cb - ca @ np.array([[c, s], [-s, c]])
    return th, tx, ty, float(m.mean())
def comp(a, r):
    c, s = math.cos(a[2]), math.sin(a[2]); return np.array([a[0] + c*r[1] - s*r[2], a[1] + s*r[1] + c*r[2], a[2] + r[0]])
scans = [(t, pts(m)) for t, m in d['/scan']][::2]
K = np.zeros(3); kP = scans[0][1]; rel = (0.0, 0.0, 0.0)
with open(D + '/icp.csv', 'w') as f:
    f.write(f'{scans[0][0]:.3f},0,0,0\n')
    for t, P in scans[1:]:
        r = icp(P, kP, *rel)
        if r is None: continue
        th, tx, ty, inl = r; rel = (th, tx, ty); g = comp(K, (th, tx, ty))
        f.write(f'{t:.3f},{g[2]:.5f},{g[0]:.3f},{g[1]:.3f}\n')
        if abs(math.degrees(th)) > 25 or inl < 0.6 or math.hypot(tx, ty) > 0.6: K, kP, rel = g, P, (0.0, 0.0, 0.0)
tw = np.array([t for t,_ in d['/yahboom/odom']]); vw = np.array([m.twist.twist.linear.x for _,m in d['/yahboom/odom']])
ti = np.array([t for t,_ in d['/im10a/imu/bias_corrected_candidate']]); gz = np.array([m.angular_velocity.z for _,m in d['/im10a/imu/bias_corrected_candidate']])
yi = np.r_[0, np.cumsum(gz[1:]*np.diff(ti))]
tt = np.arange(tw[0], tw[-1], 0.05); v = np.interp(tt, tw, vw); h = np.interp(tt, ti, yi)
X = np.r_[0, np.cumsum(v[1:]*np.cos(h[1:])*0.05)]; Y = np.r_[0, np.cumsum(v[1:]*np.sin(h[1:])*0.05)]
np.savetxt(D + '/wheelimu.csv', np.c_[tt, h, X, Y], delimiter=',', fmt='%.4f')
print('written')
