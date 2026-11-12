"""Track A: list every obstacle cluster in the current /astra/obstacle_scan (domain 77, read-only).
Run on the Jetson next to g4_shadow_check.py:  ROS_DOMAIN_ID=77 python3 g4_scene.py"""
import sys, math, os, numpy as np
sys.argv = ['x', 'none']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'g4_shadow_check.py')).read().split("if mode == 'floor':")[0])
scans.clear(); spin(10)
R = np.array([s.ranges for s in scans]); a = scans[0].angle_min + np.arange(R.shape[1]) * scans[0].angle_increment
occ = np.isfinite(R).mean(axis=0); med = np.nanmedian(np.where(np.isfinite(R), R, np.nan), axis=0)
cl, cur = [], None
for i in range(len(a)):
    if occ[i] > 0.5:
        if cur and abs(med[i] - med[i-1]) < 0.15: cur.append(i)
        else:
            cur = [i]; cl.append(cur)
    else: cur = None
print(f'{len(scans)} scans; clusters (right -> left):')
for c in cl:
    print(f'  {math.degrees(a[c[0]]):+5.1f}..{math.degrees(a[c[-1]]):+5.1f} deg  range {np.nanmin(med[c]):.2f}-{np.nanmax(med[c]):.2f} m  occupancy {occ[c].mean():.2f}')
rclpy.shutdown()
