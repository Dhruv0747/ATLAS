#!/usr/bin/env python3
"""Stage 28 offline analysis: why a ROS 2 node restart spikes whole-Jetson CPU, and what each mitigation can achieve.

Inputs (raw evidence stays outside git; pass the directory):
  stage32-u2p/.../trace.jsonl + log.txt          rover-status-web restart, passive 1-Hz per-process recorder
  dashboard-exitstack/.../trace.jsonl + log.txt  rover-status-web restart, same recorder
  stage28-recovery-coordination-*/0*-cpu-recorder-A.json   recovery restart, whole-machine recorder
  */0*-resources-*.json                          real 1-s baseline samples (preflights)
Outputs a JSON summary: attribution, cost model, and Monte Carlo outcomes for the options.
No ROS, no network, no Jetson access.
"""
import collections
import glob
import json
import random
import re
import statistics
import sys
from pathlib import Path

NCPU = 6
LIMIT = 75.0
DEFAULT_ENDPOINTS = 14          # rclpy/rclcpp node: 6 parameter services x2 + /parameter_events + /rosout
ENDPOINTS = {'recovery': 18 + DEFAULT_ENDPOINTS,       # 2 pubs + 16 subs (GNSS disabled), counted from source
             'status_web': 119 + DEFAULT_ENDPOINTS,    # >=8 pubs + 107 subs + 2 clients (x2), counted from source
             'base': 66 + DEFAULT_ENDPOINTS}           # ~55 pubs (incl. 12 per-wheel) + 10 subs + RC pub (stage B)


def web_restart(trace, log, restarted='atlas_status_web.py'):
    tr = float(re.search(r'restart_at=([0-9.]+)', Path(log).read_text()).group(1))
    rows = [r for r in map(json.loads, open(trace)) if 'per' in r]
    pre = [r for r in rows if tr - 15 <= r['wall'] < tr]
    base = collections.defaultdict(float)
    for r in pre:
        for k, v in r['per'].items():
            base[k.rsplit(':', 1)[0]] += v / len(pre)
    b = statistics.mean(r['busy'] for r in pre)
    own = peers = 0.0
    series = []
    for r in rows:
        d = r['wall'] - tr
        if not 0 <= d <= 35:
            continue
        series.append((round(d, 1), r['busy']))
        per = collections.defaultdict(float)
        for k, v in r['per'].items():
            per[k.rsplit(':', 1)[0]] += v
        for k in set(per) | set(base):
            x = per[k] - base.get(k, 0.0)
            if x > 0:
                if k == restarted:
                    own += x
                else:
                    peers += x
    over = [d for d, x in series if x > LIMIT]
    return {'baseline_pct': round(b, 1), 'own_core_s': round(own / 100, 1), 'peer_core_s': round(peers / 100, 1),
            'peer_share': round(peers / (own + peers), 3), 'over_limit_samples': len(over),
            'last_over_limit_s': max(over, default=None), 'excess_machine_pct_s': round(sum(max(0, x - b) for _, x in series), 1)}


def recovery_restart(recorder_json, journal_cpu_s=6.998, lifetime_s=30.54, steady_core=0.183):
    r = json.load(open(recorder_json))
    t0 = r['t_restart']
    s = [(round(a - t0, 1), x) for a, x in r['samples']]
    pre = [x for d, x in s if d < 0]
    b = statistics.mean(pre)
    excess = sum(max(0.0, x - b) for d, x in s if 0 <= d <= 12)
    total_core_s = excess * NCPU / 100
    own_core_s = journal_cpu_s - steady_core * lifetime_s          # systemd CPU accounting of the new process
    over = [d for d, x in s if x > LIMIT and d >= 0]
    return {'baseline_pct': round(b, 1), 'own_core_s': round(own_core_s, 1), 'peer_core_s': round(total_core_s - own_core_s, 1),
            'peer_share': round(1 - own_core_s / total_core_s, 3), 'over_limit_samples': len(over),
            'last_over_limit_s': max(over, default=None), 'excess_machine_pct_s': round(excess, 1), 'series': s}


def baselines(root):
    xs = []
    for f in glob.glob(str(Path(root) / '**/0*-resources-*.json'), recursive=True):
        d = json.load(open(f))
        if 'cpu_1s' in d:
            xs.append(d['cpu_1s'])
    return xs


def simulate(work_pct_s, t_init, baseline_windows, spread_s=0.0, spread_pct_s=0.0, init_pct=6.6, eff=0.85,
             runs=4000, horizon=40, seed=7):
    """Queue model calibrated on the measured restarts: own start-up adds init_pct for t_init seconds; then discovery
    work (machine-%*s) is drained at eff*(100-baseline) per second (peers run as fast as idle CPU allows). Optional
    pacing moves spread_pct_s of the work into a uniform trickle over spread_s seconds."""
    rnd = random.Random(seed)
    res = []
    for _ in range(runs):
        w = rnd.choice(baseline_windows)
        k = rnd.randrange(len(w))
        base = [w[(k + i) % len(w)] for i in range(horizon)]
        burst = work_pct_s - spread_pct_s
        trickle = spread_pct_s / spread_s if spread_s else 0.0
        xs = []
        for t in range(horizon):
            b = base[t]
            x = b + (init_pct if t < t_init else 0.0)
            if t >= t_init:
                if t - t_init < spread_s:
                    x += trickle
                cap = max(0.0, eff * (100.0 - x))
                use = min(cap, burst)
                burst -= use
                x += use
            xs.append(min(100.0, x))
        over = [t + 1 for t, x in enumerate(xs) if x > LIMIT]
        res.append((len(over), max(over, default=0)))
    n = len(res)
    lasts = sorted(r[1] for r in res)
    return {'p_strict_pass': round(sum(1 for r in res if r[0] == 0) / n, 3),
            'median_over_samples': statistics.median(r[0] for r in res),
            'last_over_p50_s': lasts[n // 2], 'last_over_p95_s': lasts[int(n * 0.95)], 'last_over_max_s': lasts[-1],
            'p_within_10s': round(sum(1 for r in res if r[1] <= 10) / n, 3)}


def main(root):
    root = Path(root)
    web1 = web_restart(*[str(next(root.glob(f'stage32-u2p/*/{n}'))) for n in ('trace.jsonl', 'log.txt')])
    web2 = web_restart(*[str(next(root.glob(f'dashboard-exitstack/*/{n}'))) for n in ('trace.jsonl', 'log.txt')])
    rec = recovery_restart(str(next(root.glob('stage28-recovery-coordination-*/0*-cpu-recorder-A.json'))))
    # linear cost model in core-seconds: a (per new participant, mostly peers) + b * endpoints
    e1, c1 = ENDPOINTS['recovery'], rec['own_core_s'] + rec['peer_core_s']
    e2 = ENDPOINTS['status_web']
    c2 = statistics.mean([web1['own_core_s'] + web1['peer_core_s'], web2['own_core_s'] + web2['peer_core_s']])
    b = (c2 - c1) / (e2 - e1)
    a = c1 - b * e1
    to_pct = 100.0 / NCPU
    win = baselines(root) or [[66.0] * 30]
    flat = [x for w in win for x in w]
    rec_work = rec['excess_machine_pct_s'] - 2 * 6.6
    per_ep_pct = b * to_pct
    opts = {
        'R0 recovery as measured (validation)': simulate(rec_work, 2, win),
        'R1 recovery without parameter services (-12 endpoints)': simulate(rec_work - 12 * per_ep_pct, 2, win),
        'R2 R1 + endpoint creation paced over 20 s': simulate(rec_work - 12 * per_ep_pct, 2, win, spread_s=20,
                                                              spread_pct_s=(ENDPOINTS['recovery'] - 12) * per_ep_pct),
        'R3 R2 with no fixed per-participant cost (lower bound)': simulate((ENDPOINTS['recovery'] - 12) * per_ep_pct, 2, win,
                                                                          spread_s=20, spread_pct_s=(ENDPOINTS['recovery'] - 12) * per_ep_pct),
        'W0 status web (validation)': simulate((a + b * e2) * to_pct, 5, win),
        'B0 base, Stage B (model, unmeasured)': simulate((a + b * ENDPOINTS['base']) * to_pct, 3, win),
    }
    out = {'restarts': {'recovery_20261027': {k: v for k, v in rec.items() if k != 'series'},
                        'status_web_20261021': web1, 'status_web_20261024': web2},
           'model_core_s': {'fixed_per_participant': round(a, 2), 'per_endpoint': round(b, 3)},
           'baseline_samples': {'n': len(flat), 'mean': round(statistics.mean(flat), 2), 'max': max(flat),
                                'p95': sorted(flat)[int(len(flat) * 0.95)]},
           'options': opts, 'recovery_series': rec['series']}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
