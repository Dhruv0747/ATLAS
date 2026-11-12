import sys, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
p = sys.argv[1]; out = sys.argv[2]
with open(p, 'rb') as f:
    h = b''
    while not h.endswith(b'end_header\n'): h += f.readline()
    n = int([l for l in h.split(b'\n') if l.startswith(b'element vertex')][0].split()[-1])
    a = np.frombuffer(f.read(), dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')], count=n)
P = np.c_[a['x'], a['y'], a['z']]; C = np.c_[a['r'], a['g'], a['b']] / 255.0
fig = plt.figure(figsize=(16, 8), dpi=90, facecolor='#0b1622')
ax1 = fig.add_subplot(1, 2, 1); ax1.set_facecolor('#0b1622')
o = np.argsort(P[:, 2]); ax1.scatter(P[o, 0], P[o, 1], c=C[o], s=1, marker='s', linewidths=0)
ax1.set_aspect('equal'); ax1.set_title('top view (real colours)', color='w'); ax1.tick_params(colors='w')
ax2 = fig.add_subplot(1, 2, 2, projection='3d'); ax2.set_facecolor('#0b1622')
ax2.scatter(P[:, 0], P[:, 1], P[:, 2], c=C, s=0.6, linewidths=0, depthshade=False)
ax2.view_init(elev=35, azim=-60); ax2.set_box_aspect((np.ptp(P[:,0]), np.ptp(P[:,1]), max(np.ptp(P[:,2]),0.5)))
ax2.set_title('3D view', color='w'); ax2.axis('off')
plt.tight_layout(); plt.savefig(out, facecolor=fig.get_facecolor())
print(n, 'points; x', P[:,0].min().round(1), P[:,0].max().round(1), 'y', P[:,1].min().round(1), P[:,1].max().round(1), 'z', P[:,2].min().round(2), P[:,2].max().round(2))
