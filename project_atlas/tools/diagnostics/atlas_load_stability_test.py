#!/usr/bin/env python3
"""ATLAS parked load-stability test: does ATLAS stay healthy when the Jetson runs at ~80% CPU?

Purpose: evidence for the owner's decision on the Vision Lab CPU limit (75%). It does NOT change any limit, start a
camera, record data, move the rover, or restart anything. It adds a synthetic CPU load (busy loops, no I/O) that is
continuously adjusted so the WHOLE Jetson sits at --target percent, and records whether ATLAS keeps its deadlines.

Load realism: workers run at --nice (default 0 = the same priority as the Astra driver), so the test measures real
competition with ATLAS. A nice-19 load would only fill idle time and overstate the headroom.

Phases: preflight (robot parked) -> baseline (no load) -> load (target) -> recovery (no load) -> verdict.
Immediate abort (load removed within ~1 s) on ANY of: E-STOP not latched / policy not stopped / commands nonzero /
mission not READY / a required sensor older than --abort-age-s / temperature >= 70 C / RAM >= 80% / dashboard not
answering for 3 s / whole-CPU >= --abort-cpu for 3 consecutive seconds. Hard cap: --load-s <= 600.

usage (Jetson; `run` needs OWNER_APPROVED=yes):
  atlas_load_stability_test.py check
  atlas_load_stability_test.py run --target 80 [--baseline-s 60] [--load-s 300] [--recovery-s 30] [--out DIR]
"""
import argparse, json, math, multiprocessing as mp, os, signal, statistics as S, sys, time
from pathlib import Path

DASH = os.environ.get('ATLAS_DASHBOARD_URL', 'http://127.0.0.1:8088')
THERMAL = Path(os.environ.get('ATLAS_THERMAL_ROOT', '/sys/class/thermal'))
SENSORS = ('lidar', 'odom', 'imu_yaw', 'enc_m1', 'enc_m2', 'enc_m3', 'enc_m4')     # must stay fresh
WATCH = SENSORS + ('cmd_vel', 'control_policy', 'mission_status', 'amcl_quality', 'drive_pid')
PERIOD = 0.05                                                                       # worker duty-cycle period


class Abort(RuntimeError):
    pass


# ------------------------------------------------------------------ measurements
def cpu_ticks():
    v = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
    return sum(v), v[3] + v[4]


def ram_pct():
    m = {l.split(':')[0]: int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
    return 100.0 * (m['MemTotal'] - m['MemAvailable']) / m['MemTotal']


def temp_max():
    t = []
    for z in THERMAL.glob('thermal_zone*'):
        try:
            t.append(float((z / 'temp').read_text()) / 1000)
        except (OSError, ValueError):
            pass                                                                    # Orin CV zones: EAGAIN
    return max(t) if t else None


def status():
    import urllib.request
    t0 = time.monotonic()
    d = json.load(urllib.request.urlopen(DASH + '/api/status', timeout=3))
    e = json.load(urllib.request.urlopen(DASH + '/api/estop/state', timeout=3))
    return d.get('ros', {}), e, time.monotonic() - t0


def safety(ros, est):
    """Return list of hard-fault strings (empty = safe)."""
    bad = []
    if est.get('latched') is not True:
        bad.append('E-STOP not latched')
    try:
        p = ros['control_policy']['value']; p = json.loads(p) if isinstance(p, str) else p
        if not (p.get('stop_latched') is True and p.get('manual_only') is True and p.get('commission_armed') is False and p.get('source') == 'STOPPED'):
            bad.append('policy not stopped')
    except (KeyError, ValueError, TypeError):
        bad.append('policy missing')
    try:
        c = ros['cmd_vel']['value']
        if any(not math.isfinite(float(c[k])) or float(c[k]) != 0 for k in ('lin', 'ang')):
            bad.append('motor command nonzero')
    except (KeyError, ValueError, TypeError):
        bad.append('cmd_vel missing')
    if (ros.get('mission_status') or {}).get('value') != 'READY':
        bad.append('mission not READY')
    return bad


def ages(ros):
    return {k: (ros.get(k) or {}).get('age') for k in WATCH}


def rates(ros):
    return {k: (ros.get(k) or {}).get('observed_hz') for k in SENSORS}


# ------------------------------------------------------------------ load workers
def worker(duty, stop, nice):
    os.nice(nice)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while not stop.is_set():
        d = duty.value; t0 = time.perf_counter()
        if d > 0:
            end = t0 + PERIOD * d
            while time.perf_counter() < end:
                pass
        rest = PERIOD - (time.perf_counter() - t0)
        if rest > 0:
            time.sleep(rest)


class Load:
    def __init__(self, nice):
        self.n = os.cpu_count() or 1; self.duty = mp.Value('d', 0.0); self.stop = mp.Event()
        self.procs = [mp.Process(target=worker, args=(self.duty, self.stop, nice), daemon=True) for _ in range(self.n)]
        for p in self.procs:
            p.start()

    def set(self, d):
        self.duty.value = max(0.0, min(1.0, d))

    def close(self):
        self.duty.value = 0.0; self.stop.set()
        for p in self.procs:
            p.join(2)
            if p.is_alive():
                p.kill()


# ------------------------------------------------------------------ test
def preflight():
    ros, est, lat = status()
    bad = safety(ros, est)
    a = ages(ros); stale = [k for k in SENSORS if not isinstance(a.get(k), (int, float)) or a[k] > 2.0]
    if bad or stale:
        raise Abort('preflight refused: %s' % (bad + ['stale ' + s for s in stale]))
    t = temp_max(); r = ram_pct()
    if (t is not None and t >= 68) or r >= 78:
        raise Abort('preflight refused: not enough thermal/RAM margin (temp %s C, RAM %.1f%%)' % (t, r))
    return {'ages': a, 'rates': rates(ros), 'temp': t, 'ram': r, 'dash_latency_s': lat}


def run(a):
    if os.environ.get('OWNER_APPROVED') != 'yes':
        raise Abort('owner approval required (OWNER_APPROVED=yes)')
    if not 50 <= a.target <= 85 or a.load_s > 600:
        raise Abort('target must be 50..85%% and load <= 600 s')
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); trace = open(out / 'trace.jsonl', 'w')
    pre = preflight(); rows = []
    phases = [('baseline', a.baseline_s), ('load', a.load_s), ('recovery', a.recovery_s)]
    load = Load(a.nice); duty = 0.0; integ = 0.0; hot = 0; dash_fail = 0; aborted = None
    prev = cpu_ticks(); t_start = time.monotonic()
    try:
        for phase, secs in phases:
            end = time.monotonic() + secs
            while time.monotonic() < end:
                time.sleep(1.0)
                now = cpu_ticks(); busy = 100.0 * (1 - (now[1] - prev[1]) / max(1, now[0] - prev[0])); prev = now
                # controller: hold whole-machine busy at target during the load phase only
                if phase == 'load':
                    err = (a.target - busy) / 100.0; integ = max(-2.0, min(2.0, integ + err))
                    duty = max(0.0, min(1.0, duty + 0.6 * err + 0.05 * integ)); load.set(duty)
                else:
                    duty = 0.0; integ = 0.0; load.set(0.0)
                row = {'t': round(time.monotonic() - t_start, 1), 'phase': phase, 'busy': round(busy, 1), 'duty': round(duty, 3),
                       'ram': round(ram_pct(), 1), 'temp': temp_max()}
                try:
                    ros, est, lat = status(); dash_fail = 0
                    row.update(ages=ages(ros), rates=rates(ros), dash_latency_s=round(lat, 3), faults=safety(ros, est))
                except Exception as e:                                              # noqa: BLE001
                    dash_fail += 1; row.update(faults=['dashboard not answering: %r' % e])
                rows.append(row); trace.write(json.dumps(row) + '\n'); trace.flush()
                print(json.dumps({k: row[k] for k in ('t', 'phase', 'busy', 'duty', 'ram', 'temp')}), flush=True)
                hot = hot + 1 if busy >= a.abort_cpu else 0
                stale = [k for k in SENSORS if isinstance(row.get('ages'), dict) and (not isinstance(row['ages'].get(k), (int, float)) or row['ages'][k] > a.abort_age_s)]
                reasons = [f for f in row.get('faults', []) if not f.startswith('dashboard not answering')]
                if dash_fail >= 3: reasons.append('dashboard not answering for 3 s')
                if stale: reasons.append('stale sensors %s' % stale)
                if row['temp'] is not None and row['temp'] >= 70: reasons.append('temperature %.1f C' % row['temp'])
                if row['ram'] >= 80: reasons.append('RAM %.1f%%' % row['ram'])
                if hot >= 3: reasons.append('CPU >= %.0f%% for 3 s' % a.abort_cpu)
                if reasons:
                    aborted = {'t': row['t'], 'phase': phase, 'reasons': reasons}
                    raise Abort('ABORTED: %s' % reasons)
    except Abort as e:
        print(json.dumps({'event': 'abort', 'detail': str(e)}), flush=True)
    finally:
        load.close(); trace.close()
    verdict = summarize(rows, pre, a, aborted)
    (out / 'verdict.json').write_text(json.dumps(verdict, indent=1, default=str))
    print(json.dumps({'event': 'verdict', **verdict}, default=str), flush=True)
    return verdict


def summarize(rows, pre, a, aborted):
    def ph(p): return [r for r in rows if r['phase'] == p]
    def worst_age(rs, k):
        v = [r['ages'][k] for r in rs if isinstance(r.get('ages'), dict) and isinstance(r['ages'].get(k), (int, float))]
        return max(v) if v else None
    def med_rate(rs, k):
        v = [r['rates'][k] for r in rs if isinstance(r.get('rates'), dict) and isinstance(r['rates'].get(k), (int, float))]
        return S.median(v) if v else None
    base, load = ph('baseline'), ph('load')
    steady = load[min(len(load), 20):]                                              # controller settling excluded
    out = {'target': a.target, 'nice': a.nice, 'aborted': aborted, 'preflight': pre,
           'busy': {p: (round(S.median([r['busy'] for r in ph(p)]), 1) if ph(p) else None) for p in ('baseline', 'load', 'recovery')},
           'steady_load_busy_median': round(S.median([r['busy'] for r in steady]), 1) if steady else None,
           'sensors': {k: {'baseline_worst_age_s': worst_age(base, k), 'load_worst_age_s': worst_age(load, k),
                           'baseline_hz': med_rate(base, k), 'load_hz': med_rate(load, k)} for k in SENSORS},
           'dash_latency_p95_s': {p: (sorted(r['dash_latency_s'] for r in ph(p) if 'dash_latency_s' in r)[int(.95 * (len([1 for r in ph(p) if 'dash_latency_s' in r]) - 1))]
                                      if any('dash_latency_s' in r for r in ph(p)) else None) for p in ('baseline', 'load')},
           'max_temp_c': max([r['temp'] for r in rows if r['temp'] is not None] or [None]) if rows else None,
           'max_ram_pct': max([r['ram'] for r in rows] or [None]) if rows else None}
    checks = {
        'not_aborted': aborted is None,
        'reached_target': out['steady_load_busy_median'] is not None and abs(out['steady_load_busy_median'] - a.target) <= 3,
        'sensors_fresh_under_load': all(v['load_worst_age_s'] is not None and v['load_worst_age_s'] <= 1.0 for v in out['sensors'].values()),
        'sensor_rates_kept': all(v['baseline_hz'] in (None, 0) or (v['load_hz'] is not None and v['load_hz'] >= 0.9 * v['baseline_hz']) for v in out['sensors'].values()),
        'dashboard_responsive': out['dash_latency_p95_s']['load'] is not None and out['dash_latency_p95_s']['load'] <= 1.0,
        'thermal_ram_ok': (out['max_temp_c'] is None or out['max_temp_c'] < 70) and (out['max_ram_pct'] or 0) < 80}
    out['checks'] = checks; out['verdict'] = 'PASS' if all(checks.values()) else 'FAIL'
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('check', 'run'))
    ap.add_argument('--target', type=float, default=80.0); ap.add_argument('--nice', type=int, default=0)
    ap.add_argument('--baseline-s', type=int, default=60); ap.add_argument('--load-s', type=int, default=300)
    ap.add_argument('--recovery-s', type=int, default=30); ap.add_argument('--abort-age-s', type=float, default=1.5)
    ap.add_argument('--abort-cpu', type=float, default=92.0)
    ap.add_argument('--out', default=os.path.expanduser('~/project-atlas-migration/load-stability-%s' % time.strftime('%Y%m%d_%H%M%S')))
    a = ap.parse_args()
    try:
        if a.cmd == 'check':
            print(json.dumps({'event': 'check', 'ok': True, **preflight()}, default=str))
        else:
            v = run(a); sys.exit(0 if v['verdict'] == 'PASS' else 1)
    except Abort as e:
        print(json.dumps({'event': 'REFUSE', 'reason': str(e)})); sys.exit(2)


if __name__ == '__main__':
    main()
