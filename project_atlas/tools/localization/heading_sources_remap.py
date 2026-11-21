import math, sys, numpy as np, time
from scipy.spatial import cKDTree
sys.path.insert(0, '/tmp'); import analyze_drive_bag as A
B = open('/tmp/remap3_base').read().strip()
d = A.read_bag(B, ['/scan', '/odom', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate', '/tf'])
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
scans = [(t, pts(m)) for t, m in d['/scan']][::2]
kP, kh, rel = scans[0][1], 0.0, (0.0,0.0,0.0); L=[(scans[0][0],0.0)]; fails=0
for t, P in scans[1:]:
    r = icp(P, kP, *rel)
    if r is None: fails += 1; continue
    th, tx, ty, inl = r; rel=(th,tx,ty); h = kh + math.degrees(th); L.append((t,h))
    if abs(math.degrees(th)) > 25 or inl < 0.6 or math.hypot(tx,ty) > 0.6: kP, kh, rel = P, h, (0.0,0.0,0.0)
L = np.array(L)
te = np.array([t for t,_ in d['/odom']]); ye = np.degrees(np.unwrap([A.yaw_of(m.pose.pose.orientation) for _,m in d['/odom']]))
tw = np.array([t for t,_ in d['/yahboom/odom']]); yw = np.degrees(np.unwrap([A.yaw_of(m.pose.pose.orientation) for _,m in d['/yahboom/odom']]))
ti = np.array([t for t,_ in d['/im10a/imu/bias_corrected_candidate']]); gz = np.array([m.angular_velocity.z for _,m in d['/im10a/imu/bias_corrected_candidate']])
yi = np.degrees(np.r_[0, np.cumsum(gz[1:]*np.diff(ti))])
def at(t, tt, yy): return np.interp(t, tt, yy)
t0 = L[0,0]
print(f'ICP failures {fails}/{len(scans)}; drive {L[-1,0]-t0:.0f} s')
print(' time     LiDAR    EKF   IM10A  wheel   (heading change since start, deg; + = left)')
for T in np.arange(t0, L[-1,0], 30.0):
    l = at(T, L[:,0], L[:,1]); e = at(T, te, ye)-at(t0, te, ye); i = at(T, ti, yi)-at(t0, ti, yi); w = at(T, tw, yw)-at(t0, tw, yw)
    print(f' {time.strftime("%H:%M:%S", time.localtime(T))} {l:7.1f} {e:7.1f} {i:7.1f} {w:7.1f}')
# turn-rate scale: |turn| per source over whole drive (rate integrals)
def tot(tt, yy): return np.sum(np.abs(np.diff(np.interp(np.arange(t0, L[-1,0], 0.5), tt, yy))))
print(f'total |turning|: LiDAR {tot(L[:,0],L[:,1]):.0f}  EKF {tot(te,ye):.0f}  IM10A {tot(ti,yi):.0f}  wheel {tot(tw,yw):.0f} deg')
# map->odom from /tf
mo=[]
for t, m in d['/tf']:
    for tr in m.transforms:
        if tr.header.frame_id=='map' and tr.child_frame_id=='odom':
            q=tr.transform.rotation; mo.append((t, tr.transform.translation.x, tr.transform.translation.y, math.degrees(A.yaw_of(q))))
mo=np.array(mo); np.save('/tmp/remap3_mapodom.npy', mo)
if len(mo):
    print('map->odom samples', len(mo))
    for T in (1794493221.8, 1794493312.7):
        k=np.searchsorted(mo[:,0],T); a,b=mo[max(k-15,0)],mo[min(k+15,len(mo)-1)]
        print(f' around {time.strftime("%H:%M:%S",time.localtime(T))}: map->odom ({a[1]:.2f},{a[2]:.2f},{a[3]:.1f}) -> ({b[1]:.2f},{b[2]:.2f},{b[3]:.1f})')
