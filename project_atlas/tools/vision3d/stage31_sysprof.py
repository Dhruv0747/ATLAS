#!/usr/bin/env python3
"""Passive whole-machine CPU accounting: reads /proc only. No ROS, no network, no writes."""
import os, time, json, sys
W = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
HZ = os.sysconf('SC_CLK_TCK'); NCPU = os.cpu_count()
def stat():
    p = open('/proc/stat').readline().split()[1:]
    return [int(x) for x in p]
def tasks():
    out = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit(): continue
        try:
            for tid in os.listdir('/proc/%s/task' % pid):
                try:
                    s = open('/proc/%s/task/%s/stat' % (pid, tid)).read()
                    r = s.rfind(')'); comm = s[s.find('(')+1:r]; f = s[r+2:].split()
                    out[(int(pid), int(tid))] = (comm, int(f[11]) + int(f[12]), int(f[11]), int(f[12]), int(f[16]))
                except Exception: pass
        except Exception: pass
    return out
def cmd(pid):
    try:
        c = open('/proc/%d/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode(errors='replace').strip()
        return c or '[' + open('/proc/%d/comm' % pid).read().strip() + ']'
    except Exception: return '?'
s0, t0, w0 = stat(), tasks(), time.monotonic()
time.sleep(W)
s1, t1, w1 = stat(), tasks(), time.monotonic()
el = w1 - w0
d = [b - a for a, b in zip(s0, s1)]; tot = sum(d[:8])
names = ['user','nice','system','idle','iowait','irq','softirq','steal']
brk = {n: round(100.0 * v / tot, 2) for n, v in zip(names, d[:8])}
busy = round(100.0 - brk['idle'] - brk['iowait'], 2)
proc = {}; thr = {}
for k, v in t1.items():
    a = t0.get(k); dt = v[1] - (a[1] if a else 0)
    if dt <= 0: continue
    pid, tid = k
    p = proc.setdefault(pid, [0, 0, 0, v[4], 0]); p[0] += dt; p[1] += v[2] - (a[2] if a else 0); p[2] += v[3] - (a[3] if a else 0); p[4] += 1
    thr.setdefault(pid, []).append((dt, v[0], tid))
rows = []
for pid, (dt, u, s, nice, n) in sorted(proc.items(), key=lambda x: -x[1][0]):
    one = 100.0 * dt / HZ / el
    rows.append({'pid': pid, 'one_core_pct': round(one, 2), 'machine_pct': round(one / NCPU, 3), 'user_share': round(u / max(dt, 1), 2),
                 'nice': nice, 'busy_threads': n, 'cmd': cmd(pid)[:150],
                 'top_threads': [(t[1], round(100.0 * t[0] / HZ / el, 1)) for t in sorted(thr[pid], reverse=True)[:5]]})
acc = sum(r['machine_pct'] for r in rows)
print(json.dumps({'window_s': round(el, 2), 'ncpu': NCPU, 'busy_pct': busy, 'breakdown': brk, 'accounted_machine_pct': round(acc, 2),
                  'load': open('/proc/loadavg').read().split()[:4], 'top': rows[:45]}, indent=1))
