#!/usr/bin/env python3
"""Offline analysis of a mapping-session recording (read-only): where/why SLAM corrected odometry (map->odom jumps),
odometry-vs-SLAM distance scale and heading drift, and EKF vs wheel forward speed. Usage: remap_jump_analysis.py BAG"""
import math, sys, time
import numpy as np
sys.path.insert(0, '/tmp')
import analyze_drive_bag as A

bag = sys.argv[1]
d = A.read_bag(bag, ['/tf', '/odom', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate', '/cmd_vel'])
mo, ob = [], []      # map->odom and odom->base_link samples: (t, x, y, yaw)
for t, m in d['/tf']:
    for tr in m.transforms:
        s = tr.header.stamp.sec + tr.header.stamp.nanosec * 1e-9
        q = tr.transform.rotation; p = tr.transform.translation
        row = (s, p.x, p.y, A.yaw_of(q))
        if tr.header.frame_id == 'map' and tr.child_frame_id == 'odom': mo.append(row)
        elif tr.header.frame_id == 'odom' and tr.child_frame_id == 'base_link': ob.append(row)
mo = np.array(sorted(mo)); ob = np.array(sorted(ob))
t0 = ob[0, 0]
clk = lambda s: time.strftime('%H:%M:%S', time.localtime(s))
print(f'map->odom samples {len(mo)} ({clk(mo[0,0])}..{clk(mo[-1,0])}), odom->base_link samples {len(ob)}')
# 1) map->odom corrections: changes over 1 s steps
g = np.arange(mo[0, 0], mo[-1, 0], 1.0)
mx, my = np.interp(g, mo[:, 0], mo[:, 1]), np.interp(g, mo[:, 0], mo[:, 2]); myaw = np.interp(g, mo[:, 0], np.unwrap(mo[:, 3]))
step = np.hypot(np.diff(mx), np.diff(my)); ystep = np.degrees(np.abs(np.diff(myaw)))
print('largest SLAM corrections (per 1 s):')
for k in np.argsort(step)[::-1][:6]:
    print(f'   {clk(g[k+1])}  {step[k]*100:5.1f} cm  {ystep[k]:5.1f} deg')
print(f'total SLAM correction over session: {np.hypot(mx[-1]-mx[0], my[-1]-my[0]):.2f} m, {math.degrees(myaw[-1]-myaw[0]):+.1f} deg')
# 2) robot trajectory in odom vs in map (map = SLAM-corrected best estimate)
G = np.arange(max(ob[0, 0], mo[0, 0]), min(ob[-1, 0], mo[-1, 0]), 0.5)
ox, oy = np.interp(G, ob[:, 0], ob[:, 1]), np.interp(G, ob[:, 0], ob[:, 2]); oyaw = np.interp(G, ob[:, 0], np.unwrap(ob[:, 3]))
Mx, My = np.interp(G, mo[:, 0], mo[:, 1]), np.interp(G, mo[:, 0], mo[:, 2]); Myaw = np.interp(G, mo[:, 0], np.unwrap(mo[:, 3]))
wx = Mx + np.cos(Myaw) * ox - np.sin(Myaw) * oy; wy = My + np.sin(Myaw) * ox + np.cos(Myaw) * oy; wyaw = Myaw + oyaw
print(f'path length: odom {np.hypot(np.diff(ox), np.diff(oy)).sum():.2f} m | SLAM map {np.hypot(np.diff(wx), np.diff(wy)).sum():.2f} m')
print(f'total turning: odom {math.degrees(np.abs(np.diff(oyaw)).sum()):.0f} deg | SLAM map {math.degrees(np.abs(np.diff(wyaw)).sum()):.0f} deg')
print('per 60 s window (odom vs SLAM): distance, net heading change')
for a in np.arange(G[0], G[-1], 60.0):
    m = (G >= a) & (G < a + 60)
    if m.sum() < 10: continue
    do = np.hypot(np.diff(ox[m]), np.diff(oy[m])).sum(); dm = np.hypot(np.diff(wx[m]), np.diff(wy[m])).sum()
    ho = math.degrees(oyaw[m][-1] - oyaw[m][0]); hm = math.degrees(wyaw[m][-1] - wyaw[m][0])
    if do > 0.1 or abs(ho) > 5:
        print(f'   {clk(a)}  odom {do:5.2f} m vs SLAM {dm:5.2f} m (ratio {do/max(dm,1e-6):.2f}) | heading odom {ho:+7.1f} vs SLAM {hm:+7.1f} deg')
# 3) EKF vs wheel forward speed
def ser(topic, f):
    v = d[topic]; return np.array([x for x, _ in v]), np.array([f(m) for _, m in v])
te, ve = ser('/odom', lambda m: m.twist.twist.linear.x); tw, vw = ser('/yahboom/odom', lambda m: m.twist.twist.linear.x)
H = np.arange(max(te[0], tw[0]), min(te[-1], tw[-1]), 0.1); E, W = np.interp(H, te, ve), np.interp(H, tw, vw)
mv = np.abs(W) > 0.03
print(f'forward speed while moving ({mv.sum()} samples): EKF/wheel ratio median {np.median(E[mv]/W[mv]):.2f}, corr {np.corrcoef(E[mv], W[mv])[0,1]:+.2f}')
print(f'integrated distance: wheel |vx| {np.sum(np.abs(W))*0.1:.2f} m, signed {np.sum(W)*0.1:+.2f} m | EKF |vx| {np.sum(np.abs(E))*0.1:.2f} m, signed {np.sum(E)*0.1:+.2f} m')
rev = (W < -0.03).sum() / max(1, mv.sum()); print(f'reversing share of moving time: {rev*100:.0f} %')
