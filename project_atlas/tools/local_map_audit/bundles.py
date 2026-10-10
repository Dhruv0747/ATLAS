import sys, json; sys.path.insert(0, '.')
from common import *
from candidate import build
from PIL import Image
RECS = ['hall_to_dhruv_20261009-20261009-122252', 'amcl_roundtrip_20261009_final', 'amcl_hall_outbound_20261009_retry2', 'amcl_hall_return_20261009_retry2']
T = json.load(open(f'{W}/trajectories.json')); A = json.load(open(f'{W}/anchors.json'))
def grid_json(raw):
    cells = np.where(raw < 50, 100, np.where(raw > 250, 0, -1)).astype(int).ravel()
    return {'width': int(raw.shape[1]), 'height': int(raw.shape[0]), 'resolution': 0.05, 'origin': [-3.89, -8.46], 'cells': cells.tolist()}
old = np.array(Image.open(f'{W}/atlas_latest.pgm'))[::-1].copy()
rng = np.random.default_rng(7)
for rec in RECS:
    keys = [k for k, v in T.items() if v['name'] != rec and k != 'M@107']
    cand, rem, add, _, _ = build(keys, live=True, exclude=rec)
    np.save(f'{W}/loo_{rec[:20]}.npy', cand)
    d = load(f'{rec}.npz'); laser = laser_tf(d); meta = d['scan_meta']; o = d['odom']
    a = A[rec][0]['pose']; start = (a[0], a[1], math.radians(a[2]))
    parts = [[start[0] + rng.normal(0, .10), start[1] + rng.normal(0, .10), start[2] + rng.normal(0, math.radians(5)), 1.0] for _ in range(1000)]
    scans = []
    for i, t in enumerate(d['scan_t']):
        r = d['scan_r'][i]; r = r[~np.isnan(r)]
        op = interp_pose(o, t); j = min(np.searchsorted(o[:, 0], t), len(o) - 1)
        scans.append({'time_s': float(t), 'angle_min': float(meta[0]) + laser[2], 'angle_increment': float(meta[1]), 'range_min': 0.15, 'range_max': 12.0,
                      'ranges': [None if not np.isfinite(v) else float(v) for v in r], 'moving': bool(abs(o[j, 4]) > 0.01 or abs(o[j, 5]) > 0.02),
                      'odom': {'recorded': [float(op[0]), float(op[1]), float(op[2])]}})
    for tag, g in (('old', old), ('cand', cand)):
        json.dump({'source_bag': rec, 'map': grid_json(g), 'laser': [laser[0], laser[1]], 'particles': parts, 'scans': scans}, open(f'{W}/bundle_{tag}_{rec[:20]}.json', 'w'))
    print(rec, 'LOO candidate from', len(keys), 'drives: removed', int(rem.sum()), 'added', int(add.sum()), '| scans', len(scans))
