import sys, math, time, numpy as np
sys.path.insert(0, '/tmp'); sys.path.insert(0, '/home/jetson/project_atlas/scripts')
import analyze_drive_bag as A
from atlas_icp_odometry_core import IcpOdometry, scan_to_points
d = A.read_bag(sys.argv[1], ['/scan', '/im10a/imu/bias_corrected_candidate'])
f = lambda x: time.strftime('%H:%M:%S', time.localtime(x))
for T in [float(x) for x in sys.argv[2:]]:
    g = np.array([m.angular_velocity.z for t, m in d['/im10a/imu/bias_corrected_candidate'] if T - 4 <= t <= T + 1])
    o = IcpOdometry(); P = []; val = []
    for t, m in d['/scan']:
        if T - 6 <= t <= T + 1:
            r = np.array(m.ranges); v = np.isfinite(r) & (r > 0.2) & (r < 8); val.append((v.sum(), np.median(r[v]) if v.any() else 0))
            p, ok = o.update(scan_to_points(m.ranges, m.angle_min, m.angle_increment, -0.05, 0.0, math.pi, o.cfg)); P.append((t, *p))
    P = np.array(P); sp = np.hypot(np.diff(P[:, 1]), np.diff(P[:, 2])) / np.diff(P[:, 0])
    va = np.array(val)
    print(f'{f(T)}: speed max {sp.max():.2f} m/s median {np.median(sp):.2f} | turn max {math.degrees(np.abs(g).max()):.0f} deg/s | valid beams min {va[:,0].min():.0f}/360, median range {np.median(va[:,1]):.2f} m | ICP rejected {o.rejected}')
