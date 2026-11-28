import sys, json, subprocess, os; sys.path.insert(0, os.path.dirname(__file__))
from common import *
T = json.load(open(f'{W}/trajectories.json')); A = json.load(open(f'{W}/anchors.json'))
RECS = ['hall_to_dhruv_20261009-20261009-122252', 'amcl_roundtrip_20261009_final', 'amcl_hall_outbound_20261009_retry2', 'amcl_hall_return_20261009_retry2']
def truth_fn(rec):
    segs = []
    for w in A[rec]:
        p = w['pose']; segs.append((w['t0'], w['t1'], [(w['t0'], p[0], p[1], math.radians(p[2])), (w['t1'], p[0], p[1], math.radians(p[2]))]))
    for k, v in T.items():
        if v['name'] == rec: segs.append((v['keys'][0]['t'], v['keys'][-1]['t'], [(q['t'], *q['p']) for q in v['keys']]))
    def f(t):
        for a, b, pts in segs:
            if a - 0.2 <= t <= b + 0.2:
                arr = np.array(pts); return interp_pose(arr, t)
        return None
    return f
rows = []
for rec in RECS:
    tf = truth_fn(rec)
    for tag in ('old', 'cand'):
        stats = []
        for seed in range(1, 21):
            out = f'{W}/rp_{tag}_{rec[:20]}_{seed}.json'
            subprocess.run(['./build/motion_replay', f'{W}/bundle_{tag}_{rec[:20]}.json', out, '--forced-period', '1.0', '--seed', str(seed)], check=True, capture_output=True)
            tr = json.load(open(out))['trajectory']; errs = []
            for p in tr:
                g = tf(p['time_s'])
                if g is None: continue
                errs.append((math.hypot(p['x'] - g[0], p['y'] - g[1]), abs(math.degrees(math.atan2(math.sin(p['yaw'] - g[2]), math.cos(p['yaw'] - g[2]))))))
            e = np.array(errs); lost = (e[:, 0] > 0.5) | (e[:, 1] > 20)
            stats.append((e[-1, 0], e[-1, 1], np.median(e[:, 0]), e[:, 0].max(), lost.mean(), len(e)))
            os.remove(out)
        s = np.array(stats)
        ok_end = np.mean((s[:, 0] <= 0.3) & (s[:, 1] <= 10))
        rows.append((rec[:22], tag, ok_end, np.median(s[:, 0]), np.median(s[:, 1]), np.median(s[:, 2]), np.median(s[:, 3]), np.mean(s[:, 4]), int(s[0, 5])))
        print(f'{rec[:22]:24s} {tag:4s} end-correct(<=0.3m,10deg) {ok_end*100:5.1f}%  end err med {np.median(s[:,0]):.2f} m/{np.median(s[:,1]):4.1f} deg  path err med {np.median(s[:,2]):.2f} m  max err med {np.median(s[:,3]):.2f} m  time-LOST {np.mean(s[:,4])*100:5.1f}%  (n={int(s[0,5])} scored outputs/run, 20 seeds)', flush=True)
json.dump(rows, open(f'{W}/replay_scores.json', 'w'))
