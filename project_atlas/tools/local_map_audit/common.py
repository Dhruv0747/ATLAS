import math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../scripts'))
import atlas_localization_verify_core as core
W = os.environ.get('ATLAS_MAP_AUDIT_DIR', os.getcwd())
POL = core.VerifyPolicy()
LASER = (0.0, 0.0, 0.0)
PLACES = {'Dhruv Room': (0.254, -1.539, math.radians(76.6)), 'Hall': (6.279, -2.199, math.radians(-96.1))}

def load(name):
    return np.load(f'{W}/{name}', allow_pickle=True)

def laser_tf(d):
    st = {(r[0], r[1]): r[2:] for r in d['static']}
    a = st.get(('base_link', 'base_footprint'), (0, 0, 0)); b = st.get(('base_footprint', 'laser_frame'), (0, 0, 0))
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2])

def interp_pose(arr, t):
    """arr rows (t,x,y,yaw,...) -> pose at t (yaw unwrapped)."""
    tt = arr[:, 0]; i = np.clip(np.searchsorted(tt, t), 1, len(tt) - 1)
    a, b = arr[i - 1], arr[i]; f = 0 if b[0] == a[0] else np.clip((t - a[0]) / (b[0] - a[0]), 0, 1)
    dy = math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3]))
    return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * dy)

def compose(p, q):
    c, s = math.cos(p[2]), math.sin(p[2])
    return (p[0] + c * q[0] - s * q[1], p[1] + s * q[0] + c * q[1], p[2] + q[2])

def scan_points(ranges, amin, inc, laser, rmax=8.0):
    a = amin + inc * np.arange(len(ranges)); r = np.asarray(ranges, float)
    ok = np.isfinite(r) & (r > 0.12) & (r < rmax)
    x = r[ok] * np.cos(a[ok]); y = r[ok] * np.sin(a[ok])
    c, s = math.cos(laser[2]), math.sin(laser[2])
    return np.c_[laser[0] + c * x - s * y, laser[1] + s * x + c * y]

def to_world(pts, pose):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return np.c_[pose[0] + c * pts[:, 0] - s * pts[:, 1], pose[1] + s * pts[:, 0] + c * pts[:, 1]]
