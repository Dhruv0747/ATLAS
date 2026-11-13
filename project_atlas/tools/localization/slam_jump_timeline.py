import sys, math, time, numpy as np
sys.path.insert(0, '/tmp'); import analyze_drive_bag as A
B = sys.argv[1]
d = A.read_bag(B, ['/tf', '/scan', '/odom', '/yahboom/odom'])
mo = []
for t, m in d['/tf']:
    for tr in m.transforms:
        if tr.header.frame_id == 'map' and tr.child_frame_id == 'odom':
            s = tr.header.stamp.sec + tr.header.stamp.nanosec * 1e-9
            mo.append((t, s, tr.transform.translation.x, tr.transform.translation.y, math.degrees(A.yaw_of(tr.transform.rotation))))
mo = np.array(mo)
# collapse to distinct SLAM updates (stamp changes)
u = np.r_[True, np.diff(mo[:, 1]) != 0]; U = mo[u]
step = np.hypot(np.diff(U[:, 2]), np.diff(U[:, 3])); dyaw = np.abs(np.diff(U[:, 4]))
f = lambda x: time.strftime('%H:%M:%S', time.localtime(x))
print(f'SLAM map->odom updates: {len(U)} over {U[-1,0]-U[0,0]:.0f} s; median interval {np.median(np.diff(U[:,0])):.2f} s')
print('largest correction steps:')
for i in np.argsort(-step)[:6]:
    print(f'  {f(U[i+1,0])}  step {step[i]:.3f} m  yaw {dyaw[i]:.1f} deg  (gap since previous update {U[i+1,0]-U[i,0]:.1f} s, TF delay {U[i+1,0]-U[i+1,1]:.2f} s)')
lag = U[:, 0] - U[:, 1]
st = np.array([t for t, _ in d['/scan']]); ss = np.array([m.header.stamp.sec + m.header.stamp.nanosec*1e-9 for _, m in d['/scan']])
od = np.array([t for t, _ in d['/odom']])
print('per minute: SLAM updates | max gap | SLAM TF delay med/max | scan rate | scan delay max | odom max gap')
for t0 in np.arange(U[0, 0] - U[0, 0] % 60, U[-1, 0], 60):
    m = (U[:, 0] >= t0) & (U[:, 0] < t0 + 60); ms = (st >= t0) & (st < t0 + 60); mo2 = (od >= t0) & (od < t0 + 60)
    if m.sum() < 2: print(f'  {f(t0)}  {m.sum()} updates'); continue
    print(f'  {f(t0)}  {m.sum():4d} | {np.diff(U[m,0]).max():5.1f} s | {np.median(lag[m]):.2f}/{lag[m].max():.2f} s | '
          f'{ms.sum()/60:4.1f} Hz | {(st[ms]-ss[ms]).max():.2f} s | {np.diff(od[mo2]).max() if mo2.sum()>1 else 0:.2f} s')
# wheel motion timeline
yw = np.array([(t, m.twist.twist.linear.x, m.twist.twist.angular.z) for t, m in d['/yahboom/odom']])
for t0 in (1794546139, 1794546149, 1794546159, 1794546169, 1794546179):
    k = (yw[:, 0] > t0 - 10) & (yw[:, 0] < t0 + 10)
    print(f'  wheels around {f(t0)}: max |v| {np.abs(yw[k,1]).max():.2f} m/s, max |w| {math.degrees(np.abs(yw[k,2]).max()):.0f} deg/s')
