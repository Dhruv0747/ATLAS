import sys, math, time, numpy as np
sys.path.insert(0, '/tmp'); import analyze_drive_bag as A
d = A.read_bag(sys.argv[1], ['/odom', '/scan'])
f = lambda x: time.strftime('%H:%M:%S', time.localtime(x))
od = np.array([(m.header.stamp.sec + m.header.stamp.nanosec*1e-9, m.pose.pose.position.x, m.pose.pose.position.y, A.yaw_of(m.pose.pose.orientation), m.twist.twist.linear.x) for _, m in d['/odom']])
k = (od[:, 0] > 1794546190) & (od[:, 0] < 1794546210)
o = od[k]; st = np.hypot(np.diff(o[:, 1]), np.diff(o[:, 2])); dy = np.degrees(np.diff(np.unwrap(o[:, 3])))
for i in range(len(st)):
    if st[i] > 0.08 or abs(dy[i]) > 4: print(f'odom step {f(o[i+1,0])} {st[i]:.3f} m {dy[i]:+.1f} deg dt {o[i+1,0]-o[i,0]:.2f}s')
print(f'odom max step in window {st.max():.3f} m, max dt {np.diff(o[:,0]).max():.2f}s, speed max {np.abs(o[:,4]).max():.2f}')
for t, m in d['/scan']:
    if 1794546195 < t < 1794546205:
        r = np.array(m.ranges); v = np.isfinite(r) & (r > 0.2) & (r < 8)
        print(f'scan {f(t)} valid {v.sum()} / {len(r)}, median range {np.median(r[v]):.2f} m')
        break
