"""Summarize application-level A/B runs (bench_dashboard_app.py driver output). All pairs reported; no selection."""
import json, statistics as S, sys

def main(path):
    d = json.load(open(path)); rows = [r for r in d['rows'] if 'error' not in r]
    errs = [r for r in d['rows'] if 'error' in r]
    by = {(r['pair'], r['variant']): r for r in rows}; pairs = sorted({p for p, v in by if (p, 'v0') in by and (p, 'cand') in by})
    print('%s  python %s  complete pairs %d  failed runs %d' % (path.split('/')[-1], d['python'], len(pairs), len(errs)))
    for key in ('proc_cpu_pct', 'control_thread_pct', 'status_thread_pct', 'exec_threads'):
        g = lambda r: r['control_thread_pct'] + r['status_thread_pct'] if key == 'exec_threads' else r[key]
        a = [g(by[(p, 'v0')]) for p in pairs]; b = [g(by[(p, 'cand')]) for p in pairs]
        sav = [100 * (1 - y / x) for x, y in zip(a, b)]; pts = [x - y for x, y in zip(a, b)]
        print('  %-18s live mean %6.2f  cand mean %6.2f | paired saving median %5.1f%% [%5.1f..%5.1f] %2d/%d better | median %.2f pts of one core'
              % (key, S.mean(a), S.mean(b), S.median(sav), min(sav), max(sav), sum(s > 0 for s in sav), len(sav), S.median(pts)))
    for v in ('v0', 'cand'):
        rs = [by[(p, v)] for p in pairs]
        lat = {k: (S.median(r['latency_ms'][k]['p50'] for r in rs), S.median(r['latency_ms'][k]['p95'] for r in rs), max(r['latency_ms'][k]['max'] for r in rs),
                   sum(r['latency_ms'][k]['n'] for r in rs)) for k in rs[0]['latency_ms']}
        tm = {k: (S.median(r['timer_period_ms'][k]['p50'] for r in rs), max(r['timer_period_ms'][k]['max'] for r in rs)) for k in rs[0]['timer_period_ms']}
        print('  %-4s msgs/s mean %.2f keys %s web_error %s' % (v, S.mean(r['msgs_per_s'] for r in rs), sorted({r['keys'] for r in rs}), sorted({str(r['web_error']) for r in rs})))
        print('       probe latency ms (median p50, median p95, worst max, n): ' + ', '.join('%s %.2f/%.2f/%.1f n=%d' % ((k,) + x) for k, x in lat.items()))
        print('       timer period ms (median p50, worst max): ' + ', '.join('%s %.1f/%.1f' % ((k,) + x) for k, x in tm.items()))
    ka = [set(by[(p, 'v0')]['counts']) for p in pairs]; kb = [set(by[(p, 'cand')]['counts']) for p in pairs]
    print('  same updating key set in every pair:', all(x == y for x, y in zip(ka, kb)))

if __name__ == '__main__':
    for p in sys.argv[1:]: main(p)
